# MCP — FastMCP 3.0 Proxy

## Tech Stack

- FastMCP 3.0 (Streamable HTTP transport)
- httpx async client with connection pooling
- Circuit breaker (5 failures → 30s open → half-open probe)
- Pydantic Settings (env vars / .env)

## Architecture

Thin protocol adapter: MCP tool call → authenticated HTTP request → formatted response. No business logic — all ranking, embedding, and enrichment happen at the API.

```
MCP Client → FastMCP server.py → BackendClient (httpx) → FastAPI backend
```

## 6 Tools

| Tool | API Endpoint | Type | SLA |
|------|-------------|------|-----|
| `search_traces` | POST /api/v1/traces/search | read | 10s |
| `contribute_trace` | POST /api/v1/traces | write | 30s |
| `vote_trace` | POST /api/v1/traces/{id}/votes | write | 30s |
| `get_trace` | GET /api/v1/traces/{id} | read | 10s |
| `list_tags` | GET /api/v1/tags | read | 10s |
| `amend_trace` | POST /api/v1/traces/{id}/amendments | write | 30s |

## Auth Flow

1. MCP client sends `x-api-key` header (Streamable HTTP transport)
2. Fallback: `COMMONTRACE_API_KEY` env var (stdio transport)
3. Key forwarded as `X-API-Key` to backend on every request

## Error Handling

All backend failures return human-readable degradation strings (never unhandled exceptions). Three error classes:
- `CircuitOpenError` → "temporarily unreachable, retry later"
- `BackendUnavailableError` → "timeout/connection error"
- `httpx.HTTPStatusError` → formatted 4xx error (does NOT trip circuit breaker)

## Key Files

- `app/server.py` — Tool definitions, route handlers, health endpoint
- `app/backend_client.py` — httpx wrapper, CircuitBreaker class, BackendClient singleton
- `app/config.py` — MCPSettings (Pydantic, env-based)
- `app/formatters.py` — Response formatting for agent consumption
