"""Shared utilities for onec_help package."""

import os
import sys
from pathlib import Path


def safe_error_message(e: BaseException, *, production: bool | None = None) -> str:
    """Return error message safe for API/logs: no stack trace or sensitive detail in production."""
    if production is None:
        production = (os.environ.get("PRODUCTION") or "").strip().lower() in ("1", "true", "yes")
    return type(e).__name__ if production else f"{type(e).__name__}: {e}"


def mask_path_for_log(path: str | Path) -> str:
    """Return path safe for logging: filename only to avoid leaking full paths."""
    try:
        p = Path(path)
        return p.name if p.name else str(p)[-50:]  # fallback: last 50 chars
    except Exception:
        return "<path>"


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


def format_duration(sec: float) -> str:
    """Human-readable duration: 5m 30s, 2h 15m, 1d 3h. Rounds to nearest unit."""
    if sec < 0 or not (sec == sec):  # NaN
        return "—"
    s = int(round(sec))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s" if s else f"{m}m"
    h, m = divmod(m, 60)
    if h < 24:
        parts = [f"{h}h"]
        if m:
            parts.append(f"{m}m")
        if s and not m:
            parts.append(f"{s}s")
        return " ".join(parts)
    d, h = divmod(h, 24)
    parts = [f"{d}d"]
    if h:
        parts.append(f"{h}h")
    if m and not h:
        parts.append(f"{m}m")
    return " ".join(parts)


def path_inside_base(path: Path, base: Path) -> bool:
    """Return True if path resolves to a location under base (prevents path traversal)."""
    try:
        resolved = path.resolve()
        base_resolved = base.resolve()
        return resolved.is_relative_to(base_resolved) or resolved == base_resolved
    except (ValueError, OSError):
        return False
