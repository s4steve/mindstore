from dataclasses import dataclass


@dataclass
class ChunkResult:
    text: str
    chunk_index: int
    total_chunks: int


def chunk(content: str, content_type: str) -> list[ChunkResult]:
    if content_type in ("thought", "event"):
        return [ChunkResult(text=content, chunk_index=0, total_chunks=1)]

    if content_type == "note":
        return _chunk_by_paragraph(content)

    if content_type == "article":
        return _chunk_sliding_window(content, token_size=500, overlap=50)

    # Fallback: no chunking
    return [ChunkResult(text=content, chunk_index=0, total_chunks=1)]


def _chunk_by_paragraph(content: str) -> list[ChunkResult]:
    paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) >= 50]
    if not paragraphs:
        # If no paragraph meets the min length, keep the whole content
        return [ChunkResult(text=content.strip(), chunk_index=0, total_chunks=1)]
    total = len(paragraphs)
    return [ChunkResult(text=p, chunk_index=i, total_chunks=total) for i, p in enumerate(paragraphs)]


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
