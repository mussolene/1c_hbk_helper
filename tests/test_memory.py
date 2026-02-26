"""Tests for memory module."""

from pathlib import Path
from unittest.mock import patch

from onec_help.memory import MemoryStore, _is_memory_enabled


def test_memory_disabled_by_default() -> None:
    assert _is_memory_enabled() is False


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
