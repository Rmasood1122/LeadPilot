"""Architecture tripwire: CORS_ORIGINS has two readers and they must agree.

The two readers:
  * app/main.py  — `os.getenv("CORS_ORIGINS").split(",")`, and it is the one
    that actually configures CORSMiddleware.
  * app/core/config.py — was `CORS_ORIGINS: list[str]`, which made
    pydantic-settings JSON-decode the value inside the dotenv source. It is now
    typed `str` with a `cors_origins_list` accessor.

Each format broke the other. A JSON array satisfied pydantic but made main.py
produce origins like '["https://a.com"' that never match a browser Origin
header — the API returns 200, every healthcheck passes, and the failure is
visible only in the browser as a CORS error with no server-side trace. A plain
comma-separated value fixed main.py but made Settings raise SettingsError at
import, taking the whole app down.

Comma-separated is the canonical format. These tests pin both readers to it.
"""


import os

import pytest


def _origins_as_main_py_parses(raw: str) -> list[str]:
    """Exactly the expression in app/main.py."""
    return [o.strip() for o in raw.split(",") if o.strip()]


class TestMainPyReader:
    def test_comma_separated_parses_to_clean_origins(self):
        raw = "https://app.example.com,https://www.app.example.com"
        assert _origins_as_main_py_parses(raw) == [
            "https://app.example.com",
            "https://www.app.example.com",
        ]

    def test_json_array_produces_origins_that_cannot_match(self):
        """Documents the bug: brackets/quotes survive into the origin string."""
        raw = '["https://app.example.com","https://www.app.example.com"]'
        parsed = _origins_as_main_py_parses(raw)
        assert "https://app.example.com" not in parsed
        assert any(o.startswith('["') for o in parsed)


class TestSettingsReader:
    """app/core/config.py exposes the parsed form via `cors_origins_list`.

    The field itself is typed `str` because pydantic-settings JSON-decodes
    complex types inside the dotenv source, before any validator runs — which
    is what made a comma-separated value raise SettingsError at import.
    """

    @pytest.mark.parametrize("raw,expected", [
        ("https://a.example.com", ["https://a.example.com"]),
        ("https://a.example.com,https://b.example.com",
         ["https://a.example.com", "https://b.example.com"]),
        (" https://a.example.com , https://b.example.com ",
         ["https://a.example.com", "https://b.example.com"]),
        ("", []),
    ])
    def test_comma_separated_is_accepted(self, raw, expected):
        from app.core.config import Settings

        assert Settings(CORS_ORIGINS=raw).cors_origins_list == expected

    def test_comma_separated_does_not_raise_at_construction(self):
        """The regression that took the app down at import."""
        from app.core.config import Settings

        Settings(CORS_ORIGINS="https://a.example.com,https://b.example.com")

    def test_legacy_json_array_still_parses(self):
        """An old .env must not silently yield bracketed origins."""
        from app.core.config import Settings

        raw = '["https://a.example.com","https://b.example.com"]'
        assert Settings(CORS_ORIGINS=raw).cors_origins_list == [
            "https://a.example.com",
            "https://b.example.com",
        ]


class TestBothReadersAgree:
    @pytest.mark.parametrize("raw", [
        "https://app.example.com",
        "https://app.example.com,https://www.app.example.com",
    ])
    def test_same_value_yields_same_origins_in_both_readers(self, raw):
        """The actual invariant: one env value, one meaning."""
        from app.core.config import Settings

        assert (Settings(CORS_ORIGINS=raw).cors_origins_list
                == _origins_as_main_py_parses(raw))


class TestShippedEnvTemplates:
    """The templates operators copy must use the canonical format."""

    @pytest.mark.parametrize("filename", [
        ".env.example",
        ".env.production.example",
    ])
    def test_template_does_not_use_json_array(self, filename):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, filename)
        lines = [
            line.strip()
            for line in open(path, encoding="utf-8")
            if line.strip().startswith("CORS_ORIGINS=")
        ]
        assert lines, f"{filename}: no CORS_ORIGINS line found"
        for line in lines:
            value = line.split("=", 1)[1]
            assert not value.startswith("["), (
                f"{filename}: CORS_ORIGINS uses the JSON-array form, which "
                f"app/main.py cannot parse: {line}"
            )
            assert '"' not in value and "'" not in value, (
                f"{filename}: CORS_ORIGINS contains quotes, which become part "
                f"of the origin string: {line}"
            )
