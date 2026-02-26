"""
Watchdog: monitor new .hbk files, incremental ingest; process pending memory embeddings.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ._utils import safe_error_message


def run_watchdog(
    help_source_base: Path | None = None,
    poll_interval_sec: int = 600,
    pending_interval_sec: int = 600,
) -> None:
    """
    Infinite loop: (1) check for new/changed .hbk, trigger ingest on change;
    (2) process pending memory embeddings periodically.
    """
    base = help_source_base
    if base is None:
        p = os.environ.get("HELP_SOURCE_BASE", "").strip()
        if not p:
            print("[watchdog] HELP_SOURCE_BASE not set", file=sys.stderr, flush=True)
            return
        base = Path(p)
    base = Path(base).resolve()
    if not base.exists() or not base.is_dir():
        print(f"[watchdog] HELP_SOURCE_BASE not a directory: {base}", file=sys.stderr, flush=True)
        return
    cache_path = Path(tempfile.gettempdir()) / "watchdog_hbk_cache.json"
    last_hbk: dict = {}
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
            current = {}
            for p in base.rglob("*.hbk"):
                if p.is_file():
                    try:
                        current[str(p)] = p.stat().st_mtime
                    except OSError:
                        pass
            if current != last_hbk:
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
        print(f"[watchdog] process_pending failed: {safe_error_message(e)}", file=sys.stderr, flush=True)
