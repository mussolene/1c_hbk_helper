"""Tests for CLI."""
from pathlib import Path
from unittest.mock import patch

import pytest

from onec_help.cli import (
    cmd_build_docs,
    cmd_build_index,
    cmd_ingest,
    cmd_index_status,
    cmd_unpack,
    main,
)


def test_cmd_build_docs(help_sample_dir: Path, tmp_path: Path) -> None:
    class Args:
        project_dir = str(help_sample_dir)
        output = str(tmp_path / "out_md")
    assert cmd_build_docs(Args()) == 0
    assert (tmp_path / "out_md").exists()


def test_cmd_unpack_fail() -> None:
    class Args:
        archive = "/nonexistent.hbk"
        output_dir = "/tmp/out"
    assert cmd_unpack(Args()) == 1


@patch("onec_help.indexer.build_index")
def test_cmd_build_index(mock_build, help_sample_dir: Path) -> None:
    mock_build.return_value = 5
    class Args:
        directory = str(help_sample_dir)
        docs_dir = None
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        assert cmd_build_index(Args()) == 0


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
    class Args:
        directory = str(help_sample_dir)
        debug = False
    from onec_help.cli import cmd_serve
    mock_web_app.config = {}
    mock_web_app.run = lambda **kw: None
    assert cmd_serve(Args()) == 0


@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_exists(mock_status) -> None:
    mock_status.return_value = {
        "exists": True,
        "collection": "onec_help",
        "points_count": 42,
        "versions": ["8.3.27"],
        "languages": ["ru"],
    }
    class Args:
        pass
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        assert cmd_index_status(Args()) == 0


@patch("onec_help.indexer.get_index_status")
def test_cmd_index_status_not_exists(mock_status) -> None:
    mock_status.return_value = {"exists": False}
    class Args:
        pass
    assert cmd_index_status(Args()) == 0


@patch("onec_help.ingest.run_ingest")
def test_cmd_ingest_with_sources_env(mock_run_ingest, tmp_path: Path) -> None:
    mock_run_ingest.return_value = 10
    class Args:
        sources = None
        sources_file = None
        languages = None
        temp_base = None
        workers = 2
        max_tasks = None
        quiet = False
        dry_run = False
        index_batch_size = 500
    (tmp_path / "ver").mkdir()
    with patch.dict("os.environ", {"HELP_SOURCE_BASE": str(tmp_path), "QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}):
        with patch("onec_help.ingest.discover_version_dirs") as mock_disc:
            mock_disc.return_value = [(tmp_path / "ver", "ver")]
            assert cmd_ingest(Args()) == 0
    mock_run_ingest.assert_called_once()


@patch("onec_help.ingest.run_ingest")
def test_cmd_ingest_sources_arg(mock_run_ingest) -> None:
    mock_run_ingest.return_value = 5
    class Args:
        sources = ["/path/to/1cv8:8.3"]
        sources_file = None
        languages = None
        temp_base = "/tmp/t"
        workers = 1
        max_tasks = None
        quiet = True
        dry_run = False
        index_batch_size = 500
    with patch.dict("os.environ", {"QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"}, clear=False):
        assert cmd_ingest(Args()) == 0
    mock_run_ingest.assert_called_once()
    call_kw = mock_run_ingest.call_args[1]
    assert call_kw["source_dirs_with_versions"] == [("/path/to/1cv8", "8.3")]


def test_cmd_ingest_no_sources_returns_error() -> None:
    class Args:
        sources = None
        sources_file = None
        languages = None
        temp_base = None
        workers = 1
        max_tasks = None
        quiet = False
        dry_run = False
        index_batch_size = 500
    with patch.dict("os.environ", {}, clear=True):
        assert cmd_ingest(Args()) == 1
