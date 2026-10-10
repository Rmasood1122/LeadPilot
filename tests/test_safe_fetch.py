"""F06: the one-page fetcher Quickstart points at a user-supplied URL.

A URL from a user is an instruction to make a request from inside our network
-- the SSRF surface. These pin every refusal, the per-hop re-resolution, the
manual redirect handling, and the size/type limits. Offline: DNS is
monkeypatched (`_resolve`) and HTTP goes through httpx.MockTransport.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import safe_fetch
from app.services.safe_fetch import FetchFailed, UnsafeURL


# --------------------------------------------------------------------------
# validate_url: shape only, no network
# --------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("example.com", "https://example.com/"),
    ("http://example.com/about", "https://example.com/about"),
    ("https://www.Example.com/a?b=1", "https://www.example.com/a?b=1"),
    ("https://example.com:443/", "https://example.com/"),
    ("  https://example.com  ", "https://example.com/"),
    ("https://example.com/#top", "https://example.com/"),
])
def test_valid_urls_are_normalised_to_https(raw, expected):
    assert safe_fetch.validate_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "",
    "ftp://example.com/",
    "file:///etc/passwd",
    "gopher://example.com/",
    "https://user:secret@example.com/",
    "https://example.com@10.0.0.1/",
    "https://example.com:8080/",
    "https://example.com:6379/",
    "https://localhost/",
    "https://api.localhost/",
    "https://db.internal/",
    "https://printer.local/",
    "https://intranet/",
    "https://127.0.0.1/",
    "https://10.0.0.5/",
    "https://192.168.1.1/",
    "https://172.16.0.1/",
    "https://169.254.169.254/latest/meta-data/",
    "https://100.64.0.1/",
    "https://0.0.0.0/",
    "https://[::1]/",
    "https://[fe80::1]/",
    "https://[::ffff:127.0.0.1]/",
    "https://2130706433/",            # 127.0.0.1 as a decimal integer
    "https://exa mple.com/",
    "https://example.com/\x00",
    "https://" + "a" * 2100 + ".com/",
])
def test_unsafe_or_malformed_urls_are_refused(raw):
    with pytest.raises(UnsafeURL):
        safe_fetch.validate_url(raw)


# --------------------------------------------------------------------------
# fetch_page
# --------------------------------------------------------------------------


@pytest.fixture()
def dns(monkeypatch):
    table = {"example.com": ["93.184.216.34"], "www.example.com": ["93.184.216.34"]}
    calls = []

    def _resolve(host):
        calls.append(host)
        if host not in table:
            raise OSError("NXDOMAIN")
        return table[host]

    monkeypatch.setattr(safe_fetch, "_resolve", _resolve)
    return table, calls


@pytest.fixture()
def web(monkeypatch):
    routes: dict[str, httpx.Response] = {}
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        response = routes.get(str(request.url))
        return response if response is not None else httpx.Response(404)

    monkeypatch.setattr(safe_fetch, "_http", lambda: httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False))
    return routes, seen


HTML = """<html><head><title>Acme Fire  Inspections</title>
<meta name="description" content="NFPA inspections for Texas facilities.">
<style>body{color:red}</style><script>var secret='do not read';</script></head>
<body><nav>Home</nav><h1>We keep sprinklers compliant</h1>
<p>Serving property managers in Austin &amp; Dallas.</p><noscript>enable js</noscript>
</body></html>"""


def _html(body=HTML, **kw):
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                          content=body.encode(), **kw)


def test_reads_visible_text_and_title(dns, web):
    routes, _ = web
    routes["https://example.com/"] = _html()
    page = safe_fetch.fetch_page("example.com")
    assert page.final_url == "https://example.com/"
    assert page.title == "Acme Fire Inspections"
    assert "We keep sprinklers compliant" in page.text
    assert "Austin & Dallas" in page.text
    assert "NFPA inspections for Texas facilities." in page.text
    assert "secret" not in page.text and "color:red" not in page.text
    assert "enable js" not in page.text
    assert page.meta()["bytes"] == len(HTML.encode())


def test_a_host_resolving_to_a_private_address_is_refused(dns, web):
    table, _ = dns
    table["evil.example.org"] = ["10.1.2.3"]
    routes, seen = web
    with pytest.raises(UnsafeURL):
        safe_fetch.fetch_page("https://evil.example.org/")
    assert seen == [], "no request may be made to a private destination"


def test_any_private_address_in_the_answer_is_enough_to_refuse(dns, web):
    table, _ = dns
    table["mixed.example.org"] = ["93.184.216.34", "127.0.0.1"]
    with pytest.raises(UnsafeURL):
        safe_fetch.fetch_page("https://mixed.example.org/")


def test_a_redirect_into_the_metadata_service_is_refused(dns, web):
    routes, seen = web
    routes["https://example.com/"] = httpx.Response(
        302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
    with pytest.raises(UnsafeURL):
        safe_fetch.fetch_page("https://example.com/")
    assert seen == ["https://example.com/"]


def test_a_redirect_to_a_host_resolving_privately_is_refused(dns, web):
    table, calls = dns
    table["internal.example.net"] = ["192.168.0.10"]
    routes, seen = web
    routes["https://example.com/"] = httpx.Response(
        301, headers={"location": "https://internal.example.net/"})
    with pytest.raises(UnsafeURL):
        safe_fetch.fetch_page("https://example.com/")
    assert "internal.example.net" in calls, "every hop must be re-resolved"
    assert seen == ["https://example.com/"]


def test_safe_redirects_are_followed_and_revalidated(dns, web):
    routes, seen = web
    routes["https://example.com/"] = httpx.Response(
        301, headers={"location": "http://www.example.com/home"})
    routes["https://www.example.com/home"] = _html()
    page = safe_fetch.fetch_page("https://example.com/")
    # http:// in the Location header is upgraded, never followed in clear text
    assert seen == ["https://example.com/", "https://www.example.com/home"]
    assert page.final_url == "https://www.example.com/home"


def test_redirect_loops_are_bounded(dns, web):
    routes, seen = web
    routes["https://example.com/"] = httpx.Response(302, headers={"location": "/a"})
    routes["https://example.com/a"] = httpx.Response(302, headers={"location": "/"})
    with pytest.raises(FetchFailed):
        safe_fetch.fetch_page("https://example.com/")
    assert len(seen) == safe_fetch.MAX_REDIRECTS + 1


def test_the_body_is_capped(dns, web):
    routes, _ = web
    big = "<html><body><p>" + ("word " * 200_000) + "</p></body></html>"
    routes["https://example.com/"] = _html(big)
    page = safe_fetch.fetch_page("https://example.com/", max_bytes=10_000)
    assert page.truncated is True
    assert page.bytes_read == 10_000
    assert len(page.text) <= safe_fetch.MAX_TEXT_CHARS


def test_non_page_content_is_refused(dns, web):
    routes, _ = web
    routes["https://example.com/"] = httpx.Response(
        200, headers={"content-type": "application/octet-stream"}, content=b"\x00\x01")
    with pytest.raises(FetchFailed):
        safe_fetch.fetch_page("https://example.com/")


def test_http_errors_and_dns_failures_are_fetch_failures(dns, web):
    routes, _ = web
    routes["https://example.com/"] = httpx.Response(503)
    with pytest.raises(FetchFailed):
        safe_fetch.fetch_page("https://example.com/")
    with pytest.raises(FetchFailed):
        safe_fetch.fetch_page("https://does-not-exist.example/")


def test_unsafe_url_is_a_value_error_so_the_api_answers_422():
    assert issubclass(UnsafeURL, ValueError)


def test_html_to_text_survives_broken_markup():
    title, text = safe_fetch.html_to_text("<html><title>T</title><body><p>a<div>b</p")
    assert title == "T"
    assert "a" in text and "b" in text
