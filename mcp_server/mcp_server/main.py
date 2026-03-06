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


def main():
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
