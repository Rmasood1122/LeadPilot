"""Product defect #16: GET /integrations/gmail/callback answered raw JSON (or a
JSON error) in the user's browser tab, while the Slack, HubSpot and Salesforce
callbacks redirect back to /settings?tab=integrations&<provider>=connected|error,
where the settings page shows a toast. Gmail now does the same. Tokens are
never put in the redirect.
"""

from urllib.parse import parse_qs, urlparse

from app.integrations import gmail
from app.integrations.gmail import make_state


class _FakeOAuth:
    def __init__(self, tokens=None, fail=False):
        self.tokens = tokens or {"access_token": "at-secret", "refresh_token": "rt-secret",
                                 "expires_in": 3600, "scope": "send read"}
        self.fail = fail

    def exchange_code(self, code):
        if self.fail:
            raise RuntimeError("google said no")
        return self.tokens

    def fetch_profile_email(self, access_token):
        return "me@founder.co"


def _query(resp):
    assert resp.status_code in (302, 303), resp.text
    url = urlparse(resp.headers["location"])
    assert url.path == "/settings"
    return {k: v[0] for k, v in parse_qs(url.query).items()}


def test_success_redirects_to_settings(client, test_user, monkeypatch):
    monkeypatch.setattr(gmail, "get_oauth", lambda: _FakeOAuth())
    monkeypatch.setattr("app.api.integrations.get_oauth", lambda: _FakeOAuth())
    resp = client.get("/integrations/gmail/callback",
                      params={"code": "c", "state": make_state(test_user.id)},
                      follow_redirects=False)
    q = _query(resp)
    assert q == {"tab": "integrations", "gmail": "connected"}
    assert "secret" not in resp.headers["location"]
    assert client.get("/integrations/gmail/status").json()["connected"] is True


def test_google_error_redirects_with_reason(client):
    resp = client.get("/integrations/gmail/callback", params={"error": "access_denied"},
                      follow_redirects=False)
    q = _query(resp)
    assert q["gmail"] == "error" and "access_denied" in q["reason"]


def test_tampered_state_redirects_with_error(client):
    resp = client.get("/integrations/gmail/callback",
                      params={"code": "c", "state": "forged"}, follow_redirects=False)
    assert _query(resp)["gmail"] == "error"


def test_failed_exchange_redirects_with_error(client, test_user, monkeypatch):
    monkeypatch.setattr("app.api.integrations.get_oauth", lambda: _FakeOAuth(fail=True))
    resp = client.get("/integrations/gmail/callback",
                      params={"code": "c", "state": make_state(test_user.id)},
                      follow_redirects=False)
    assert _query(resp)["gmail"] == "error"


def test_no_refresh_token_redirects_with_error(client, test_user, monkeypatch):
    oauth = _FakeOAuth(tokens={"access_token": "at", "expires_in": 3600})
    monkeypatch.setattr("app.api.integrations.get_oauth", lambda: oauth)
    monkeypatch.setattr(gmail, "get_oauth", lambda: oauth)
    resp = client.get("/integrations/gmail/callback",
                      params={"code": "c", "state": make_state(test_user.id)},
                      follow_redirects=False)
    q = _query(resp)
    assert q["gmail"] == "error" and "refresh" in q["reason"].lower()


def test_any_storage_failure_redirects_with_error(client, test_user, monkeypatch):
    """Review L6: every store_tokens failure (not only a missing refresh
    token) lands on Settings with gmail=error, never a 500 page."""
    monkeypatch.setattr("app.api.integrations.get_oauth", lambda: _FakeOAuth())

    def _explode(*a, **k):
        raise RuntimeError("encryption key mismatch")

    monkeypatch.setattr("app.api.integrations.store_tokens", _explode)
    resp = client.get("/integrations/gmail/callback",
                      params={"code": "c", "state": make_state(test_user.id)},
                      follow_redirects=False)
    q = _query(resp)
    assert q["gmail"] == "error"
    assert "encryption" not in q["reason"]  # internal detail stays in the log
