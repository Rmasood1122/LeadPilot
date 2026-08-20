"""Phase C — exercise every standalone Claude-backed service against the REAL API.

These services have only ever run against a transport-layer mock. This
script makes real calls and asserts on the SHAPE of what comes back (the
contract each caller depends on), not on exact wording.

The 72/144-step pipeline and the 10 verification passes are NOT run here —
they go through Celery and are driven by scripts/phase_c_pipeline.py.

Usage:  python scripts/phase_c_services.py
Exit code 0 = every check passed.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.anthropic_client import get_client  # noqa: E402
from app.services.pattern_recognition import PATTERN_KEYS, extract_patterns  # noqa: E402
from app.services.reply_classification import REPLY_CLASSES, classify_reply  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        detail = fn()
        _results.append((name, True, detail or ""))
        print(f"  PASS  {name}  {detail or ''}")
    except Exception as exc:  # noqa: BLE001 - harness reports, never masks
        _results.append((name, False, f"{type(exc).__name__}: {exc}"))
        print(f"  FAIL  {name}  {type(exc).__name__}: {exc}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# 1. Gateway connectivity — the single chokepoint every other service uses.
# ---------------------------------------------------------------------------
def _connectivity() -> str:
    text = get_client().complete(
        system="Reply with exactly one word and nothing else.",
        prompt="Say OK",
        max_tokens=16,
    )
    assert text.strip(), "empty completion"
    return f"-> {text.strip()[:20]!r}"


def _json_mode() -> str:
    data = get_client().complete_json(
        system="Respond with ONLY a JSON object, no prose, no fences.",
        prompt='Return {"ok": true, "n": 42}',
        max_tokens=64,
    )
    assert isinstance(data, dict), f"not a dict: {type(data)}"
    assert data.get("n") == 42, f"unexpected payload: {data}"
    return f"-> {data}"


# ---------------------------------------------------------------------------
# 2. Pattern recognition (Flow 1 intake).
# ---------------------------------------------------------------------------
def _pattern_recognition() -> str:
    out = extract_patterns(
        details=(
            "Northwind Logistics, a regional freight brokerage in Ohio with "
            "about 40 employees. We sold them our compliance automation "
            "suite for $24,000 a year. The buyer was their VP of Operations."
        ),
        acquisition_story=(
            "They found us after failing a DOT audit in March. A mutual "
            "contact referred them. From first call to signed contract took "
            "about three weeks."
        ),
    )
    assert isinstance(out, dict), f"not a dict: {type(out)}"
    missing = [k for k in PATTERN_KEYS if k not in out]
    assert not missing, f"missing keys: {missing}"
    assert not out.get("_extraction_error"), f"extraction error: {out.get('_extraction_error')}"
    # The model should have picked up at least the strongly-stated fields.
    populated = [k for k in PATTERN_KEYS if out.get(k)]
    assert len(populated) >= 5, f"only {len(populated)} of 7 populated: {out}"
    return f"-> {len(populated)}/7 populated, industry={out.get('industry')!r}, channel={out.get('acquisition_channel')!r}"


# ---------------------------------------------------------------------------
# 3. Reply classification — every routing class the sequence engine branches on.
# ---------------------------------------------------------------------------
_REPLY_CASES = [
    (
        "interested",
        ("dana@acme.com", "Re: quick question",
         "This looks genuinely useful. Can you send over pricing and "
         "availability for a call next week?"),
    ),
    (
        "not_interested",
        ("raj@acme.com", "Re: quick question",
         "Thanks but we're all set with our current vendor. Not something "
         "we're looking at this year."),
    ),
    (
        "unsubscribe_request",
        ("lee@acme.com", "Re: quick question",
         "Please remove me from your list and stop emailing me."),
    ),
    (
        "out_of_office",
        ("sam@acme.com", "Automatic reply: quick question",
         "I am out of the office until 14 March with limited access to "
         "email. For urgent matters contact ops@acme.com."),
    ),
    (
        "bounce",
        ("mailer-daemon@acme.com", "Undeliverable: quick question",
         "Delivery to the following recipient failed permanently: "
         "nobody@acme.com. The email account that you tried to reach does "
         "not exist. 550 5.1.1 Address not found."),
    ),
    (
        "objection",
        ("kim@acme.com", "Re: quick question",
         "Honestly this seems way too expensive for what it does, and we "
         "already tried something similar last year that didn't work."),
    ),
]


def _reply_classification() -> str:
    wrong = []
    for expected, (frm, subj, body) in _REPLY_CASES:
        got = classify_reply(frm, subj, body)
        assert got in REPLY_CLASSES, f"{got!r} is not a valid class"
        if got != expected:
            wrong.append(f"{expected}->{got}")
    assert not wrong, f"misclassified: {', '.join(wrong)}"
    return f"-> {len(_REPLY_CASES)}/{len(_REPLY_CASES)} classified correctly"


def _reply_degrades_safely() -> str:
    """Garbage in must still yield a valid routing class, never an exception."""
    got = classify_reply("x@y.z", None, "?????")
    assert got in REPLY_CLASSES, f"{got!r} is not a valid class"
    return f"-> {got!r}"


def main() -> int:
    print("Phase C - standalone Claude-backed services (REAL API)")
    print("=" * 62)
    print("[1] Anthropic gateway")
    check("gateway.complete", _connectivity)
    check("gateway.complete_json", _json_mode)
    print("[2] Pattern recognition (Flow 1 intake)")
    check("pattern_recognition.extract_patterns", _pattern_recognition)
    print("[3] Reply classification")
    check("reply_classification.classify_reply", _reply_classification)
    check("reply_classification.degrades_safely", _reply_degrades_safely)

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print("=" * 62)
    print(f"RESULT: {passed}/{total} passed")
    for name, ok, detail in _results:
        if not ok:
            print(f"  FAILED: {name}: {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
