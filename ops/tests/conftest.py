"""Shared test fakes — no live network/DB calls in CI."""
import json


class FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text or json.dumps(self._json)

    def json(self):
        return self._json


class FakeHTTPClient:
    """Records POSTs; returns a queued FakeResponse."""

    def __init__(self, response=None):
        self.response = response or FakeResponse()
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response
