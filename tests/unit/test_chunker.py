import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../ingestion"))

from ingestion.chunker import chunk


def test_thought_no_chunking():
    results = chunk("A quick thought", "thought")
    assert len(results) == 1
    assert results[0].text == "A quick thought"
    assert results[0].chunk_index == 0
    assert results[0].total_chunks == 1


def test_event_no_chunking():
    results = chunk("Something happened today", "event")
    assert len(results) == 1
    assert results[0].chunk_index == 0


def test_note_paragraph_chunking():
    content = "\n\n".join(
        [
            "This is the first paragraph with enough content to pass the minimum.",
            "This is the second paragraph with enough content to pass the minimum.",
            "This is the third paragraph with enough content to pass the minimum.",
        ]
    )
    results = chunk(content, "note")
    assert len(results) == 3
    for i, r in enumerate(results):
        assert r.chunk_index == i
        assert r.total_chunks == 3


def test_note_short_paragraphs_short_content_fallback():
    # Paragraphs under 50 chars, content under threshold — return whole content
    results = chunk("Short.\n\nAlso short.", "note")
    assert len(results) == 1
    assert results[0].chunk_index == 0


def test_note_long_no_paragraphs_uses_sliding_window():
    # Short paragraphs (under 50 chars each) so paragraph chunking is skipped,
    # but total word count exceeds the 500-word sliding window threshold.
    # Using \n\n to create many small paragraphs that all fail the >=50 char filter.
    words = ["w"] * 600
    content = "\n\n".join(words)
    results = chunk(content, "note")
    # With 500-token window and 50 overlap, step=450
    # chunk 0: 0..500, chunk 1: 450..600 (end)
    assert len(results) == 2
    assert results[0].chunk_index == 0
    assert results[1].chunk_index == 1
    assert results[0].total_chunks == 2


def test_note_long_with_paragraphs_uses_paragraphs():
    # Long content but with clear paragraph structure — prefer paragraphs
    paragraphs = ["word " * 60] * 10  # 10 paragraphs, each ~60 words
    content = "\n\n".join(paragraphs)
    results = chunk(content, "note")
    assert len(results) == 10


def test_chunk_indices_are_sequential():
    content = "\n\n".join(["A" * 60] * 5)
    results = chunk(content, "note")
    indices = [r.chunk_index for r in results]
    assert indices == list(range(len(results)))
