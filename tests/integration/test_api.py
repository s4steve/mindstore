"""
Integration tests for the ingestion REST API.
Requires the full Docker stack to be running:
    docker compose up -d
"""

import os

import httpx
import pytest

BASE_URL = os.environ.get("INGESTION_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "")

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def test_health_no_auth():
    r = httpx.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


def test_ingest_thought():
    r = httpx.post(
        f"{BASE_URL}/ingest",
        json={"content": "Integration test thought", "content_type": "thought"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["chunks_created"] == 1
    assert data["content_type"] == "thought"
    assert len(data["ids"]) == 1


def test_ingest_requires_auth():
    r = httpx.post(
        f"{BASE_URL}/ingest",
        json={"content": "Should fail", "content_type": "thought"},
    )
    assert r.status_code == 403


def test_ingest_content_too_long():
    r = httpx.post(
        f"{BASE_URL}/ingest",
        json={"content": "x" * 50_001, "content_type": "thought"},
        headers=HEADERS,
    )
    assert r.status_code == 422


def test_ingest_note_with_tags():
    paragraphs = [
        "First paragraph of the note with enough characters to pass the minimum length.",
        "Second paragraph of the note with enough characters to pass the minimum length.",
    ]
    r = httpx.post(
        f"{BASE_URL}/ingest",
        json={
            "content": "\n\n".join(paragraphs),
            "content_type": "note",
            "title": "Test Note",
            "tags": ["test", "integration"],
        },
        headers=HEADERS,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["chunks_created"] == 2
    assert data["content_type"] == "note"


def test_refine_requires_auth():
    r = httpx.post(f"{BASE_URL}/refine", json={"content": "hello"})
    assert r.status_code == 403


def test_refine_content_too_long():
    r = httpx.post(
        f"{BASE_URL}/refine",
        json={"content": "x" * 50_001, "content_type": "thought"},
        headers=HEADERS,
    )
    assert r.status_code == 422


def test_refine_smoke():
    """Live refine. Skips if the refiner backend is disabled (no API key)."""
    r = httpx.post(
        f"{BASE_URL}/refine",
        json={"content": "went to teh store, forgot the milk again ugh", "content_type": "thought"},
        headers=HEADERS,
        timeout=60.0,
    )
    if r.status_code == 503:
        pytest.skip("refiner backend disabled (ANTHROPIC_API_KEY unset)")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["content"], str) and data["content"].strip()
    assert isinstance(data["tags"], list)
    assert data["content_type"] == "thought"


def test_stats():
    r = httpx.get(f"{BASE_URL}/stats", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "by_type" in data
    assert data["total"] >= 1
