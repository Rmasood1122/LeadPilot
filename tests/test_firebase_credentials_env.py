"""F-OPS-04 — one secret, two names.

app/core/config.py declares FIREBASE_CREDENTIALS_JSON (the service-account JSON
inline). app/services/notifications.py read FIREBASE_CREDENTIALS_PATH (a file on
disk). An operator who set the documented variable got a RuntimeError at the
first push, and the inline form is the one actually configured in the
deployments -- a hosted container has nowhere to put the file.

Both names are now accepted, JSON preferred. These tests drive _get_firebase_app
with firebase_admin stubbed, so nothing here contacts Google or needs the real
SDK installed.
"""

from __future__ import annotations

import sys
import types

import pytest

from app.services import notifications

SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": "leadpilot-test",
    "private_key_id": "k1",
    "client_email": "svc@leadpilot-test.iam.gserviceaccount.com",
}


@pytest.fixture()
def firebase(monkeypatch):
    """A stub firebase_admin that records how Certificate() was called."""
    seen: dict = {}

    cred_mod = types.ModuleType("firebase_admin.credentials")

    def Certificate(arg):  # noqa: N802 - mirrors the SDK's name
        seen["certificate_arg"] = arg
        return ("cred", arg)

    cred_mod.Certificate = Certificate

    admin = types.ModuleType("firebase_admin")
    admin.credentials = cred_mod

    def initialize_app(cred):
        seen["initialised_with"] = cred
        return "app-handle"

    admin.initialize_app = initialize_app

    monkeypatch.setitem(sys.modules, "firebase_admin", admin)
    monkeypatch.setitem(sys.modules, "firebase_admin.credentials", cred_mod)
    # the singleton must not leak between tests
    monkeypatch.setattr(notifications, "_firebase_app", None, raising=False)
    monkeypatch.delenv("FIREBASE_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)
    return seen


def test_inline_json_is_accepted(firebase, monkeypatch) -> None:
    """The documented variable, and the one the deployments actually set."""
    import json

    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", json.dumps(SERVICE_ACCOUNT))

    assert notifications._get_firebase_app() == "app-handle"
    assert firebase["certificate_arg"] == SERVICE_ACCOUNT


def test_path_is_still_accepted(firebase, monkeypatch) -> None:
    """The name the code used before. Removing it would break any deployment on it."""
    monkeypatch.setenv("FIREBASE_CREDENTIALS_PATH", "/etc/secrets/fb.json")

    assert notifications._get_firebase_app() == "app-handle"
    assert firebase["certificate_arg"] == "/etc/secrets/fb.json"


def test_json_wins_when_both_are_set(firebase, monkeypatch) -> None:
    """Inline needs no filesystem, so it is the safer of the two to prefer."""
    import json

    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", json.dumps(SERVICE_ACCOUNT))
    monkeypatch.setenv("FIREBASE_CREDENTIALS_PATH", "/etc/secrets/fb.json")

    notifications._get_firebase_app()

    assert firebase["certificate_arg"] == SERVICE_ACCOUNT


def test_the_config_default_of_empty_object_counts_as_unset(firebase, monkeypatch) -> None:
    """config.py defaults FIREBASE_CREDENTIALS_JSON to "{}".

    Treating that as a credential would hand Certificate() an empty dict and
    fail somewhere deep in the SDK instead of saying what is missing.
    """
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", "{}")

    with pytest.raises(RuntimeError) as exc:
        notifications._get_firebase_app()

    assert "FIREBASE_CREDENTIALS_JSON" in str(exc.value)
    assert "FIREBASE_CREDENTIALS_PATH" in str(exc.value)


def test_neither_set_names_both_variables(firebase) -> None:
    with pytest.raises(RuntimeError) as exc:
        notifications._get_firebase_app()

    message = str(exc.value)
    assert "FIREBASE_CREDENTIALS_JSON" in message
    assert "FIREBASE_CREDENTIALS_PATH" in message


def test_malformed_json_says_so_instead_of_failing_deep_in_the_sdk(
        firebase, monkeypatch) -> None:
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", "/etc/secrets/fb.json")

    with pytest.raises(RuntimeError) as exc:
        notifications._get_firebase_app()

    assert "not valid JSON" in str(exc.value)
