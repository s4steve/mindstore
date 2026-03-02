from typing import Literal
from pydantic import BaseModel, Field


ContentType = Literal["thought", "note", "event", "article"]


class IngestRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50_000)
    content_type: ContentType = "thought"
    title: str | None = None
    tags: list[str] = []
    source: str = "api"
    metadata: dict = {}


class IngestResponse(BaseModel):
    ids: list[str]
    chunks_created: int
    content_type: str


class HealthResponse(BaseModel):
    status: str
    db: str


class StatsResponse(BaseModel):
    total: int
    by_type: dict[str, int]
    most_recent: str | None
