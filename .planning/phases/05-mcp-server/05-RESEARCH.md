# Phase 5: MCP Server - Research

**Researched:** 2026-02-20
**Domain:** MCP protocol adapter (FastMCP v3.0.0 + circuit breaker + API key injection)
**Confidence:** HIGH

## Summary

The MCP server is a stateless protocol adapter that translates MCP tool calls into HTTP requests to the existing CommonTrace FastAPI backend. FastMCP v3.0.0 (released February 18, 2026) is the correct framework -- it is GA, stable, and provides all required capabilities: `@mcp.tool` decorator for tool definitions, dual transport (stdio + Streamable HTTP) from the same code, `CurrentHeaders()` dependency injection for API key extraction from client config, `@mcp.custom_route` for health endpoints, and middleware for cross-cutting concerns like circuit breaking.

The MCP server lives in the existing `mcp-server/` workspace directory (already in the uv workspace). It calls the FastAPI backend at `http://api:8000` (Docker) or `http://localhost:8000` (local) using httpx.AsyncClient. API keys are injected from MCP client configuration headers (e.g., `X-API-Key: ...` in Claude Desktop/Code config) and extracted in tool functions via `CurrentHeaders()` -- they never appear as tool parameters. Circuit breaking is implemented as a lightweight custom class (no third-party library needed) wrapping httpx calls with per-operation timeouts (200ms read, 2s write) and failure counting (open after 5 failures, half-open after 30s).

**Primary recommendation:** Use FastMCP v3.0.0 with `CurrentHeaders()` for API key injection, a custom async circuit breaker wrapping httpx.AsyncClient, and `mcp.run(transport=...)` controlled by environment variable for stdio/HTTP transport selection.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastmcp | 3.0.0 | MCP server framework | GA release (Feb 18, 2026). Decorator-based tool definitions, dual transport, DI, middleware. Official Python MCP ecosystem standard. |
| httpx | >=0.28.1 | Async HTTP client to backend API | Already a required dependency of fastmcp. AsyncClient with connection pooling for backend calls. |
| pydantic | >=2.0 | Tool parameter validation | Already a dependency of fastmcp. Tool parameters validated automatically from type annotations. |
| pydantic-settings | >=2.0 | Configuration management | Environment-based config (API base URL, timeouts, circuit breaker thresholds). Matches API project pattern. |
| structlog | >=24.0 | Structured logging | JSON logs matching the API layer. Consistent observability across the stack. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uvicorn | >=0.30.0 | ASGI server for HTTP transport | Already a dependency of fastmcp. Used when running HTTP transport in production. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom circuit breaker | aiobreaker, pybreaker, circuitbreaker | Third-party libraries add dependencies for ~50 lines of code. Custom is simpler, zero external deps, exactly fits our timeout-per-operation pattern. |
| FastMCP middleware for circuit breaking | Inline try/except in each tool | Middleware would intercept at MCP protocol level but circuit breaker belongs at the HTTP client level (per-endpoint, not per-tool). |
| fastapi_mcp (auto-expose FastAPI as MCP) | FastMCP standalone | fastapi_mcp couples MCP to FastAPI process. Violates layered architecture. MCP server must be a separate process. |

**Installation:**
```bash
cd /home/bitnami/commontrace/mcp-server
uv add fastmcp>=3.0.0 pydantic-settings>=2.0.0 structlog>=24.0
```

Note: httpx, uvicorn, and pydantic are transitive dependencies of fastmcp -- no need to add explicitly.

## Architecture Patterns

### Recommended Project Structure
```
mcp-server/
    app/
        __init__.py
        server.py           # FastMCP instance, tool definitions
        config.py            # Pydantic Settings (base URL, timeouts)
        backend_client.py    # httpx.AsyncClient wrapper + circuit breaker
        formatters.py        # Format API responses for MCP tool output
    pyproject.toml
    Dockerfile
```

### Pattern 1: Thin MCP Proxy (Zero Business Logic)
**What:** Every MCP tool is a thin wrapper that calls the FastAPI backend via HTTP. No database access, no embedding, no scoring in the MCP server.
**When to use:** Always -- this is the architectural invariant.
**Example:**
```python
# Source: architecture decision from ARCHITECTURE.md + FastMCP 3.0 docs
from fastmcp import FastMCP, Context
from fastmcp.server.dependencies import CurrentHeaders, Depends

mcp = FastMCP(
    name="CommonTrace",
    instructions="Search, contribute, and vote on coding traces from the CommonTrace knowledge base.",
)

@mcp.tool
async def search_traces(
    query: str = "",
    tags: list[str] = [],
    limit: int = 10,
    headers: dict = Depends(CurrentHeaders()),
) -> str:
    """Search CommonTrace for traces matching a natural language query and/or tags."""
    api_key = headers.get("x-api-key", "")
    result = await backend.post(
        "/api/v1/traces/search",
        json={"q": query or None, "tags": tags, "limit": limit},
        api_key=api_key,
    )
    return format_search_results(result)
```

### Pattern 2: API Key Injection via CurrentHeaders()
**What:** API keys are passed from MCP client configuration as HTTP headers, extracted in tool functions via `CurrentHeaders()`, and forwarded to the backend. They never appear as tool parameters.
**When to use:** For all tools that call authenticated backend endpoints.
**How it works:**

MCP client config (Claude Code example):
```bash
claude mcp add --transport http commontrace https://mcp.commontrace.dev/mcp \
  --header "X-API-Key: ct_abc123..."
```

Or in `.mcp.json` for project-scoped config:
```json
{
  "mcpServers": {
    "commontrace": {
      "type": "http",
      "url": "https://mcp.commontrace.dev/mcp",
      "headers": {
        "X-API-Key": "${COMMONTRACE_API_KEY}"
      }
    }
  }
}
```

For stdio transport (local dev):
```bash
claude mcp add --transport stdio commontrace \
  --env COMMONTRACE_API_KEY=ct_abc123... \
  -- uv run --project /path/to/mcp-server python -m app.server
```

In tool functions:
```python
from fastmcp.server.dependencies import CurrentHeaders, Depends

@mcp.tool
async def contribute_trace(
    title: str,
    context_text: str,
    solution_text: str,
    tags: list[str] = [],
    headers: dict = Depends(CurrentHeaders()),
) -> str:
    """Submit a new trace to CommonTrace."""
    api_key = headers.get("x-api-key", "")
    # For stdio transport, headers dict is empty -- fall back to env var
    if not api_key:
        api_key = settings.commontrace_api_key
    result = await backend.post(
        "/api/v1/traces",
        json={...},
        api_key=api_key,
    )
    return format_contribution_result(result)
```

**Critical detail:** `CurrentHeaders()` returns an empty dict for stdio transport. The fallback to an environment variable handles local development. The `Depends()` wrapper ensures `headers` is excluded from the tool's MCP schema -- clients never see it as a callable parameter.

### Pattern 3: Dual Transport from Same Code
**What:** The same server code runs in both stdio and HTTP modes, selected by environment variable or CLI argument.
**When to use:** Always -- single codebase, two transports.
**Example:**
```python
# Source: FastMCP 3.0 official docs (gofastmcp.com/deployment/running-server)
import os

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(transport="http", host="0.0.0.0", port=8080)
    else:
        mcp.run()  # stdio is default
```

Or via CLI without code changes:
```bash
# stdio (default)
fastmcp run app/server.py

# HTTP
fastmcp run app/server.py --transport http --host 0.0.0.0 --port 8080
```

### Pattern 4: Circuit Breaker with Per-Operation SLAs
**What:** A lightweight async circuit breaker wrapping backend HTTP calls. Different timeout SLAs per operation type. Graceful degradation messages when circuit is open.
**When to use:** Every backend HTTP call.
**Example:**
```python
import asyncio
import time
import httpx

class CircuitBreaker:
    """Simple async circuit breaker with three states: closed, open, half-open."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "closed"  # closed | open | half-open

    async def call(self, coro, timeout: float):
        """Execute coroutine with circuit breaker protection."""
        if self.state == "open":
            if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
            else:
                raise CircuitOpenError(
                    "CommonTrace backend is temporarily unavailable. "
                    "Please try again in a few seconds."
                )

        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            self._on_success()
            return result
        except (httpx.HTTPError, asyncio.TimeoutError, ConnectionError) as exc:
            self._on_failure()
            raise BackendUnavailableError(str(exc)) from exc

    def _on_success(self):
        self.failure_count = 0
        self.state = "closed"

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
```

Usage in backend client:
```python
class BackendClient:
    def __init__(self, base_url: str):
        self.client = httpx.AsyncClient(base_url=base_url, timeout=5.0)
        self.breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

    async def post(self, path: str, json: dict, api_key: str, timeout: float = 2.0):
        async def _do():
            resp = await self.client.post(
                path,
                json=json,
                headers={"X-API-Key": api_key},
            )
            resp.raise_for_status()
            return resp.json()
        return await self.breaker.call(_do(), timeout=timeout)
```

Tool-level SLA application:
```python
# Read operations: 200ms timeout (fast auto-query)
result = await backend.post("/api/v1/traces/search", json=..., api_key=key, timeout=0.2)

# Write operations: 2s timeout (contributions, votes)
result = await backend.post("/api/v1/traces", json=..., api_key=key, timeout=2.0)
```

### Pattern 5: Graceful Degradation Messages
**What:** When the circuit breaker is open or a backend call fails, return a structured error message that the agent can understand and act on, rather than throwing an exception that crashes the agent session.
**When to use:** Every tool that calls the backend.
**Example:**
```python
from fastmcp.exceptions import ToolError

@mcp.tool
async def search_traces(
    query: str = "",
    tags: list[str] = [],
    limit: int = 10,
    headers: dict = Depends(CurrentHeaders()),
) -> str:
    """Search CommonTrace for traces matching a natural language query and/or tags."""
    api_key = _extract_api_key(headers)
    try:
        result = await backend.post(
            "/api/v1/traces/search",
            json={"q": query or None, "tags": tags, "limit": limit},
            api_key=api_key,
            timeout=0.2,  # 200ms SLA for reads
        )
        return format_search_results(result)
    except CircuitOpenError:
        return (
            "[CommonTrace unavailable] The knowledge base is temporarily unreachable. "
            "Continuing without trace lookup. You can retry later."
        )
    except BackendUnavailableError:
        return (
            "[CommonTrace timeout] Search took too long and was cancelled. "
            "The knowledge base may be under heavy load. Continuing without results."
        )
```

**Critical detail:** Return a string message, do NOT raise `ToolError`. A `ToolError` signals to the MCP client that the tool call failed, which may cause the agent to retry or error out. A returned string is treated as a successful tool response -- the agent reads the degradation message and moves on.

### Anti-Patterns to Avoid
- **Business logic in MCP server:** No database access, no embedding calls, no trust score computation. The MCP server is a protocol adapter only.
- **API key as tool parameter:** Never `def search_traces(api_key: str, query: str)`. Keys flow through headers/env, not tool schemas.
- **Raising ToolError on backend failure:** This signals tool failure. Instead, return a graceful degradation message as a string. The agent session continues.
- **Shared mutable state across requests:** The MCP server is stateless. No session-scoped caches, no request counting in memory (leave rate limiting to the backend).
- **Coupling to FastAPI process:** The MCP server is a separate process. Do not import from `api/app/`. Communication is HTTP only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol handling | Custom JSON-RPC server | FastMCP v3.0.0 | Protocol compliance, transport negotiation, session management, schema generation -- all handled. |
| Tool schema generation | Manual JSON schema for each tool | FastMCP `@mcp.tool` decorator | Auto-generates from Python type annotations + docstrings. |
| Header extraction | Custom ASGI middleware | `CurrentHeaders()` dependency | Built into FastMCP, safe across all transports (empty dict for stdio). |
| HTTP transport | Custom Starlette/uvicorn setup | `mcp.run(transport="http")` | FastMCP handles Streamable HTTP protocol, session management, ASGI app creation. |
| Health endpoint | Separate Starlette app | `@mcp.custom_route("/health")` | Built into FastMCP, serves alongside MCP endpoint. |
| Parameter hiding from schema | Manual schema override | `Depends()` | Parameters with `Depends()` are automatically excluded from tool schema. |

**Key insight:** FastMCP v3.0.0 handles almost everything at the protocol level. The only custom code needed is the backend HTTP client wrapper and the circuit breaker (both are ~50 lines each).

## Common Pitfalls

### Pitfall 1: ToolError Kills Agent Sessions
**What goes wrong:** Raising `ToolError` or letting exceptions propagate from tool functions when the backend is down. The MCP client sees tool failure and may abort the agent's workflow.
**Why it happens:** Natural instinct is to raise exceptions on errors.
**How to avoid:** Catch all backend errors inside each tool function. Return a human-readable degradation message as a string. Reserve `ToolError` for truly invalid inputs (wrong parameter types, missing required fields).
**Warning signs:** Agent logs showing "tool call failed" during backend outages.

### Pitfall 2: stdio Transport Has No HTTP Headers
**What goes wrong:** `CurrentHeaders()` returns empty dict for stdio transport. API key extraction fails, all backend calls get 401.
**Why it happens:** stdio transport communicates via stdin/stdout, not HTTP. There are no HTTP headers.
**How to avoid:** Fall back to environment variable (`COMMONTRACE_API_KEY`) when headers are empty. Document both patterns in client configuration guide.
**Warning signs:** All tool calls returning 401 errors when running locally via stdio.

### Pitfall 3: Blocking the Event Loop with Synchronous Code
**What goes wrong:** Using synchronous `httpx.Client` or `requests` instead of `httpx.AsyncClient`. MCP server becomes unresponsive during backend calls.
**Why it happens:** Copying patterns from synchronous Python tutorials.
**How to avoid:** Always use `async def` for tools and `httpx.AsyncClient` for backend calls. FastMCP v3 auto-dispatches sync tools to threadpool, but async is preferred for I/O.
**Warning signs:** MCP server hangs during concurrent tool calls.

### Pitfall 4: Connection Pool Exhaustion
**What goes wrong:** Creating a new `httpx.AsyncClient` per tool call instead of sharing one. Leads to socket exhaustion under load.
**Why it happens:** Not managing client lifecycle properly.
**How to avoid:** Create a single `httpx.AsyncClient` at module level or in the backend client class. The MCP server is long-lived -- one client for the process lifetime. Set `limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)`.
**Warning signs:** "Connection pool full" or "Too many open files" errors.

### Pitfall 5: Search Endpoint is POST, Not GET
**What goes wrong:** Calling `GET /api/v1/traces/search?q=...` instead of `POST /api/v1/traces/search` with JSON body.
**Why it happens:** Assumption that search is a GET request.
**How to avoid:** The CommonTrace API uses POST for search (with JSON body `{"q": "...", "tags": [...], "limit": 10}`). This is intentional -- search queries can be complex with nested tag lists.
**Warning signs:** 405 Method Not Allowed or 422 validation errors from backend.

### Pitfall 6: Forgetting to Pass API Key to Backend
**What goes wrong:** Making backend calls without the `X-API-Key` header. Backend returns 401.
**Why it happens:** API key extraction is done at tool level but must be threaded to every HTTP call.
**How to avoid:** The backend client's `post()` and `get()` methods always accept and forward the `api_key` parameter to the `X-API-Key` header.
**Warning signs:** 401 responses from backend for all tool calls.

### Pitfall 7: Lifespan Not Wired Correctly for HTTP Transport
**What goes wrong:** When mounting FastMCP as ASGI sub-app on another framework, forgetting to pass `mcp_app.lifespan` to the parent app. Session manager is not initialized.
**Why it happens:** FastMCP's internal session manager needs its lifespan context to start.
**How to avoid:** For this project, use `mcp.run(transport="http")` directly (not mounted on FastAPI). This handles lifespan automatically. Only mount if adding to an existing FastAPI app.
**Warning signs:** "Session not found" or "StreamableHTTPSessionManager not initialized" errors.

## Code Examples

Verified patterns from official FastMCP 3.0.0 documentation:

### FastMCP Server with Tool Definitions
```python
# Source: gofastmcp.com/servers/tools + gofastmcp.com/deployment/running-server
from fastmcp import FastMCP
from fastmcp.server.dependencies import CurrentHeaders, Depends

mcp = FastMCP(
    name="CommonTrace",
    instructions=(
        "CommonTrace is a shared knowledge base for AI coding agents. "
        "Use search_traces to find solutions before writing code. "
        "Use contribute_trace after solving a problem to help future agents. "
        "Use vote_trace to rate traces you've used."
    ),
)

@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": True},
)
async def search_traces(
    query: str = "",
    tags: list[str] = [],
    limit: int = 10,
    headers: dict = Depends(CurrentHeaders()),
) -> str:
    """Search CommonTrace for coding traces matching a natural language query and/or tags.

    Args:
        query: Natural language description of what you're looking for (e.g., "FastAPI JWT auth setup")
        tags: Filter by tags like language, framework, or task type (AND semantics)
        limit: Maximum number of results (1-50, default 10)
    """
    ...
```

### Custom Route for Health Check
```python
# Source: gofastmcp.com/deployment/running-server
from starlette.responses import JSONResponse

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({
        "status": "healthy",
        "service": "commontrace-mcp",
    })
```

### Backend Client with Circuit Breaker
```python
# Source: custom implementation based on Martin Fowler circuit breaker pattern
import httpx
from app.config import settings

class BackendClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=httpx.Timeout(5.0, connect=2.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self.breaker = CircuitBreaker(
            failure_threshold=settings.circuit_failure_threshold,
            recovery_timeout=settings.circuit_recovery_timeout,
        )

    async def post(self, path: str, json: dict, api_key: str, timeout: float = 2.0) -> dict:
        async def _request():
            resp = await self.client.post(
                path,
                json=json,
                headers={"X-API-Key": api_key},
            )
            resp.raise_for_status()
            return resp.json()
        return await self.breaker.call(_request(), timeout=timeout)

    async def get(self, path: str, api_key: str, timeout: float = 0.5) -> dict:
        async def _request():
            resp = await self.client.get(
                path,
                headers={"X-API-Key": api_key},
            )
            resp.raise_for_status()
            return resp.json()
        return await self.breaker.call(_request(), timeout=timeout)

    async def close(self):
        await self.client.aclose()

# Module-level singleton
backend = BackendClient()
```

### Configuration via Pydantic Settings
```python
# Source: pydantic-settings docs + project pattern from api/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    api_base_url: str = "http://localhost:8000"
    commontrace_api_key: str = ""  # fallback for stdio transport
    mcp_transport: str = "stdio"   # "stdio" or "http"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8080

    # Circuit breaker
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 30.0

    # SLA timeouts (seconds)
    read_timeout: float = 0.2   # 200ms for search/get
    write_timeout: float = 2.0  # 2s for contribute/vote

settings = MCPSettings()
```

### Entrypoint with Transport Selection
```python
# Source: gofastmcp.com/deployment/running-server
from app.server import mcp
from app.config import settings

if __name__ == "__main__":
    if settings.mcp_transport == "http":
        mcp.run(
            transport="http",
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
    else:
        mcp.run()  # stdio default
```

### Docker Compose Service Addition
```yaml
# Added to existing docker-compose.yml
mcp-server:
  build:
    context: ./mcp-server
  env_file:
    - .env
  environment:
    - API_BASE_URL=http://api:8000
    - MCP_TRANSPORT=http
    - MCP_PORT=8080
  ports:
    - "8080:8080"
  depends_on:
    api:
      condition: service_started
```

### MCP Client Configuration Examples
```bash
# Claude Code -- HTTP transport (remote)
claude mcp add --transport http commontrace http://localhost:8080/mcp \
  --header "X-API-Key: ct_your_key_here"

# Claude Code -- stdio transport (local dev)
claude mcp add --transport stdio commontrace \
  --env COMMONTRACE_API_KEY=ct_your_key_here \
  -- uv run --project ./mcp-server python -m app.server
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastMCP v2 (decorator returns Component object) | FastMCP v3 (decorator returns callable function) | v3.0.0, Feb 2026 | Decorators work like Flask/FastAPI now. Set `FASTMCP_DECORATOR_MODE=object` for v2 compat. |
| SSE transport for remote MCP | Streamable HTTP transport | MCP spec 2025 | SSE is deprecated. Use `transport="http"` for remote. |
| `ctx.get_state()` / `ctx.set_state()` (sync) | `await ctx.get_state()` / `await ctx.set_state()` (async) | v3.0.0 | All state ops are async in v3. |
| `mcp[cli]` package from Anthropic | `fastmcp` standalone package (PrefectHQ) | v3.0.0 | FastMCP is the ecosystem standard. Repo moved from jlowin/fastmcp to PrefectHQ/fastmcp. |
| `enabled` parameter on tool decorators | `mcp.enable()` / `mcp.disable()` with tag/name filtering | v3.0.0 | Component visibility system replaces per-tool enabled flag. |
| Auth auto-loaded from env vars | Explicit auth configuration required | v3.0.0 | Must explicitly configure auth providers. |

**Deprecated/outdated:**
- SSE transport: Use Streamable HTTP instead. SSE maintained only for backward compat.
- FastMCP v2 decorator behavior: v3 decorators return callable functions, not Component objects.
- `from mcp.server.fastmcp import FastMCP`: Old import path. Use `from fastmcp import FastMCP`.

## Existing API Endpoints (MCP Tool Targets)

These are the backend endpoints the MCP tools will call:

| MCP Tool | Backend Endpoint | Method | Auth | Timeout SLA |
|----------|-----------------|--------|------|-------------|
| `search_traces` | `/api/v1/traces/search` | POST (JSON body) | X-API-Key | 200ms |
| `contribute_trace` | `/api/v1/traces` | POST (JSON body) | X-API-Key + RequireEmail | 2s |
| `vote_trace` | `/api/v1/traces/{id}/votes` | POST (JSON body) | X-API-Key + RequireEmail | 2s |
| `get_trace` | `/api/v1/traces/{id}` | GET | X-API-Key | 200ms |
| `list_tags` | No endpoint exists yet | - | - | - |

**Note on list_tags:** There is no `GET /api/v1/tags` endpoint in the current API. Options:
1. Add a simple endpoint to the API (preferred -- keeps all data access in the backend).
2. Have the MCP server return a hardcoded/cached list (violates thin-proxy pattern).
3. Defer `list_tags` tool to a later plan if not critical for success criteria.

**Recommendation:** Add `GET /api/v1/tags` to the API as part of Plan 05-01. It is a simple SELECT DISTINCT query. This keeps the MCP server truly stateless.

## Open Questions

1. **list_tags endpoint**
   - What we know: No GET /api/v1/tags endpoint exists. The roadmap lists `list_tags` as an MCP tool.
   - What's unclear: Whether to add the API endpoint in Phase 5 or defer.
   - Recommendation: Add a minimal `GET /api/v1/tags` endpoint in the API as part of Plan 05-01. It is ~10 lines of FastAPI code and keeps the MCP server stateless.

2. **httpx.AsyncClient lifecycle in stdio transport**
   - What we know: For HTTP transport, the ASGI server stays alive. For stdio, the process lives as long as the MCP session.
   - What's unclear: Whether a module-level AsyncClient is correctly cleaned up on stdio process exit.
   - Recommendation: Use module-level client. Python process exit will close sockets. For clean shutdown, register an atexit handler or use FastMCP lifespan if available.

3. **200ms read SLA feasibility**
   - What we know: The search endpoint does embedding + pgvector ANN + re-ranking. Cold embedding calls to OpenAI take 100-300ms.
   - What's unclear: Whether 200ms is achievable end-to-end (MCP -> HTTP -> embed -> search -> respond).
   - Recommendation: Set 200ms as the MCP-to-backend timeout. If search consistently exceeds this, the agent gets a degradation message. The backend can optimize independently. Consider 500ms as a fallback SLA if 200ms proves too aggressive.

## Sources

### Primary (HIGH confidence)
- FastMCP 3.0.0 official docs -- tool definitions, all code patterns: https://gofastmcp.com/servers/tools
- FastMCP 3.0.0 official docs -- running server, transports: https://gofastmcp.com/deployment/running-server
- FastMCP 3.0.0 official docs -- HTTP deployment, custom routes, ASGI: https://gofastmcp.com/deployment/http
- FastMCP 3.0.0 official docs -- dependency injection (CurrentHeaders, Depends): https://gofastmcp.com/python-sdk/fastmcp-server-dependencies
- FastMCP 3.0.0 official docs -- server-side DI patterns: https://gofastmcp.com/servers/dependency-injection
- FastMCP 3.0.0 official docs -- middleware (on_call_tool, error handling): https://gofastmcp.com/servers/middleware
- FastMCP 3.0.0 official docs -- context (state, lifespan): https://gofastmcp.com/python-sdk/fastmcp-server-context
- Claude Code MCP configuration -- adding servers, headers, scopes: https://code.claude.com/docs/en/mcp
- FastMCP 3.0.0 PyPI release (Feb 18, 2026): https://pypi.org/project/fastmcp/

### Secondary (MEDIUM confidence)
- FastMCP 3.0 GA launch blog: https://www.jlowin.dev/blog/fastmcp-3-launch
- FastMCP 3.0 what's new blog (breaking changes): https://www.jlowin.dev/blog/fastmcp-3-whats-new
- FastMCP auth implementation pattern: https://gelembjuk.com/blog/post/authentication-remote-mcp-server-python/
- Martin Fowler circuit breaker pattern: https://martinfowler.com/bliki/CircuitBreaker.html
- circuitbreaker PyPI (v2.1.3, async support): https://pypi.org/project/circuitbreaker/

### Tertiary (LOW confidence)
- None -- all claims verified against official FastMCP documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- FastMCP 3.0.0 GA is verified, API surface confirmed from official docs
- Architecture: HIGH -- Thin proxy pattern validated by existing ARCHITECTURE.md + FastMCP DI system
- API key injection: HIGH -- CurrentHeaders() + Depends() pattern verified in official docs, empty-dict fallback for stdio confirmed
- Circuit breaker: HIGH -- Pattern is well-established (Fowler), implementation is straightforward
- Dual transport: HIGH -- `mcp.run(transport=...)` verified in official docs
- 200ms SLA feasibility: MEDIUM -- Depends on backend search performance, may need adjustment
- list_tags endpoint gap: HIGH -- Confirmed by codebase audit (no GET /tags route exists)

**Research date:** 2026-02-20
**Valid until:** 2026-03-20 (FastMCP v3 is GA and stable; 30-day validity)
