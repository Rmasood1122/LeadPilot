"""Self-tests for the integration harness's Anthropic guard (conftest.py).

The root conftest refuses every get_client() call. This directory narrows
that refusal so the real ClaudeClient can run against the respx Anthropic
mock. These tests pin the narrowing: no route -> refused, unrouted request ->
error inside the process, never a request to api.anthropic.com.
"""
from __future__ import annotations

import pytest

from tests.integration.mocks import anthropic_mock


def test_refused_without_a_respx_router():
    from app.services import anthropic_client

    with pytest.raises(RuntimeError, match="real Anthropic call"):
        anthropic_client.get_client()


def test_refused_when_router_has_no_anthropic_route(mock_transports):
    from app.services import anthropic_client

    with pytest.raises(RuntimeError, match="real Anthropic call"):
        anthropic_client.get_client()


def test_every_module_binding_is_guarded(mock_transports):
    # engine binds get_client by name at import; a stale binding there is
    # what made the suite order-dependent.
    from app.pipeline import engine
    from app.services import anthropic_client

    assert engine.get_client is anthropic_client.get_client
    with pytest.raises(RuntimeError, match="real Anthropic call"):
        engine.get_client()


def test_routed_call_is_answered_by_the_mock(mock_transports):
    from app.services import anthropic_client

    anthropic_mock.register(mock_transports)
    client = anthropic_client.get_client()

    assert client is not anthropic_client._client   # singleton untouched
    route = next(r for r in mock_transports.routes
                 if "api.anthropic.com" in repr(r.pattern))
    client.complete("system", "Extract past client patterns", max_tokens=200)
    assert route.call_count == 1


def test_unrouted_anthropic_endpoint_never_leaves_the_process(mock_transports):
    import anthropic

    from app.services import anthropic_client

    anthropic_mock.register(mock_transports)
    sdk = anthropic_client.get_client()._client.with_options(max_retries=0)

    # /v1/models has no route: respx raises inside the transport, which the
    # SDK reports as a connection error. A real request would come back as an
    # HTTP status error (401 for the placeholder key) instead.
    with pytest.raises(anthropic.APIConnectionError):
        sdk.models.list()
