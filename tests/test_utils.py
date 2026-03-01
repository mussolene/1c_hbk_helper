"""Tests for _utils."""

from pathlib import Path
from unittest.mock import patch

from onec_help._utils import (
    format_duration,
    mask_path_for_log,
    path_inside_base,
    progress_done,
    progress_line,
    safe_error_message,
)


def test_safe_error_message_production_hides_detail() -> None:
    """In production, only exception type is returned."""
    e = ValueError("sensitive path /home/secret")
    assert safe_error_message(e, production=True) == "ValueError"


def test_safe_error_message_non_production_shows_detail() -> None:
    """When not production, full message is included."""
    e = ValueError("disk full")
    assert "disk full" in safe_error_message(e, production=False)


def test_mask_path_for_log_exception_returns_placeholder() -> None:
    """When Path() raises, return safe placeholder."""
    with patch.object(Path, "__new__", side_effect=TypeError("bad")):
        assert mask_path_for_log("anything") == "<path>"


def test_mask_path_for_log_root_uses_fallback() -> None:
    """Path('/') has empty name; uses str(p)[-50:] fallback."""
    result = mask_path_for_log(Path("/"))
    assert result
    assert result != "<path>"


def test_progress_line_non_tty_no_overwrite() -> None:
    """When stderr is not TTY, use plain newline."""
    with patch("sys.stderr") as stderr:
        stderr.isatty.return_value = False
        progress_line("hello", overwrite=True)
        stderr.write.assert_called()
        call_args = "".join(c[0][0] for c in stderr.write.call_args_list)
        assert "\n" in call_args or "hello" in call_args


def test_progress_done_writes_newline() -> None:
    """progress_done writes message with newline."""
    with patch("sys.stderr") as stderr:
        progress_done("done")
        stderr.write.assert_called_once()
        assert stderr.write.call_args[0][0].endswith("\n")
        assert "done" in stderr.write.call_args[0][0]


def test_format_duration() -> None:
    """format_duration returns human-readable strings."""
    assert format_duration(0) == "0s"
    assert format_duration(45) == "45s"
    assert format_duration(90) == "1m 30s"
    assert format_duration(125) == "2m 5s"
    assert format_duration(3661) == "1h 1m"
    assert format_duration(7200) == "2h"
    assert format_duration(90061) == "1d 1h"
    assert format_duration(-1) == "—"
    assert format_duration(float("nan")) == "—"
    assert format_duration(3605) == "1h 5s"
    assert format_duration(86700) == "1d 5m"


def test_path_inside_base_valueerror_returns_false() -> None:
    """When resolve raises ValueError, return False."""
    base = Path("/base")
    path = base / "file"
    with patch.object(Path, "resolve", side_effect=ValueError("invalid")):
        assert path_inside_base(path, base) is False


def test_path_inside_base_path_equals_base() -> None:
    """When path resolves to base itself, return True."""
    base = Path(__file__).resolve().parent
    assert path_inside_base(base, base) is True
