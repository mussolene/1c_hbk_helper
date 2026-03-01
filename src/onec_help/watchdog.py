"""
Watchdog: monitor new .hbk files, incremental ingest; process pending memory embeddings.
Uses same discovery as ingest (discover_version_dirs + collect_hbk_tasks) so new platform
installations are detected reliably.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from ._utils import safe_error_message
from .ingest import _ingest_cache_path, collect_hbk_tasks, discover_version_dirs


def _parse_languages() -> list[str] | None:
    raw = os.environ.get("HELP_LANGUAGES", "").strip()
    if not raw or raw.lower() == "all":
        return None
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _watchdog_state_path() -> Path:
    """State file path: same directory as ingest cache (persists across container restarts)."""
    return Path(_ingest_cache_path()).parent / "watchdog_hbk_cache.json"


def _scan_hbk_like_ingest(base: Path | None = None) -> dict[str, float]:
    """Scan .hbk files using same logic as ingest (version dirs + languages filter)."""
    if base is None:
        base_str = os.environ.get("HELP_SOURCE_BASE", "").strip()
        if not base_str:
            return {}
        base = Path(base_str).resolve()
    if not base.exists() or not base.is_dir():
        return {}
    version_dirs = discover_version_dirs(base)
    if not version_dirs:
        return {}
    source_pairs = [(p, v) for p, v in version_dirs]
    languages = _parse_languages()
    tasks = collect_hbk_tasks(source_pairs, languages)
    current: dict[str, float] = {}
    for path, _version, _lang in tasks:
        if path.is_file():
            try:
                current[str(path.resolve())] = path.stat().st_mtime
            except OSError:
                pass
    return current


def run_watchdog(
    help_source_base: Path | None = None,
    poll_interval_sec: int = 600,
    pending_interval_sec: int = 600,
) -> None:
    """
    Infinite loop: (1) check for new/changed .hbk (same discovery as ingest), trigger ingest;
    (2) process pending memory embeddings periodically.
    """
    if help_source_base is not None:
        base = Path(help_source_base).resolve()
    else:
        base_str = os.environ.get("HELP_SOURCE_BASE", "").strip()
        if not base_str:
            print("[watchdog] HELP_SOURCE_BASE not set", file=sys.stderr, flush=True)
            return
        base = Path(base_str).resolve()
    if not base.exists() or not base.is_dir():
        print(f"[watchdog] HELP_SOURCE_BASE not a directory: {base}", file=sys.stderr, flush=True)
        return
    cache_path = _watchdog_state_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    last_hbk: dict[str, float] = {}
    if cache_path.exists():
        try:
            last_hbk = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    last_pending = 0.0
    poll = max(60, poll_interval_sec)
    pending_int = max(60, pending_interval_sec)
    while True:
        try:
            now = time.time()
            current = _scan_hbk_like_ingest(base)
            if current != last_hbk:
                prev_keys = set(last_hbk)
                curr_keys = set(current)
                added = len(curr_keys - prev_keys)
                removed = len(prev_keys - curr_keys)
                changed = sum(1 for k in curr_keys & prev_keys if last_hbk.get(k) != current.get(k))
                if added or removed or changed:
                    print(
                        f"[watchdog] .hbk changed: +{added} new, -{removed} removed, ~{changed} modified",
                        file=sys.stderr,
                        flush=True,
                    )
                last_hbk = current
                try:
                    cache_path.write_text(json.dumps(current, indent=0), encoding="utf-8")
                except OSError:
                    pass
                if current:
                    _run_ingest()
            if now - last_pending >= pending_int:
                last_pending = now
                _process_pending_memory()
        except Exception as e:
            print(f"[watchdog] error: {safe_error_message(e)}", file=sys.stderr, flush=True)
        time.sleep(poll)


def _run_ingest() -> None:
    """Run full ingest (python -m onec_help ingest)."""
    try:
        subprocess.run(
            [sys.executable, "-m", "onec_help", "ingest"],
            capture_output=True,
            timeout=3600,
            env=os.environ.copy(),
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"[watchdog] ingest failed: {safe_error_message(e)}", file=sys.stderr, flush=True)


def _process_pending_memory() -> None:
    """Process pending memory embeddings via MemoryStore."""
    try:
        from .memory import get_memory_store

        n = get_memory_store().process_pending()
        if n > 0:
            print(f"[watchdog] processed {n} pending memory entries", file=sys.stderr, flush=True)
    except Exception as e:
        print(
            f"[watchdog] process_pending failed: {safe_error_message(e)}",
            file=sys.stderr,
            flush=True,
        )
