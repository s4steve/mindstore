import asyncpg

from embedder import EmbedderBase

from . import chunker
from . import db as db_module
from .models import IngestRequest, IngestResponse


async def ingest(
    request: IngestRequest, db_pool: asyncpg.Pool, embedder: EmbedderBase
) -> IngestResponse:
    chunks = chunker.chunk(request.content, request.content_type)
    parent_id: str | None = None
    ids: list[str] = []

    for chunk in chunks:
        vector = embedder.embed(chunk.text)
        entry_id = await db_module.insert_thought(
            pool=db_pool,
            content=chunk.text,
            embedding=vector,
            source=request.source,
            content_type=request.content_type,
            title=request.title,
            tags=request.tags,
            metadata=request.metadata,
            chunk_index=chunk.chunk_index,
            parent_id=parent_id,
        )
        if parent_id is None and len(chunks) > 1:
            parent_id = entry_id
        ids.append(entry_id)

    return IngestResponse(
        ids=ids,
        chunks_created=len(chunks),
        content_type=request.content_type,
    )
