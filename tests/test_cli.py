"""Tests for CLI."""
from pathlib import Path
from unittest.mock import patch

import pytest

from onec_help.cli import (
    cmd_build_docs,
    cmd_build_index,
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
