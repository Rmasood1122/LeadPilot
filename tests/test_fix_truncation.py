"""Reproduction of the bug that corrupted the real strategy document.

THE BUG (2026-08-19 Phase C run, confirmed from its own logs):

    strategy_document was ~8,234 tokens.
    _generate_fix asked for "the complete revised document" with max_tokens=8000.
    ClaudeClient.complete() never checked stop_reason, so a length cutoff came
    back looking exactly like a finished answer.
    The loop then did `strategy.strategy_document = revised`.

7 of the 8 fixer calls in that run returned exactly out_tokens=8000. Seven fix
applications each lopped the end off the document, which still ends mid-sentence
at "**Pricing range:** $3,000-". Nothing raised, nothing logged an error, and
each truncation gave the next judge a fresh inconsistency to fail on.

WHAT IS PINNED HERE

  1. the gateway raises on a length cutoff instead of returning partial text;
  2. the loop never writes a truncated revision to strategy_document;
  3. the ceiling is high enough that a realistic document fits;
  4. the pass ends with a distinguishable outcome rather than looking like an
     ordinary content failure.

No real API calls: a fake client reproduces the stop_reason the API returns.
"""

import pytest

from app.config import settings
from app.db import models as m
from app.services.anthropic_client import TruncatedResponseError
from app.verification.loop import run_verification_loop

# The real document that was corrupted, and the shape of the damage.
REAL_DOCUMENT_TOKENS = 8_234
REAL_TRUNCATED_TAIL = "**Pricing range:** $3,000-"

GOOD_DOCUMENT = "# Strategy\n\n## Pricing\nFoundation $3,000/mo, Growth $5,500/mo.\n"


class _Resp:
    """Minimal stand-in for an Anthropic Message."""

    def __init__(self, text, stop_reason, out_tokens):
        self.content = [type("B", (), {"type": "text", "text": text})()]
        self.stop_reason = stop_reason
        self.usage = type("U", (), {"input_tokens": 1000, "output_tokens": out_tokens})()


class _Stream:
    """Context manager matching the SDK's streaming helper."""

    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class TruncatingRawClient:
    """Returns stop_reason="max_tokens" while the requested ceiling is below
    `fits_at` — exactly what the API does when a rewrite does not fit.

    Implements BOTH transports, because `complete()` switches to streaming
    above _NON_STREAMING_MAX_TOKENS (the SDK refuses large non-streaming
    requests locally) and the fixer's ceiling is above that line.
    """

    def __init__(self, fits_at: int, body: str = GOOD_DOCUMENT):
        self.fits_at = fits_at
        self.body = body
        self.ceilings_requested: list[int] = []
        self.streamed: list[bool] = []
        self.messages = self

    def _respond(self, max_tokens: int) -> _Resp:
        self.ceilings_requested.append(max_tokens)
        if max_tokens < self.fits_at:
            # Truncated: the partial text is what the old code persisted.
            return _Resp(self.body[: len(self.body) // 2], "max_tokens", max_tokens)
        return _Resp(self.body, "end_turn", 1200)

    def create(self, *, model, max_tokens, system, messages):
        self.streamed.append(False)
        return self._respond(max_tokens)

    def stream(self, *, model, max_tokens, system, messages):
        self.streamed.append(True)
        return _Stream(self._respond(max_tokens))


def _client_with(raw):
    from app.services.anthropic_client import ClaudeClient

    client = ClaudeClient.__new__(ClaudeClient)  # bypass __init__ (needs a key)
    client._client = raw
    return client


class TestGatewayDetectsTheCutoff:
    """Layer 2: a length cutoff must not look like a finished answer."""

    def test_complete_raises_on_max_tokens_stop_reason(self):
        client = _client_with(TruncatingRawClient(fits_at=9_999))

        with pytest.raises(TruncatedResponseError) as exc:
            client.complete(system="s", prompt="p", max_tokens=8000)

        assert exc.value.limit == 8000
        assert "cut off" in str(exc.value)

    def test_partial_text_is_carried_but_not_returned(self):
        """The old code RETURNED this text; now it is only attached to the
        error for diagnostics, where it cannot be mistaken for a document."""
        client = _client_with(TruncatingRawClient(fits_at=9_999))

        with pytest.raises(TruncatedResponseError) as exc:
            client.complete(system="s", prompt="p", max_tokens=8000)

        assert exc.value.partial_text
        assert exc.value.partial_text != GOOD_DOCUMENT

    def test_normal_completion_still_returns_text(self):
        """No false positives: end_turn must pass through untouched."""
        client = _client_with(TruncatingRawClient(fits_at=1))

        assert client.complete(system="s", prompt="p", max_tokens=8000) == GOOD_DOCUMENT

    def test_json_helper_inherits_the_check(self):
        """complete_json delegates to complete, so judges are covered too."""
        client = _client_with(TruncatingRawClient(fits_at=9_999, body='{"result":"PASS"}'))

        with pytest.raises(TruncatedResponseError):
            client.complete_json(system="s", prompt="p", max_tokens=8000)


class TestCeilingIsBigEnough:
    """Layer 1: the configured bound must clear a realistic document."""

    def test_fixer_ceiling_exceeds_the_document_that_broke_it(self):
        assert settings.verification_fixer_max_tokens > REAL_DOCUMENT_TOKENS

    def test_fixer_ceiling_has_real_headroom_for_growth(self):
        """~2x the largest observed document (8,234 tokens).

        Not more, because the primary call must stay under the SDK's
        non-streaming cut-off — see _NON_STREAMING_MAX_TOKENS. The headroom
        beyond 2x comes from the doubled retry and the refuse-to-persist rule,
        not from this number alone.
        """
        assert settings.verification_fixer_max_tokens >= REAL_DOCUMENT_TOKENS * 2

    def test_fixer_ceiling_stays_within_the_model_output_cap(self):
        from app.verification.loop import _MODEL_MAX_OUTPUT_TOKENS

        assert settings.verification_fixer_max_tokens <= _MODEL_MAX_OUTPUT_TOKENS

    def test_loop_no_longer_hardcodes_the_old_ceiling(self):
        """The literal 8000 that caused this must be gone from the call site."""
        import inspect

        from app.verification import loop

        source = inspect.getsource(loop._generate_fix)
        assert "8000" not in source
        assert "verification_fixer_max_tokens" in source


class TestLoopNeverPersistsTruncation:
    """Layer 3: the document must survive a fix that cannot be returned."""

    def _prepare(self, db, product_with_strategy):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        strategy.strategy_document = GOOD_DOCUMENT
        db.commit()
        return strategy

    def test_document_is_left_untouched_when_every_ceiling_truncates(
        self, db_session, monkeypatch, product_with_strategy
    ):
        strategy = self._prepare(db_session, product_with_strategy)

        # Judge always fails pass 1; fixer never fits, even when doubled.
        raw = TruncatingRawClient(fits_at=10 ** 9)

        class Client:
            def complete_json(self, system, prompt, max_tokens=None):
                import re
                pass_no = int(re.search(r"criterion #(\d+)", prompt, re.I).group(1))
                if pass_no == 1:
                    return {"result": "FAIL", "fix_description": "fix the pricing"}
                return {"result": "PASS"}

            def complete(self, system, prompt, max_tokens=None):
                return _client_with(raw).complete(
                    system=system, prompt=prompt, max_tokens=max_tokens)

        monkeypatch.setattr("app.verification.loop.get_client", lambda: Client())

        run_verification_loop(db_session, strategy)

        assert strategy.strategy_document == GOOD_DOCUMENT, (
            "the truncated rewrite was persisted — this is the original bug"
        )
        assert not strategy.strategy_document.endswith("-")

    def test_pass_is_flagged_as_truncated_not_as_a_content_failure(
        self, db_session, monkeypatch, product_with_strategy
    ):
        strategy = self._prepare(db_session, product_with_strategy)
        raw = TruncatingRawClient(fits_at=10 ** 9)

        class Client:
            def complete_json(self, system, prompt, max_tokens=None):
                import re
                pass_no = int(re.search(r"criterion #(\d+)", prompt, re.I).group(1))
                return ({"result": "FAIL", "fix_description": "fix it"}
                        if pass_no == 1 else {"result": "PASS"})

            def complete(self, system, prompt, max_tokens=None):
                return _client_with(raw).complete(
                    system=system, prompt=prompt, max_tokens=max_tokens)

        monkeypatch.setattr("app.verification.loop.get_client", lambda: Client())

        final = run_verification_loop(db_session, strategy)

        entries = [e for e in strategy.verified_passes_json if e["pass_no"] == 1]
        assert entries[-1]["outcome"] == "fix_truncated"
        assert entries[-1]["conflict"]["output_token_ceiling"] > 0
        assert entries[-1]["fix_applied"] is False
        assert final is m.StrategyStatus.NEEDS_HUMAN_REVIEW

    def test_one_retry_at_a_higher_ceiling_before_giving_up(
        self, db_session, monkeypatch, product_with_strategy
    ):
        """A document that outgrew the bound should still get through once."""
        strategy = self._prepare(db_session, product_with_strategy)
        # Fits only above the configured ceiling -> the doubled retry succeeds.
        raw = TruncatingRawClient(fits_at=settings.verification_fixer_max_tokens + 1)

        class Client:
            def complete_json(self, system, prompt, max_tokens=None):
                import re
                pass_no = int(re.search(r"criterion #(\d+)", prompt, re.I).group(1))
                if pass_no == 1 and not getattr(self, "_seen", False):
                    self._seen = True
                    return {"result": "FAIL", "fix_description": "fix it"}
                return {"result": "PASS"}

            def complete(self, system, prompt, max_tokens=None):
                return _client_with(raw).complete(
                    system=system, prompt=prompt, max_tokens=max_tokens)

        monkeypatch.setattr("app.verification.loop.get_client", lambda: Client())

        run_verification_loop(db_session, strategy)

        assert len(raw.ceilings_requested) >= 2, "no retry at a raised ceiling"
        assert raw.ceilings_requested[1] > raw.ceilings_requested[0]
        # The retry fit, so the document WAS legitimately updated.
        assert strategy.strategy_document == GOOD_DOCUMENT


class TestTheOriginalCorruptionShape:
    def test_a_document_ending_mid_sentence_is_what_we_are_preventing(self):
        """Documents the observed damage so the shape is not forgotten."""
        assert REAL_TRUNCATED_TAIL.endswith("-")
        assert not REAL_TRUNCATED_TAIL.endswith(".")


class TestLargeCeilingsUseStreaming:
    """The SDK refuses a non-streaming request whose max_tokens implies a
    generation over 10 minutes — it raises ValueError locally, before sending.
    Measured on this SDK version: 21,333 accepted, 32,000 refused.

    The fixer's ceiling is above that line, so the gateway must stream. This was
    caught by the integration suite, not by unit tests: a 32,000-token
    non-streaming fixer call made run_pipeline crash-retry.
    """

    def test_primary_fixer_call_stays_non_streaming(self):
        """It must sit under the cut-off: the integration mock serves JSON, not
        SSE, and a streaming primary call made run_pipeline crash-retry."""
        raw = TruncatingRawClient(fits_at=1)
        _client_with(raw).complete(
            system="s", prompt="p",
            max_tokens=settings.verification_fixer_max_tokens,
        )
        assert raw.streamed == [False]

    def test_doubled_retry_ceiling_streams(self):
        """The retry crosses the cut-off, so it must take the streaming path or
        the SDK would refuse it outright."""
        raw = TruncatingRawClient(fits_at=1)
        _client_with(raw).complete(
            system="s", prompt="p",
            max_tokens=settings.verification_fixer_max_tokens * 2,
        )
        assert raw.streamed == [True]

    def test_ordinary_calls_stay_non_streaming(self):
        """Pipeline steps and judges must keep the simple path."""
        raw = TruncatingRawClient(fits_at=1)
        _client_with(raw).complete(system="s", prompt="p", max_tokens=4096)
        assert raw.streamed == [False]

    def test_streamed_response_is_still_checked_for_truncation(self):
        """stop_reason must be honoured on the streaming path too."""
        raw = TruncatingRawClient(fits_at=10 ** 9)
        with pytest.raises(TruncatedResponseError):
            _client_with(raw).complete(
                system="s", prompt="p",
                max_tokens=settings.verification_fixer_max_tokens * 2,
            )

    def test_primary_ceiling_is_under_the_sdk_cut_off(self):
        """Measured: 21,333 accepted non-streaming, 32,000 refused locally."""
        from app.services.anthropic_client import _NON_STREAMING_MAX_TOKENS

        assert settings.verification_fixer_max_tokens <= _NON_STREAMING_MAX_TOKENS
        assert _NON_STREAMING_MAX_TOKENS < 21_333
