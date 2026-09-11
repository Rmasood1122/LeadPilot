"""Role-based access for workspace members (Feature Group 8).

Enforced ONCE, in app/services/auth.py::get_current_user -- the same
chokepoint that already enforces email verification -- so a route added
tomorrow is covered without anyone remembering to guard it.

    owner    everything, including branding, the approval rule and roles
    manager  everything an owner can do with the data, approves SDR launches,
             manages SDRs and viewers (not other managers)
    sdr      works leads and campaigns; launching a campaign asks a manager
             (when the workspace requires approval); cannot touch
             integrations, webhooks, costs or delete anything
    viewer   read-only

Finer rules (who may change whose role, who may approve) live next to the
action in app/services/workspaces.py and app/api/sequences.py; this module is
the coarse gate every request passes.
"""

from __future__ import annotations

from fastapi import HTTPException

ROLES = ("owner", "manager", "sdr", "viewer")
RANK = {"viewer": 0, "sdr": 1, "manager": 2, "owner": 3}
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Routes that are about the PERSON, not the workspace's data: they always
# act as the signed-in user, whatever workspace is selected.
PERSONAL_PREFIXES = ("/auth", "/me", "/devices", "/support", "/tutorials", "/onboarding",
                     "/workspaces", "/branding")

# Writes an SDR may not make: account plumbing and money.
SDR_BLOCKED_PREFIXES = ("/integrations", "/webhooks/outbound", "/webhooks/targets", "/costs",
                        "/admin", "/playbook")


def is_personal(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PERSONAL_PREFIXES)


def at_least(role: str | None, minimum: str) -> bool:
    return RANK.get(role or "", -1) >= RANK[minimum]


def enforce(role: str, method: str, path: str) -> None:
    """Raise 403 if `role` may not make this request."""
    if role == "owner" or method.upper() in SAFE_METHODS:
        return
    if role == "viewer":
        raise HTTPException(status_code=403,
                            detail="Viewers have read-only access to this workspace.")
    if role == "sdr":
        if method.upper() == "DELETE":
            raise HTTPException(status_code=403,
                                detail="Deleting needs a manager in this workspace.")
        if any(path == p or path.startswith(p + "/") for p in SDR_BLOCKED_PREFIXES):
            raise HTTPException(status_code=403,
                                detail="Integrations, webhooks and costs need a manager.")
    if role not in RANK:
        raise HTTPException(status_code=403, detail="Unknown workspace role.")
