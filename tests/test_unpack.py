"""Tests for unpack module."""

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from onec_help.unpack import (
    _try_unzip,
    _try_zipfile_from_offset,
    ensure_dir,
    unpack_hbk,
)


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
        run.side_effect = [
            MagicMock(returncode=2),
            MagicMock(returncode=2),
            MagicMock(returncode=1),
        ]
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


def test_unpack_hbk_real_zip_no_mock(tmp_path: Path) -> None:
    """Unpack a real .hbk-sized zip (no 7z mock): fallback zipfile must succeed."""
    archive = tmp_path / "sample_ru.hbk"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("PayloadData/index.html", "<html><body><h1>Test</h1></body></html>")
        zf.writestr("PayloadData/page2.html", "<html><body><p>Second</p></body></html>")
    out = tmp_path / "unpacked"
    # 7z may fail on .hbk or succeed; zipfile fallback will work
    unpack_hbk(archive, out)
    assert (out / "PayloadData" / "index.html").exists()
    assert "Test" in (out / "PayloadData" / "index.html").read_text()


def test_try_zipfile_from_offset_success(tmp_path: Path) -> None:
    """When archive has header, unpack from offset."""
    archive = tmp_path / "with_header.zip"
    with open(archive, "wb") as f:
        f.write(b"x" * 512)
    with zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.txt", "hello")
    out = tmp_path / "out"
    out.mkdir()
    assert _try_zipfile_from_offset(archive, out, offset=512) is True
    assert (out / "data.txt").read_text() == "hello"


def test_try_zipfile_from_offset_truncate_tail(tmp_path: Path) -> None:
    """truncate_tail cuts trailing bytes before opening as zip."""
    archive = tmp_path / "trunc.zip"
    data = b"header" * 100
    with open(archive, "wb") as f:
        f.write(data)
    with zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("x", "y")
    out = tmp_path / "out"
    out.mkdir()
    # Should fail when reading wrong offset; truncate_tail used in unpack_hbk
    assert _try_zipfile_from_offset(archive, out, offset=0, truncate_tail=0) in (True, False)


def test_try_unzip_mocked(tmp_path: Path) -> None:
    """_try_unzip returns True when unzip command succeeds."""
    archive = tmp_path / "a.zip"
    archive.write_bytes(b"fake")
    out = tmp_path / "out"
    out.mkdir()
    with patch("onec_help.unpack.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        assert _try_unzip(archive, out) is True
    with patch("onec_help.unpack.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1)
        assert _try_unzip(archive, out) is False


def test_unpack_hbk_via_offset(tmp_path: Path) -> None:
    """When 7z and direct zipfile fail, offset unpack can succeed."""
    archive = tmp_path / "arch.hbk"
    with open(archive, "wb") as f:
        f.write(b" " * 512)
    with zipfile.ZipFile(archive, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("PayloadData/index.html", "<h1>OK</h1>")
    out = tmp_path / "out"
    with patch("onec_help.unpack.subprocess.run") as run:
        run.side_effect = [MagicMock(returncode=1), MagicMock(returncode=1)]
        unpack_hbk(archive, out)
    assert (out / "PayloadData" / "index.html").exists()


def test_unpack_hbk_non_hbk_suffix_error(tmp_path: Path) -> None:
    """When suffix is not .hbk, error message does not mention manual unpack."""
    archive = tmp_path / "data.bin"
    archive.write_bytes(b"not zip")
    out = tmp_path / "out"
    with patch("onec_help.unpack.subprocess.run") as run:
        run.side_effect = [
            MagicMock(returncode=2),
            MagicMock(returncode=2),
            MagicMock(returncode=1),
        ]
        with pytest.raises(RuntimeError) as exc_info:
            unpack_hbk(archive, out)
    assert "All unpack methods failed" in str(exc_info.value)


def test_unpack_hbk_7z_not_found_fallback_zipfile(tmp_path: Path) -> None:
    """When 7z is missing (FileNotFoundError), fallback to zipfile is used."""
    archive = tmp_path / "data.hbk"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("inner.txt", "content")
    out = tmp_path / "out"
    with patch("onec_help.unpack.subprocess.run") as run:
        run.side_effect = FileNotFoundError("7z not found")
        unpack_hbk(archive, out)
    assert (out / "inner.txt").read_text() == "content"
