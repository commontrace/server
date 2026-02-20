"""HTTP client for the CommonTrace backend API.

BackendClient wraps httpx.AsyncClient to provide a clean interface for
making authenticated POST and GET requests to the FastAPI backend.

Plan 05-02 will add circuit breaker logic on top of these methods.
"""

import httpx

from app.config import settings


class BackendClient:
    """Thin wrapper around httpx.AsyncClient for backend API calls.

    Manages a persistent async HTTP client with connection pooling.
    API key authentication is forwarded from MCP client headers.
    """

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=httpx.Timeout(5.0, connect=2.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def post(
        self,
        path: str,
        json: dict,
        api_key: str,
        timeout: float = 2.0,
    ) -> dict:
        """Make an authenticated POST request to the backend.

        Args:
            path: URL path (e.g. "/api/v1/traces")
            json: Request body as a dict (serialized to JSON)
            api_key: API key forwarded from MCP client headers
            timeout: Per-request timeout override in seconds

        Returns:
            Parsed JSON response body as dict

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses (after raise_for_status)
            httpx.HTTPError: On network/transport errors
        """
        resp = await self.client.post(
            path,
            json=json,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    async def get(
        self,
        path: str,
        api_key: str,
        timeout: float = 0.5,
    ) -> dict:
        """Make an authenticated GET request to the backend.

        Args:
            path: URL path (e.g. "/api/v1/tags")
            api_key: API key forwarded from MCP client headers
            timeout: Per-request timeout override in seconds

        Returns:
            Parsed JSON response body as dict

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses (after raise_for_status)
            httpx.HTTPError: On network/transport errors
        """
        resp = await self.client.get(
            path,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Close the underlying httpx client and release connections."""
        await self.client.aclose()


# Module-level singleton — shared across all tool invocations
backend = BackendClient()
