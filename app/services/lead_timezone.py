"""A lead's timezone, from the location it already carries.

Spec: docs/features/autopilot-launch.md section 3.4.

WHY. The send window (sequence_engine.next_window_slot / in_send_window) and
best-time scheduling run in the lead's local time, read from
`enrichment_json.timezone` -- which nothing ever wrote, so every lead fell back
to the deployment default (UTC). A Chicago prospect was emailed from 03:00
their time; "best time in the prospect's local time" meant UTC for everyone.

RESOLUTION (deterministic, no network, no model):
  1. the zone already recorded on the lead (`enrichment_json.timezone`);
  2. the lead's own location, person first, then their organization:
     a provider-reported IANA `time_zone`; else a single-zone country; else
     a state/province table for the United States, Canada, Australia and
     Brazil (each state's PRIMARY zone -- a state split between zones, e.g.
     Texas' El Paso corner, takes the zone most of its people live in).
     A multi-zone country without a state stays unresolved;
  3. FALLBACKS, never written onto the lead: the strategy's target region
     (its ICP locations: the zone most of them resolve to), then the account's
     timezone (its calendar availability), then the deployment default
     (`send_window_timezone`).

WRITTEN at enrichment (lead_tasks.enrich_leads_impl -> record()) as
`timezone` + `timezone_source`; resolved lazily on read for leads enriched
before this existed (no data migration, and a read never writes).

COMPLIANCE. compliance_region.lead_region() uses the lead's COUNTRY first and
the recorded `timezone` only when no country is known. record() writes only a
zone derived from the lead's own location (so it always agrees with the
country), and the fallbacks are never stored -- so an account in Dublin can
never make an unknown lead look like an EU lead, or a Texas ICP make it look
American. The send window itself now opens in the prospect's own business
hours (it used to be UTC's): sends move, they are not added or removed.
"""

from __future__ import annotations

import re
import time as _time
from collections import Counter
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SOURCE_RECORDED = "lead_recorded"
SOURCE_LOCATION = "lead_location"
SOURCE_STRATEGY = "strategy_region"
SOURCE_ACCOUNT = "account"
SOURCE_DEFAULT = "deployment_default"
SOURCES = (SOURCE_RECORDED, SOURCE_LOCATION, SOURCE_STRATEGY, SOURCE_ACCOUNT, SOURCE_DEFAULT)

_CACHE_KEY = "lead_timezone_cache"
_CACHE_SECONDS = 600

# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

#: Countries with one zone (or one zone for the mainland / nearly everyone).
_SINGLE_ZONE: dict[str, str] = {
    "united kingdom": "Europe/London", "uk": "Europe/London", "gb": "Europe/London",
    "great britain": "Europe/London", "england": "Europe/London",
    "scotland": "Europe/London", "wales": "Europe/London",
    "northern ireland": "Europe/London",
    "ireland": "Europe/Dublin", "ie": "Europe/Dublin",
    "germany": "Europe/Berlin", "de": "Europe/Berlin",
    "france": "Europe/Paris", "fr": "Europe/Paris",
    "netherlands": "Europe/Amsterdam", "nl": "Europe/Amsterdam", "holland": "Europe/Amsterdam",
    "belgium": "Europe/Brussels", "be": "Europe/Brussels",
    "luxembourg": "Europe/Luxembourg", "lu": "Europe/Luxembourg",
    "switzerland": "Europe/Zurich", "ch": "Europe/Zurich",
    "austria": "Europe/Vienna", "at": "Europe/Vienna",
    "italy": "Europe/Rome", "it": "Europe/Rome",
    "spain": "Europe/Madrid", "es": "Europe/Madrid",
    "portugal": "Europe/Lisbon", "pt": "Europe/Lisbon",
    "sweden": "Europe/Stockholm", "se": "Europe/Stockholm",
    "norway": "Europe/Oslo", "no": "Europe/Oslo",
    "denmark": "Europe/Copenhagen", "dk": "Europe/Copenhagen",
    "finland": "Europe/Helsinki", "fi": "Europe/Helsinki",
    "iceland": "Atlantic/Reykjavik", "is": "Atlantic/Reykjavik",
    "poland": "Europe/Warsaw", "pl": "Europe/Warsaw",
    "czech republic": "Europe/Prague", "czechia": "Europe/Prague", "cz": "Europe/Prague",
    "slovakia": "Europe/Bratislava", "sk": "Europe/Bratislava",
    "hungary": "Europe/Budapest", "hu": "Europe/Budapest",
    "romania": "Europe/Bucharest", "ro": "Europe/Bucharest",
    "bulgaria": "Europe/Sofia", "bg": "Europe/Sofia",
    "greece": "Europe/Athens", "gr": "Europe/Athens",
    "croatia": "Europe/Zagreb", "hr": "Europe/Zagreb",
    "slovenia": "Europe/Ljubljana", "si": "Europe/Ljubljana",
    "estonia": "Europe/Tallinn", "ee": "Europe/Tallinn",
    "latvia": "Europe/Riga", "lv": "Europe/Riga",
    "lithuania": "Europe/Vilnius", "lt": "Europe/Vilnius",
    "malta": "Europe/Malta", "mt": "Europe/Malta",
    "cyprus": "Asia/Nicosia", "cy": "Asia/Nicosia",
    "liechtenstein": "Europe/Vaduz", "li": "Europe/Vaduz",
    "ukraine": "Europe/Kyiv", "ua": "Europe/Kyiv",
    "turkey": "Europe/Istanbul", "türkiye": "Europe/Istanbul", "tr": "Europe/Istanbul",
    "israel": "Asia/Jerusalem", "il": "Asia/Jerusalem",
    "united arab emirates": "Asia/Dubai", "uae": "Asia/Dubai", "ae": "Asia/Dubai",
    "saudi arabia": "Asia/Riyadh", "sa": "Asia/Riyadh",
    "qatar": "Asia/Qatar", "qa": "Asia/Qatar",
    "pakistan": "Asia/Karachi", "pk": "Asia/Karachi",
    "india": "Asia/Kolkata", "in": "Asia/Kolkata",
    "bangladesh": "Asia/Dhaka", "bd": "Asia/Dhaka",
    "sri lanka": "Asia/Colombo", "lk": "Asia/Colombo",
    "singapore": "Asia/Singapore", "sg": "Asia/Singapore",
    "malaysia": "Asia/Kuala_Lumpur", "my": "Asia/Kuala_Lumpur",
    "thailand": "Asia/Bangkok", "th": "Asia/Bangkok",
    "vietnam": "Asia/Ho_Chi_Minh", "viet nam": "Asia/Ho_Chi_Minh", "vn": "Asia/Ho_Chi_Minh",
    "philippines": "Asia/Manila", "ph": "Asia/Manila",
    "hong kong": "Asia/Hong_Kong", "hk": "Asia/Hong_Kong",
    "taiwan": "Asia/Taipei", "tw": "Asia/Taipei",
    "china": "Asia/Shanghai", "cn": "Asia/Shanghai",
    "japan": "Asia/Tokyo", "jp": "Asia/Tokyo",
    "south korea": "Asia/Seoul", "korea": "Asia/Seoul", "republic of korea": "Asia/Seoul",
    "kr": "Asia/Seoul",
    "new zealand": "Pacific/Auckland", "nz": "Pacific/Auckland",
    "south africa": "Africa/Johannesburg", "za": "Africa/Johannesburg",
    "nigeria": "Africa/Lagos", "ng": "Africa/Lagos",
    "kenya": "Africa/Nairobi", "ke": "Africa/Nairobi",
    "egypt": "Africa/Cairo", "eg": "Africa/Cairo",
    "argentina": "America/Argentina/Buenos_Aires", "ar": "America/Argentina/Buenos_Aires",
    "colombia": "America/Bogota", "co": "America/Bogota",
    "peru": "America/Lima", "pe": "America/Lima",
    "chile": "America/Santiago", "cl": "America/Santiago",
}

_US_NAMES = {"united states", "united states of america", "usa", "us", "u.s.", "u.s.a."}
_CA_NAMES = {"canada", "ca"}
_AU_NAMES = {"australia", "au"}
_BR_NAMES = {"brazil", "brasil", "br"}

_E, _C, _M, _P = ("America/New_York", "America/Chicago", "America/Denver",
                  "America/Los_Angeles")
#: (code, name) -> primary zone.
_US_STATES: dict[tuple[str, str], str] = {
    ("al", "alabama"): _C, ("ak", "alaska"): "America/Anchorage",
    ("az", "arizona"): "America/Phoenix", ("ar", "arkansas"): _C, ("ca", "california"): _P,
    ("co", "colorado"): _M, ("ct", "connecticut"): _E, ("de", "delaware"): _E,
    ("dc", "district of columbia"): _E, ("fl", "florida"): _E, ("ga", "georgia"): _E,
    ("hi", "hawaii"): "Pacific/Honolulu", ("id", "idaho"): "America/Boise",
    ("il", "illinois"): _C, ("in", "indiana"): "America/Indiana/Indianapolis",
    ("ia", "iowa"): _C, ("ks", "kansas"): _C, ("ky", "kentucky"): _E,
    ("la", "louisiana"): _C, ("me", "maine"): _E, ("md", "maryland"): _E,
    ("ma", "massachusetts"): _E, ("mi", "michigan"): "America/Detroit",
    ("mn", "minnesota"): _C, ("ms", "mississippi"): _C, ("mo", "missouri"): _C,
    ("mt", "montana"): _M, ("ne", "nebraska"): _C, ("nv", "nevada"): _P,
    ("nh", "new hampshire"): _E, ("nj", "new jersey"): _E, ("nm", "new mexico"): _M,
    ("ny", "new york"): _E, ("nc", "north carolina"): _E, ("nd", "north dakota"): _C,
    ("oh", "ohio"): _E, ("ok", "oklahoma"): _C, ("or", "oregon"): _P,
    ("pa", "pennsylvania"): _E, ("ri", "rhode island"): _E, ("sc", "south carolina"): _E,
    ("sd", "south dakota"): _C, ("tn", "tennessee"): _C, ("tx", "texas"): _C,
    ("ut", "utah"): _M, ("vt", "vermont"): _E, ("va", "virginia"): _E,
    ("wa", "washington"): _P, ("wv", "west virginia"): _E, ("wi", "wisconsin"): _C,
    ("wy", "wyoming"): _M, ("pr", "puerto rico"): "America/Puerto_Rico",
}
_CA_PROVINCES: dict[tuple[str, str], str] = {
    ("ab", "alberta"): "America/Edmonton", ("bc", "british columbia"): "America/Vancouver",
    ("mb", "manitoba"): "America/Winnipeg", ("nb", "new brunswick"): "America/Moncton",
    ("nl", "newfoundland and labrador"): "America/St_Johns",
    ("ns", "nova scotia"): "America/Halifax", ("on", "ontario"): "America/Toronto",
    ("pe", "prince edward island"): "America/Halifax", ("qc", "quebec"): "America/Toronto",
    ("sk", "saskatchewan"): "America/Regina", ("nt", "northwest territories"):
    "America/Yellowknife", ("nu", "nunavut"): "America/Iqaluit",
    ("yt", "yukon"): "America/Whitehorse",
}
_AU_STATES: dict[tuple[str, str], str] = {
    ("nsw", "new south wales"): "Australia/Sydney", ("vic", "victoria"): "Australia/Melbourne",
    ("qld", "queensland"): "Australia/Brisbane", ("sa", "south australia"): "Australia/Adelaide",
    ("wa", "western australia"): "Australia/Perth", ("tas", "tasmania"): "Australia/Hobart",
    ("nt", "northern territory"): "Australia/Darwin",
    ("act", "australian capital territory"): "Australia/Sydney",
}
_SP = "America/Sao_Paulo"
_BR_STATES: dict[tuple[str, str], str] = {
    ("sp", "sao paulo"): _SP, ("rj", "rio de janeiro"): _SP, ("mg", "minas gerais"): _SP,
    ("es", "espirito santo"): _SP, ("pr", "parana"): _SP, ("sc", "santa catarina"): _SP,
    ("rs", "rio grande do sul"): _SP, ("go", "goias"): _SP, ("df", "distrito federal"): _SP,
    ("ba", "bahia"): "America/Bahia", ("ce", "ceara"): "America/Fortaleza",
    ("ma", "maranhao"): "America/Fortaleza", ("pi", "piaui"): "America/Fortaleza",
    ("rn", "rio grande do norte"): "America/Fortaleza", ("pb", "paraiba"): "America/Fortaleza",
    ("pe", "pernambuco"): "America/Recife", ("al", "alagoas"): "America/Maceio",
    ("se", "sergipe"): "America/Maceio", ("pa", "para"): "America/Belem",
    ("ap", "amapa"): "America/Belem", ("to", "tocantins"): "America/Araguaina",
    ("am", "amazonas"): "America/Manaus", ("mt", "mato grosso"): "America/Cuiaba",
    ("ms", "mato grosso do sul"): "America/Campo_Grande",
    ("ro", "rondonia"): "America/Porto_Velho", ("ac", "acre"): "America/Rio_Branco",
    ("rr", "roraima"): "America/Boa_Vista",
}


def _index(table: dict[tuple[str, str], str]) -> dict[str, str]:
    out = {}
    for (code, name), zone in table.items():
        out[code] = zone
        out[name] = zone
    return out


_STATE_TABLES: list[tuple[set[str], dict[str, str]]] = [
    (_US_NAMES, _index(_US_STATES)), (_CA_NAMES, _index(_CA_PROVINCES)),
    (_AU_NAMES, _index(_AU_STATES)), (_BR_NAMES, _index(_BR_STATES)),
]

_ACCENTS = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")


def _norm(value) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.strip().lower().translate(_ACCENTS))


def valid_zone(value) -> str | None:
    if not isinstance(value, str) or "/" not in value:
        return None
    try:
        ZoneInfo(value.strip())
        return value.strip()
    except (ZoneInfoNotFoundError, ValueError):
        return None


def zone_for(country, state=None) -> str | None:
    """IANA zone for a country (+ state/province); None when unresolved."""
    c = _norm(country)
    if not c:
        return None
    if c in _SINGLE_ZONE:
        return _SINGLE_ZONE[c]
    s = _norm(state)
    for names, table in _STATE_TABLES:
        if c in names:
            return table.get(s) if s else None
    return None


def zone_for_place(text: str) -> str | None:
    """'Texas, US' / 'London, UK' / 'Ontario, Canada' / 'Germany' (an ICP
    location string the research produced) -> zone, or None."""
    parts = [p.strip() for p in str(text or "").split(",") if p.strip()]
    if not parts:
        return None
    country = parts[-1]
    if len(parts) >= 2:
        zone = zone_for(country, parts[-2])
        if zone:
            return zone
    zone = zone_for(country)
    if zone:
        return zone
    # A bare US state name ("Texas") -- "georgia" is also a country, so not it.
    name = _norm(parts[0])
    if name != "georgia":
        for (_code, full), zone in _US_STATES.items():
            if name == full:
                return zone
    return None


# --------------------------------------------------------------------------
# From the lead's own data
# --------------------------------------------------------------------------


def _people(enrichment: dict) -> list[dict]:
    """Person dicts, strongest first: top level, the enrichment match
    response's person, the sourcing search row."""
    out = [enrichment]
    for value in (enrichment.get("enrichment"), enrichment.get("raw"), enrichment.get("person")):
        if isinstance(value, dict):
            nested = value.get("person")
            if isinstance(nested, dict):
                out.append(nested)
            out.append(value)
    return out


def _from_dict(d: dict) -> tuple[str, str] | None:
    for key in ("time_zone", "timezone"):
        zone = valid_zone(d.get(key))
        if zone:
            return zone, f"provider time_zone: {zone}"
    country = d.get("country") or d.get("country_code") or d.get("organization_country")
    state = d.get("state") or d.get("region") or d.get("province")
    if zone_for(country):
        return zone_for(country), f"location: {str(country).strip()}"
    zone = zone_for(country, state)
    if zone:
        return zone, f"location: {str(state).strip()}, {str(country).strip()}"
    return None


def zone_from_lead(lead) -> tuple[str, str] | None:
    """(zone, evidence) from the lead's OWN location, or None. Pure."""
    enrichment = getattr(lead, "enrichment_json", None)
    if not isinstance(enrichment, dict):
        return None
    people = _people(enrichment)
    for d in people:
        found = _from_dict(d)
        if found:
            return found
    for d in people:
        org = d.get("organization")
        if isinstance(org, dict):
            found = _from_dict(org)
            if found:
                return found[0], found[1].replace("location: ", "organization location: ", 1)
    return None


def record(lead) -> bool:
    """Write the lead's own zone into enrichment_json (timezone +
    timezone_source) when it resolves and none is recorded. Not committed.
    Never writes a fallback."""
    enrichment = lead.enrichment_json if isinstance(lead.enrichment_json, dict) else {}
    if valid_zone(enrichment.get("timezone")):
        return False
    found = zone_from_lead(lead)
    if found is None:
        return False
    lead.enrichment_json = {**enrichment, "timezone": found[0], "timezone_source": found[1]}
    return True


# --------------------------------------------------------------------------
# With fallbacks
# --------------------------------------------------------------------------


def clear_cache(session) -> None:
    session.info.pop(_CACHE_KEY, None)


def _session_of(lead):
    try:
        from sqlalchemy.orm import object_session  # noqa: PLC0415

        return object_session(lead)
    except Exception:  # noqa: BLE001 -- an unmapped stand-in
        return None


def strategy_zone(strategy) -> str | None:
    """The zone most of the strategy's ICP locations resolve to (ties: the
    first named), or None."""
    inputs = getattr(strategy, "pattern_inputs_json", None)
    icp = inputs.get("icp") if isinstance(inputs, dict) else None
    locations = icp.get("locations") if isinstance(icp, dict) else None
    zones = [z for z in (zone_for_place(loc) for loc in (locations or [])) if z]
    if not zones:
        return None
    counts = Counter(zones)
    best = max(counts.values())
    return next(z for z in zones if counts[z] == best)


def _fallback(session, strategy_id) -> tuple[str, str]:
    from app.config import settings  # noqa: PLC0415

    if session is not None and strategy_id is not None:
        cache = session.info.setdefault(_CACHE_KEY, {})
        hit = cache.get(strategy_id)
        if hit is not None and _time.monotonic() - hit[0] < _CACHE_SECONDS:
            return hit[1]
        result = None
        try:
            from app.db.models import Strategy  # noqa: PLC0415
            from app.services import daily_send_approval, notifications  # noqa: PLC0415

            strategy = session.get(Strategy, strategy_id)
            zone = strategy_zone(strategy)
            if zone:
                result = (zone, SOURCE_STRATEGY)
            else:
                owner = notifications.owner_of_strategy(session, strategy)
                if owner is not None:
                    tz, source = daily_send_approval.account_timezone(session, owner)
                    if source == daily_send_approval.TZ_SOURCE_CALENDAR:
                        result = (tz, SOURCE_ACCOUNT)
        except Exception:  # noqa: BLE001 -- the default below is always safe
            result = None
        result = result or (settings.send_window_timezone, SOURCE_DEFAULT)
        cache[strategy_id] = (_time.monotonic(), result)
        return result
    return settings.send_window_timezone, SOURCE_DEFAULT


def resolve(lead, session=None) -> tuple[str, str]:
    """(IANA zone, source) for a lead -- see the module docstring."""
    enrichment = getattr(lead, "enrichment_json", None)
    enrichment = enrichment if isinstance(enrichment, dict) else {}
    recorded = valid_zone(enrichment.get("timezone"))
    if recorded:
        return recorded, SOURCE_RECORDED
    found = zone_from_lead(lead)
    if found is not None:
        return found[0], SOURCE_LOCATION
    return _fallback(session or _session_of(lead), getattr(lead, "strategy_id", None))
