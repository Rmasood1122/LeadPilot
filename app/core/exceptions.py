"""Canonical application exceptions (M8-C3 error handling contract).

ComplianceError carries a machine-readable `rule` identifier and a
plain-language `remediation` string (project-wide compliance convention),
plus `compliance_code` which the global error handler exposes to clients.
"""
from __future__ import annotations


class ClientHunterError(Exception):
    """Base class for all application errors.

    `user_safe`: the message is a sentence the application wrote for the
    account holder, so app.core.errors.public_detail may put it in an API
    response. A subclass whose message can carry a PROVIDER's text (a Stripe,
    Resend/SMTP or Twilio error body) sets it False; its callers map it to
    fixed text themselves (gaps-sweep-2 review L2).
    """

    user_safe: bool = True


class ComplianceError(ClientHunterError):
    """A compliance rule blocked the operation (CAN-SPAM, GDPR, WhatsApp policy...).

    Raised → HTTP 422 by app.core.errors.global_exception_handler.
    """

    def __init__(self, message: str, *, rule: str = "unspecified",
                 remediation: str = "", compliance_code: str | None = None):
        super().__init__(message)
        self.rule = rule
        self.remediation = remediation
        self.compliance_code = compliance_code or rule


class ResourceNotFoundError(ClientHunterError):
    """Requested resource does not exist or is not visible to this user. → 404"""

    def __init__(self, message: str = "resource not found", *, resource: str = ""):
        super().__init__(message)
        self.resource = resource


class ForbiddenError(ClientHunterError):
    """Authenticated but not allowed. → 403"""
