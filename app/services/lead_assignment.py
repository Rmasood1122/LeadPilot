"""Lead assignment inside a workspace (Feature 1 of the team-accounts brief).

WHAT "ASSIGNED" MEANS HERE
`crm_lead_meta.owner_user_id` -- the column the M9 grid already shows as
"Owner". DATA ownership does not move: a lead still belongs to the workspace
owner through lead -> strategy -> product -> user_id, and every tenant-scoped
query keeps scoping by that chain. Assignment answers a different question,
"which person on the team is working this lead", and so lives in the CRM's own
meta table rather than on `leads` (migration 0019's rule: the CRM adds no
columns to the row the pipeline, the sequence engine and the SDK all load).

WHY THIS NEEDED MORE THAN LIFTING THE OLD CHECK
Inside a workspace, get_current_user returns the workspace OWNER as the
principal (app/services/auth.py::_workspace_principal) so that every
user_id-scoped route keeps working. The old rule -- "owner_user_id must be the
authenticated user" -- therefore recorded the workspace owner whenever an SDR
clicked "claim". The person who acted is `request.state.actor`; the role they
act with is `request.state.workspace_role`. Both are read here, never inferred
from the principal.

THE RULES
  * An assignee must be a member of the workspace that owns the lead (or the
    owner themself). Anyone else is a 422 that does not say whether the id
    exists.
  * owner / manager  assign to any member, or clear.
  * sdr              claim an UNASSIGNED lead for themself, or release a lead
                     assigned to themself. Taking a lead off a colleague is a
                     manager decision.
  * viewer           cannot reach here: rbac.enforce refuses every write.

ROUND-ROBIN IS LEAST-LOADED, AND STATELESS
A stored rotation cursor is one more row that can disagree with reality (a
member removed, a lead reassigned by hand) and has to be locked under
concurrency. Instead each unassigned lead goes to the eligible member holding
the fewest OPEN assigned leads, ties broken by user id. Over a batch this
rotates exactly like round-robin from an even start, and from an uneven start
it levels the team -- which is what a manager distributing leads wants.

IDEMPOTENT BY CONSTRUCTION
Every round-robin write is `UPDATE ... WHERE owner_user_id IS NULL`. A retried
request, or two managers pressing the button at once, cannot move a lead that
somebody already holds; the loser reports it in `skipped`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import CrmLeadMeta, Lead, User, Workspace, WorkspaceMember
from app.services import crm_service, rbac

# Roles round-robin distributes to when the caller does not say.
DEFAULT_ROUND_ROBIN_ROLES = ("sdr",)


@dataclass(frozen=True)
class Assigner:
    """Who is assigning, with what role, on whose data."""

    principal: User          # the data owner (workspace owner)
    actor: User              # the person who signed in
    role: str                # their role in the principal's workspace


def assigner_for(request: Request, principal: User) -> Assigner:
    actor = getattr(request.state, "actor", None) or principal
    role = getattr(request.state, "workspace_role", None) or "owner"
    return Assigner(principal=principal, actor=actor, role=role)


def _workspace_of(db: Session, principal: User) -> Workspace | None:
    """The principal's own workspace, WITHOUT creating it.

    workspaces.personal_workspace() creates and commits on first use, which is
    right for GET /workspaces and wrong here: this runs mid-request, and a
    commit would flush a half-applied PATCH (status already changed, owner
    not yet validated) before the request has decided to succeed.
    """
    return db.execute(
        select(Workspace).where(Workspace.owner_user_id == principal.id)
    ).scalar_one_or_none()


def member_roles(db: Session, principal: User) -> dict[uuid.UUID, str]:
    """Every user who may hold one of the principal's leads, with their role.

    The principal is always included: a solo account that has never opened
    Team has no workspace row, and must still be able to own its own leads.
    """
    roles: dict[uuid.UUID, str] = {principal.id: "owner"}
    ws = _workspace_of(db, principal)
    if ws is not None:
        for user_id, role in db.execute(
            select(WorkspaceMember.user_id, WorkspaceMember.role)
            .where(WorkspaceMember.workspace_id == ws.id)
        ).all():
            roles[user_id] = role
    return roles


def require_assignable(db: Session, principal: User, assignee_id: uuid.UUID | None) -> None:
    """422 unless `assignee_id` is None or a member of the principal's workspace."""
    if assignee_id is None:
        return
    if assignee_id not in member_roles(db, principal):
        raise HTTPException(
            status_code=422,
            detail="owner_user_id must be a member of this workspace",
        )


def refusal(who: Assigner, current: uuid.UUID | None, new: uuid.UUID | None) -> str | None:
    """Why `who` may not change this lead's assignee from `current` to `new`,
    or None when they may. Pure, so the single and bulk paths share it."""
    if current == new:
        return None
    if rbac.at_least(who.role, "manager"):
        return None
    if who.role == "sdr":
        claiming = new == who.actor.id and current is None
        releasing = new is None and current == who.actor.id
        if claiming or releasing:
            return None
        return ("an SDR can claim an unassigned lead or release their own; "
                "reassigning needs a manager")
    return "your role cannot assign leads"


def open_load(db: Session, principal: User, user_ids) -> dict[uuid.UUID, int]:
    """Open (non-terminal) leads currently assigned to each of `user_ids`,
    counted over the principal's leads only -- in SQL, one query."""
    load = {uid: 0 for uid in user_ids}
    if not load:
        return load
    rows = db.execute(
        select(CrmLeadMeta.owner_user_id, func.count(CrmLeadMeta.id))
        .join(Lead, Lead.id == CrmLeadMeta.lead_id)
        .where(
            CrmLeadMeta.owner_user_id.in_(list(load)),
            Lead.id.in_(crm_service.owned_leads_subquery(principal)),
            Lead.status.notin_(list(crm_service.TERMINAL_STAGES)),
        )
        .group_by(CrmLeadMeta.owner_user_id)
    ).all()
    for user_id, count in rows:
        load[user_id] = int(count)
    return load


def claim_if_unassigned(db: Session, lead: Lead, assignee_id: uuid.UUID) -> bool:
    """Assign `lead` to `assignee_id` only if nobody holds it. True if written.

    The WHERE clause is the concurrency guard: two writers racing on the same
    lead both issue this UPDATE, and exactly one matches a NULL owner.
    """
    crm_service.get_or_create_meta(db, lead)
    result = db.execute(
        update(CrmLeadMeta)
        .where(CrmLeadMeta.lead_id == lead.id, CrmLeadMeta.owner_user_id.is_(None))
        .values(owner_user_id=assignee_id)
        .execution_options(synchronize_session="fetch")
    )
    return result.rowcount == 1


def round_robin(db: Session, principal: User, leads: list[Lead],
                roles=DEFAULT_ROUND_ROBIN_ROLES) -> tuple[list[tuple[Lead, uuid.UUID]], list[dict]]:
    """Distribute the unassigned `leads` across members holding `roles`.

    Returns (assigned [(lead, user_id)], skipped [{lead_id, reason}]). Does NOT
    commit and does NOT log activity -- the router owns both, so an activity
    row can never outlive the change it describes.
    """
    wanted = set(roles)
    eligible = sorted(
        (uid for uid, role in member_roles(db, principal).items() if role in wanted),
        key=str,
    )
    if not eligible:
        raise HTTPException(
            status_code=422,
            detail=f"no workspace members with role(s) {sorted(wanted)} to assign to",
        )

    load = open_load(db, principal, eligible)
    assigned: list[tuple[Lead, uuid.UUID]] = []
    skipped: list[dict] = []
    # Stable order, so the same batch distributes the same way on a retry.
    for lead in sorted(leads, key=lambda row: str(row.id)):
        assignee = min(eligible, key=lambda uid: (load[uid], str(uid)))
        if not claim_if_unassigned(db, lead, assignee):
            skipped.append({"lead_id": str(lead.id), "reason": "already assigned"})
            continue
        assigned.append((lead, assignee))
        if lead.status not in crm_service.TERMINAL_STAGES:
            load[assignee] += 1
    return assigned, skipped
