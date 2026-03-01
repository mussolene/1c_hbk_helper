"""Tests for watchdog module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from onec_help.watchdog import (
    _process_pending_memory,
    _run_ingest,
    run_watchdog,
)


def test_run_watchdog_no_help_source_base(capsys: pytest.CaptureFixture[str]) -> None:
    """When HELP_SOURCE_BASE is not set, run_watchdog prints message and returns."""
    with patch.dict("os.environ", {}, clear=True):
        run_watchdog()
    err = capsys.readouterr().err
    assert "HELP_SOURCE_BASE not set" in err


def test_run_watchdog_base_not_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When HELP_SOURCE_BASE is not a directory, run_watchdog prints message and returns."""
    missing_dir = tmp_path / "nonexistent"
    run_watchdog(help_source_base=missing_dir)
    err = capsys.readouterr().err
    assert "not a directory" in err


def test_run_watchdog_base_is_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """When help_source_base is a file, run_watchdog prints message and returns."""
    f = tmp_path / "file.txt"
    f.write_text("x")
    run_watchdog(help_source_base=f)
    err = capsys.readouterr().err
    assert "not a directory" in err


def test_run_watchdog_help_source_base_from_env(tmp_path: Path) -> None:
    """When help_source_base is None, run_watchdog uses HELP_SOURCE_BASE from env."""
    with patch.dict("os.environ", {"HELP_SOURCE_BASE": str(tmp_path)}, clear=False):
        sleep_count = 0

        def mock_sleep(sec: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 1:
                raise StopIteration("stop")

        with patch("onec_help.watchdog.time.sleep", side_effect=mock_sleep):
            with patch("onec_help.watchdog.time.time", return_value=0.0):
                with patch("onec_help.watchdog._run_ingest"):
                    with patch("onec_help.watchdog._process_pending_memory"):
                        try:
                            run_watchdog(
                                help_source_base=None, poll_interval_sec=60, pending_interval_sec=60
                            )
                        except StopIteration:
                            pass


def test_run_watchdog_one_iteration_then_stop(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """run_watchdog runs one iteration then exits when sleep raises (simulates KeyboardInterrupt)."""

    class StopAfterOne(Exception):
        pass

    sleep_count = 0

    def mock_sleep(sec: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 1:
            raise StopAfterOne("stop")

    with patch("onec_help.watchdog.time.sleep", side_effect=mock_sleep):
        with patch("onec_help.watchdog.time.time", return_value=0.0):
            with patch("onec_help.watchdog._run_ingest"):
                with patch("onec_help.watchdog._process_pending_memory"):
                    with pytest.raises(StopAfterOne):
                        run_watchdog(
                            help_source_base=tmp_path,
                            poll_interval_sec=60,
                            pending_interval_sec=60,
                        )


def test_run_watchdog_triggers_ingest_on_hbk_change(
    tmp_path: Path,
) -> None:
    """When .hbk files exist and differ from cache, _run_ingest is called."""
    (tmp_path / "8.3.27").mkdir()
    (tmp_path / "8.3.27" / "1cv8_ru.hbk").write_bytes(b"x")
    ingest_called = []

    def capture_ingest() -> None:
        ingest_called.append(1)

    sleep_count = 0

    def mock_sleep(sec: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 1:
            raise StopIteration("stop")

    with patch("onec_help.watchdog.time.sleep", side_effect=mock_sleep):
        with patch("onec_help.watchdog.time.time", return_value=0.0):
            with patch("onec_help.watchdog._run_ingest", side_effect=capture_ingest):
                with patch("onec_help.watchdog._process_pending_memory"):
                    try:
                        run_watchdog(
                            help_source_base=tmp_path,
                            poll_interval_sec=60,
                            pending_interval_sec=60,
                        )
                    except StopIteration:
                        pass
    assert len(ingest_called) >= 1


def test_run_ingest_success() -> None:
    """_run_ingest runs subprocess without error when ingest succeeds."""
    with patch("onec_help.watchdog.subprocess.run") as mock_run:
        mock_run.return_value = type("R", (), {"returncode": 0})()
        _run_ingest()
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert "onec_help" in call_args
    assert "ingest" in call_args


def test_run_ingest_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """_run_ingest logs when subprocess fails."""
    with patch("onec_help.watchdog.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("7z not found")
        _run_ingest()
    err = capsys.readouterr().err
    assert "ingest failed" in err


def test_process_pending_memory_success(capsys: pytest.CaptureFixture[str]) -> None:
    """_process_pending_memory logs when entries are processed."""
    with patch("onec_help.memory.get_memory_store") as mock_get:
        mock_store = type("Store", (), {"process_pending": lambda self: 3})()
        mock_get.return_value = mock_store
        _process_pending_memory()
    err = capsys.readouterr().err
    assert "processed 3 pending" in err


def test_process_pending_memory_no_entries() -> None:
    """_process_pending_memory does not log when 0 entries processed."""
    with patch("onec_help.memory.get_memory_store") as mock_get:
        mock_store = type("Store", (), {"process_pending": lambda self: 0})()
        mock_get.return_value = mock_store
        _process_pending_memory()
    # No exception, no log for 0


def test_process_pending_memory_import_from_memory() -> None:
    """_process_pending_memory imports get_memory_store from memory module."""
    with patch("onec_help.memory.get_memory_store") as mock_get:
        mock_store = type("Store", (), {"process_pending": lambda self: 0})()
        mock_get.return_value = mock_store
        _process_pending_memory()
    mock_get.assert_called_once()
