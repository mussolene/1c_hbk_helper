"""Tests for CLI."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from onec_help.cli import (
    _env_path,
    cmd_build_docs,
    cmd_build_index,
    cmd_index_status,
    cmd_ingest,
    cmd_load_snippets,
    cmd_load_standards,
    cmd_mcp,
    cmd_unpack,
    cmd_unpack_dir,
    cmd_watchdog,
    main,
)


def make_args(**kwargs) -> SimpleNamespace:
    """Create argparse.Namespace-like object for cmd_* tests."""
    return SimpleNamespace(**kwargs)


def test_cmd_build_docs(help_sample_dir: Path, tmp_path: Path) -> None:
    args = make_args(project_dir=str(help_sample_dir), output=str(tmp_path / "out_md"))
    assert cmd_build_docs(args) == 0
    assert (tmp_path / "out_md").exists()


@patch("onec_help.html2md.build_docs")
def test_cmd_build_docs_error(mock_build_docs, tmp_path: Path) -> None:
    mock_build_docs.side_effect = RuntimeError("disk full")
    tmp_path.mkdir(exist_ok=True)
    args = make_args(project_dir=str(tmp_path), output=str(tmp_path / "out_md"))
    assert cmd_build_docs(args) == 1


def test_cmd_unpack_fail() -> None:
    args = make_args(archive="/nonexistent.hbk", output_dir="/tmp/out")
    assert cmd_unpack(args) == 1


@patch("onec_help.unpack.unpack_hbk")
def test_cmd_unpack_success(mock_unpack, tmp_path: Path) -> None:
    (tmp_path / "fake.hbk").write_bytes(b"x")
    args = make_args(archive=str(tmp_path / "fake.hbk"), output_dir=str(tmp_path / "out"))
    assert cmd_unpack(args) == 0
    mock_unpack.assert_called_once()


@patch("onec_help.indexer.build_index")
def test_cmd_build_index(mock_build, help_sample_dir: Path) -> None:
    mock_build.return_value = 5
    args = make_args(directory=str(help_sample_dir), docs_dir=None)
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        assert cmd_build_index(args) == 0


@patch("onec_help.indexer.build_index")
def test_cmd_build_index_error(mock_build, help_sample_dir: Path) -> None:
    mock_build.side_effect = RuntimeError("Qdrant unavailable")
    args = make_args(directory=str(help_sample_dir), docs_dir=None)
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        assert cmd_build_index(args) == 1


def test_main_help() -> None:
    with patch("sys.argv", ["onec_help", "--help"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0


def test_main_unpack_usage() -> None:
    with patch("sys.argv", ["onec_help", "unpack", "--help"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0


@patch("onec_help.web.app")
def test_cmd_serve(mock_web_app, help_sample_dir: Path) -> None:
    from onec_help.cli import cmd_serve

    mock_web_app.config = {}
    mock_web_app.run = lambda **kw: None
    args = make_args(directory=str(help_sample_dir), debug=False)
    with patch.dict("os.environ", {"HELP_SERVE_ALLOWED_DIRS": str(help_sample_dir.parent)}, clear=False):
        assert cmd_serve(args) == 0


def test_cmd_serve_rejects_without_allowlist(help_sample_dir: Path) -> None:
    """serve requires HELP_SERVE_ALLOWED_DIRS; returns 1 when not set."""
    from onec_help.cli import cmd_serve

    args = make_args(directory=str(help_sample_dir), debug=False)
    with patch.dict("os.environ", {}, clear=True):
        env = {k: v for k, v in os.environ.items() if k != "HELP_SERVE_ALLOWED_DIRS"}
        with patch.dict("os.environ", env, clear=False):
            # Ensure HELP_SERVE_ALLOWED_DIRS is unset
            os.environ.pop("HELP_SERVE_ALLOWED_DIRS", None)
            assert cmd_serve(args) == 1


@patch("onec_help.web.app")
def test_cmd_serve_production_disables_debug(mock_web_app, help_sample_dir: Path) -> None:
    """When PRODUCTION=1 and debug=True, debug is disabled for security."""
    from onec_help.cli import cmd_serve

    mock_web_app.config = {}
    mock_run = MagicMock()
    mock_web_app.run = mock_run
    args = make_args(directory=str(help_sample_dir), debug=True)
    with patch.dict(
        "os.environ", {"PRODUCTION": "1", "HELP_SERVE_ALLOWED_DIRS": str(help_sample_dir.parent)}, clear=False
    ):
        assert cmd_serve(args) == 0
    call_kw = mock_run.call_args[1]
    assert call_kw.get("debug") is False


@patch("onec_help.ingest.read_ingest_status")
@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_ingest_backend_none(
    mock_status, mock_ingest, capsys: pytest.CaptureFixture[str]
) -> None:
    """index-status with ingest backend 'none' prints 'Embedding speed: none'."""
    mock_status.return_value = {"exists": True, "points_count": 10}
    mock_ingest.return_value = {
        "embedding_backend": "none",
        "status": "completed",
    }
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        assert cmd_index_status(make_args()) == 0
    out = capsys.readouterr().out
    assert "Embedding speed: none" in out


@patch("onec_help.ingest.read_ingest_status")
@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_ingest_speed_none(
    mock_status, mock_ingest, capsys: pytest.CaptureFixture[str]
) -> None:
    """index-status with ingest speed None prints 'Embedding speed: —'."""
    mock_status.return_value = {"exists": True, "points_count": 10}
    mock_ingest.return_value = {
        "embedding_backend": "openai_api",
        "elapsed_sec": 5.0,
        "status": "in progress",
    }
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        assert cmd_index_status(make_args()) == 0
    out = capsys.readouterr().out
    assert "Embedding speed: —" in out or "Embedding speed:" in out


@patch("onec_help.ingest.read_ingest_status")
@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_storage_path_not_dir(
    mock_status, mock_ingest, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When QDRANT_STORAGE_PATH exists but is not a directory, DB size shows dash."""
    mock_ingest.return_value = None
    mock_status.return_value = {"exists": True, "points_count": 10}
    f = tmp_path / "file"
    f.write_text("x")
    with patch.dict(
        "os.environ",
        {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333", "QDRANT_STORAGE_PATH": str(f)},
    ):
        assert cmd_index_status(make_args()) == 0
    out = capsys.readouterr().out
    assert "DB size" in out


@patch("onec_help.ingest.read_ingest_status")
@patch("onec_help.indexer.get_index_status")
@patch("os.walk")
def test_cmd_index_status_storage_path_oserror(
    mock_walk, mock_status, mock_ingest, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When os.walk raises OSError, DB size shows dash."""
    mock_ingest.return_value = None
    mock_status.return_value = {"exists": True, "points_count": 10}
    mock_walk.side_effect = OSError("permission denied")
    with patch.dict(
        "os.environ",
        {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333", "QDRANT_STORAGE_PATH": str(tmp_path)},
    ):
        assert cmd_index_status(make_args()) == 0
    out = capsys.readouterr().out
    assert "DB size" in out


@patch("onec_help.ingest.read_ingest_status")
@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_ingest_with_eta(
    mock_status, mock_ingest, capsys: pytest.CaptureFixture[str]
) -> None:
    """index-status with ingest ETA prints ETA seconds."""
    mock_status.return_value = {"exists": True, "points_count": 10}
    mock_ingest.return_value = {
        "embedding_backend": "openai_api",
        "status": "in progress",
        "eta_sec": 120,
        "elapsed_sec": 10.0,
    }
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        assert cmd_index_status(make_args()) == 0
    out = capsys.readouterr().out
    assert "ETA" in out or "120" in out


@patch("onec_help.ingest.read_ingest_status")
@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_ingest_with_current_workers(
    mock_status, mock_ingest, capsys: pytest.CaptureFixture[str]
) -> None:
    """index-status with ingest current workers shows 'Current (per thread)'."""
    mock_status.return_value = {"exists": True, "points_count": 10}
    mock_ingest.return_value = {
        "embedding_backend": "openai_api",
        "status": "in progress",
        "current": [{"path": "x", "version": "8.3", "language": "ru", "stage": "embed"}],
    }
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        assert cmd_index_status(make_args()) == 0
    out = capsys.readouterr().out
    assert "Current (per thread)" in out


@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_exists(mock_status) -> None:
    mock_status.return_value = {
        "exists": True,
        "collection": "onec_help",
        "points_count": 42,
        "versions": ["8.3.27"],
        "languages": ["ru"],
    }

    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        assert cmd_index_status(make_args()) == 0


@patch("onec_help.ingest.read_ingest_status")
@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_shows_embeddings_and_db_size(
    mock_status, mock_ingest, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """index-status shows Topics indexed, Embeddings (same as points), and DB size when QDRANT_STORAGE_PATH is set."""
    mock_ingest.return_value = None
    mock_status.return_value = {
        "exists": True,
        "collection": "onec_help",
        "points_count": 100,
    }
    (tmp_path / "some_file").write_bytes(b"x" * 500)  # ~0.5 KB

    with patch.dict(
        "os.environ",
        {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333", "QDRANT_STORAGE_PATH": str(tmp_path)},
    ):
        assert cmd_index_status(make_args()) == 0
    out = capsys.readouterr().out
    assert "Topics indexed: 100" in out
    assert "Embeddings: 100" in out
    assert "DB size:" in out
    assert "MB" in out


@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_not_exists(mock_status) -> None:
    mock_status.return_value = {"exists": False}

    assert cmd_index_status(make_args()) == 0


@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_error(mock_status) -> None:
    mock_status.return_value = {"error": "connection refused"}
    assert cmd_index_status(make_args()) == 1


@patch("onec_help.ingest.read_ingest_status")
@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_with_ingest(
    mock_status, mock_ingest, capsys: pytest.CaptureFixture[str]
) -> None:
    """index-status shows embedding speed, per-folder, total time when ingest status exists.
    When status is completed, current is empty so no stale workers are shown."""
    mock_status.return_value = {
        "exists": True,
        "collection": "onec_help",
        "points_count": 100,
        "versions": ["8.3"],
        "languages": ["ru"],
    }
    mock_ingest.return_value = {
        "embedding_backend": "openai_api",
        "embedding_speed_pts_per_sec": 12.5,
        "elapsed_sec": 8.0,
        "status": "completed",
        "total_elapsed_sec": 8.2,
        "current": [],  # cleared when ingest completes
        "folders": [
            {
                "version": "8.3",
                "language": "ru",
                "hbk_count": 1,
                "html_count": 50,
                "md_count": 100,
                "err_count": 0,
                "points": 100,
                "status": "done",
            },
        ],
    }

    assert cmd_index_status(make_args()) == 0
    out = capsys.readouterr().out
    assert "Current (per thread):" not in out  # completed => no worker list


@patch("onec_help.ingest.run_ingest")
def test_cmd_ingest_with_sources_env(mock_run_ingest, tmp_path: Path) -> None:
    mock_run_ingest.return_value = 10
    (tmp_path / "ver").mkdir()
    args = make_args(
        sources=None,
        sources_file=None,
        languages=None,
        temp_base=None,
        workers=2,
        max_tasks=None,
        quiet=False,
        dry_run=False,
        index_batch_size=500,
    )
    with patch.dict(
        "os.environ",
        {"HELP_SOURCE_BASE": str(tmp_path), "QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"},
    ):
        with patch("onec_help.ingest.discover_version_dirs") as mock_disc:
            mock_disc.return_value = [(tmp_path / "ver", "ver")]
            assert cmd_ingest(args) == 0
    mock_run_ingest.assert_called_once()


@patch("onec_help.ingest.run_ingest")
def test_cmd_ingest_sources_arg(mock_run_ingest) -> None:
    mock_run_ingest.return_value = 5
    args = make_args(
        sources=["/path/to/1cv8:8.3"],
        sources_file=None,
        languages=None,
        temp_base="/tmp/t",
        workers=1,
        max_tasks=None,
        quiet=True,
        dry_run=False,
        index_batch_size=500,
    )
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}, clear=False):
        assert cmd_ingest(args) == 0
    mock_run_ingest.assert_called_once()
    call_kw = mock_run_ingest.call_args[1]
    assert call_kw["source_dirs_with_versions"] == [("/path/to/1cv8", "8.3")]


def test_env_path() -> None:
    assert _env_path("NONEXISTENT_VAR") is None
    with patch.dict("os.environ", {"TEST_VAR": "/path"}):
        assert _env_path("TEST_VAR") == "/path"
    with patch.dict("os.environ", {"PORT": "8080"}):
        assert _env_path("PORT", "5000") == "8080"
    assert _env_path("MISSING", "default") == "default"


def test_cmd_ingest_no_sources_returns_error() -> None:
    args = make_args(
        sources=None,
        sources_file=None,
        languages=None,
        temp_base=None,
        workers=1,
        max_tasks=None,
        quiet=False,
        dry_run=False,
        index_batch_size=500,
    )
    with patch.dict("os.environ", {}, clear=True):
        assert cmd_ingest(args) == 1


@patch("onec_help.ingest.run_unpack_only")
def test_cmd_unpack_dir_sources_path_version(mock_run, tmp_path: Path) -> None:
    """cmd_unpack_dir parses sources as path:version."""
    mock_run.return_value = 1
    out = tmp_path / "out"
    out.mkdir()
    args = make_args(
        source_dir="",
        output_dir=str(out),
        sources=["/path/to/1cv8:8.3"],
        languages=None,
        workers=1,
    )
    assert cmd_unpack_dir(args) == 0
    call_kw = mock_run.call_args[1]
    assert call_kw["source_dirs_with_versions"] == [("/path/to/1cv8", "8.3")]


@patch("onec_help.ingest.run_unpack_only")
def test_cmd_unpack_dir_sources_path_only(mock_run, tmp_path: Path) -> None:
    """cmd_unpack_dir with single path (no colon) uses path name as version."""
    mock_run.return_value = 1
    out = tmp_path / "out"
    out.mkdir()
    args = make_args(
        source_dir="",
        output_dir=str(out),
        sources=["/single/path"],
        languages=None,
        workers=1,
    )
    assert cmd_unpack_dir(args) == 0
    call_kw = mock_run.call_args[1]
    assert len(call_kw["source_dirs_with_versions"]) == 1
    assert call_kw["source_dirs_with_versions"][0][0] == "/single/path"


def test_cmd_unpack_dir_no_sources_error(tmp_path: Path) -> None:
    """When no sources and no HELP_SOURCE_BASE, cmd_unpack_dir returns 1."""
    args = make_args(
        source_dir="",
        output_dir=str(tmp_path / "out"),
        sources=None,
        languages=None,
        workers=1,
    )
    with patch.dict("os.environ", {}, clear=True):
        assert cmd_unpack_dir(args) == 1


@patch("onec_help.ingest.run_unpack_only")
def test_cmd_unpack_dir_success(mock_run, tmp_path: Path) -> None:
    mock_run.return_value = 2
    args = make_args(
        source_dir=str(tmp_path),
        output_dir=str(tmp_path / "out"),
        sources=None,
        languages="ru",
        workers=1,
        quiet=True,
    )
    assert cmd_unpack_dir(args) == 0
    mock_run.assert_called_once()


@patch("onec_help.ingest.run_ingest")
def test_cmd_ingest_sources_file(mock_run, tmp_path: Path) -> None:
    mock_run.return_value = 3
    sf = tmp_path / "sources.txt"
    sf.write_text("/path/1:ver1\n/path/2:ver2\n", encoding="utf-8")
    args = make_args(
        sources=None,
        sources_file=str(sf),
        languages=None,
        temp_base=None,
        workers=1,
        max_tasks=None,
        quiet=True,
        dry_run=False,
        index_batch_size=500,
    )
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}, clear=False):
        assert cmd_ingest(args) == 0
    call_kw = mock_run.call_args[1]
    assert len(call_kw["source_dirs_with_versions"]) == 2


@patch("onec_help.ingest.run_ingest")
def test_cmd_ingest_sources_file_path_only(mock_run, tmp_path: Path) -> None:
    """sources_file with lines without colon uses path name as version."""
    mock_run.return_value = 1
    sf = tmp_path / "list.txt"
    sf.write_text("/only/path\n", encoding="utf-8")
    args = make_args(
        sources=None,
        sources_file=str(sf),
        languages=None,
        temp_base=None,
        workers=1,
        max_tasks=None,
        quiet=True,
        dry_run=False,
        index_batch_size=500,
    )
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}, clear=False):
        assert cmd_ingest(args) == 0
    call_kw = mock_run.call_args[1]
    assert len(call_kw["source_dirs_with_versions"]) == 1
    assert call_kw["source_dirs_with_versions"][0][0] == "/only/path"


@patch("onec_help.ingest.run_ingest")
def test_cmd_ingest_exception(mock_run) -> None:
    mock_run.side_effect = RuntimeError("Qdrant down")
    args = make_args(
        sources=["/x:v"],
        sources_file=None,
        languages=None,
        temp_base=None,
        workers=1,
        max_tasks=None,
        quiet=True,
        dry_run=False,
        index_batch_size=500,
    )
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}, clear=False):
        assert cmd_ingest(args) == 1


@patch("onec_help.watchdog.run_watchdog")
def test_cmd_watchdog_success(mock_run_watchdog) -> None:
    """cmd_watchdog calls run_watchdog with poll/pending intervals and returns 0."""
    args = make_args(poll_interval=120, pending_interval=300)
    assert cmd_watchdog(args) == 0
    mock_run_watchdog.assert_called_once_with(
        poll_interval_sec=120,
        pending_interval_sec=300,
    )


@patch("onec_help.watchdog.run_watchdog")
def test_cmd_watchdog_exception(mock_run_watchdog) -> None:
    """cmd_watchdog returns 1 when run_watchdog raises."""
    mock_run_watchdog.side_effect = RuntimeError("watchdog error")
    args = make_args(poll_interval=60, pending_interval=60)
    assert cmd_watchdog(args) == 1


@patch("onec_help.watchdog.run_watchdog")
def test_cmd_watchdog_keyboard_interrupt(mock_run_watchdog) -> None:
    """cmd_watchdog returns 0 on KeyboardInterrupt (graceful exit)."""
    mock_run_watchdog.side_effect = KeyboardInterrupt
    args = make_args(poll_interval=60, pending_interval=60)
    assert cmd_watchdog(args) == 0


@patch("onec_help.mcp_server.run_mcp")
def test_cmd_mcp_run_raises(mock_run_mcp) -> None:
    """When run_mcp raises (e.g. fastmcp required), cmd_mcp returns 1."""
    mock_run_mcp.side_effect = RuntimeError("fastmcp required: pip install fastmcp")
    args = make_args(directory="/tmp", transport=None, host=None, port=None, path=None)
    assert cmd_mcp(args) == 1


def test_cmd_load_snippets_file_not_found() -> None:
    """cmd_load_snippets returns 1 when path does not exist."""
    args = make_args(snippets_file="/nonexistent/snippets.json")
    assert cmd_load_snippets(args) == 1


def test_cmd_load_snippets_no_source(capsys) -> None:
    """cmd_load_snippets returns 0 with message when no path and no SNIPPETS_DIR."""
    with patch.dict("os.environ", {"SNIPPETS_JSON_PATH": "", "SNIPPETS_DIR": ""}, clear=False):
        args = make_args(snippets_file=None)
        assert cmd_load_snippets(args) == 0
    out = capsys.readouterr().err
    assert "No source" in out or "examples only" in out


def test_cmd_load_snippets_invalid_json(tmp_path: Path) -> None:
    """cmd_load_snippets returns 1 when JSON is invalid."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    args = make_args(snippets_file=str(bad))
    assert cmd_load_snippets(args) == 1


def test_cmd_load_snippets_not_array(tmp_path: Path) -> None:
    """cmd_load_snippets returns 1 when JSON is not an array."""
    bad = tmp_path / "bad.json"
    bad.write_text('{"title": "x"}')
    args = make_args(snippets_file=str(bad))
    assert cmd_load_snippets(args) == 1


@patch("onec_help.memory.get_memory_store")
def test_cmd_load_snippets_success(mock_get_store, tmp_path: Path) -> None:
    """cmd_load_snippets loads snippets and prints count."""
    snippet_file = tmp_path / "snippets.json"
    snippet_file.write_text(
        '[{"title": "Test", "description": "desc", "code_snippet": "Сообщить(1);"}]',
        encoding="utf-8",
    )
    mock_store = MagicMock()
    mock_store.upsert_curated_snippets.return_value = 1
    mock_get_store.return_value = mock_store
    args = make_args(snippets_file=str(snippet_file))
    assert cmd_load_snippets(args) == 0
    mock_store.upsert_curated_snippets.assert_called_once()
    call_args = mock_store.upsert_curated_snippets.call_args[0][0]
    assert len(call_args) == 1
    assert call_args[0]["title"] == "Test"


def test_main_load_snippets(tmp_path: Path) -> None:
    """main() parses load-snippets and invokes cmd_load_snippets."""
    snippet_file = tmp_path / "snippets.json"
    snippet_file.write_text('[{"title": "X", "code_snippet": "x"}]', encoding="utf-8")
    with patch("onec_help.memory.get_memory_store") as mock_get:
        mock_store = MagicMock()
        mock_store.upsert_curated_snippets.return_value = 1
        mock_get.return_value = mock_store
        with patch("sys.argv", ["onec_help", "load-snippets", str(snippet_file)]):
            assert main() == 0
        mock_store.upsert_curated_snippets.assert_called_once()


def test_cmd_load_snippets_exception(tmp_path: Path) -> None:
    """cmd_load_snippets returns 1 when get_memory_store raises."""
    snippet_file = tmp_path / "snippets.json"
    snippet_file.write_text('[{"title": "X", "code_snippet": "x"}]', encoding="utf-8")
    with patch("onec_help.memory.get_memory_store", side_effect=RuntimeError("no qdrant")):
        args = make_args(snippets_file=str(snippet_file))
        assert cmd_load_snippets(args) == 1


@patch("onec_help.memory.get_memory_store")
def test_cmd_load_snippets_from_folder(mock_get_store, tmp_path: Path) -> None:
    """cmd_load_snippets loads from folder (*.bsl, *.1c, *.json) when path is directory."""
    (tmp_path / "example.bsl").write_text("Сообщить(1);", encoding="utf-8")
    (tmp_path / "other.1c").write_text("Возврат Истина;", encoding="utf-8")
    (tmp_path / "extra.json").write_text(
        '[{"title":"FromJSON","description":"","code_snippet":"Возврат;"}]', encoding="utf-8"
    )
    mock_store = MagicMock()
    mock_store.upsert_curated_snippets.return_value = 3
    mock_get_store.return_value = mock_store
    args = make_args(snippets_file=str(tmp_path))
    assert cmd_load_snippets(args) == 0
    mock_store.upsert_curated_snippets.assert_called_once()
    items = mock_store.upsert_curated_snippets.call_args[0][0]
    assert len(items) == 3
    titles = {it["title"] for it in items}
    assert titles == {"example", "other", "FromJSON"}


def test_cmd_load_standards_no_source(capsys) -> None:
    """cmd_load_standards returns 0 when no path, no STANDARDS_DIR, no STANDARDS_REPO."""
    args = make_args(standards_path=None)
    with patch.dict("os.environ", {"STANDARDS_DIR": "", "STANDARDS_REPO": ""}):
        assert cmd_load_standards(args) == 0
    err = capsys.readouterr().err
    assert "No source" in err and ("STANDARDS_REPO" in err or "STANDARDS_DIR" in err)


@patch("onec_help.memory.get_memory_store")
def test_cmd_load_standards_success(mock_get_store, tmp_path: Path) -> None:
    """cmd_load_standards loads markdown and upserts with domain=standards."""
    (tmp_path / "rule.md").write_text("# Проверка\n\nОписание правила.", encoding="utf-8")
    mock_store = MagicMock()
    mock_store.upsert_curated_snippets.return_value = 1
    mock_get_store.return_value = mock_store
    args = make_args(standards_path=str(tmp_path))
    assert cmd_load_standards(args) == 0
    mock_store.upsert_curated_snippets.assert_called_once()
    call_kw = mock_store.upsert_curated_snippets.call_args[1]
    assert call_kw.get("domain") == "standards"


@patch("onec_help.memory.get_memory_store")
@patch("onec_help.standards_loader.fetch_repo_archive")
def test_cmd_load_standards_from_repo(mock_fetch, mock_get_store, tmp_path: Path) -> None:
    """cmd_load_standards fetches from STANDARDS_REPO when no path given."""
    (tmp_path / "fetched.md").write_text("# Fetched rule\n\nContent.", encoding="utf-8")
    mock_fetch.return_value = (tmp_path, Path("/tmp/nonexistent_standards_xxx"))
    mock_store = MagicMock()
    mock_store.upsert_curated_snippets.return_value = 1
    mock_get_store.return_value = mock_store
    args = make_args(standards_path=None)
    with patch.dict(
        "os.environ",
        {"STANDARDS_DIR": "", "STANDARDS_REPO": "https://github.com/1C-Company/v8-code-style"},
    ):
        assert cmd_load_standards(args) == 0
    mock_fetch.assert_called_once()
    mock_store.upsert_curated_snippets.assert_called_once()


@patch("onec_help.indexer.get_index_status")
def test_main_index_status(mock_status) -> None:
    """main() parses argv and invokes cmd_index_status."""
    mock_status.return_value = {"exists": True, "points_count": 10, "collection": "onec_help"}
    with patch("sys.argv", ["onec_help", "index-status"]):
        from onec_help.cli import main

        assert main() == 0
    mock_status.assert_called_once()
