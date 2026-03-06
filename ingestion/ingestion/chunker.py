from dataclasses import dataclass


@dataclass
class ChunkResult:
    text: str
    chunk_index: int
    total_chunks: int


_SLIDING_WINDOW_THRESHOLD = 500  # words; notes longer than this fall back to sliding window


def chunk(content: str, content_type: str) -> list[ChunkResult]:
    if content_type in ("thought", "event"):
        return [ChunkResult(text=content, chunk_index=0, total_chunks=1)]

    if content_type == "note":
        return _chunk_note(content)

    # Fallback: no chunking
    return [ChunkResult(text=content, chunk_index=0, total_chunks=1)]


def _chunk_note(content: str) -> list[ChunkResult]:
    paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) >= 50]
    if paragraphs:
        total = len(paragraphs)
        return [ChunkResult(text=p, chunk_index=i, total_chunks=total) for i, p in enumerate(paragraphs)]

    # No usable paragraphs — fall back to sliding window for long content
    word_count = len(content.split())
    if word_count > _SLIDING_WINDOW_THRESHOLD:
        return _chunk_sliding_window(content, token_size=500, overlap=50)

    return [ChunkResult(text=content.strip(), chunk_index=0, total_chunks=1)]


def _chunk_sliding_window(content: str, token_size: int = 500, overlap: int = 50) -> list[ChunkResult]:
    # Approximate tokens by splitting on whitespace
    words = content.split()
    if not words:
        return [ChunkResult(text=content, chunk_index=0, total_chunks=1)]

    step = token_size - overlap
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + token_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += step

    total = len(chunks)
    return [ChunkResult(text=c, chunk_index=i, total_chunks=total) for i, c in enumerate(chunks)]
