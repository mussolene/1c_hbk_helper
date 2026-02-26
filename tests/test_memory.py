"""Tests for memory module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from onec_help.memory import (
    MemoryStore,
    _is_memory_enabled,
    get_memory_store,
)


def test_memory_disabled_by_default() -> None:
    assert _is_memory_enabled() is False


def test_memory_enabled_variants() -> None:
    for val in ("1", "true", "yes", "on"):
        with patch.dict("os.environ", {"MEMORY_ENABLED": val}, clear=False):
            from importlib import reload

            from onec_help import memory

            reload(memory)
            assert memory._is_memory_enabled() is True
    with patch.dict("os.environ", {"MEMORY_ENABLED": "0"}, clear=False):
        from importlib import reload

        from onec_help import memory

        reload(memory)
        assert memory._is_memory_enabled() is False


def test_write_event_disabled_returns_early(tmp_path: Path) -> None:
    """When MEMORY_ENABLED=0, write_event returns without writing."""
    with patch.dict("os.environ", {"MEMORY_ENABLED": "0"}, clear=False):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        store.write_event("get_topic", {"topic_path": "a.md"})
    assert len(store.get_short()) == 0
    assert not (tmp_path / "session_memory.jsonl").exists()


def test_get_memory_store_singleton(tmp_path: Path) -> None:
    with patch.dict("os.environ", {"MEMORY_BASE_PATH": str(tmp_path)}, clear=False):
        from onec_help import memory

        memory._store = None
        s1 = get_memory_store()
        s2 = get_memory_store()
        assert s1 is s2


def test_get_memory_store_from_env(tmp_path: Path) -> None:
    with patch.dict(
        "os.environ",
        {
            "MEMORY_BASE_PATH": str(tmp_path),
            "MEMORY_SHORT_LIMIT": "10",
            "MEMORY_MEDIUM_LIMIT": "200",
            "MEMORY_MEDIUM_TTL_DAYS": "3",
        },
        clear=False,
    ):
        from onec_help import memory

        memory._store = None
        store = get_memory_store()
        assert store.base_path == tmp_path
        assert store.medium_limit == 200
        assert store.medium_ttl_days == 3


def test_get_memory_store_explicit_base_path(tmp_path: Path) -> None:
    from onec_help import memory

    memory._store = None
    store = get_memory_store(base_path=tmp_path)
    assert store.base_path == tmp_path


def test_memory_store_short_medium(tmp_path: Path) -> None:
    """write_event writes to short and medium when MEMORY_ENABLED=1."""
    with patch.dict("os.environ", {"MEMORY_ENABLED": "1"}, clear=False):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        store.write_event("get_topic", {"topic_path": "a.md", "title": "A"})
        short = store.get_short()
        assert len(short) == 1
        assert short[0]["topic_path"] == "a.md"
        medium = store.get_medium()
        assert len(medium) == 1
        assert "a.md" in medium[0]["summary"] or "A" in medium[0]["summary"]


def test_memory_store_short_fifo(tmp_path: Path) -> None:
    """Short memory respects maxlen (FIFO)."""
    with patch.dict("os.environ", {"MEMORY_ENABLED": "1"}, clear=False):
        store = MemoryStore(tmp_path, short_limit=3, medium_limit=100, medium_ttl_days=7)
        for i in range(5):
            store.write_event("get_topic", {"topic_path": f"p{i}.md", "title": str(i)})
        short = store.get_short()
        assert len(short) == 3
        assert short[0]["topic_path"] == "p2.md"
        assert short[-1]["topic_path"] == "p4.md"


def test_format_medium_summary_topic_path_list(tmp_path: Path) -> None:
    """_format_medium_summary handles topic_path as list."""
    with patch.dict("os.environ", {"MEMORY_ENABLED": "1"}, clear=False):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        store.write_event("get_topic", {"topic_path": ["a.md", "b.md"], "query": "q"})
        medium = store.get_medium()
        assert len(medium) == 1
        assert "a.md" in medium[0]["summary"] and "b.md" in medium[0]["summary"]


def test_format_medium_summary_description(tmp_path: Path) -> None:
    """_format_medium_summary uses description or response_snippet."""
    with patch.dict("os.environ", {"MEMORY_ENABLED": "1"}, clear=False):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        store.write_event("save_snippet", {"description": "Test desc 123"})
        medium = store.get_medium()
        assert "Test desc 123" in medium[0]["summary"]


def test_append_medium_oserror(tmp_path: Path) -> None:
    """_append_medium handles OSError gracefully."""
    with patch.dict("os.environ", {"MEMORY_ENABLED": "1"}, clear=False):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        with patch("builtins.open", side_effect=OSError("disk full")):
            store._append_medium(1.0, "summary")


def test_trim_medium(tmp_path: Path) -> None:
    """_trim_medium trims old entries and limits count."""
    with patch.dict("os.environ", {"MEMORY_ENABLED": "1"}, clear=False):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=5, medium_ttl_days=7)
        for i in range(3):
            store.write_event("get_topic", {"topic_path": f"p{i}.md"})
        assert store.medium_path.exists()
        lines = store.medium_path.read_text().strip().split("\n")
        assert len(lines) <= 5


def test_trim_medium_json_decode_error(tmp_path: Path) -> None:
    """_trim_medium skips invalid JSON lines."""
    store = MemoryStore(tmp_path, short_limit=5, medium_limit=10, medium_ttl_days=7)
    store.medium_path.write_text('{"ts": 9999999999, "summary": "ok"}\ninvalid\n')
    store._trim_medium()
    assert store.medium_path.exists()


def test_write_long_or_pending_embedding_available(tmp_path: Path) -> None:
    """When embedding available, _write_long_or_pending upserts to Qdrant."""
    with patch.dict(
        "os.environ",
        {"MEMORY_ENABLED": "1", "QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"},
        clear=False,
    ):
        with patch("onec_help.embedding.is_embedding_available", return_value=True):
            with patch("onec_help.embedding.get_embedding", return_value=[0.1] * 384):
                with patch("qdrant_client.QdrantClient") as mock_qc:
                    mock_client = MagicMock()
                    mock_client.collection_exists.return_value = True
                    mock_qc.return_value = mock_client
                    store = MemoryStore(
                        tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7
                    )
                    store._write_long_or_pending(
                        "get_topic", {"topic_path": "a.md", "title": "A"}, 1.0
                    )
                    mock_client.upsert.assert_called_once()


def test_write_long_or_pending_embedding_fails_appends_pending(tmp_path: Path) -> None:
    """When get_embedding raises, _write_long_or_pending appends to pending."""
    with patch.dict("os.environ", {"MEMORY_ENABLED": "1"}, clear=False):
        with patch("onec_help.embedding.is_embedding_available", return_value=True):
            with patch("onec_help.embedding.get_embedding", side_effect=RuntimeError("API down")):
                store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
                store._write_long_or_pending("get_topic", {"topic_path": "a.md"}, 1.0)
                assert store.pending_path.exists()
                data = json.loads(store.pending_path.read_text())
                assert len(data) == 1
                assert data[0]["payload"]["topic_path"] == "a.md"


def test_append_pending(tmp_path: Path) -> None:
    """_append_pending creates and appends to pending file."""
    with patch.dict("os.environ", {"MEMORY_ENABLED": "1"}, clear=False):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        store._append_pending({"topic_path": "x.md"}, 1.0)
        assert store.pending_path.exists()
        data = json.loads(store.pending_path.read_text())
        assert len(data) == 1
        store._append_pending({"topic_path": "y.md"}, 2.0)
        data = json.loads(store.pending_path.read_text())
        assert len(data) == 2


def test_append_pending_existing_file(tmp_path: Path) -> None:
    """_append_pending appends to existing pending file."""
    store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
    store.pending_path.write_text('[{"id":"a","payload":{},"created_at":0}]')
    store._append_pending({"topic_path": "b.md"}, 1.0)
    data = json.loads(store.pending_path.read_text())
    assert len(data) == 2


def test_get_medium(tmp_path: Path) -> None:
    """get_medium returns records within TTL."""
    store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
    store.medium_path.write_text('{"ts": 9999999999, "summary": "recent"}\n')
    out = store.get_medium()
    assert len(out) == 1
    assert "recent" in out[0]["summary"]


def test_get_medium_empty_file(tmp_path: Path) -> None:
    """get_medium returns [] for empty or missing file."""
    store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
    assert store.get_medium() == []
    store.medium_path.write_text("")
    assert store.get_medium() == []


def test_process_pending_embedding_available(tmp_path: Path) -> None:
    """process_pending embeds and upserts when embedding available."""
    store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
    store.pending_path.write_text(
        json.dumps(
            [{"id": "id1", "payload": {"topic_path": "a.md", "title": "A"}, "created_at": 1.0}]
        )
    )
    with patch("onec_help.embedding.is_embedding_available", return_value=True):
        with patch("onec_help.embedding.get_embedding", return_value=[0.1] * 384):
            with patch("qdrant_client.QdrantClient") as mock_qc:
                mock_client = MagicMock()
                mock_client.collection_exists.return_value = True
                mock_qc.return_value = mock_client
                n = store.process_pending()
                assert n == 1
                mock_client.upsert.assert_called_once()


def test_process_pending_embedding_unavailable(tmp_path: Path) -> None:
    """process_pending returns 0 when embedding unavailable."""
    with patch("onec_help.embedding.is_embedding_available", return_value=False):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        store.pending_path.write_text('[{"id":"x","payload":{"a":1},"created_at":0}]')
        assert store.process_pending() == 0


def test_process_pending_no_file(tmp_path: Path) -> None:
    """process_pending returns 0 when no pending file."""
    with patch("onec_help.embedding.is_embedding_available", return_value=True):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        assert store.process_pending() == 0


def test_process_pending_invalid_data(tmp_path: Path) -> None:
    """process_pending handles invalid JSON or non-list."""
    with patch("onec_help.embedding.is_embedding_available", return_value=True):
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        store.pending_path.write_text("not json")
        assert store.process_pending() == 0
        store.pending_path.write_text("{}")
        assert store.process_pending() == 0


def test_search_long(tmp_path: Path) -> None:
    """search_long queries Qdrant and returns results."""
    with patch("onec_help.embedding.get_embedding", return_value=[0.1] * 384):
        with patch("qdrant_client.QdrantClient") as mock_qc:
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_point = MagicMock()
            mock_point.payload = {"topic_path": "a.md"}
            mock_point.score = 0.9
            mock_client.query_points.return_value = MagicMock(points=[mock_point])
            mock_qc.return_value = mock_client
            store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
            results = store.search_long("query", limit=5)
            assert len(results) == 1
            assert results[0]["payload"]["topic_path"] == "a.md"
            assert results[0]["score"] == 0.9


def test_search_long_no_collection(tmp_path: Path) -> None:
    """search_long returns [] when collection does not exist."""
    with patch("onec_help.embedding.get_embedding", return_value=[0.1] * 384):
        with patch("qdrant_client.QdrantClient") as mock_qc:
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = False
            mock_qc.return_value = mock_client
            store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
            assert store.search_long("query") == []


def test_search_long_with_domain_filter(tmp_path: Path) -> None:
    """search_long passes domain filter to Qdrant."""
    with patch("onec_help.embedding.get_embedding", return_value=[0.1] * 384):
        with patch("qdrant_client.QdrantClient") as mock_qc:
            mock_client = MagicMock()
            mock_client.collection_exists.return_value = True
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_qc.return_value = mock_client
            store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
            store.search_long("query", limit=3, domain="user")
            call_kw = mock_client.query_points.call_args[1]
            assert "query_filter" in call_kw


def test_upsert_long_exception(tmp_path: Path) -> None:
    """_upsert_long handles Qdrant exception gracefully."""
    with patch("qdrant_client.QdrantClient") as mock_qc:
        mock_qc.side_effect = RuntimeError("connection refused")
        store = MemoryStore(tmp_path, short_limit=5, medium_limit=100, medium_ttl_days=7)
        store._upsert_long("id", [0.1] * 384, {"topic_path": "a.md"})
