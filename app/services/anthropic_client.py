"""The single gateway for every Anthropic API call in LeadPilot.

Pattern recognition (intake), all 72/144 pipeline steps, the 10
verification passes and fix-generation all go through ClaudeClient, so
retries, model selection and logging live in exactly one place — and the
test suite mocks exactly one thing (`get_client`).
"""

import json
import logging
import re

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.core.exceptions import ClientHunterError

logger = logging.getLogger(__name__)

# Transient errors worth retrying; 4xx client errors are not retried.
#
# OverloadedError (529) is here deliberately: it is NOT a subclass of
# InternalServerError (both derive straight from APIStatusError), so listing
# InternalServerError alone left 529 unretried even though "server is
# overloaded, try again" is the single most retryable response the API sends.
RETRYABLE_API_ERRORS = (
    anthropic.RateLimitError,        # 429
    anthropic.APIConnectionError,    # network
    anthropic.APITimeoutError,       # network
    anthropic.InternalServerError,   # 5xx
    anthropic.OverloadedError,       # 529
)

# Errors that CANNOT succeed on retry, no matter how long you wait.
#
# The gateway already refuses to retry these (they are simply absent from
# RETRYABLE_API_ERRORS), but tenacity's silence is not the same as telling the
# CALLER not to retry. app/workers/tasks.py used to re-enqueue every exception
# through Celery's own retry, so a revoked key or an exhausted credit balance
# burned all three attempts at 30s intervals before giving up -- and then left
# the strategy stuck, because nothing set a terminal status. Both halves of
# that are fixed; this tuple is the half that says "stop".
PERMANENT_API_ERRORS = (
    anthropic.BadRequestError,          # 400 — malformed request, credit exhaustion
    anthropic.AuthenticationError,      # 401 — missing/revoked/invalid key
    anthropic.PermissionDeniedError,    # 403 — key lacks access to the model
    anthropic.NotFoundError,            # 404 — unknown model name
    anthropic.RequestTooLargeError,     # 413 — prompt over the hard limit
    anthropic.UnprocessableEntityError, # 422
)

# Backwards-compatible private alias — the @retry decorator below still uses it.
_RETRYABLE = RETRYABLE_API_ERRORS


def is_permanent_error(exc: BaseException) -> bool:
    """True when retrying `exc` is provably pointless.

    Anything not classified here keeps the old retry behaviour: unknown and
    unexpected failures (DB blips, transient bugs) are still worth another
    attempt, and a wrong "permanent" verdict would turn a recoverable hiccup
    into a dead strategy. Only errors that are certain are listed.
    """
    # A truncated response repeats identically against the same ceiling — see
    # TruncatedResponseError's docstring. Raising the ceiling is the caller's
    # job (app/verification/loop.py::_generate_fix), not a retry's.
    if isinstance(exc, TruncatedResponseError):
        return True
    if isinstance(exc, RETRYABLE_API_ERRORS):
        return False          # explicit: retryable wins over any overlap
    return isinstance(exc, PERMANENT_API_ERRORS)

# Above this ceiling `complete()` switches to the streaming endpoint.
#
# The SDK REFUSES a non-streaming request whose max_tokens could imply more than
# 10 minutes of generation, raising ValueError("Streaming is required ...")
# locally before anything is sent. Measured against this SDK version:
# max_tokens=21,333 is accepted, 32,000 is refused. 20,000 sits just under that
# cut-off with margin.
#
# Everything the app normally does (pipeline steps at 4,096, judges at the
# default, the fixer at verification_fixer_max_tokens) stays on the simple
# non-streaming path; only the fixer's doubled retry crosses into streaming.
_NON_STREAMING_MAX_TOKENS = 20_000


class TruncatedResponseError(ClientHunterError):
    """The model stopped at the max_tokens ceiling instead of finishing.

    Deliberately NOT in _RETRYABLE: retrying the identical request against the
    identical ceiling produces the identical truncation. The caller must either
    raise the ceiling or abandon the operation — see
    app/verification/loop.py::_generate_fix.

    `partial_text` is carried for diagnostics only. Do not persist it; that is
    exactly the bug this exception exists to prevent.
    """

    def __init__(self, message: str, *, limit: int, partial_text: str = "") -> None:
        super().__init__(message)
        self.limit = limit
        self.partial_text = partial_text


class ClaudeClient:
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env "
                "(see .env.example)."
            )
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(settings.anthropic_max_retries),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        reraise=True,
    )
    def complete(self, system: str, prompt: str, max_tokens: int | None = None) -> str:
        """One text completion. Returns concatenated text blocks.

        Raises TruncatedResponseError when the model stopped because it hit
        `max_tokens` rather than finishing. A length cutoff is NOT a shorter
        answer — it is an answer with the end missing, and callers that write
        the result somewhere durable will persist corrupted data.

        This is not hypothetical. The verification fixer asked for "the complete
        revised document" with max_tokens=8000 against a ~8,234-token document;
        7 of 8 fixer calls in the 2026-08-19 run returned exactly
        out_tokens=8000, and the loop wrote each truncated result straight over
        strategy_document. The document still ends mid-sentence at
        "**Pricing range:** $3,000-". Nothing errored, because this method
        returned the truncated text exactly like a complete answer.
        """
        limit = max_tokens or settings.anthropic_max_tokens
        request = dict(
            model=settings.anthropic_model,
            max_tokens=limit,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if limit > _NON_STREAMING_MAX_TOKENS:
            # The SDK REFUSES a non-streaming request whose max_tokens implies a
            # generation that could exceed 10 minutes — it raises
            # ValueError("Streaming is required ...") locally, before sending.
            # Measured on this SDK version: 21,333 is accepted, 32,000 is not.
            # Streaming removes the restriction and is what the API docs
            # recommend for large outputs, so the fixer's ceiling is not
            # hostage to an undocumented client-side heuristic.
            with self._client.messages.stream(**request) as stream:
                resp = stream.get_final_message()
        else:
            resp = self._client.messages.create(**request)
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        stop_reason = getattr(resp, "stop_reason", None)
        out_tokens = getattr(resp.usage, "output_tokens", "?")
        # Feature Group 3: attribute the spend to the active campaign scope
        # (a no-op outside one). Before the truncation check -- a cut-off
        # answer was still paid for.
        from app.services import usage_meter  # noqa: PLC0415

        usage_meter.note("anthropic", settings.anthropic_model,
                         getattr(resp.usage, "input_tokens", 0) or 0,
                         out_tokens if isinstance(out_tokens, int) else 0)
        logger.info(
            "anthropic call ok model=%s in_tokens=%s out_tokens=%s stop_reason=%s",
            settings.anthropic_model,
            getattr(resp.usage, "input_tokens", "?"),
            out_tokens,
            stop_reason,
        )
        if stop_reason == "max_tokens":
            raise TruncatedResponseError(
                f"model hit the {limit}-token output ceiling "
                f"(stop_reason=max_tokens, out_tokens={out_tokens}); the "
                f"response is cut off and must not be treated as complete",
                limit=limit,
                partial_text=text,
            )
        return text

    def complete_json(self, system: str, prompt: str, max_tokens: int | None = None) -> dict:
        """Completion that must return a single JSON object.

        The system prompt should already demand JSON-only output; this
        method additionally strips markdown fences and grabs the outermost
        object as a safety net, then raises ValueError if parsing fails so
        callers can decide how to degrade.
        """
        raw = self.complete(system=system, prompt=prompt, max_tokens=max_tokens)
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"Model did not return valid JSON: {raw[:200]!r}")


_client: ClaudeClient | None = None


def get_client() -> ClaudeClient:
    """Lazy singleton. Tests monkeypatch THIS function to inject a fake."""
    global _client
    if _client is None:
        _client = ClaudeClient()
    return _client
