import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../ingestion"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../embedder"))

from ingestion.models import IngestRequest
from ingestion.pipeline import ingest


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_mock_embedder(dims=384):
    embedder = MagicMock()
    embedder.embed.return_value = [0.1] * dims
    return embedder


def make_mock_pool(return_id="test-uuid"):
    pool = MagicMock()
    # insert_thought calls pool.fetchrow
    row = MagicMock()
    row.__getitem__ = lambda self, key: return_id
    pool.fetchrow = AsyncMock(return_value=row)
    return pool


def test_ingest_thought_calls_embed_once():
    embedder = make_mock_embedder()
    pool = make_mock_pool()

    request = IngestRequest(content="A thought", content_type="thought")
    result = run(ingest(request, pool, embedder))

    embedder.embed.assert_called_once_with("A thought")
    assert result.chunks_created == 1
    assert result.content_type == "thought"


def test_ingest_note_chunks_by_paragraph():
    embedder = make_mock_embedder()
    pool = make_mock_pool()

    paragraphs = [
        "This is the first long paragraph with more than fifty characters total here.",
        "This is the second long paragraph with more than fifty characters total here.",
    ]
    content = "\n\n".join(paragraphs)
    request = IngestRequest(content=content, content_type="note")
    result = run(ingest(request, pool, embedder))

    assert result.chunks_created == 2
    assert embedder.embed.call_count == 2


def test_ingest_sets_parent_id_for_multi_chunk():
    call_count = 0
    ids = ["parent-uuid", "child-uuid"]

    async def mock_insert(**kwargs):
        return ids[0] if kwargs.get("parent_id") is None else ids[1]

    embedder = make_mock_embedder()

    with patch("ingestion.db.insert_thought", side_effect=mock_insert):
        paragraphs = [
            "First paragraph that is long enough to pass the fifty char minimum right here.",
            "Second paragraph that is long enough to pass the fifty char minimum right here.",
        ]
        content = "\n\n".join(paragraphs)
        request = IngestRequest(content=content, content_type="note")
        pool = MagicMock()
        result = run(ingest(request, pool, embedder))
        assert result.chunks_created == 2


def test_ingest_returns_correct_ids():
    embedder = make_mock_embedder()
    pool = make_mock_pool(return_id="abc-123")

    request = IngestRequest(content="Single thought", content_type="thought")
    result = run(ingest(request, pool, embedder))

    assert result.ids == ["abc-123"]
