from datetime import date, datetime
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


# ── Tasks ─────────────────────────────────────────────────────────────────────

TaskStatus = Literal["open", "done", "cancelled"]
TaskPriority = Literal["high", "medium", "low"]
TaskCategory = Literal["general", "work", "personal", "health", "finance", "home"]


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    notes: str | None = None
    status: TaskStatus = "open"
    priority: TaskPriority = "medium"
    due_date: date | None = None
    recurrence_days: int | None = None
    category: TaskCategory = "general"
    tags: list[str] = []


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    notes: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    recurrence_days: int | None = None
    category: TaskCategory | None = None
    tags: list[str] | None = None


class TaskResponse(BaseModel):
    id: str
    title: str
    notes: str | None
    status: str
    priority: str
    due_date: date | None
    recurrence_days: int | None
    category: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ── Contacts ──────────────────────────────────────────────────────────────────


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    notes: str | None = None
    tags: list[str] = []


class ContactUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    notes: str | None = None
    tags: list[str] | None = None


class ContactResponse(BaseModel):
    id: str
    name: str
    email: str | None
    phone: str | None
    company: str | None
    last_contact_at: datetime | None
    notes: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class ContactInteraction(BaseModel):
    note: str = Field(..., min_length=1, max_length=5000)


# ── Home items ────────────────────────────────────────────────────────────────


class HomeItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    notes: str | None = None
    interval_days: int | None = None
    next_due_at: datetime | None = None
    tags: list[str] = []


class HomeItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    notes: str | None = None
    interval_days: int | None = None
    next_due_at: datetime | None = None
    tags: list[str] | None = None


class HomeItemResponse(BaseModel):
    id: str
    name: str
    notes: str | None
    last_done_at: datetime | None
    next_due_at: datetime | None
    interval_days: int | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ── Dashboard ─────────────────────────────────────────────────────────────────


class DashboardResponse(BaseModel):
    overdue_tasks: list[TaskResponse]
    due_soon_tasks: list[TaskResponse]
    overdue_home: list[HomeItemResponse]
    due_soon_home: list[HomeItemResponse]
    contacts_to_reach: list[ContactResponse]
