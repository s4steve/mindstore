import os
import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from embedder import SentenceTransformerEmbedder
from . import db as db_module
from .tools import register_tools

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
INGESTION_URL = os.environ.get("INGESTION_URL", "http://ingestion:8000")
API_KEY = os.environ["API_KEY"]
EMBEDDER_MODEL = os.environ.get("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8001"))
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN") or None


@asynccontextmanager
async def lifespan(app):
    from . import tools as tools_module
    logger.info("Loading embedder model...")
    tools_module._embedder = SentenceTransformerEmbedder(EMBEDDER_MODEL)
    logger.info("Connecting to database...")
    tools_module._pool = await db_module.create_pool(DATABASE_URL)
    tools_module._ingestion_url = INGESTION_URL
    tools_module._api_key = API_KEY
    logger.info("MCP server ready.")
    yield
    await tools_module._pool.close()


mcp = FastMCP("mindstore", host=MCP_HOST, port=MCP_PORT, lifespan=lifespan)

# Register tools at module level so they're available before any SSE connection
register_tools(mcp)


class BearerTokenMiddleware:
    """
    Pure ASGI middleware that validates Authorization: Bearer <token> on all
    incoming connections: HTTP GET, HTTP POST, and WebSocket upgrades.

    If MCP_AUTH_TOKEN is None (not configured), the middleware is a no-op
    and every request passes through unconditionally.
    """

    def __init__(self, app, token: str | None):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if self.token is None or scope["type"] not in ("http", "websocket"):
            # Auth not configured or non-HTTP/WebSocket scope — pass through
            await self.app(scope, receive, send)
            return

        # Extract Authorization header from the ASGI scope
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("latin-1")

        if auth_header.lower().startswith("bearer "):
            provided_token = auth_header[7:]
            if provided_token == self.token:
                await self.app(scope, receive, send)
                return

        # Token missing or invalid — return 401
        await self._reject(scope, send)

    async def _reject(self, scope, send):
        body = b'{"error":"unauthorized","detail":"Valid Bearer token required"}'
        if scope["type"] == "websocket":
            # Close WebSocket with 4401 close code before upgrade completes
            await send({"type": "websocket.close", "code": 4401})
            return
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b'Bearer realm="MCP"'),
            ],
        })
        await send({"type": "http.response.body", "body": body})


def main():
    import uvicorn
    import anyio

    logging.basicConfig(level=logging.INFO)

    if MCP_AUTH_TOKEN:
        logger.info("MCP server: Bearer token authentication enabled.")
    else:
        logger.warning(
            "MCP server: MCP_AUTH_TOKEN is not set. "
            "The server is accepting unauthenticated connections. "
            "Set MCP_AUTH_TOKEN in production."
        )

    starlette_app = mcp.streamable_http_app()
    protected_app = BearerTokenMiddleware(starlette_app, MCP_AUTH_TOKEN)

    config = uvicorn.Config(
        protected_app,
        host=MCP_HOST,
        port=MCP_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)

    anyio.run(server.serve)


if __name__ == "__main__":
    main()
