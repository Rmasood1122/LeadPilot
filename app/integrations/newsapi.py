"""NewsAPI — recent news about ONE company (Feature Group 2's outreach hook).

The company-name problem, and what is done about it: "Apex", "Summit" and
"Acme" are in thousands of headlines that are not about the lead's company.
An outreach email that congratulates someone on another company's funding
round is worse than no hook. So:

  * the query is the exact phrase, quoted;
  * an article is kept only when the company name appears in its TITLE or
    DESCRIPTION, not merely somewhere in a body we never see;
  * only the last 30 days count.

It still cannot rule out a same-name company, which is why the prompt tells
the model to reference the news only if it plausibly concerns the lead.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx

NEWSAPI_URL = "https://newsapi.org/v2/everything"
WINDOW_DAYS = 30


class NewsUnavailable(Exception):
    pass


def _http() -> httpx.Client:
    """Factory tests monkeypatch."""
    return httpx.Client(timeout=15.0)


def mentions(company: str, *texts: str | None) -> bool:
    name = re.escape(company.strip())
    pattern = re.compile(rf"(?<![A-Za-z0-9]){name}(?![A-Za-z0-9])", re.I)
    return any(pattern.search(t or "") for t in texts)


def fetch_company_news(api_key: str, company: str,
                       now: datetime | None = None, limit: int = 3) -> list[dict]:
    """Up to `limit` articles from the last 30 days that name the company."""
    now = now or datetime.now(timezone.utc)
    company = (company or "").strip()
    if len(company) < 2:
        return []
    params = {
        "q": f'"{company}"',
        "from": (now - timedelta(days=WINDOW_DAYS)).date().isoformat(),
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 20,
    }
    with _http() as client:
        resp = client.get(NEWSAPI_URL, params=params, headers={"X-Api-Key": api_key})
    if resp.status_code >= 400:
        raise NewsUnavailable(f"newsapi HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json() or {}
    if data.get("status") == "error":
        raise NewsUnavailable(f"newsapi: {data.get('message')}")

    out = []
    cutoff = now - timedelta(days=WINDOW_DAYS)
    for article in data.get("articles") or []:
        title, description = article.get("title"), article.get("description")
        if not title or not mentions(company, title, description):
            continue
        published = article.get("publishedAt")
        try:
            when = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if when < cutoff:
            continue
        out.append({
            "headline": str(title)[:300],
            "summary": str(description or "")[:600],
            "url": article.get("url"),
            "source": (article.get("source") or {}).get("name"),
            "published_at": when.isoformat(),
        })
        if len(out) >= limit:
            break
    return out
