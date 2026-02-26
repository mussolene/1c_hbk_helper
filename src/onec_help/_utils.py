"""Shared utilities for onec_help package."""

import sys
from pathlib import Path


def _is_tty() -> bool:
    """True if stderr is a TTY (for progress overwrite)."""
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


def progress_line(msg: str, *, overwrite: bool = True) -> None:
    """Print compact progress line. Overwrites previous if TTY and overwrite=True."""
    pad = msg.ljust(78) if overwrite and _is_tty() else msg
    term = "\r" if (overwrite and _is_tty()) else "\n"
    sys.stderr.write(pad + term)
    sys.stderr.flush()


def progress_done(msg: str) -> None:
    """Print final progress line (newline, no overwrite)."""
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


def path_inside_base(path: Path, base: Path) -> bool:
    """Return True if path resolves to a location under base (prevents path traversal)."""
    try:
        resolved = path.resolve()
        base_resolved = base.resolve()
        return resolved.is_relative_to(base_resolved) or resolved == base_resolved
    except (ValueError, OSError):
        return False
