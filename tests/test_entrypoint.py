"""Tests for entrypoint scripts (MCP_MODE, split architecture)."""

from pathlib import Path


def test_entrypoint_contains_mcp_mode_check() -> None:
    """Entrypoint must check MCP_MODE to skip background jobs when api."""
    root = Path(__file__).resolve().parent.parent
    entrypoint = root / "entrypoint.sh"
    content = entrypoint.read_text()
    assert "MCP_MODE" in content
    assert "_mcp_mode" in content or "MCP_MODE" in content
    assert "api" in content


def test_entrypoint_mcp_only_exists() -> None:
    """entrypoint-mcp-only.sh exists for api-only containers."""
    root = Path(__file__).resolve().parent.parent
    mcp_only = root / "entrypoint-mcp-only.sh"
    assert mcp_only.exists()
    content = mcp_only.read_text()
    assert "exec" in content
