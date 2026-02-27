"""Tests for ingest module: collect tasks, discover versions, parse env, run_ingest (dry_run / empty)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from onec_help.ingest import (
    _file_sha256,
    _language_from_filename,
    _load_ingest_cache,
    _update_ingest_cache_entry,
    _write_ingest_status,
    collect_hbk_tasks,
    discover_version_dirs,
    parse_languages_env,
    parse_source_dirs_env,
    read_ingest_status,
    run_ingest,
    run_unpack_only,
)


def test_language_from_filename() -> None:
    assert _language_from_filename("1cv8_ru.hbk") == "ru"
    assert _language_from_filename("shcntx_en.HBK") == "en"
    assert _language_from_filename("other.hbk") is None
    assert _language_from_filename("no_ext") is None


def test_collect_hbk_tasks_empty_sources() -> None:
    assert collect_hbk_tasks([], None) == []
    assert collect_hbk_tasks([], ["ru"]) == []


def test_collect_hbk_tasks_no_dir(tmp_path: Path) -> None:
    assert collect_hbk_tasks([(tmp_path / "missing", "v1")], None) == []


def test_collect_hbk_tasks_filters_language(tmp_path: Path) -> None:
    sub = tmp_path / "8.3"
    sub.mkdir()
    (sub / "1cv8_ru.hbk").write_bytes(b"x")
    (sub / "1cv8_en.hbk").write_bytes(b"y")
    tasks = collect_hbk_tasks([(tmp_path, "8.3")], ["ru"])
    paths = [t[0] for t in tasks]
    assert len(paths) == 1
    assert paths[0].name == "1cv8_ru.hbk"


def test_collect_hbk_tasks_all_languages(tmp_path: Path) -> None:
    sub = tmp_path / "v"
    sub.mkdir()
    (sub / "1cv8_ru.hbk").write_bytes(b"x")
    (sub / "1cv8_en.hbk").write_bytes(b"y")
    tasks = collect_hbk_tasks([(tmp_path, "v")], None)
    assert len(tasks) == 2
    names = {t[0].name for t in tasks}
    assert names == {"1cv8_ru.hbk", "1cv8_en.hbk"}


def test_collect_hbk_tasks_skips_no_lang(tmp_path: Path) -> None:
    sub = tmp_path / "v"
    sub.mkdir()
    (sub / "plain.hbk").write_bytes(b"x")
    tasks = collect_hbk_tasks([(tmp_path, "v")], None)
    assert len(tasks) == 0


def test_discover_version_dirs_empty(tmp_path: Path) -> None:
    assert discover_version_dirs(tmp_path) == []


def test_discover_version_dirs_ignores_files(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("x")
    assert discover_version_dirs(tmp_path) == []


def test_discover_version_dirs_ignores_hidden(tmp_path: Path) -> None:
    (tmp_path / ".hidden").mkdir()
    assert discover_version_dirs(tmp_path) == []


def test_discover_version_dirs_returns_subdirs(tmp_path: Path) -> None:
    (tmp_path / "8.3.27").mkdir()
    (tmp_path / "8.3.26").mkdir()
    result = discover_version_dirs(tmp_path)
    assert len(result) == 2
    names = {r[1] for r in result}
    assert names == {"8.3.27", "8.3.26"}


def test_file_sha256(tmp_path: Path) -> None:
    """_file_sha256 returns hex digest of file contents; same content => same hash."""
    f = tmp_path / "a.hbk"
    f.write_bytes(b"hello")
    h1 = _file_sha256(f)
    assert h1 is not None
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)
    f.write_bytes(b"hello")
    assert _file_sha256(f) == h1
    f.write_bytes(b"world")
    assert _file_sha256(f) != h1


def test_file_sha256_missing() -> None:
    """_file_sha256 returns None for non-existent file."""
    assert _file_sha256(Path("/nonexistent/file.hbk")) is None


def test_load_ingest_cache_error_returns_empty(tmp_path: Path) -> None:
    """When cache read raises, _load_ingest_cache returns empty dict."""
    with patch.dict("os.environ", {"INGEST_CACHE_FILE": "/nonexistent/cache.db"}, clear=False):
        with patch("onec_help.ingest.sqlite3.connect", side_effect=OSError("read-only")):
            c = _load_ingest_cache()
    assert c == {}


def test_load_save_ingest_cache(tmp_path: Path) -> None:
    """_load_ingest_cache returns entries from SQLite; _update_ingest_cache_entry persists one row."""
    cache_file = tmp_path / "cache.db"
    with patch.dict("os.environ", {"INGEST_CACHE_FILE": str(cache_file)}, clear=False):
        c = _load_ingest_cache()
        assert c == {}
        _update_ingest_cache_entry("v/ru/1cv8.hbk", "abc", 10)
        c2 = _load_ingest_cache()
        assert c2["v/ru/1cv8.hbk"] == {"hash": "abc", "indexed": True, "points": 10}


def test_run_ingest_skips_cached(tmp_path: Path) -> None:
    """When cache has same-hash entry with indexed=true, task is skipped (no unpack/index)."""
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    cache_file = tmp_path / "cache.db"
    key = "v/ru/1cv8_ru.hbk"
    h = _file_sha256(tmp_path / "v" / "1cv8_ru.hbk")
    with patch.dict("os.environ", {"INGEST_CACHE_FILE": str(cache_file)}, clear=False):
        _update_ingest_cache_entry(key, h, 5)
        with patch("onec_help.indexer.build_index") as mock_idx:
            with patch("onec_help.html2md.build_docs") as mock_docs:
                with patch("onec_help.unpack.unpack_hbk") as mock_unpack:
                    n = run_ingest(
                        source_dirs_with_versions=[(tmp_path, "v")],
                        languages=["ru"],
                        temp_base=tmp_path / "temp",
                        max_workers=1,
                        verbose=False,
                    )
    assert n == 0
    mock_unpack.assert_not_called()
    mock_docs.assert_not_called()
    mock_idx.assert_not_called()


def test_write_ingest_status_completed_clears_current(tmp_path: Path) -> None:
    """When status is completed, written JSON has current=[] so no stale workers are shown."""
    import json

    status_file = str(tmp_path / "status.json")
    _write_ingest_status(
        status_file,
        started_at=0.0,
        embedding_backend="local",
        total_tasks=2,
        done_tasks=2,
        total_points=100,
        folders=[],
        status="completed",
        finished_at=1.0,
    )
    data = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert data["current"] == []


def test_read_ingest_status_missing() -> None:
    """read_ingest_status returns None when file does not exist."""
    assert read_ingest_status("/nonexistent/path/status.json") is None


def test_read_ingest_status_exists(tmp_path: Path) -> None:
    """read_ingest_status returns parsed JSON when file exists."""
    status_file = tmp_path / "status.json"
    status_file.write_text(
        '{"status": "completed", "embedding_backend": "local", "total_points": 10}',
        encoding="utf-8",
    )
    out = read_ingest_status(str(status_file))
    assert out is not None
    assert out["status"] == "completed"
    assert out["embedding_backend"] == "local"
    assert out["total_points"] == 10


def test_parse_source_dirs_env_empty() -> None:
    assert parse_source_dirs_env("") == []
    assert parse_source_dirs_env(None) == []


def test_parse_source_dirs_env_path_only() -> None:
    out = parse_source_dirs_env("/opt/1cv8")
    assert out == [("/opt/1cv8", "1cv8")]


def test_parse_source_dirs_env_path_version() -> None:
    out = parse_source_dirs_env("/opt/1cv8:8.3.27")
    assert out == [("/opt/1cv8", "8.3.27")]


def test_parse_source_dirs_env_multiple() -> None:
    out = parse_source_dirs_env("/a:va,/b:vb")
    assert out == [("/a", "va"), ("/b", "vb")]


def test_parse_languages_env_empty() -> None:
    assert parse_languages_env("") is None
    assert parse_languages_env(None) is None


def test_parse_languages_env_all() -> None:
    assert parse_languages_env("all") is None


def test_parse_languages_env_single() -> None:
    assert parse_languages_env("ru") == ["ru"]


def test_parse_languages_env_multi() -> None:
    assert parse_languages_env("ru,en") == ["ru", "en"]


def test_run_ingest_dry_run(tmp_path: Path) -> None:
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    n = run_ingest(
        source_dirs_with_versions=[(tmp_path, "v")],
        languages=["ru"],
        temp_base=tmp_path / "temp",
        dry_run=True,
        verbose=True,
    )
    assert n == 0


def test_run_ingest_dry_run_many_tasks(tmp_path: Path) -> None:
    """Dry run with >25 tasks hits the '... and N more' log branch."""
    (tmp_path / "v").mkdir()
    for i in range(30):
        (tmp_path / "v" / f"1cv8_ru_{i}.hbk").write_bytes(b"x")
    n = run_ingest(
        source_dirs_with_versions=[(tmp_path, "v")],
        languages=["ru"],
        temp_base=tmp_path / "temp",
        dry_run=True,
        verbose=True,
    )
    assert n == 0


@patch("onec_help.ingest._unpack_and_build_docs")
@patch("qdrant_client.QdrantClient")
def test_run_ingest_max_tasks(mock_qdrant: MagicMock, mock_task: MagicMock, tmp_path: Path) -> None:
    """max_tasks limits how many .hbk are processed."""
    (tmp_path / "v").mkdir()
    # Names must match LANG_PATTERN (*_ru.hbk) so collect_hbk_tasks returns them
    for name in ("a_ru.hbk", "b_ru.hbk", "c_ru.hbk", "d_ru.hbk", "e_ru.hbk"):
        (tmp_path / "v" / name).write_bytes(b"x")
    mock_task.return_value = (None, None, "v", "ru", "skip")
    mock_qdrant.return_value.collection_exists.return_value = True
    n = run_ingest(
        source_dirs_with_versions=[(tmp_path, "v")],
        languages=["ru"],
        temp_base=tmp_path / "temp",
        max_tasks=2,
        max_workers=1,
        verbose=False,
    )
    assert mock_task.call_count == 2, "_unpack_and_build_docs should be called max_tasks=2 times"
    assert n == 0


def test_discover_version_dirs_not_dir(tmp_path: Path) -> None:
    """When base is a file or missing, returns []."""
    assert discover_version_dirs(tmp_path / "missing") == []
    (tmp_path / "file").write_text("x")
    assert discover_version_dirs(tmp_path / "file") == []


def test_parse_source_dirs_env_blank_parts() -> None:
    """Blank and comma-only parts are skipped."""
    assert parse_source_dirs_env("  ,  /a:v1  ,  ") == [("/a", "v1")]


def test_run_ingest_empty_sources() -> None:
    n = run_ingest(
        source_dirs_with_versions=[],
        temp_base="/tmp/help_ingest",
    )
    assert n == 0


def test_run_ingest_no_tasks(tmp_path: Path) -> None:
    (tmp_path / "v").mkdir()
    # no .hbk files
    n = run_ingest(
        source_dirs_with_versions=[(tmp_path, "v")],
        languages=["ru"],
        temp_base=tmp_path / "temp",
    )
    assert n == 0


def test_run_unpack_only_empty(tmp_path: Path) -> None:
    n = run_unpack_only(
        source_dirs_with_versions=[],
        output_dir=tmp_path,
        verbose=False,
    )
    assert n == 0


def test_run_unpack_only_no_tasks(tmp_path: Path) -> None:
    (tmp_path / "v").mkdir()
    n = run_unpack_only(
        source_dirs_with_versions=[(tmp_path, "v")],
        output_dir=tmp_path / "out",
        languages=["ru"],
        verbose=False,
    )
    assert n == 0


@patch("onec_help.unpack.unpack_hbk")
def test_run_unpack_only_one_archive(mock_unpack: MagicMock, tmp_path: Path) -> None:
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    out = tmp_path / "output"
    n = run_unpack_only(
        source_dirs_with_versions=[(tmp_path, "v")],
        output_dir=out,
        languages=["ru"],
        max_workers=1,
        verbose=False,
    )
    assert n == 1
    mock_unpack.assert_called_once()
    call_args = mock_unpack.call_args[0]
    assert call_args[0].name == "1cv8_ru.hbk"
    assert (out / "v" / "ru" / "1cv8_ru").exists()


@patch("onec_help.indexer.build_index")
@patch("onec_help.html2md.build_docs")
@patch("onec_help.unpack.unpack_hbk")
@patch("qdrant_client.QdrantClient")
def test_run_ingest_unpack_fails_one_task(
    mock_qdrant: MagicMock,
    mock_unpack: MagicMock,
    mock_build_docs: MagicMock,
    mock_build_index: MagicMock,
    tmp_path: Path,
) -> None:
    """When unpack raises, task is skipped and no index call for that task."""
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    mock_unpack.side_effect = RuntimeError("7z failed")
    mock_qdrant.return_value.collection_exists.return_value = True
    n = run_ingest(
        source_dirs_with_versions=[(tmp_path, "v")],
        languages=["ru"],
        temp_base=tmp_path / "temp",
        max_workers=1,
        verbose=False,
    )
    assert n == 0
    mock_build_index.assert_not_called()


@patch("onec_help.indexer.build_index")
@patch("onec_help.html2md.build_docs")
@patch("onec_help.unpack.unpack_hbk")
@patch("qdrant_client.QdrantClient")
def test_run_ingest_integration_mock(
    mock_qdrant: MagicMock,
    mock_unpack: MagicMock,
    mock_build_docs: MagicMock,
    mock_build_index: MagicMock,
    tmp_path: Path,
) -> None:
    """Run ingest with one .hbk; unpack and build_docs succeed; index is called."""
    (tmp_path / "v").mkdir()
    hbk = tmp_path / "v" / "1cv8_ru.hbk"
    hbk.write_bytes(b"x")
    md_dir = tmp_path / "temp" / "v" / "ru" / "1cv8_ru" / "md"
    md_dir.mkdir(parents=True)
    (md_dir / "one.md").write_text("# One\n\nBody.", encoding="utf-8")
    mock_build_docs.side_effect = lambda src, out: (out / "one.md").write_text(
        "# One\n\nBody.", encoding="utf-8"
    )

    mock_build_index.return_value = 1
    mock_qdrant.return_value.collection_exists.return_value = False

    with patch.dict("os.environ", {"INGEST_CACHE_FILE": str(tmp_path / "cache.json")}, clear=False):
        n = run_ingest(
            source_dirs_with_versions=[(tmp_path, "v")],
            languages=["ru"],
            temp_base=tmp_path / "temp",
            qdrant_host="localhost",
            qdrant_port=6333,
            max_workers=1,
            verbose=False,
        )
    assert mock_unpack.called
    assert mock_build_index.return_value == 1
    assert n >= 1


@patch("onec_help.unpack.unpack_hbk")
def test_run_unpack_only_two_workers(mock_unpack: MagicMock, tmp_path: Path) -> None:
    """run_unpack_only with max_workers=2 uses thread pool."""
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    (tmp_path / "v" / "1cv8_en.hbk").write_bytes(b"y")
    out = tmp_path / "out"
    n = run_unpack_only(
        source_dirs_with_versions=[(tmp_path, "v")],
        output_dir=out,
        languages=None,
        max_workers=2,
        verbose=False,
    )
    assert n == 2
    assert mock_unpack.call_count == 2


def test_run_ingest_temp_base_creation_fails(tmp_path: Path) -> None:
    """When temp_base cannot be created, run_ingest raises RuntimeError."""
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    real_mkdir = Path.mkdir
    first_call = [True]

    def mkdir_raise_first(self, *args, **kwargs):
        if first_call[0]:
            first_call[0] = False
            raise OSError(13, "Permission denied")
        return real_mkdir(self, *args, **kwargs)

    with patch.object(Path, "mkdir", mkdir_raise_first):
        with pytest.raises(RuntimeError, match="Cannot create temp dir"):
            run_ingest(
                source_dirs_with_versions=[(tmp_path, "v")],
                languages=["ru"],
                temp_base=tmp_path / "temp",
                max_workers=1,
            )


@patch("onec_help.indexer.build_index")
@patch("onec_help.html2md.build_docs")
@patch("onec_help.unpack.unpack_hbk")
@patch("qdrant_client.QdrantClient")
def test_run_ingest_failed_log(
    mock_qdrant: MagicMock,
    mock_unpack: MagicMock,
    mock_build_docs: MagicMock,
    mock_build_index: MagicMock,
    tmp_path: Path,
) -> None:
    """When some tasks fail, INGEST_FAILED_LOG is written if set."""
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    mock_unpack.side_effect = RuntimeError("7z failed")
    mock_qdrant.return_value.collection_exists.return_value = True
    fail_log = tmp_path / "failed.txt"
    with patch.dict(
        "os.environ",
        {"INGEST_FAILED_LOG": str(fail_log), "INGEST_CACHE_FILE": str(tmp_path / "cache.json")},
        clear=False,
    ):
        n = run_ingest(
            source_dirs_with_versions=[(tmp_path, "v")],
            languages=["ru"],
            temp_base=tmp_path / "temp",
            max_workers=1,
            verbose=True,
        )
    assert n == 0
    assert fail_log.exists()
    assert "1cv8_ru" in fail_log.read_text()


@patch("onec_help.indexer.build_index")
@patch("onec_help.html2md.build_docs")
@patch("onec_help.unpack.unpack_hbk")
@patch("qdrant_client.QdrantClient")
def test_run_ingest_failed_log_write_raises(
    mock_qdrant: MagicMock,
    mock_unpack: MagicMock,
    mock_build_docs: MagicMock,
    mock_build_index: MagicMock,
    tmp_path: Path,
) -> None:
    """When writing INGEST_FAILED_LOG raises OSError, ingest still completes and logs the error."""
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "1cv8_ru.hbk").write_bytes(b"x")
    mock_unpack.side_effect = RuntimeError("7z failed")
    mock_qdrant.return_value.collection_exists.return_value = True
    fail_log = tmp_path / "failed.txt"
    real_open = open

    def open_raise_for_fail_log(path, mode="r", *args, **kwargs):
        if path == str(fail_log) and "w" in mode:
            raise OSError(13, "Permission denied")
        return real_open(path, mode, *args, **kwargs)

    with patch.dict(
        "os.environ",
        {"INGEST_FAILED_LOG": str(fail_log), "INGEST_CACHE_FILE": str(tmp_path / "cache2.json")},
        clear=False,
    ):
        with patch("builtins.open", open_raise_for_fail_log):
            n = run_ingest(
                source_dirs_with_versions=[(tmp_path, "v")],
                languages=["ru"],
                temp_base=tmp_path / "temp",
                max_workers=1,
                verbose=True,
            )
    assert n == 0
