"""Resolve an anonymized 2-letter country code from a request.

Resolution order:
  1. A trusted CDN header (``CF-IPCountry`` etc.) — covers the case where a
     proxy is ever placed in front of the API.
  2. The client IP, looked up against a bundled DB-IP IP-to-Country Lite
     database (CC BY 4.0 — see ``app/data/README.md``).

Privacy: only the resolved country is returned (and persisted by callers).
The client IP is never stored or logged here. Private, loopback, reserved,
and unparseable addresses resolve to ``None``.

The database is loaded lazily and cached. If the optional ``maxminddb``
dependency or the ``.mmdb`` file is missing, the IP path degrades silently
to ``None`` and the header path still works.
"""

import ipaddress
from pathlib import Path
from typing import Optional

try:  # optional dependency / file — IP path is best-effort
    import maxminddb
except ImportError:  # pragma: no cover - exercised only when dep absent
    maxminddb = None

# Trusted CDN country headers, in priority order.
_CDN_HEADERS = ("CF-IPCountry", "X-Vercel-IP-Country", "X-Country-Code")

# app/services/geoip.py -> app/data/dbip-country-lite.mmdb
_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "dbip-country-lite.mmdb"

_reader = None
_reader_loaded = False


def _get_reader():
    """Open the bundled DB once; return None if unavailable."""
    global _reader, _reader_loaded
    if _reader_loaded:
        return _reader
    _reader_loaded = True
    if maxminddb is not None and _DB_PATH.exists():
        try:
            _reader = maxminddb.open_database(str(_DB_PATH))
        except Exception:  # pragma: no cover - corrupt/unreadable db
            _reader = None
    return _reader


def _valid_code(value) -> Optional[str]:
    if isinstance(value, str) and len(value) == 2 and value.isalpha():
        return value.upper()
    return None


def _country_from_headers(request) -> Optional[str]:
    for header in _CDN_HEADERS:
        code = _valid_code(request.headers.get(header))
        if code:
            return code
    return None


def _client_ip(request) -> Optional[str]:
    """Leftmost X-Forwarded-For hop (the real client), else request.client."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return client.host
    return None


def _country_from_ip(request) -> Optional[str]:
    reader = _get_reader()
    if reader is None:
        return None
    ip = _client_ip(request)
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
        return None
    try:
        record = reader.get(ip)
    except Exception:  # pragma: no cover - defensive
        return None
    if not isinstance(record, dict):
        return None
    country = record.get("country")
    if isinstance(country, dict):
        return _valid_code(country.get("iso_code"))
    return None


def country_from_request(request) -> Optional[str]:
    """Return a 2-letter uppercase ISO country code, or None if unknown."""
    return _country_from_headers(request) or _country_from_ip(request)
