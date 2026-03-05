import os
import logging
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader

from embedder import SentenceTransformerEmbedder, EmbedderBase
from . import db as db_module
from . import pipeline
from .models import (
    IngestRequest, IngestResponse,
    UpdateRequest, UpdateResponse,
    DeleteResponse,
    BulkIngestRequest, BulkIngestResponse,
    HealthResponse, StatsResponse,
)

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ["API_KEY"]
EMBEDDER_MODEL = os.environ.get("EMBEDDER_MODEL", "all-MiniLM-L6-v2")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

_db_pool: asyncpg.Pool | None = None
_embedder: EmbedderBase | None = None


async def get_api_key(key: str = Security(api_key_header)) -> str:
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return key


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool, _embedder
    logger.info("Loading embedder model...")
    _embedder = SentenceTransformerEmbedder(EMBEDDER_MODEL)
    logger.info("Connecting to database...")
    _db_pool = await db_module.create_pool(DATABASE_URL)
    logger.info("Ingestion service ready.")
    yield
    await _db_pool.close()


app = FastAPI(title="Mindstore Ingestion", lifespan=lifespan)


def get_pool() -> asyncpg.Pool:
    return _db_pool


def get_embedder() -> EmbedderBase:
    return _embedder


@app.post("/ingest", response_model=IngestResponse, dependencies=[Depends(get_api_key)])
async def ingest_endpoint(request: IngestRequest):
    return await pipeline.ingest(request, get_pool(), get_embedder())


@app.get("/health", response_model=HealthResponse)
async def health():
    db_ok = await db_module.check_connection(get_pool())
    return HealthResponse(
        status="ok",
        db="ok" if db_ok else "error",
    )


@app.get("/stats", response_model=StatsResponse, dependencies=[Depends(get_api_key)])
async def stats():
    data = await db_module.get_stats(get_pool())
    return StatsResponse(**data)


@app.get("/recent", dependencies=[Depends(get_api_key)])
async def recent(limit: int = 10, content_type: str | None = None):
    return await db_module.get_recent(get_pool(), limit=limit, content_type=content_type)


@app.get("/search", dependencies=[Depends(get_api_key)])
async def search_endpoint(q: str, limit: int = 10, content_type: str | None = None):
    embedding = get_embedder().embed(q)
    return await db_module.semantic_search(get_pool(), embedding=embedding, limit=limit, content_type=content_type)


@app.put("/thoughts/{id}", response_model=UpdateResponse, dependencies=[Depends(get_api_key)])
async def update_thought(id: str, request: UpdateRequest):
    re_embedded = False
    embedding = None
    if request.content is not None:
        embedding = get_embedder().embed(request.content)
        re_embedded = True
    updated = await db_module.update_thought(
        pool=get_pool(),
        id=id,
        content=request.content,
        embedding=embedding,
        title=request.title,
        tags=request.tags,
        metadata=request.metadata,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Thought not found")
    return UpdateResponse(id=id, re_embedded=re_embedded)


@app.delete("/thoughts/{id}", response_model=DeleteResponse, dependencies=[Depends(get_api_key)])
async def delete_thought(id: str):
    deleted = await db_module.delete_thought(get_pool(), id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Thought not found")
    return DeleteResponse(id=id, deleted=True)


@app.post("/ingest/batch", response_model=BulkIngestResponse, dependencies=[Depends(get_api_key)])
async def ingest_batch(request: BulkIngestRequest):
    results = []
    for entry in request.entries:
        result = await pipeline.ingest(entry, get_pool(), get_embedder())
        results.append(result)
    return BulkIngestResponse(
        results=results,
        total_entries=len(results),
        total_chunks=sum(r.chunks_created for r in results),
    )
