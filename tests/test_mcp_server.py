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
