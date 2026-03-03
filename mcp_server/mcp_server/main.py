import os
import logging
import asyncio

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

mcp = FastMCP("mindstore", host=MCP_HOST, port=MCP_PORT)


async def startup() -> tuple:
    logger.info("Loading embedder model...")
    embedder = SentenceTransformerEmbedder(EMBEDDER_MODEL)
    logger.info("Connecting to database...")
    pool = await db_module.create_pool(DATABASE_URL)
    logger.info("Registering MCP tools...")
    register_tools(mcp, INGESTION_URL, API_KEY, embedder, pool)
    logger.info("MCP server ready.")
    return embedder, pool


def main():
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(startup())
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
