"""Real-time reply-authenticity scoring (Feature A3).

`classify_reply` answers "how does the system ROUTE this reply?" and
reply_fraud's second pass drops obvious machines from engagement metrics.
This answers the question a person working the inbox actually has: IS THIS A
REAL BUYER, and how sure are we? Every inbound reply on every channel is
scored the moment it is stored, and the result is kept on the reply row.

KINDS (separated, because each wants a different action)
  genuine          a person wrote it -- work it
  out_of_office    a vacation/leave responder -- wait, the sequence pauses
  auto_responder   a receipt, helpdesk or ticket acknowledgement -- ignore
  bot              a no-reply / unmonitored system mailbox -- ignore, and the
                   address is not a real contact
  bounce           a delivery failure notice

SCORES (all 0..1)
  authenticity_score   how likely a human wrote it
  buyer_intent_score   for a genuine reply, how strongly it signals buying
                       intent (0 for every automated kind)
  confidence           how sure the kind is
The signals behind each are stored, so a score can always be explained.

HOW. Deterministic evidence, no extra model call on the hot path:
  * RFC 3834 / auto-responder headers (strongest), sender and subject patterns,
    body phrases, out-of-office and bounce phrasing (reply_fraud.py);
  * timing: a reply inside RAPID_REPLY_SECONDS of our send is almost always
    machine-generated;
  * the classifier's own verdict (automated_response / out_of_office / bounce)
    counts as evidence, and for genuine replies sets the intent baseline;
  * buying signals in the text (meeting, pricing, a concrete question).
Independent pieces of automation evidence combine as 1 - prod(1 - weight), so
two medium signals outweigh one, and no single weak phrase condemns a reply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services import reply_fraud

GENUINE, OUT_OF_OFFICE, AUTO_RESPONDER, BOT, BOUNCE = (
    "genuine", "out_of_office", "auto_responder", "bot", "bounce")
KINDS = (GENUINE, OUT_OF_OFFICE, AUTO_RESPONDER, BOT, BOUNCE)
RAPID_REPLY_SECONDS = 45
AUTOMATION_THRESHOLD = 0.6

_INTENT_BASE = {"interested": 0.8, "question": 0.55, "objection": 0.35,
                "not_interested": 0.08, "unsubscribe_request": 0.0}
_INTENT_SIGNALS = [(name, re.compile(pattern, re.I)) for name, pattern in (
    ("meeting", r"\b(call|chat|meet(ing)?|demo|calendar|calendly|zoom|book (a|some) time|"
                r"(mon|tues|wednes|thurs|fri)day|next week|tomorrow)\b"),
    ("pricing", r"\b(pric(e|ing)|cost|budget|quote|proposal|contract|how much)\b"),
    ("more_info", r"\b(tell me more|send (me|over)|more (info|details)|case stud(y|ies)|"
                  r"how (does|would) (it|this) work)\b"),
    ("interest", r"\b(interested|sounds (good|great|interesting)|let'?s (talk|do it)|keen)\b"),
    ("question", r"\?"),
)]
_BOT_MARKERS = ("from:no-reply sender", "body:(this|the) (mailbox|inbox) is (not|un)",
                "body:\\bticket\\s*(number|no\\.?|#|id)\\b")


@dataclass
class AuthenticityResult:
    kind: str
    authenticity_score: float
    buyer_intent_score: float
    confidence: float
    signals: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "authenticity_score": self.authenticity_score,
                "buyer_intent_score": self.buyer_intent_score,
                "confidence": self.confidence, "signals": list(self.signals)}


def _combine(weights: list[float]) -> float:
    remaining = 1.0
    for w in weights:
        remaining *= 1.0 - max(0.0, min(w, 0.99))
    return 1.0 - remaining


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def score(*, from_address: str | None, subject: str | None, body: str | None,
          classification: str | None = None, headers: dict | None = None,
          received_at: datetime | None = None, sent_at: datetime | None = None) -> AuthenticityResult:
    header = reply_fraud.header_signals(headers)
    automated = reply_fraud.signals(from_address, subject, body)
    ooo = reply_fraud.out_of_office_signals(subject, body)
    bounce = reply_fraud.bounce_signals(from_address, subject, body)

    weights: list[float] = [0.9] * len(header)
    weights += [0.8 if s.startswith(("from:", "subject:")) else 0.35 for s in automated]
    weights += [0.55] * len(ooo)
    weights += [0.9] * len(bounce)
    signals = header + automated + ooo + bounce

    rapid = False
    if received_at is not None and sent_at is not None:
        delta = (_aware(received_at) - _aware(sent_at)).total_seconds()
        if 0 <= delta < RAPID_REPLY_SECONDS:
            rapid = True
            weights.append(0.45)
            signals.append(f"timing:replied {int(delta)}s after send")

    if classification == "automated_response":
        weights.append(0.7)
        signals.append("classifier:automated_response")
    elif classification == "out_of_office":
        weights.append(0.75)
        signals.append("classifier:out_of_office")
    elif classification == "bounce":
        weights.append(0.9)
        signals.append("classifier:bounce")

    automation = _combine(weights)
    ooo_strength = _combine([0.55] * len(ooo) + ([0.75] if classification == "out_of_office" else []))
    bounce_strength = _combine([0.9] * len(bounce) + ([0.9] if classification == "bounce" else []))

    if bounce_strength >= AUTOMATION_THRESHOLD:
        kind, confidence = BOUNCE, bounce_strength
    elif ooo_strength >= 0.5:
        kind, confidence = OUT_OF_OFFICE, max(ooo_strength, automation)
    elif automation >= AUTOMATION_THRESHOLD:
        is_bot = any(s.startswith(marker) for s in automated for marker in _BOT_MARKERS)
        kind, confidence = (BOT if is_bot else AUTO_RESPONDER), automation
    else:
        kind = GENUINE
        # No evidence either way is not certainty: 0.7 is "nothing looks
        # automated". Each piece of weak automation evidence lowers it.
        confidence = max(0.5, min(0.97, (1.0 - automation) * (0.7 if not signals else 1.0)
                                  if not rapid else 0.55))

    intent = 0.0
    if kind == GENUINE:
        intent = _INTENT_BASE.get(classification or "", 0.3)
        found = [name for name, pattern in _INTENT_SIGNALS if pattern.search(body or "")]
        signals += [f"intent:{name}" for name in found]
        if classification not in ("not_interested", "unsubscribe_request"):
            intent = min(1.0, intent + 0.05 * len(found))
        if found and not automated:
            confidence = min(0.97, confidence + 0.1)

    return AuthenticityResult(
        kind=kind,
        authenticity_score=round(1.0 - automation, 3),
        buyer_intent_score=round(intent, 3),
        confidence=round(confidence, 3),
        signals=signals[:40],
    )


def apply(session: Session, reply, *, classification: str | None = None,
          headers: dict | None = None, sent_at: datetime | None = None,
          now: datetime | None = None) -> AuthenticityResult:
    """Score one InboundReply row and store the result on it (no commit)."""
    result = score(from_address=reply.from_address, subject=reply.subject, body=reply.body,
                   classification=classification or reply.classification,
                   headers=headers, received_at=reply.received_at, sent_at=sent_at)
    reply.authenticity_kind = result.kind
    reply.authenticity_score = result.authenticity_score
    reply.buyer_intent_score = result.buyer_intent_score
    reply.authenticity_confidence = result.confidence
    reply.authenticity_signals_json = result.signals
    reply.authenticity_scored_at = now or datetime.now(timezone.utc)
    return result


def headers_from_raw(raw: dict | None) -> dict:
    """Best-effort header map from a provider's raw inbound payload.

    Gmail's API shape is payload.headers = [{name, value}]; other providers
    send a flat dict. Anything unrecognised yields {} (headers are an
    optional signal, never a requirement)."""
    if not isinstance(raw, dict):
        return {}
    candidates = [raw.get("headers"), (raw.get("payload") or {}).get("headers")
                  if isinstance(raw.get("payload"), dict) else None]
    for value in candidates:
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        if isinstance(value, list):
            return {str(h.get("name")): str(h.get("value") or "") for h in value
                    if isinstance(h, dict) and h.get("name")}
    return {}


def safe_apply(session: Session, reply, **kwargs) -> AuthenticityResult | None:
    """apply(), but a scoring failure never breaks reply routing."""
    import logging  # noqa: PLC0415

    try:
        return apply(session, reply, **kwargs)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("authenticity scoring failed for reply %s",
                                              getattr(reply, "id", None))
        return None
