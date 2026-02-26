"""Tests for MCP server (tools logic with mocked FastMCP)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from onec_help import mcp_server


def test_run_mcp_requires_fastmcp(help_sample_dir: Path) -> None:
    with patch.object(mcp_server, "_HAS_FASTMCP", False):
        with pytest.raises(RuntimeError, match="fastmcp"):
            mcp_server.run_mcp(help_sample_dir, transport="stdio")


@patch.object(mcp_server, "_HAS_FASTMCP", True)
@patch.object(mcp_server, "_search")
@patch.object(mcp_server, "_get_topic")
def test_search_and_get_topic(mock_get, mock_search, help_sample_dir: Path) -> None:
    mcp_server._HELP_PATH = help_sample_dir
    mock_search.return_value = [{"title": "Test", "path": "field626.html", "text": "snippet"}]
    mock_get.return_value = "# Test\n\nContent"
    assert mcp_server._search("query", limit=5)
    assert mcp_server._get_topic("field626.html") == "# Test\n\nContent"
    mcp_server._HELP_PATH = None


@patch.object(mcp_server, "_search_keyword")
@patch.object(mcp_server, "_search")
def test_hybrid_search_handles_score_none(mock_search, mock_search_keyword) -> None:
    """_hybrid_search must not fail when keyword results have score=None."""
    mock_search.return_value = [{"path": "a.md", "title": "A", "text": "x", "score": 0.9}]
    mock_search_keyword.return_value = [{"path": "b.md", "title": "B", "text": "y", "score": None}]
    results = mcp_server._hybrid_search("test", limit=5)
    paths = [r.get("path") for r in results]
    assert "a.md" in paths
    assert "b.md" in paths


def test_extract_code_blocks() -> None:
    """_extract_code_blocks extracts bsl and generic code blocks from markdown."""
    md = """
# Title
Text before.
```bsl
Код = 1;
```
More text.
```
plain block
```
"""
    blocks = mcp_server._extract_code_blocks(md)
    assert len(blocks) == 2
    assert "Код = 1;" in blocks[0]
    assert "plain block" in blocks[1]
