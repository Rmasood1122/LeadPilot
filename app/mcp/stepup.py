"""Scope step-up for write tools (MCP authorization, "scope challenge").

The SDK checks one set of required scopes for the whole endpoint
(`leadpilot:read`). A write tool also needs `leadpilot:write`, and a client
holding a read-only token must be told so in the way it can act on: HTTP 403
with `WWW-Authenticate: Bearer error="insufficient_scope",
scope="<scopes needed>", resource_metadata="..."`, which makes Claude
re-authorize with the wider scope. A tool-level error would only be read by
the model.

So this ASGI wrapper sits in front of the SDK app, reads the JSON-RPC body
of a POST, and when it is a `tools/call` of a write tool whose bearer token
(signature, audience and expiry verified) lacks `leadpilot:write`, answers
the challenge. Everything else -- including a token it cannot verify -- is
passed through unchanged with the body replayed, and the SDK's own bearer
middleware makes the real authentication decision. The tool itself checks
the scope again (app/mcp/context.tool_call), so this is the protocol answer,
not the only gate.
"""

from __future__ import annotations

import json

from mcp.server.auth.routes import build_resource_metadata_url
from pydantic import AnyHttpUrl
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.mcp import scopes
from app.services import auth as auth_svc

# A JSON-RPC request to /mcp is small; anything larger is not a tool call
# this wrapper needs to look at, and is left to the SDK's own body limit.
MAX_INSPECT_BYTES = 256 * 1024


def _bearer(scope: Scope) -> str | None:
    for name, value in scope.get("headers") or []:
        if name == b"authorization":
            text = value.decode("latin-1")
            if text.startswith("Bearer "):
                return text.removeprefix("Bearer ").strip()
    return None


def _called_tools(body: bytes) -> set[str]:
    try:
        payload = json.loads(body)
    except ValueError:
        return set()
    messages = payload if isinstance(payload, list) else [payload]
    names = set()
    for message in messages:
        if isinstance(message, dict) and message.get("method") == "tools/call":
            params = message.get("params")
            if isinstance(params, dict) and isinstance(params.get("name"), str):
                names.add(params["name"])
    return names


def _granted(token: str | None) -> set[str] | None:
    """The scopes of a verifiable connector token; None if unverifiable."""
    if not token:
        return None
    try:
        claims = auth_svc.decode_mcp_access_token(token, audience=settings.mcp_resource)
    except auth_svc.TokenRejected:
        return None
    return set(str(claims.get("scope") or "").split())


class ScopeChallenge:
    def __init__(self, app: ASGIApp, write_tools: frozenset[str]):
        self.app = app
        self.write_tools = write_tools

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        size = 0
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                # Client went away: nothing to answer.
                return
            chunk = message.get("body", b"")
            chunks.append(chunk)
            size += len(chunk)
            more = message.get("more_body", False)
            if size > MAX_INSPECT_BYTES:
                break
        body = b"".join(chunks)

        if not more and self.write_tools & _called_tools(body):
            granted = _granted(_bearer(scope))
            if granted is not None and scopes.WRITE not in granted:
                await self._challenge(send)
                return

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": more}
            return await receive()

        await self.app(scope, replay, send)

    async def _challenge(self, send: Send) -> None:
        metadata_url = build_resource_metadata_url(AnyHttpUrl(settings.mcp_resource))
        needed = f"{scopes.READ} {scopes.WRITE}"
        header = (f'Bearer error="insufficient_scope", scope="{needed}", '
                  f'resource_metadata="{metadata_url}", '
                  f'error_description="this tool needs the {scopes.WRITE} scope"')
        body = json.dumps({"error": "insufficient_scope",
                           "error_description": f"this tool needs the {scopes.WRITE} scope"}
                          ).encode()
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json"),
                                (b"www-authenticate", header.encode()),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
