"""Output contracts (Phase 3 item 2).

Every complete_json call names the JSON it expects as a schema, a module-level
constant whose name ends in _SCHEMA. The gateway sends it as
output_config.format only to models that support structured outputs
(anthropic_client.STRUCTURED_OUTPUT_MODELS); on any other model the request
is unchanged and the call site's own parsing and guards stay the contract.

What is checked here, offline:
  * the gateway sends the schema to a supported model, and only then;
  * every schema is one the API accepts: a valid JSON Schema, every object
    closed with additionalProperties: false, required fields that exist, and
    none of the keywords the API rejects (numeric and length limits);
  * every complete_json call in the app passes a schema.

tests/test_ai_evals.py checks the other half: each good recorded answer in
the golden sets validates against the schema its call sent, so a schema that
would forbid an answer the app accepts fails here before it constrains a
real model.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from app.config import settings
from app.services import anthropic_client

APP = Path(__file__).resolve().parents[1] / "app"
PACKAGES = ("app.services", "app.verification", "app.pipeline")

# The API rejects these (Anthropic structured-outputs reference, 2026-10-21):
# numeric and string-length constraints and complex array constraints.
UNSUPPORTED = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
               "minLength", "maxLength", "minItems", "maxItems", "uniqueItems", "contains",
               "minProperties", "maxProperties", "patternProperties"}


# --- the gateway ----------------------------------------------------------------

class _Messages:
    def __init__(self):
        self.sent: list[dict] = []

    def create(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"label": "a"}')],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                               stop_reason="end_turn")


def _send(monkeypatch, model: str, schema: dict | None) -> dict:
    monkeypatch.setattr(settings, "anthropic_model", model)
    client = anthropic_client.ClaudeClient.__new__(anthropic_client.ClaudeClient)
    client._client = SimpleNamespace(messages=_Messages())
    client.complete_json(system="s", prompt="p", schema=schema)
    return client._client.messages.sent[0]


SCHEMA = {"type": "object", "properties": {"label": {"type": "string"}},
          "required": ["label"], "additionalProperties": False}


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5",
                                   "claude-haiku-4-5-20251001"])
def test_a_supported_model_gets_the_schema(monkeypatch, model):
    sent = _send(monkeypatch, model, SCHEMA)
    assert sent["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}


@pytest.mark.parametrize("model", ["claude-sonnet-4-6", "claude-sonnet-4-6-20260101", ""])
def test_an_unsupported_model_gets_the_same_request_as_before(monkeypatch, model):
    assert "output_config" not in _send(monkeypatch, model, SCHEMA)


def test_no_schema_no_output_config(monkeypatch):
    assert "output_config" not in _send(monkeypatch, "claude-sonnet-5-5", None)


# --- every schema the app defines ---------------------------------------------

def _schemas() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for package_name in PACKAGES:
        package = importlib.import_module(package_name)
        for info in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{package_name}.{info.name}")
            for name, value in vars(module).items():
                if name.endswith("_SCHEMA") and isinstance(value, dict):
                    found[f"{module.__name__}.{name}"] = value
    return found


def _problems(node, path: str) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        bad = UNSUPPORTED & node.keys()
        if bad:
            out.append(f"{path}: unsupported {sorted(bad)}")
        if node.get("type") == "object" or "properties" in node:
            if node.get("additionalProperties") is not False:
                out.append(f"{path}: object without additionalProperties: false")
            missing = set(node.get("required") or []) - set(node.get("properties") or {})
            if missing:
                out.append(f"{path}: required but not a property {sorted(missing)}")
        for key, child in node.items():
            out += _problems(child, f"{path}.{key}")
    elif isinstance(node, list):
        for i, child in enumerate(node):
            out += _problems(child, f"{path}[{i}]")
    return out


SCHEMAS = _schemas()


@pytest.mark.parametrize("name", sorted(SCHEMAS) or ["(none yet)"])
def test_every_schema_is_one_the_api_accepts(name):
    if name == "(none yet)":
        pytest.skip("no *_SCHEMA constant defined yet")
    schema = SCHEMAS[name]
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema.get("type") == "object", "the top level must be an object (complete_json)"
    assert _problems(schema, name) == []


# --- every call passes one ------------------------------------------------------

def _json_calls_without_a_schema() -> list[str]:
    out = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "complete_json"
                    and not any(k.arg == "schema" for k in node.keywords)):
                out.append(f"{path.relative_to(APP.parent)}:{node.lineno}")
    return out


@pytest.mark.xfail(strict=True, reason="Phase 3 item 2 in progress: call sites get their "
                   "schemas one module group per commit; this marker comes off with the last")
def test_every_complete_json_call_passes_a_schema():
    assert _json_calls_without_a_schema() == []
