"""WhatsApp template management — Milestone 4, Chunk 2.

Lifecycle (mirrors Meta's):   draft -> submitted -> approved | rejected
                              rejected -> (edit) -> draft -> submitted ...
Approved templates are IMMUTABLE here: editing one creates a NEW row with
version+1 under the same (name, language), linked via supersedes_id.
Only status=approved templates are ever sendable — the adapter's send()
guard checks this table, so a template name passed in manually cannot
bypass approval.

The Meta Business Management API calls live on the adapter
(app/integrations/whatsapp.py) so they inherit the shared plumbing;
this module owns validation + state transitions and is directly testable
without HTTP (Chunk 4).

AI-assisted drafting: Claude turns the strategy's Phase 6 (messaging) and
Phase 2 (persona) outputs into 2-3 COMPLIANT draft candidates — clear
sender identity, honest value proposition, an opt-out instruction in the
body — and they are saved as drafts ONLY. Nothing is ever auto-submitted;
the user reviews and submits explicitly.
"""

import json
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    PipelineKind,
    ResearchStep,
    Strategy,
    WhatsAppTemplate,
    WhatsAppTemplateCategory,
    WhatsAppTemplateStatus,
)
from app.services.anthropic_client import get_client

logger = logging.getLogger(__name__)


class TemplateError(ValueError):
    """Invalid template content or an illegal lifecycle transition."""


_PLACEHOLDER = re.compile(r"\{\{(\d+)\}\}")
# Meta template names: lowercase letters, digits, underscores.
# TODO: verify against current WhatsApp docs (exact charset + max length)
_NAME_RE = re.compile(r"^[a-z0-9_]{1,200}$")


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validate_body(body: str) -> dict[int, str]:
    """Validate the body text; return {placeholder_no: ''} slots found.

    Rules:
      - non-empty, within the configured length limit
        (# TODO: verify limits against current WhatsApp docs — 1024 chars
        for the body component is the configured default)
      - variable placeholders must be exactly {{1}}..{{k}} — sequential,
        starting at 1, no gaps, no duplicates ({{2}} without {{1}} is a
        Meta rejection anyway; we fail fast locally)
    """
    text = (body or "").strip()
    if not text:
        raise TemplateError("template body must not be empty")
    if len(text) > settings.whatsapp_template_body_max_chars:
        raise TemplateError(
            f"template body exceeds {settings.whatsapp_template_body_max_chars}"
            " characters"
        )
    numbers = [int(n) for n in _PLACEHOLDER.findall(text)]
    unique = sorted(set(numbers))
    if len(unique) != len(numbers):
        raise TemplateError("duplicate variable placeholders (each {{n}} once)")
    if unique != list(range(1, len(unique) + 1)):
        raise TemplateError(
            "variable placeholders must be sequential starting at {{1}} "
            f"— found {['{{%d}}' % n for n in unique] or 'none'}"
        )
    return {n: "" for n in unique}


def validate_name(name: str) -> str:
    n = (name or "").strip().lower()
    if not _NAME_RE.match(n):
        raise TemplateError(
            "template name must be lowercase letters, digits and "
            "underscores only (e.g. 'intro_offer_v1')"
        )
    return n


def _validate_variable_descriptions(
    slots: dict[int, str], descriptions: dict | None
) -> dict[str, str]:
    """Descriptions tell Chunk 3's sequence engine what to fill into each
    {{n}}. Every placeholder needs one; extras are rejected."""
    provided = {str(k): str(v) for k, v in (descriptions or {}).items()}
    expected = {str(n) for n in slots}
    missing = expected - set(provided)
    extra = set(provided) - expected
    if missing:
        raise TemplateError(
            f"missing variable descriptions for placeholder(s): {sorted(missing)}"
        )
    if extra:
        raise TemplateError(
            f"variable descriptions given for nonexistent placeholder(s): {sorted(extra)}"
        )
    return provided


# --------------------------------------------------------------------------
# CRUD / lifecycle
# --------------------------------------------------------------------------

_EDITABLE = (WhatsAppTemplateStatus.DRAFT, WhatsAppTemplateStatus.REJECTED)


def _latest_version(session: Session, name: str, language: str) -> int:
    versions = session.execute(
        select(WhatsAppTemplate.version)
        .where(WhatsAppTemplate.name == name,
               WhatsAppTemplate.language == language)
    ).scalars().all()
    return max(versions) if versions else 0


def create_draft(
    session: Session,
    *,
    name: str,
    language: str,
    category: WhatsAppTemplateCategory,
    body: str,
    variable_descriptions: dict | None = None,
    supersedes: WhatsAppTemplate | None = None,
) -> WhatsAppTemplate:
    name = validate_name(name)
    language = (language or "").strip()
    if not language:
        raise TemplateError("language is required (e.g. 'en_US')")
    slots = validate_body(body)
    descriptions = _validate_variable_descriptions(slots, variable_descriptions)

    row = WhatsAppTemplate(
        name=name,
        language=language,
        version=_latest_version(session, name, language) + 1,
        category=category,
        status=WhatsAppTemplateStatus.DRAFT,
        body=body.strip(),
        variable_descriptions_json=descriptions,
        supersedes_id=supersedes.id if supersedes is not None else None,
    )
    session.add(row)
    session.commit()
    return row


def update_template(
    session: Session,
    template: WhatsAppTemplate,
    *,
    body: str | None = None,
    category: WhatsAppTemplateCategory | None = None,
    variable_descriptions: dict | None = None,
) -> WhatsAppTemplate:
    """Edit in place ONLY while draft or rejected. Editing an approved
    template creates a NEW draft version instead (immutability); editing
    a submitted one is refused — sync or wait for Meta's verdict first."""
    if template.status is WhatsAppTemplateStatus.SUBMITTED:
        raise TemplateError(
            "template is submitted and awaiting Meta review — sync its "
            "status first; it cannot be edited while under review"
        )

    if template.status is WhatsAppTemplateStatus.APPROVED:
        # Immutable: spawn version+1 as a new draft.
        return create_draft(
            session,
            name=template.name,
            language=template.language,
            category=category or template.category,
            body=body if body is not None else (template.body or ""),
            variable_descriptions=(
                variable_descriptions
                if variable_descriptions is not None
                else template.variable_descriptions_json
            ),
            supersedes=template,
        )

    # draft | rejected: edit in place, back to a clean draft.
    if body is not None:
        slots = validate_body(body)
        template.body = body.strip()
        template.variable_descriptions_json = _validate_variable_descriptions(
            slots,
            variable_descriptions
            if variable_descriptions is not None
            else template.variable_descriptions_json,
        )
    elif variable_descriptions is not None:
        slots = validate_body(template.body or "")
        template.variable_descriptions_json = _validate_variable_descriptions(
            slots, variable_descriptions
        )
    if category is not None:
        template.category = category
    template.status = WhatsAppTemplateStatus.DRAFT
    template.rejection_reason = None
    session.commit()
    return template


def submit_template(session: Session, template: WhatsAppTemplate,
                    adapter) -> WhatsAppTemplate:
    """Submit a draft/rejected template to Meta review via the Business
    Management API (adapter.submit_template). status -> submitted."""
    if template.status not in _EDITABLE:
        raise TemplateError(
            f"only draft or rejected templates can be submitted "
            f"(current status: {template.status.value})"
        )
    # Re-validate right before submission — the db row could predate a
    # rule change.
    validate_body(template.body or "")
    result = adapter.submit_template(
        name=template.name,
        language=template.language,
        category=template.category.value,
        body=template.body or "",
    )
    template.meta_template_id = result.get("id") or template.meta_template_id
    template.status = WhatsAppTemplateStatus.SUBMITTED
    template.rejection_reason = None
    session.commit()
    return template


_META_STATUS_TO_OURS = {
    # TODO: verify against current WhatsApp docs (template status values;
    # Meta uses uppercase e.g. APPROVED / REJECTED / PENDING)
    "APPROVED": WhatsAppTemplateStatus.APPROVED,
    "REJECTED": WhatsAppTemplateStatus.REJECTED,
    "PENDING": WhatsAppTemplateStatus.SUBMITTED,
}


def apply_meta_status(session: Session, template: WhatsAppTemplate,
                      meta_status: str, reason: str | None = None,
                      meta_template_id: str | None = None) -> WhatsAppTemplate:
    """Apply a status reported by Meta (from a sync poll OR a webhook
    event) to our row. Unknown statuses are logged and ignored — never
    guessed."""
    mapped = _META_STATUS_TO_OURS.get((meta_status or "").upper())
    if mapped is None:
        logger.info("unmapped Meta template status %r for %s — ignored",
                    meta_status, template.name)
        return template
    template.status = mapped
    if meta_template_id:
        template.meta_template_id = meta_template_id
    template.rejection_reason = (
        reason if mapped is WhatsAppTemplateStatus.REJECTED else None
    )
    session.commit()

    # Notify only on a terminal Meta decision - SUBMITTED/PENDING is noise.
    #
    # RECIPIENT: admins, not a user. whatsapp_templates has NO owner column
    # (see app/db/models.py::WhatsAppTemplate): one Meta WhatsApp Business
    # Account per install makes templates a deployment-wide shared resource,
    # which is why the API is login-required but deliberately not
    # owner-scoped. There is therefore no single user to notify, and pushing
    # an approval to every user would leak that the template exists to
    # accounts that never touched it. Admins are the people who submit and
    # fix templates.
    if mapped in (WhatsAppTemplateStatus.APPROVED, WhatsAppTemplateStatus.REJECTED):
        from app.services import notifications  # noqa: PLC0415
        from app.services.notification_service import NotificationService  # noqa: PLC0415

        approved = mapped is WhatsAppTemplateStatus.APPROVED
        for admin_id in NotificationService._admin_user_ids():
            notifications.dispatch(notifications.notify_whatsapp_template_status(
                admin_id, template.name, approved=approved,
            ))

    return template


def sync_template(session: Session, template: WhatsAppTemplate,
                  adapter) -> WhatsAppTemplate:
    """Pull the current review status from Meta and apply it."""
    if template.status in (WhatsAppTemplateStatus.DRAFT,):
        raise TemplateError("template has not been submitted yet — nothing to sync")
    data = adapter.fetch_template_status(
        name=template.name, language=template.language,
        meta_template_id=template.meta_template_id,
    )
    if data is None:
        logger.info("Meta returned no status for template %s (%s)",
                    template.name, template.language)
        return template
    return apply_meta_status(
        session, template,
        meta_status=data.get("status", ""),
        reason=data.get("rejected_reason") or data.get("reason"),
        meta_template_id=data.get("id"),
    )


def sendable_template(session: Session, name: str,
                      language: str) -> WhatsAppTemplate | None:
    """The highest APPROVED version for (name, language) — what the
    adapter's send() guard consults. None => not sendable."""
    return session.execute(
        select(WhatsAppTemplate)
        .where(WhatsAppTemplate.name == name,
               WhatsAppTemplate.language == language,
               WhatsAppTemplate.status == WhatsAppTemplateStatus.APPROVED)
        .order_by(WhatsAppTemplate.version.desc())
        .limit(1)
    ).scalars().first()


# --------------------------------------------------------------------------
# AI-assisted drafting (drafts ONLY — never auto-submitted)
# --------------------------------------------------------------------------

_GENERATE_SYSTEM = (
    "You are LeadPilot's WhatsApp template drafter. Produce COMPLIANT Meta "
    "message-template candidates for B2B outreach. Respond with ONLY a JSON "
    'object: {"templates": [ ... ]} containing 2 or 3 items, each: '
    '{"name": "<lowercase_snake_case>", "language": "<e.g. en_US>", '
    '"category": "marketing" | "utility", "body": "<text>", '
    '"variable_descriptions": {"1": "...", ...}}. '
    "HARD RULES for every body: (1) identify the sender by name/company in "
    "the first sentence — no anonymous messages; (2) an honest, specific "
    "value proposition drawn from the provided strategy — no invented "
    "claims, statistics, urgency or guarantees; (3) end with a plain "
    "opt-out instruction such as 'Reply STOP to opt out.'; (4) variable "
    "placeholders exactly {{1}}, {{2}}... sequential from 1, each described "
    "in variable_descriptions; (5) body under "
    f"{settings.whatsapp_template_body_max_chars} characters; "
    "(6) no emojis walls, no ALL CAPS, no misleading familiarity."
)

_GENERATE_PROMPT = """STRATEGY CONTEXT

Persona / ICP (Phase 2 outputs):
{persona}

Messaging & offer design (Phase 6 outputs):
{messaging}

Draft 2-3 WhatsApp template candidates for the FIRST cold touch to this
persona, following every hard rule."""


def _phase_outputs(session: Session, strategy: Strategy, phase: int,
                   limit_chars: int = 3000) -> str:
    steps = session.execute(
        select(ResearchStep)
        .where(ResearchStep.strategy_id == strategy.id,
               ResearchStep.pipeline == PipelineKind.STRATEGY,
               ResearchStep.phase == phase)
        .order_by(ResearchStep.step_no.asc())
    ).scalars().all()
    joined = "\n\n".join(f"[{s.step_id} {s.name}]\n{s.output}" for s in steps)
    return joined[:limit_chars] or "(no outputs recorded for this phase)"


def generate_drafts(session: Session, strategy: Strategy) -> list[WhatsAppTemplate]:
    """Claude-drafted candidates from the strategy's own research. Saved
    as DRAFTS; the user reviews and submits each explicitly. Candidates
    that fail local validation are dropped (logged), not 'fixed' silently."""
    data = get_client().complete_json(
        system=_GENERATE_SYSTEM,
        prompt=_GENERATE_PROMPT.format(
            persona=_phase_outputs(session, strategy, phase=2),
            messaging=_phase_outputs(session, strategy, phase=6),
        ),
    )
    candidates = data.get("templates") or []
    if not isinstance(candidates, list):
        raise TemplateError("model returned no template list")

    created: list[WhatsAppTemplate] = []
    for cand in candidates[:3]:
        try:
            category = WhatsAppTemplateCategory(
                str(cand.get("category", "marketing")).lower()
            )
        except ValueError:
            category = WhatsAppTemplateCategory.MARKETING
        try:
            row = create_draft(
                session,
                name=str(cand.get("name", "")),
                language=str(cand.get("language", "en_US")),
                category=category,
                body=str(cand.get("body", "")),
                variable_descriptions=cand.get("variable_descriptions") or {},
            )
            created.append(row)
        except TemplateError as exc:
            logger.info("dropped invalid generated template %r: %s",
                        cand.get("name"), exc)
    if not created:
        raise TemplateError(
            "no generated candidate passed validation — try again or "
            "write a draft manually"
        )
    return created


def get_template(session: Session, template_id: uuid.UUID) -> WhatsAppTemplate:
    row = session.get(WhatsAppTemplate, template_id)
    if row is None:
        raise TemplateError("template not found")
    return row


def serialize(template: WhatsAppTemplate) -> dict:
    return {
        "id": str(template.id),
        "name": template.name,
        "language": template.language,
        "version": template.version,
        "category": template.category.value,
        "status": template.status.value,
        "body": template.body,
        "variable_descriptions": template.variable_descriptions_json or {},
        "rejection_reason": template.rejection_reason,
        "meta_template_id": template.meta_template_id,
        "supersedes_id": str(template.supersedes_id) if template.supersedes_id else None,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }
