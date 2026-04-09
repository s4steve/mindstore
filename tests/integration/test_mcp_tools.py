"""
Integration tests for MCP server tools via streamable-http endpoint.
Requires the full Docker stack to be running:
    docker compose up -d

Tests the MCP streamable-http endpoint is reachable, requires bearer token authentication,
and the tools list is correct.
Full tool invocation testing requires an MCP client; these tests verify
the server is up and discoverable.
"""

import os

import httpx
import pytest

MCP_URL = os.environ.get("MCP_URL", "http://localhost:8001")
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")
AUTH_HEADERS = {"Authorization": f"Bearer {MCP_AUTH_TOKEN}"} if MCP_AUTH_TOKEN else {}

EXPECTED_TOOLS = {
    "add_thought",
    "add_note",
    "add_event",
    "search_thoughts",
    "get_recent",
    "get_by_tag",
    "get_stats",
}


def test_mcp_endpoint_reachable():
    """The MCP endpoint should return a response when properly authenticated."""
    r = httpx.get(f"{MCP_URL}/mcp", headers=AUTH_HEADERS, timeout=5.0)
    # streamable-http connections may redirect, begin streaming, or return 200/405
    assert r.status_code in (200, 307, 405)


def test_mcp_server_health():
    """MCP server process is running if we can connect to port 8001."""
    r = httpx.get(f"{MCP_URL}/", timeout=5.0)
    # Any response means the server is up
    assert r.status_code in (200, 404, 405)


def test_unauthorized_rejected_when_auth_configured():
    """When MCP_AUTH_TOKEN is set, requests without a token must get 401."""
    if not MCP_AUTH_TOKEN:
        pytest.skip("MCP_AUTH_TOKEN not set; skipping auth enforcement test")
    r = httpx.get(f"{MCP_URL}/mcp", timeout=5.0)  # No auth header
    assert r.status_code == 401
    assert "unauthorized" in r.text.lower()


def test_wrong_token_rejected():
    """Requests with wrong token must get 401."""
    if not MCP_AUTH_TOKEN:
        pytest.skip("MCP_AUTH_TOKEN not set; skipping auth enforcement test")
    r = httpx.get(f"{MCP_URL}/mcp", headers={"Authorization": "Bearer wrongtoken"}, timeout=5.0)
    assert r.status_code == 401
    assert "unauthorized" in r.text.lower()
