from typing import Literal
from pydantic import BaseModel, Field


ContentType = Literal["thought", "note", "event"]


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


class UpdateRequest(BaseModel):
    content: str | None = Field(None, min_length=1, max_length=50_000)
    title: str | None = None
    tags: list[str] | None = None
    metadata: dict | None = None


class UpdateResponse(BaseModel):
    id: str
    re_embedded: bool


class DeleteResponse(BaseModel):
    id: str
    deleted: bool


class BulkIngestRequest(BaseModel):
    entries: list[IngestRequest] = Field(..., min_length=1, max_length=500)


class BulkIngestResponse(BaseModel):
    results: list[IngestResponse]
    total_entries: int
    total_chunks: int


class HealthResponse(BaseModel):
    status: str
    db: str


class StatsResponse(BaseModel):
    total: int
    by_type: dict[str, int]
    most_recent: str | None
