"""The Connect Gmail button navigated to /settings/undefined/ because the
backend answers GET /integrations/gmail/auth-url with {"auth_url", "state"}
while the frontend destructured {url}. Pin both sides of that contract."""

import re
from pathlib import Path

from app.integrations import gmail as gmail_mod

ROOT = Path(__file__).resolve().parents[1]


class _FakeOAuth:
    def build_auth_url(self, state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"


def test_backend_returns_auth_url_key(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "google_client_id", "id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "secret")
    monkeypatch.setattr(gmail_mod, "get_oauth", lambda: _FakeOAuth())
    body = client.get("/integrations/gmail/auth-url").json()
    assert body["auth_url"].startswith("https://accounts.google.com/")
    assert "url" not in body


def test_missing_google_credentials_is_a_clear_503(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "google_client_id", "")
    r = client.get("/integrations/gmail/auth-url")
    assert r.status_code == 503
    assert "GOOGLE_CLIENT_ID" in r.json()["detail"]


def test_frontend_reads_the_same_key():
    api_ts = (ROOT / "frontend/src/lib/api/integrations.ts").read_text()
    page = (ROOT / "frontend/src/app/(app)/settings/page.tsx").read_text()
    assert re.search(r"gmailAuthUrl\(\): Promise<\{ auth_url: string \}>", api_ts)
    assert "const { auth_url } = await gmailAuthUrl()" in page
    assert "const { url } = await gmailAuthUrl()" not in page
