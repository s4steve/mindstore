import asyncio
import hmac
import logging
import os

from mcp.server.fastmcp import FastMCP

from embedder import SentenceTransformerEmbedder

from . import db as db_module
from . import tools as tools_module
from .tools import register_tools

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
INGESTION_URL = os.environ.get("INGESTION_URL", "http://ingestion:8000")
API_KEY = os.environ["API_KEY"]
EMBEDDER_MODEL = os.environ.get("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8001"))
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN") or None
if not MCP_AUTH_TOKEN:
    raise RuntimeError(
        "MCP_AUTH_TOKEN is not set. "
        "The MCP server refuses to start without authentication. "
        "Set MCP_AUTH_TOKEN in your .env file."
    )


async def _initialize_server():
    """Initialize server resources once at startup."""
    logger.info("Loading embedder model...")
    tools_module._embedder = SentenceTransformerEmbedder(EMBEDDER_MODEL)
    logger.info("Connecting to database...")
    tools_module._pool = await db_module.create_pool(DATABASE_URL)
    tools_module._ingestion_url = INGESTION_URL
    tools_module._api_key = API_KEY
    logger.info("MCP server ready.")


mcp = FastMCP("mindstore", host=MCP_HOST, port=MCP_PORT)

# Register tools at module level so they're available before any SSE connection
register_tools(mcp)


class BearerTokenMiddleware:
    """
    ASGI middleware that validates authorization via:
    1. Authorization: Bearer <token> header
    2. ?token=<token> query parameter
    """

    def __init__(self, app, token: str | None):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if self.token is None or scope["type"] not in ("http", "websocket"):
            # Auth not configured or non-HTTP/WebSocket scope — pass through
            await self.app(scope, receive, send)
            return

        # Try Authorization header first
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("latin-1")

        if auth_header.lower().startswith("bearer "):
            provided_token = auth_header[7:]
            if hmac.compare_digest(provided_token, self.token):
                await self.app(scope, receive, send)
                return

        # Try query parameter as fallback
        query_string = scope.get("query_string", b"").decode("latin-1")
        if query_string:
            for param in query_string.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    if key == "token" and hmac.compare_digest(value, self.token):
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
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b'Bearer realm="MCP"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def main():
    import uvicorn

    logging.basicConfig(level=logging.INFO)

    logger.info("MCP server: Bearer token authentication enabled.")

    starlette_app = mcp.streamable_http_app()
    protected_app = BearerTokenMiddleware(starlette_app, MCP_AUTH_TOKEN)

    config = uvicorn.Config(
        protected_app,
        host=MCP_HOST,
        port=MCP_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)

    async def _run():
        await _initialize_server()
        await server.serve()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
