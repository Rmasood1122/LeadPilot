"""Which privacy/anti-spam regime a lead falls under.

One question, asked in several places: open tracking (Feature Group 3 -- a
tracking pixel needs consent under the EU ePrivacy rules and the UK's PECR),
and the per-send compliance audit (Feature Group 9 -- CAN-SPAM, GDPR, CASL,
PDPA). Answering it once, here, is what keeps those two from disagreeing
about the same person.

Evidence, strongest first:
  1. a country on the lead's enrichment record (Apollo's person/organization
     country, or a top-level `country`);
  2. the lead's IANA timezone (enrichment_json.timezone), which the send
     window already uses.

Returns None when there is no evidence. Callers decide what unknown means --
open tracking treats it as allowed (the product's markets are US-first), the
compliance audit records it as "unknown" rather than guessing.
"""

from __future__ import annotations

from app.db.models import Lead

# EU member states + the EEA three (Iceland, Liechtenstein, Norway): the
# GDPR / ePrivacy area.
_EEA = {
    "AT": "austria", "BE": "belgium", "BG": "bulgaria", "HR": "croatia",
    "CY": "cyprus", "CZ": "czech republic", "DK": "denmark", "EE": "estonia",
    "FI": "finland", "FR": "france", "DE": "germany", "GR": "greece",
    "HU": "hungary", "IE": "ireland", "IT": "italy", "LV": "latvia",
    "LT": "lithuania", "LU": "luxembourg", "MT": "malta", "NL": "netherlands",
    "PL": "poland", "PT": "portugal", "RO": "romania", "SK": "slovakia",
    "SI": "slovenia", "ES": "spain", "SE": "sweden",
    "IS": "iceland", "LI": "liechtenstein", "NO": "norway",
}
_NAMES = {
    "us": {"us", "usa", "united states", "united states of america", "u.s.", "u.s.a."},
    "uk": {"gb", "uk", "united kingdom", "great britain", "england", "scotland",
           "wales", "northern ireland"},
    "ca": {"ca", "canada"},
    "sg": {"sg", "singapore"},
    "au": {"au", "australia"},
    "nz": {"nz", "new zealand"},
}
_EEA_NAMES = {code.lower() for code in _EEA} | set(_EEA.values()) | {"czechia", "holland"}

_US_TZ = {"America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
          "America/Phoenix", "America/Anchorage", "America/Detroit", "America/Boise",
          "America/Indiana/Indianapolis", "Pacific/Honolulu"}
_CA_TZ = {"America/Toronto", "America/Vancouver", "America/Edmonton", "America/Winnipeg",
          "America/Halifax", "America/St_Johns", "America/Regina", "America/Montreal"}

REGIMES = {
    "us": "CAN-SPAM",
    "ca": "CASL",
    "eu": "GDPR",
    "uk": "UK GDPR / PECR",
    "sg": "PDPA",
    "au": "Spam Act 2003",
    "nz": "UEMA 2007",
}


def _dicts(enrichment: dict) -> list[dict]:
    out = [enrichment]
    for key in ("person", "raw"):
        value = enrichment.get(key)
        if isinstance(value, dict):
            out.append(value)
            nested = value.get("person")
            if isinstance(nested, dict):
                out.append(nested)
    for d in list(out):
        org = d.get("organization")
        if isinstance(org, dict):
            out.append(org)
    return out


def lead_country(lead: Lead) -> str | None:
    enrichment = lead.enrichment_json if isinstance(lead.enrichment_json, dict) else {}
    for d in _dicts(enrichment):
        for key in ("country", "country_code", "organization_country"):
            value = d.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def region_for_country(country: str | None) -> str | None:
    if not country:
        return None
    c = country.strip().lower()
    if c in _EEA_NAMES:
        return "eu"
    for region, names in _NAMES.items():
        if c in names:
            return region
    return "other"


def region_for_timezone(tz: str | None) -> str | None:
    if not tz:
        return None
    if tz in ("Europe/London", "Europe/Belfast"):
        return "uk"
    if tz in _US_TZ:
        return "us"
    if tz in _CA_TZ:
        return "ca"
    if tz == "Asia/Singapore":
        return "sg"
    if tz.startswith("Australia/"):
        return "au"
    if tz in ("Pacific/Auckland", "Pacific/Chatham"):
        return "nz"
    if tz.startswith("Europe/"):
        # Approximate: also matches Switzerland, Serbia, Russia... Used only
        # when no country is recorded, and erring toward the stricter regime.
        return "eu"
    return None


def lead_region(lead: Lead) -> str | None:
    """us | ca | eu | uk | sg | au | nz | other, or None when unknown."""
    region = region_for_country(lead_country(lead))
    if region is not None:
        return region
    enrichment = lead.enrichment_json if isinstance(lead.enrichment_json, dict) else {}
    tz = enrichment.get("timezone")
    return region_for_timezone(tz if isinstance(tz, str) else None)


def open_tracking_allowed(lead: Lead) -> bool:
    """False for EU/EEA/UK leads: a tracking pixel is 'storing or accessing
    information on terminal equipment' and needs prior consent there."""
    return lead_region(lead) not in ("eu", "uk")
