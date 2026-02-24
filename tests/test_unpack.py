"""Tests for unpack module."""
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from onec_help.unpack import ensure_dir, unpack_hbk


def test_ensure_dir(tmp_path: Path) -> None:
    d = tmp_path / "sub"
    ensure_dir(d)
    assert d.is_dir()
    ensure_dir(d)
    assert d.is_dir()


def test_unpack_hbk_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        unpack_hbk("/nonexistent.hbk", "/tmp/out")


def test_unpack_hbk_calls_7z(tmp_path: Path) -> None:
    archive = tmp_path / "test.hbk"
    archive.write_bytes(b"fake")
    out = tmp_path / "out"
    with patch("onec_help.unpack.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        unpack_hbk(archive, out)
        run.assert_called()
        args = run.call_args[0][0]
        assert "7z" in args
        assert "x" in args
        assert "-y" in args


def test_unpack_hbk_retry_with_tstar(tmp_path: Path) -> None:
    """When 7z fails, retry with -t*."""
    archive = tmp_path / "a.hbk"
    archive.write_bytes(b"x")
    out = tmp_path / "out"
    with patch("onec_help.unpack.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1, stderr="err")
        run.return_value.returncode = 0
        run.side_effect = [MagicMock(returncode=1), MagicMock(returncode=0)]
        unpack_hbk(archive, out)
        assert run.call_count == 2
        second_call = run.call_args_list[1][0][0]
        assert "-t*" in second_call


def test_unpack_hbk_error_message(tmp_path: Path) -> None:
    """When 7z and zipfile and unzip all fail, error message must suggest manual unpack."""
    archive = tmp_path / "help.hbk"
    archive.write_bytes(b"not a zip or 7z archive")
    out = tmp_path / "out"
    with patch("onec_help.unpack.subprocess.run") as run:
        run.return_value = MagicMock(returncode=2, stderr="Headers Error", stdout="")
        run.side_effect = [MagicMock(returncode=2), MagicMock(returncode=2), MagicMock(returncode=1)]
        with pytest.raises(RuntimeError) as exc_info:
            unpack_hbk(archive, out)
        msg = str(exc_info.value)
        assert "manually" in msg.lower() or "unpack" in msg.lower()
        assert "zipfile" in msg.lower() or "7z" in msg.lower()


def test_unpack_fallback_zipfile(tmp_path: Path) -> None:
    """When 7z fails, unpack via Python zipfile if the file is ZIP."""
    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("file.txt", "hello")
    out = tmp_path / "out"
    with patch("onec_help.unpack.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1)
        unpack_hbk(archive, out)
    assert (out / "file.txt").read_text() == "hello"
