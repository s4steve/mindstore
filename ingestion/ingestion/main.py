import hmac
import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from embedder import EmbedderBase, SentenceTransformerEmbedder

from . import db as db_module
from . import pipeline
from .auth import COOKIE_NAME, create_cookie_value, verify_cookie
from .models import (
    BulkIngestRequest,
    BulkIngestResponse,
    ContactCreate,
    ContactInteraction,
    ContactResponse,
    ContactUpdate,
    DashboardResponse,
    DeleteResponse,
    HealthResponse,
    HomeItemCreate,
    HomeItemResponse,
    HomeItemUpdate,
    IngestRequest,
    IngestResponse,
    StatsResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    UpdateRequest,
    UpdateResponse,
)

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ["API_KEY"]
EMBEDDER_MODEL = os.environ.get("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
WEB_USERNAME = os.environ.get("WEB_USERNAME", "")
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

_db_pool: asyncpg.Pool | None = None
_embedder: EmbedderBase | None = None


async def get_api_key(key: str = Security(api_key_header)) -> str:
    if not hmac.compare_digest(key, API_KEY):
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


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Mindstore Ingestion", lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    raise HTTPException(status_code=429, detail="Rate limit exceeded")


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
@limiter.limit("5/minute")
async def auth_login(request: Request, creds: LoginRequest):
    if not (
        hmac.compare_digest(creds.username, WEB_USERNAME)
        and hmac.compare_digest(creds.password, WEB_PASSWORD)
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    cookie_value = create_cookie_value(creds.username)
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        max_age=30 * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    return response


@app.get("/auth/check")
async def auth_check(
    mindstore_session: str | None = Cookie(None),
):
    if not mindstore_session or not verify_cookie(mindstore_session):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"status": "ok"}


@app.get("/auth/logout")
async def auth_logout():
    response = RedirectResponse(url="/login.html", status_code=302)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


def get_pool() -> asyncpg.Pool:
    return _db_pool


def get_embedder() -> EmbedderBase:
    return _embedder


@app.post("/ingest", response_model=IngestResponse, dependencies=[Depends(get_api_key)])
@limiter.limit("30/minute")
async def ingest_endpoint(request: Request, ingest_req: IngestRequest):
    return await pipeline.ingest(ingest_req, get_pool(), get_embedder())


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
@limiter.limit("60/minute")
async def search_endpoint(
    request: Request, q: str, limit: int = 10, content_type: str | None = None
):
    embedding = get_embedder().embed(q)
    return await db_module.cross_table_search(
        get_pool(), embedding=embedding, limit=limit, content_type=content_type
    )


class EmbedRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000)


@app.post("/embed", dependencies=[Depends(get_api_key)])
@limiter.limit("120/minute")
async def embed_endpoint(request: Request, body: EmbedRequest) -> dict:
    """Return an embedding vector for the given text.

    Exists so that peer services (mcp_server) can avoid loading their own
    copy of the sentence-transformers model. The schema pins vector(384);
    callers that write these vectors must trust this endpoint as the single
    source of truth for embeddings.
    """
    return {"embedding": get_embedder().embed(body.text)}


def _embed(*parts: str | None) -> list[float]:
    """Embed the concatenation of non-None parts."""
    text = "\n".join(p for p in parts if p)
    return get_embedder().embed(text)


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


@app.get("/thoughts/{thought_id}", dependencies=[Depends(get_api_key)])
async def get_thought(thought_id: str):
    result = await db_module.get_thought_full(get_pool(), thought_id)
    if not result:
        raise HTTPException(status_code=404, detail="Thought not found")
    return result


@app.delete("/thoughts/{id}", response_model=DeleteResponse, dependencies=[Depends(get_api_key)])
async def delete_thought(id: str):
    deleted = await db_module.delete_thought(get_pool(), id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Thought not found")
    return DeleteResponse(id=id, deleted=True)


@app.post("/ingest/batch", response_model=BulkIngestResponse, dependencies=[Depends(get_api_key)])
@limiter.limit("5/minute")
async def ingest_batch(request: Request, batch_req: BulkIngestRequest):
    results = []
    for entry in batch_req.entries:
        result = await pipeline.ingest(entry, get_pool(), get_embedder())
        results.append(result)
    return BulkIngestResponse(
        results=results,
        total_entries=len(results),
        total_chunks=sum(r.chunks_created for r in results),
    )


# ── Tasks ─────────────────────────────────────────────────────────────────────


@app.post("/tasks", response_model=TaskResponse, dependencies=[Depends(get_api_key)])
async def create_task(request: TaskCreate):
    data = await db_module.create_task(
        get_pool(),
        embedding=_embed(request.title, request.notes),
        **request.model_dump(),
    )
    return TaskResponse(**data)


@app.get("/tasks", response_model=list[TaskResponse], dependencies=[Depends(get_api_key)])
async def list_tasks(
    status: str | None = None, category: str | None = None, due_soon_days: int | None = None
):
    rows = await db_module.list_tasks(
        get_pool(), status=status, category=category, due_soon_days=due_soon_days
    )
    return [TaskResponse(**r) for r in rows]


@app.get("/tasks/{id}", response_model=TaskResponse, dependencies=[Depends(get_api_key)])
async def get_task(id: str):
    row = await db_module.get_task(get_pool(), id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(**row)


@app.put("/tasks/{id}", response_model=TaskResponse, dependencies=[Depends(get_api_key)])
async def update_task(id: str, request: TaskUpdate):
    fields = {k: v for k, v in request.model_dump().items() if v is not None}
    embedding = None
    if "title" in fields or "notes" in fields:
        # Fetch current values to merge with updates for embedding text
        current = await db_module.get_task(get_pool(), id)
        if current:
            embedding = _embed(
                fields.get("title", current["title"]),
                fields.get("notes", current["notes"]),
            )
    row = await db_module.update_task(get_pool(), id, embedding=embedding, **fields)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(**row)


@app.delete("/tasks/{id}", response_model=DeleteResponse, dependencies=[Depends(get_api_key)])
async def delete_task(id: str):
    deleted = await db_module.delete_task(get_pool(), id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return DeleteResponse(id=id, deleted=True)


@app.post("/tasks/{id}/complete", response_model=TaskResponse, dependencies=[Depends(get_api_key)])
async def complete_task(id: str):
    row = await db_module.complete_task(get_pool(), id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(**row)


# ── Contacts ──────────────────────────────────────────────────────────────────


@app.post("/contacts", response_model=ContactResponse, dependencies=[Depends(get_api_key)])
async def create_contact(request: ContactCreate):
    data = await db_module.create_contact(
        get_pool(),
        embedding=_embed(request.name, request.notes),
        **request.model_dump(),
    )
    return ContactResponse(**data)


@app.get("/contacts", response_model=list[ContactResponse], dependencies=[Depends(get_api_key)])
async def list_contacts(reach_out_days: int | None = None):
    rows = await db_module.list_contacts(get_pool(), reach_out_days=reach_out_days)
    return [ContactResponse(**r) for r in rows]


@app.get("/contacts/{id}", response_model=ContactResponse, dependencies=[Depends(get_api_key)])
async def get_contact(id: str):
    row = await db_module.get_contact(get_pool(), id)
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactResponse(**row)


@app.put("/contacts/{id}", response_model=ContactResponse, dependencies=[Depends(get_api_key)])
async def update_contact(id: str, request: ContactUpdate):
    fields = {k: v for k, v in request.model_dump().items() if v is not None}
    embedding = None
    if "name" in fields or "notes" in fields:
        current = await db_module.get_contact(get_pool(), id)
        if current:
            embedding = _embed(
                fields.get("name", current["name"]),
                fields.get("notes", current["notes"]),
            )
    row = await db_module.update_contact(get_pool(), id, embedding=embedding, **fields)
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactResponse(**row)


@app.delete("/contacts/{id}", response_model=DeleteResponse, dependencies=[Depends(get_api_key)])
async def delete_contact(id: str):
    deleted = await db_module.delete_contact(get_pool(), id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found")
    return DeleteResponse(id=id, deleted=True)


@app.post(
    "/contacts/{id}/interaction",
    response_model=ContactResponse,
    dependencies=[Depends(get_api_key)],
)
async def log_interaction(id: str, request: ContactInteraction):
    # Get current contact to build updated embedding text (name + accumulated notes)
    current = await db_module.get_contact(get_pool(), id)
    if not current:
        raise HTTPException(status_code=404, detail="Contact not found")
    import datetime

    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    updated_notes = (
        f"{current['notes']}\n\n{timestamp}: {request.note}"
        if current["notes"]
        else f"{timestamp}: {request.note}"
    )
    embedding = _embed(current["name"], updated_notes)
    row = await db_module.log_interaction(get_pool(), id, request.note, embedding=embedding)
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactResponse(**row)


# ── Home items ────────────────────────────────────────────────────────────────


@app.post("/home", response_model=HomeItemResponse, dependencies=[Depends(get_api_key)])
async def create_home_item(request: HomeItemCreate):
    data = await db_module.create_home_item(
        get_pool(),
        embedding=_embed(request.name, request.notes),
        **request.model_dump(),
    )
    return HomeItemResponse(**data)


@app.get("/home", response_model=list[HomeItemResponse], dependencies=[Depends(get_api_key)])
async def list_home_items(due_soon_days: int | None = None):
    rows = await db_module.list_home_items(get_pool(), due_soon_days=due_soon_days)
    return [HomeItemResponse(**r) for r in rows]


@app.get("/home/{id}", response_model=HomeItemResponse, dependencies=[Depends(get_api_key)])
async def get_home_item(id: str):
    row = await db_module.get_home_item(get_pool(), id)
    if not row:
        raise HTTPException(status_code=404, detail="Home item not found")
    return HomeItemResponse(**row)


@app.put("/home/{id}", response_model=HomeItemResponse, dependencies=[Depends(get_api_key)])
async def update_home_item(id: str, request: HomeItemUpdate):
    fields = {k: v for k, v in request.model_dump().items() if v is not None}
    embedding = None
    if "name" in fields or "notes" in fields:
        current = await db_module.get_home_item(get_pool(), id)
        if current:
            embedding = _embed(
                fields.get("name", current["name"]),
                fields.get("notes", current["notes"]),
            )
    row = await db_module.update_home_item(get_pool(), id, embedding=embedding, **fields)
    if not row:
        raise HTTPException(status_code=404, detail="Home item not found")
    return HomeItemResponse(**row)


@app.delete("/home/{id}", response_model=DeleteResponse, dependencies=[Depends(get_api_key)])
async def delete_home_item(id: str):
    deleted = await db_module.delete_home_item(get_pool(), id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Home item not found")
    return DeleteResponse(id=id, deleted=True)


@app.post(
    "/home/{id}/complete", response_model=HomeItemResponse, dependencies=[Depends(get_api_key)]
)
async def complete_home_item(id: str):
    row = await db_module.complete_home_item(get_pool(), id)
    if not row:
        raise HTTPException(status_code=404, detail="Home item not found")
    return HomeItemResponse(**row)


# ── Dashboard ─────────────────────────────────────────────────────────────────

# ── Wiki / Tags ──────────────────────────────────────────────────────────────


@app.get("/tags", dependencies=[Depends(get_api_key)])
async def list_tags():
    return await db_module.get_all_tags(get_pool())


@app.get("/tags/{tag}", dependencies=[Depends(get_api_key)])
async def get_tag_detail(tag: str):
    items = await db_module.get_items_by_tag(get_pool(), tag)
    related_tags = await db_module.get_related_tags(get_pool(), tag)
    suggested = await db_module.get_suggested_connections(get_pool(), tag)
    return {
        "tag": tag,
        "items": items,
        "related_tags": related_tags,
        "suggested": suggested,
    }


@app.get("/dashboard", response_model=DashboardResponse, dependencies=[Depends(get_api_key)])
async def get_dashboard():
    data = await db_module.get_dashboard(get_pool())
    return DashboardResponse(
        overdue_tasks=[TaskResponse(**r) for r in data["overdue_tasks"]],
        due_soon_tasks=[TaskResponse(**r) for r in data["due_soon_tasks"]],
        overdue_home=[HomeItemResponse(**r) for r in data["overdue_home"]],
        due_soon_home=[HomeItemResponse(**r) for r in data["due_soon_home"]],
        contacts_to_reach=[ContactResponse(**r) for r in data["contacts_to_reach"]],
    )
