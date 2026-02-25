"""Tests for indexer module."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from onec_help import indexer as indexer_mod
from onec_help.indexer import (
    _get_embedding,
    _path_to_point_id,
    build_index,
    get_index_status,
    get_topic_by_path,
    search_index,
)


def test_get_embedding() -> None:
    vec = _get_embedding("test text")
    assert isinstance(vec, list)
    assert len(vec) == indexer_mod.VECTOR_SIZE
    assert all(isinstance(x, float) for x in vec)


def test_get_topic_by_path(help_sample_dir: Path) -> None:
    content = get_topic_by_path(help_sample_dir, "field626.html")
    assert content
    content2 = get_topic_by_path(help_sample_dir, "field626")
    assert content2


def test_get_topic_by_path_missing(help_sample_dir: Path) -> None:
    assert get_topic_by_path(help_sample_dir, "nonexistent") == ""


@patch("onec_help.indexer.QdrantClient")
def test_search_index(mock_client: MagicMock) -> None:
    mock_client.return_value.search.return_value = []
    result = search_index("query", limit=5)
    assert isinstance(result, list)


@patch("onec_help.indexer.QdrantClient")
def test_build_index(mock_client: MagicMock, help_sample_dir: Path, tmp_path: Path) -> None:
    (tmp_path / "one.md").write_text("# Test\n\nBody.", encoding="utf-8")
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    n = build_index(tmp_path, qdrant_host="localhost", qdrant_port=6333)
    assert n >= 1
    mock_instance.recreate_collection.assert_called_once()
    mock_instance.upsert.assert_called_once()


@patch("onec_help.indexer.QdrantClient")
def test_build_index_html_only(mock_client: MagicMock, help_sample_dir: Path) -> None:
    """Index when only .html exist (no .md) - uses html2md fallback."""
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    n = build_index(help_sample_dir, qdrant_host="localhost", qdrant_port=6333)
    assert n >= 1
    mock_instance.upsert.assert_called_once()


def test_path_to_point_id() -> None:
    a = _path_to_point_id("a.md", version="8.3", language="ru")
    b = _path_to_point_id("a.md", version="8.3", language="ru")
    assert a == b
    c = _path_to_point_id("b.md", version="8.3", language="ru")
    assert a != c
    assert isinstance(a, int)
    assert 0 <= a < 2**63


@patch("onec_help.indexer.QdrantClient")
def test_get_index_status_no_collection(mock_client: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.collection_exists.return_value = False
    s = get_index_status(qdrant_host="localhost", qdrant_port=6333)
    assert s["exists"] is False
    assert s.get("points_count", 0) == 0


@patch("onec_help.indexer.QdrantClient")
def test_get_index_status_exists(mock_client: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.collection_exists.return_value = True
    mock_instance.get_collection.return_value = MagicMock(points_count=100)
    mock_instance.scroll.return_value = (
        [
            MagicMock(payload={"version": "8.3", "language": "ru"}),
            MagicMock(payload={"version": "8.3", "language": "en"}),
        ],
        None,
    )
    s = get_index_status(qdrant_host="localhost", qdrant_port=6333)
    assert s["exists"] is True
    assert s["points_count"] == 100
    assert "8.3" in s.get("versions", [])
    assert "ru" in s.get("languages", [])
    assert "en" in s.get("languages", [])
