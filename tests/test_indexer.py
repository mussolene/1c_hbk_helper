"""Tests for indexer module."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from onec_help import indexer as indexer_mod
from onec_help.indexer import (
    _get_embedding,
    _path_to_point_id,
    build_index,
    get_index_status,
    get_topic_by_path,
    get_topic_content,
    get_topic_from_index,
    list_index_titles,
    search_index,
    search_index_keyword,
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


@patch("onec_help.indexer.QdrantClient")
def test_build_index_incremental_creates_collection(mock_client: MagicMock, tmp_path: Path) -> None:
    (tmp_path / "one.md").write_text("# One\n\nBody.", encoding="utf-8")
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.collection_exists.return_value = False
    n = build_index(tmp_path, qdrant_host="localhost", qdrant_port=6333, incremental=True)
    assert n >= 1
    mock_instance.create_collection.assert_called_once()
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


@patch("onec_help.indexer.QdrantClient", None)
def test_get_index_status_no_qdrant_client() -> None:
    s = get_index_status(qdrant_host="localhost", qdrant_port=6333)
    assert s.get("error") == "qdrant-client not available"
    assert s["exists"] is False


@patch("onec_help.indexer.QdrantClient")
def test_get_index_status_connection_error(mock_client: MagicMock) -> None:
    mock_client.side_effect = RuntimeError("connection refused")
    s = get_index_status(qdrant_host="localhost", qdrant_port=6333)
    assert "error" in s
    assert s["exists"] is False


@patch("onec_help.indexer.QdrantClient")
def test_get_index_status_get_collection_raises(mock_client: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.collection_exists.return_value = True
    mock_instance.get_collection.side_effect = RuntimeError("timeout")
    s = get_index_status(qdrant_host="localhost", qdrant_port=6333)
    assert s["exists"] is True
    assert "error" in s
    assert s.get("points_count") is None


@patch("onec_help.indexer.QdrantClient")
def test_search_index_query_points(mock_client: MagicMock) -> None:
    """search_index uses query_points when available (qdrant-client 2.x)."""
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.query_points.return_value = MagicMock(points=[])
    result = search_index("query", limit=5)
    assert isinstance(result, list)
    assert mock_instance.query_points.called or mock_instance.search.called


@patch("onec_help.indexer.QdrantClient")
def test_search_index_keyword_empty_query(mock_client: MagicMock) -> None:
    assert search_index_keyword("  ", limit=5) == []
    assert search_index_keyword("", limit=5) == []


@patch("onec_help.indexer.QdrantClient", None)
def test_search_index_keyword_no_client() -> None:
    assert search_index_keyword("term") == []


@patch("onec_help.indexer.QdrantClient")
def test_search_index_keyword_hits(mock_client: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.scroll.return_value = (
        [MagicMock(payload={"path": "a.md", "title": "Term here", "text": "body"})],
        None,
    )
    result = search_index_keyword("term", limit=5)
    assert len(result) == 1
    assert result[0]["path"] == "a.md"
    assert result[0]["title"] == "Term here"


@patch("onec_help.indexer.QdrantClient", None)
def test_list_index_titles_no_client() -> None:
    assert list_index_titles() == []


@patch("onec_help.indexer.QdrantClient")
def test_list_index_titles_with_prefix(mock_client: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.scroll.return_value = (
        [
            MagicMock(payload={"path": "zif/a.html", "title": "A"}),
            MagicMock(payload={"path": "other/b.html", "title": "B"}),
        ],
        None,
    )
    result = list_index_titles(path_prefix="zif", limit=10)
    assert len(result) == 1
    assert result[0]["path"] == "zif/a.html"


@patch("onec_help.indexer.QdrantClient")
@patch("onec_help.indexer.Filter")
@patch("onec_help.indexer.FieldCondition")
@patch("onec_help.indexer.MatchValue")
def test_get_topic_from_index_found(
    mock_mv: MagicMock,
    mock_fc: MagicMock,
    mock_f: MagicMock,
    mock_client: MagicMock,
) -> None:
    mock_instance = MagicMock()
    mock_client.return_value = mock_instance
    mock_instance.scroll.return_value = (
        [MagicMock(payload={"path": "topic.md", "text": "Full topic text"})],
        None,
    )
    text = get_topic_from_index("topic.md", qdrant_host="localhost", qdrant_port=6333)
    assert text == "Full topic text"


@patch("onec_help.indexer.QdrantClient", None)
def test_get_topic_from_index_no_client() -> None:
    assert get_topic_from_index("any") == ""


def test_get_topic_content_from_disk(help_sample_dir: Path) -> None:
    content = get_topic_content(help_sample_dir, "field626.html")
    assert content
    assert "реквизит" in content.lower() or "field" in content.lower()


@patch("onec_help.indexer.get_topic_by_path")
@patch("onec_help.indexer.get_topic_from_index")
def test_get_topic_content_fallback_to_index(
    mock_from_index: MagicMock,
    mock_by_path: MagicMock,
) -> None:
    mock_by_path.return_value = ""
    mock_from_index.return_value = "From index"
    content = get_topic_content("/none", "path/to/topic")
    assert content == "From index"
    mock_from_index.assert_called_once()
