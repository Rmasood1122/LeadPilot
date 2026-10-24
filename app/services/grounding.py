"""Is a model's text grounded in what it was given? Deterministic checks.

Several writers are told, in their prompt, never to invent a statistic, a
price, a date, a funding round, a discount or a deadline. A prompt rule is not
a control: these checks compare the output with the source text the model was
given and name what the source does not contain. No model call.

They are pattern checks, not judges. A number that appears anywhere in the
source passes even if the output uses it for something else; a claim phrased
without a number, a round name or a date is not seen.
"""

from __future__ import annotations

import re

# A number as people write it: 45, 1,200, $2.5, 63%. The same shape the eval
# graders use (evals/ai/graders.py NUMBER_RE), so app and eval agree.
_NUMBER = re.compile(r"(?<![\w.])\$?\d[\d,]*(?:\.\d+)?%?")

_FUNDING = re.compile(
    r"\bseries\s+[a-h]\b|\b(?:pre-?)?seed\s+(?:round|funding)\b|\bfunding\s+round\b",
    re.IGNORECASE)

# Offers and promises a writer may not make up: discounts, free extras,
# guarantees.
_DISCOUNT = re.compile(
    r"\bdiscount(?:s|ed)?\b|\b\d+\s?%\s+off\b"
    r"|\bfree\s+(?:months?|weeks?|trial|onboarding|set-?up|implementation|migration|"
    r"training|support|consultation|audit)\b"
    r"|\bmoney[- ]back\b|\bguarantee[ds]?\b",
    re.IGNORECASE)

_DAY = (r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow|"
        r"tonight|end\s+of\s+(?:the\s+)?(?:day|week|month|quarter))")
# A day word counts as a deadline only right after "by/until/before" or
# "closes/ends/expires", so "ask how long close takes today" is not one.
_DEADLINE = re.compile(
    r"\b(?:by|until|before|(?:closes?|ends?|expires?|deadline\s+is)(?:\s+(?:on|at))?)"
    r"\s+(?:(?:this|next|the)\s+)?" + _DAY + r"\b"
    r"|\blast\s+chance\b|\btoday\s+only\b|\blimited[- ]time\b",
    re.IGNORECASE)


def _norm_number(raw: str) -> str:
    return raw.strip("$%").replace(",", "")


def numbers_in(text: str | None) -> set[str]:
    return {_norm_number(n) for n in _NUMBER.findall(text or "")}


def unsupported_numbers(text: str | None, *sources: str | None) -> list[str]:
    """Numbers in `text` that none of `sources` contains, sorted."""
    known: set[str] = set()
    for source in sources:
        known |= numbers_in(source)
    return sorted(numbers_in(text) - known)


def unsupported_funding(text: str | None, *sources: str | None) -> list[str]:
    """Funding-round names ('Series B', 'seed round') in `text` that no
    source mentions."""
    known = " ".join((s or "").lower() for s in sources)
    found = {" ".join(m.group(0).lower().split()) for m in _FUNDING.finditer(text or "")}
    return sorted(f for f in found if f not in " ".join(known.split()))


def unsupported_offers(text: str | None, *sources: str | None) -> list[str]:
    """Discount or deadline wording in `text` that no source contains. A
    playbook that really offers '20% off' grounds it; an invented 'closes this
    Friday' is named."""
    known = " ".join(" ".join((s or "").lower().split()) for s in sources)
    hits = [m.group(0) for m in _DISCOUNT.finditer(text or "")]
    hits += [m.group(0) for m in _DEADLINE.finditer(text or "")]
    found = {" ".join(h.lower().split()) for h in hits}
    return sorted(h for h in found if h not in known)


def problems(text: str | None, *sources: str | None) -> list[str]:
    """Every ungrounded item in `text`, as readable reasons ([] = grounded)."""
    out = []
    numbers = unsupported_numbers(text, *sources)
    if numbers:
        out.append(f"numbers not in the source ({', '.join(numbers)})")
    rounds = unsupported_funding(text, *sources)
    if rounds:
        out.append(f"funding not in the source ({', '.join(rounds)})")
    offers = unsupported_offers(text, *sources)
    if offers:
        out.append(f"offers or deadlines not in the source ({', '.join(offers)})")
    return out


# A quotation of three words or more, in straight or curly double quotes.
_QUOTE = re.compile(r"[\"“]([^\"”]{3,400})[\"”]")


def _plain(text: str | None) -> str:
    return " ".join(re.sub(r"[^\w\s%$]", " ", (text or "").lower()).split())


def appears_in(passage: str | None, *sources: str | None) -> bool:
    """True when `passage` occurs in a source, ignoring case, spacing and
    punctuation. For text presented as someone's own words."""
    wanted = _plain(passage)
    return bool(wanted) and any(wanted in _plain(s) for s in sources)


def unsupported_quotes(text: str | None, *sources: str | None) -> list[str]:
    """Quoted passages in `text` (three words or more) that appear in no
    source. A quote attributed to a prospect must be something they wrote."""
    known = " ".join(_plain(s) for s in sources)
    out = []
    for match in _QUOTE.finditer(text or ""):
        quoted = _plain(match.group(1))
        if len(quoted.split()) >= 3 and quoted not in known:
            out.append(match.group(1).strip())
    return out


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def drop_ungrounded_sentences(text: str | None, *sources: str | None) -> tuple[str, list[str]]:
    """(`text` without its ungrounded sentences, the reasons). A sentence is
    ungrounded when it states a number, funding round, offer or deadline, or
    quotes a passage, that no source contains."""
    kept, reasons = [], []
    for sentence in _SENTENCE_END.split((text or "").strip()):
        found = problems(sentence, *sources)
        quotes = unsupported_quotes(sentence, *sources)
        if quotes:
            found.append(f"quotes not in the source ({'; '.join(quotes)})")
        if found:
            reasons.extend(found)
        elif sentence:
            kept.append(sentence)
    return " ".join(kept), reasons
