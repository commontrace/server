"""Tests for app.services.geoip — anonymized country resolution.

Two paths: a trusted CDN header (if a proxy ever fronts the API) and an
IP -> country lookup against the bundled DB-IP IP-to-Country Lite database.
The IP-lookup tests rely on the real checked-in .mmdb (8.8.8.8 -> US etc.),
so they double as a smoke test that the bundled DB loads and reads.
"""
from types import SimpleNamespace

from app.services import geoip


class _Headers:
    """Case-insensitive header stand-in (Starlette Headers is case-insensitive)."""

    def __init__(self, d=None):
        self._d = {k.lower(): v for k, v in (d or {}).items()}

    def get(self, key, default=None):
        return self._d.get(key.lower(), default)


def _req(headers=None, client_host=None):
    return SimpleNamespace(
        headers=_Headers(headers),
        client=SimpleNamespace(host=client_host) if client_host else None,
    )


def test_cdn_header_takes_priority():
    # CF-IPCountry is trusted and short-circuits the IP lookup.
    assert geoip.country_from_request(_req({"CF-IPCountry": "fr"})) == "FR"


def test_cdn_header_ignored_when_malformed():
    # Three-letter / non-alpha values fall through to the IP path.
    r = _req({"CF-IPCountry": "FRA", "X-Forwarded-For": "8.8.8.8"})
    assert geoip.country_from_request(r) == "US"


def test_ip_lookup_from_xff_first_hop():
    # X-Forwarded-For: "client, proxy" -> use the leftmost (client) IP.
    r = _req({"X-Forwarded-For": "8.8.8.8, 10.0.0.1, 10.0.0.2"})
    assert geoip.country_from_request(r) == "US"


def test_ip_lookup_from_client_host_fallback():
    # No XFF -> fall back to request.client.host.
    assert geoip.country_from_request(_req(client_host="78.46.0.1")) == "DE"


def test_private_ip_returns_none():
    assert geoip.country_from_request(_req({"X-Forwarded-For": "10.0.0.5"})) is None


def test_loopback_returns_none():
    assert geoip.country_from_request(_req(client_host="127.0.0.1")) is None


def test_unmapped_ip_returns_none():
    # 203.0.113.0/24 is TEST-NET-3 (reserved) — never in the DB.
    assert geoip.country_from_request(_req({"X-Forwarded-For": "203.0.113.5"})) is None


def test_garbage_ip_returns_none():
    assert geoip.country_from_request(_req({"X-Forwarded-For": "not-an-ip"})) is None


def test_no_signal_returns_none():
    assert geoip.country_from_request(_req()) is None
