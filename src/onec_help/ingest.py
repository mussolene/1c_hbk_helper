"""
Ingest .hbk from multiple read-only source directories.
Unpacks to a temp dir in the container, builds docs, indexes with version/language, then cleans up.
Supports language filter (e.g. only *_ru.hbk) and concurrent processing.
Progress is printed to stderr so long runs are not killed by "no output" timeouts.
Writes ingest status to INDEX_STATUS_FILE for index-status command (embedding speed, per-folder, ETA).
"""

import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Path for ingest status (read by index-status). Default under /tmp so it works without /app.
DEFAULT_INDEX_STATUS_FILE = "/tmp/onec_help_ingest_status.json"
# How often to write status file while ingest runs (seconds); env INDEX_STATUS_INTERVAL_SEC
STATUS_UPDATE_INTERVAL_SEC = 2.0
# Path for ingest cache (SQLite). Skip re-parsing and re-embedding if .hbk unchanged.
DEFAULT_INGEST_CACHE_FILE = "/tmp/onec_help_ingest_cache.db"
_CACHE_TABLE = "ingest_cache"


def _default_workers() -> int:
    """Default workers = half of available CPUs, at least 1 (do not exceed half of resources)."""
    return max(1, (os.cpu_count() or 4) // 2)


def _file_sha256(path: Path) -> Optional[str]:
    """SHA256 of file contents (for .hbk). Returns None on read error."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _ingest_cache_path() -> str:
    return os.environ.get("INGEST_CACHE_FILE", DEFAULT_INGEST_CACHE_FILE)


def _load_ingest_cache() -> Dict[str, Dict[str, Any]]:
    """Load cache from SQLite. Returns dict key -> {hash, indexed, points}."""
    path = _ingest_cache_path()
    entries: Dict[str, Dict[str, Any]] = {}
    try:
        conn = sqlite3.connect(path)
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_CACHE_TABLE} "
            "(key TEXT PRIMARY KEY, hash TEXT NOT NULL, indexed INTEGER NOT NULL, points INTEGER)"
        )
        for row in conn.execute(
            f"SELECT key, hash, indexed, points FROM {_CACHE_TABLE}"
        ):
            entries[row[0]] = {
                "hash": row[1],
                "indexed": bool(row[2]),
                "points": row[3],
            }
        conn.close()
    except (OSError, sqlite3.Error):
        pass
    return entries


def _update_ingest_cache_entry(key: str, file_hash: str, points: int) -> None:
    """Persist one cache entry (SQLite INSERT OR REPLACE). No full rewrite."""
    path = _ingest_cache_path()
    try:
        conn = sqlite3.connect(path)
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_CACHE_TABLE} "
            "(key TEXT PRIMARY KEY, hash TEXT NOT NULL, indexed INTEGER NOT NULL, points INTEGER)"
        )
        conn.execute(
            f"INSERT OR REPLACE INTO {_CACHE_TABLE} (key, hash, indexed, points) VALUES (?, ?, 1, ?)",
            (key, file_hash, points),
        )
        conn.commit()
        conn.close()
    except (OSError, sqlite3.Error):
        pass


def _status_writer_loop(
    stop_event: threading.Event,
    state_lock: threading.Lock,
    state: Dict[str, Any],
    status_file: str,
    interval_sec: float,
) -> None:
    """Background thread: write status file every interval_sec until stop_event is set."""
    while not stop_event.wait(timeout=interval_sec):
        with state_lock:
            if state.get("status") == "completed":
                break
            done_tasks = state["done_tasks"]
            total_points = state["total_points"]
            folders = copy.deepcopy(state["folders"])
            current = list(state["current_work"].values())
        _write_ingest_status(
            status_file,
            started_at=state["started_at"],
            embedding_backend=state["embedding_backend"],
            total_tasks=state["total_tasks"],
            done_tasks=done_tasks,
            total_points=total_points,
            folders=folders,
            status="in_progress",
            current=current,
        )


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _write_ingest_status(
    status_file: str,
    *,
    started_at: float,
    embedding_backend: str,
    total_tasks: int,
    done_tasks: int,
    total_points: int,
    folders: List[Dict[str, Any]],
    status: str = "in_progress",
    finished_at: Optional[float] = None,
    current: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Write ingest status JSON for index-status command. current = list of {path, version, language, stage} per active thread."""
    elapsed = time.time() - started_at
    payload: Dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_at)),
        "embedding_backend": embedding_backend or "none",
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "total_points": total_points,
        "folders": folders,
        "status": status,
        "elapsed_sec": round(elapsed, 1),
    }
    if status == "completed":
        payload["current"] = []
    elif current:
        payload["current"] = current
    if elapsed > 0 and total_points > 0:
        payload["embedding_speed_pts_per_sec"] = round(total_points / elapsed, 2)
    if done_tasks > 0 and total_tasks > done_tasks and total_points > 0 and elapsed > 0:
        avg_pts = total_points / done_tasks
        remaining_tasks = total_tasks - done_tasks
        eta_points = avg_pts * remaining_tasks
        rate = total_points / elapsed
        payload["eta_sec"] = round(eta_points / rate, 0) if rate > 0 else None
    if finished_at is not None:
        payload["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished_at))
        payload["total_elapsed_sec"] = round(finished_at - started_at, 1)
    try:
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def read_ingest_status(status_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Read ingest status JSON (for index-status). Returns None if file missing or invalid."""
    path = status_file or os.environ.get("INDEX_STATUS_FILE", DEFAULT_INDEX_STATUS_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# Language: filename pattern like 1cv8_ru.hbk, shcntx_en.hbk
LANG_PATTERN = re.compile(r"_([a-z]{2})\.hbk$", re.IGNORECASE)


def _language_from_filename(name: str) -> Optional[str]:
    m = LANG_PATTERN.search(name)
    return m.group(1).lower() if m else None


def _count_html_md(dir_path: Path) -> Tuple[int, int]:
    """Return (html_count, md_count) for files under dir_path (recursive)."""
    html_c, md_c = 0, 0
    try:
        for p in dir_path.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() == ".html":
                html_c += 1
            elif p.suffix.lower() == ".md":
                md_c += 1
    except OSError:
        pass
    return (html_c, md_c)


def collect_hbk_tasks(
    source_dirs_with_versions: list[tuple[Path, str]],
    languages: Optional[List[str]],
) -> List[Tuple[Path, str, str]]:
    """
    Scan source dirs (read-only) for .hbk files. Each item: (source_dir, version_label).
    Поиск рекурсивный (rglob), в т.ч. в подпапке bin/ (типично для Windows:
    C:\\Program Files\\1cv8\\8.3.27.1859\\bin).
    languages: e.g. ["ru"] for only *_ru.hbk; None or [] = all languages.
    Returns list of (hbk_path, version, language).
    """
    tasks: List[Tuple[Path, str, str]] = []
    for source_dir, version in source_dirs_with_versions:
        source_dir = Path(source_dir).resolve()
        if not source_dir.is_dir():
            continue
        for path in source_dir.rglob("*.hbk"):
            if not path.is_file():
                continue
            lang = _language_from_filename(path.name)
            if lang is None:
                continue
            if languages and lang not in [x.lower() for x in languages]:
                continue
            tasks.append((path, version, lang))
    return tasks


def _unpack_and_build_docs(
    hbk_path: Path,
    version: str,
    language: str,
    temp_base: Path,
    unpack_fn: Any,
    build_docs_fn: Any,
    current_work: Optional[Dict[int, Dict[str, Any]]] = None,
    state_lock: Optional[threading.Lock] = None,
) -> Tuple[Optional[Path], str, str, Optional[str]]:
    """Unpack one .hbk to temp, build .md there. Returns (md_dir, version, language, error_message) or (None, v, l, reason) on failure.
    If current_work and state_lock are set, updates current file/stage for this thread for status display."""
    ident = threading.get_ident()
    safe_name = re.sub(r"[^\w\-]", "_", hbk_path.stem)
    out_sub = temp_base / version / language / safe_name
    unpacked = out_sub / "unpacked"
    md_dir = out_sub / "md"
    err_msg: Optional[str] = None
    try:
        if current_work is not None and state_lock is not None:
            with state_lock:
                current_work[ident] = {
                    "path": hbk_path.name,
                    "version": version,
                    "language": language,
                    "stage": "unpack",
                }
        unpacked.mkdir(parents=True, exist_ok=True)
        unpack_fn(hbk_path, unpacked)
        if current_work is not None and state_lock is not None:
            with state_lock:
                if ident in current_work:
                    current_work[ident]["stage"] = "build_docs"
        md_dir.mkdir(parents=True, exist_ok=True)
        build_docs_fn(unpacked, md_dir)
        if any(md_dir.rglob("*.md")) or any(md_dir.rglob("*")) and not list(md_dir.rglob("*.md")):
            # build_docs may create .md or we have extension-less HTML; indexer will use HTML fallback
            return (md_dir, version, language, None)
        return (md_dir, version, language, None)
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        return (None, version, language, err_msg)
    finally:
        if current_work is not None and state_lock is not None:
            with state_lock:
                current_work.pop(ident, None)
        if unpacked.exists():
            try:
                shutil.rmtree(unpacked)
            except OSError:
                pass


def run_ingest(
    source_dirs_with_versions: List[Tuple[Union[Path, str], str]],
    languages: Optional[List[str]] = None,
    temp_base: Optional[Union[Path, str]] = None,
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    collection: str = "onec_help",
    incremental: bool = True,
    max_workers: Optional[int] = None,
    max_tasks: Optional[int] = None,
    verbose: bool = True,
    dry_run: bool = False,
    index_batch_size: int = 500,
    embedding_batch_size: Optional[int] = None,
    embedding_workers: Optional[int] = None,
) -> int:
    """
    Ingest .hbk from multiple source dirs (read-only): unpack to temp, build docs, index in batches, cleanup.
    source_dirs_with_versions: [(path, version_label), ...].
    languages: e.g. ["ru"] for only *_ru.hbk; None or [] = all.
    temp_base: dir inside container for unpack (default /tmp/help_ingest). Removed at end.
    max_tasks: if set, process only first N .hbk files (for resumable runs or to avoid timeout).
    verbose: print progress to stderr (keeps long runs from being killed by "no output" timeouts).
    dry_run: if True, only report how many .hbk tasks would be processed and return 0.
    index_batch_size: number of files per index upsert (smaller = more progress, less memory per step).
    embedding_batch_size: texts per embedding batch (env EMBEDDING_BATCH_SIZE).
    embedding_workers: parallel API requests for openai_api (env EMBEDDING_WORKERS).
    Returns total points indexed (0 if dry_run).
    """
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    from .html2md import build_docs
    from .indexer import build_index, get_embedding_dimension
    from .unpack import unpack_hbk

    if not source_dirs_with_versions:
        return 0

    base = Path(temp_base or "/tmp/help_ingest").resolve()
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Cannot create temp dir {base}: {e}") from e

    pairs = [(Path(p).resolve(), v) for p, v in source_dirs_with_versions]
    all_tasks = collect_hbk_tasks(pairs, languages)
    if not all_tasks:
        return 0

    skip_cache = (os.environ.get("INGEST_SKIP_CACHE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    cache_entries = _load_ingest_cache()
    to_process: List[Tuple[Path, str, str]] = []
    task_hashes: Dict[Tuple[str, str, str], str] = {}
    skipped = 0
    for path, version, lang in all_tasks:
        key = f"{version}/{lang}/{path.name}"
        h = None if skip_cache else _file_sha256(path)
        if h is None:
            to_process.append((path, version, lang))
            task_hashes[(version, lang, path.name)] = ""
            continue
        task_hashes[(version, lang, path.name)] = h
        ent = cache_entries.get(key)
        if ent and ent.get("hash") == h and ent.get("indexed"):
            skipped += 1
            continue
        to_process.append((path, version, lang))
    tasks = to_process
    if verbose and skipped > 0:
        _log(f"[ingest] Cache hit: skip {skipped} already indexed .hbk (unchanged)")

    if dry_run:
        if verbose:
            _log(f"[ingest] DRY RUN: would process {len(tasks)} .hbk task(s)")
            for i, (path, version, lang) in enumerate(tasks[:25], 1):
                _log(f"  {i}. {version}/{lang}  {path.name}")
            if len(tasks) > 25:
                _log(f"  ... and {len(tasks) - 25} more")
        return 0

    if max_tasks is not None and max_tasks > 0:
        tasks = tasks[:max_tasks]
        if verbose:
            _log(f"[ingest] Limiting to first {max_tasks} task(s)")

    if not tasks:
        if verbose and skipped > 0:
            _log("[ingest] All tasks skipped (cache); nothing to do.")
        return 0

    if max_workers is None:
        max_workers = _default_workers()
    if verbose:
        _log(f"[ingest] Found {len(tasks)} .hbk task(s); workers={max_workers}")

    status_file = os.environ.get("INDEX_STATUS_FILE", DEFAULT_INDEX_STATUS_FILE)
    embedding_backend = (os.environ.get("EMBEDDING_BACKEND") or "local").strip().lower()
    if embedding_backend not in ("local", "openai_api"):
        embedding_backend = "none"
    started_at = time.time()
    # One entry per folder (version/language): hbk_count, html/md/err/points aggregated
    folder_hbk_count: Dict[Tuple[str, str], int] = Counter()
    for _, v, l in tasks:
        folder_hbk_count[(v, l)] += 1
    folders = [
        {
            "version": v,
            "language": l,
            "hbk_count": folder_hbk_count[(v, l)],
            "html_count": 0,
            "md_count": 0,
            "err_count": 0,
            "points": 0,
            "tasks_done": 0,
            "status": "pending",
        }
        for (v, l) in sorted(folder_hbk_count.keys())
    ]
    _write_ingest_status(
        status_file,
        started_at=started_at,
        embedding_backend=embedding_backend,
        total_tasks=len(tasks),
        done_tasks=0,
        total_points=0,
        folders=folders,
        status="in_progress",
    )

    state_lock = threading.Lock()
    current_work: Dict[int, Dict[str, Any]] = {}
    state: Dict[str, Any] = {
        "done_tasks": 0,
        "total_points": 0,
        "folders": folders,
        "current_work": current_work,
        "started_at": started_at,
        "embedding_backend": embedding_backend,
        "total_tasks": len(tasks),
        "status": "in_progress",
        "status_file": status_file,
    }
    interval_sec = float(os.environ.get("INDEX_STATUS_INTERVAL_SEC", str(STATUS_UPDATE_INTERVAL_SEC)))
    stop_event = threading.Event()
    writer = threading.Thread(
        target=_status_writer_loop,
        args=(stop_event, state_lock, state, status_file, interval_sec),
        daemon=True,
    )
    writer.start()

    # Ensure collection exists once (avoid race when multiple workers call build_index)
    if incremental:
        client = QdrantClient(host=qdrant_host, port=qdrant_port, check_compatibility=False)
        if not client.collection_exists(collection):
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=get_embedding_dimension(), distance=Distance.COSINE),
            )
            if verbose:
                _log("[ingest] Created Qdrant collection")

    total_indexed = 0
    done = 0
    failed: List[Tuple[Path, str, str, str]] = []  # (path, version, language, error_message)
    main_ident = threading.get_ident()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _unpack_and_build_docs,
                path,
                version,
                lang,
                base,
                unpack_hbk,
                build_docs,
                current_work,
                state_lock,
            ): (path, version, lang)
            for path, version, lang in tasks
        }
        for future in as_completed(futures):
            path_hbk, version, language = futures[future]
            done += 1
            md_dir, _, _, err_msg = future.result()
            if md_dir is None or not md_dir.exists():
                reason = (err_msg or "unknown").split("\n")[0].strip()[:200]
                failed.append((path_hbk, version, language, err_msg or "unknown"))
                for fo in folders:
                    if fo["version"] == version and fo["language"] == language:
                        fo["err_count"] = fo.get("err_count", 0) + 1
                        fo["tasks_done"] = fo.get("tasks_done", 0) + 1
                        if fo["tasks_done"] + fo["err_count"] >= fo["hbk_count"]:
                            fo["status"] = "done"
                        break
                with state_lock:
                    state["done_tasks"] = done
                    state["total_points"] = total_indexed
                _write_ingest_status(
                    status_file,
                    started_at=started_at,
                    embedding_backend=embedding_backend,
                    total_tasks=len(tasks),
                    done_tasks=done,
                    total_points=total_indexed,
                    folders=folders,
                    status="in_progress",
                )
                if verbose:
                    _log(
                        f"[ingest] [{done}/{len(tasks)}] skip (unpack/build failed) {version}/{language} — {path_hbk}"
                    )
                    _log(f"[ingest]   reason: {reason}")
                continue
            try:
                if verbose:
                    _log(
                        f"[ingest] [{done}/{len(tasks)}] indexing {version}/{language} — {path_hbk}"
                    )
                with state_lock:
                    current_work[main_ident] = {
                        "path": path_hbk.name,
                        "version": version,
                        "language": language,
                        "stage": "indexing",
                    }
                try:
                    n = build_index(
                        docs_dir=md_dir,
                        qdrant_host=qdrant_host,
                        qdrant_port=qdrant_port,
                        collection=collection,
                        incremental=incremental,
                        extra_payload={"version": version, "language": language},
                        batch_size=index_batch_size,
                        embedding_batch_size=embedding_batch_size,
                        embedding_workers=embedding_workers,
                    )
                    total_indexed += n
                    key = f"{version}/{language}/{path_hbk.name}"
                    h = task_hashes.get((version, language, path_hbk.name)) or _file_sha256(
                        path_hbk
                    )
                    if h:
                        cache_entries[key] = {"hash": h, "indexed": True, "points": n}
                        _update_ingest_cache_entry(key, h, n)
                    html_c, md_c = _count_html_md(md_dir)
                    for fo in folders:
                        if fo["version"] == version and fo["language"] == language:
                            fo["html_count"] = fo.get("html_count", 0) + html_c
                            fo["md_count"] = fo.get("md_count", 0) + md_c
                            fo["points"] = fo.get("points", 0) + n
                            fo["tasks_done"] = fo.get("tasks_done", 0) + 1
                            if fo["tasks_done"] + fo.get("err_count", 0) >= fo["hbk_count"]:
                                fo["status"] = "done"
                            break
                    with state_lock:
                        state["done_tasks"] = done
                        state["total_points"] = total_indexed
                        current_snapshot = list(current_work.values())
                    _write_ingest_status(
                        status_file,
                        started_at=started_at,
                        embedding_backend=embedding_backend,
                        total_tasks=len(tasks),
                        done_tasks=done,
                        total_points=total_indexed,
                        folders=folders,
                        status="in_progress",
                        current=current_snapshot,
                    )
                    if verbose:
                        _log(
                            f"[ingest] [{done}/{len(tasks)}] indexed {n} points ({version}/{language}) — {path_hbk}, total={total_indexed}"
                        )
                finally:
                    with state_lock:
                        current_work.pop(main_ident, None)
                    try:
                        shutil.rmtree(md_dir.parent)
                    except OSError:
                        pass
            finally:
                pass
    finished_at = time.time()
    with state_lock:
        state["status"] = "completed"
        current_work.clear()
    stop_event.set()
    writer.join(timeout=interval_sec * 2 + 1)
    _write_ingest_status(
        status_file,
        started_at=started_at,
        embedding_backend=embedding_backend,
        total_tasks=len(tasks),
        done_tasks=len(tasks),
        total_points=total_indexed,
        folders=folders,
        status="completed",
        finished_at=finished_at,
        current=[],
    )
    try:
        shutil.rmtree(base)
    except OSError:
        pass
    if verbose:
        _log(f"[ingest] Done. Total points indexed: {total_indexed}")
    if failed and verbose:
        _log(f"[ingest] Failed {len(failed)} file(s) (unpack or build_docs error):")
        for path_hbk, version, language, err in failed:
            short_err = (err or "").split("\n")[0].strip()[:150]
            _log(f"[ingest]   — {version}/{language} {path_hbk.name}: {short_err}")
        fail_log = os.environ.get("INGEST_FAILED_LOG")
        if fail_log:
            try:
                with open(fail_log, "w", encoding="utf-8") as f:
                    f.write(f"# Ingest failed .hbk ({len(failed)})\n")
                    for path_hbk, version, language, err in failed:
                        f.write(f"{version}\t{language}\t{path_hbk}\t{err or ''}\n")
                _log(f"[ingest] Wrote failure list to {fail_log}")
            except OSError as e:
                _log(f"[ingest] Could not write failure log {fail_log}: {e}")
    return total_indexed


def _unpack_one(
    path: Path,
    version: str,
    lang: str,
    output_base: Path,
    unpack_fn: Any,
    verbose: bool,
) -> Tuple[bool, str]:
    """Unpack one .hbk. Returns (success, message)."""
    safe_name = re.sub(r"[^\w\-]", "_", path.stem)
    out_sub = output_base / version / lang / safe_name
    try:
        out_sub.mkdir(parents=True, exist_ok=True)
        unpack_fn(path, out_sub)
        msg = f"{version}/{lang} → {out_sub.relative_to(output_base)}"
        if verbose:
            _log(f"[unpack] {msg}")
        return (True, msg)
    except Exception as e:
        if verbose:
            _log(f"[unpack] skip {path}: {e}")
        return (False, str(e))


def run_unpack_only(
    source_dirs_with_versions: List[Tuple[Union[Path, str], str]],
    output_dir: Union[Path, str],
    languages: Optional[List[str]] = None,
    max_workers: int = 4,
    verbose: bool = True,
) -> int:
    """
    Only unpack .hbk files into output_dir (no build-docs, no indexing).
    Structure: output_dir / version / language / safe_stem / (unpacked files).
    Returns number of .hbk archives unpacked.
    """
    from .unpack import unpack_hbk

    output_base = Path(output_dir).resolve()
    pairs = [(Path(p).resolve(), v) for p, v in source_dirs_with_versions]
    tasks = collect_hbk_tasks(pairs, languages)
    if not tasks:
        return 0
    count = 0
    if max_workers <= 1:
        for path, version, lang in tasks:
            ok, _ = _unpack_one(path, version, lang, output_base, unpack_hbk, verbose)
            if ok:
                count += 1
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futs = [
                executor.submit(_unpack_one, path, version, lang, output_base, unpack_hbk, verbose)
                for path, version, lang in tasks
            ]
            for fut in as_completed(futs):
                ok, _ = fut.result()
                if ok:
                    count += 1
    return count


def discover_version_dirs(base_path: Union[Path, str]) -> List[Tuple[Path, str]]:
    """
    Сканировать базовый каталог: каждая прямая подпапка = версия 1С.
    Возвращает [(путь_к_подпапке, имя_подпапки), ...]. Скрытые и не-каталоги пропускаются.
    На Windows каталоги версий часто имеют вид ...\\8.3.27.1859\\bin — поиск .hbk идёт
    рекурсивно (rglob), так что файлы в bin/ находятся автоматически.
    """
    base = Path(base_path).resolve()
    if not base.is_dir():
        return []
    out: List[Tuple[Path, str]] = []
    for child in sorted(base.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        out.append((child, child.name))
    return out


def parse_source_dirs_env(env_value: Optional[str]) -> List[Tuple[str, str]]:
    """
    Parse HELP_SOURCE_DIRS (legacy): "path1:version1,path2:version2" or "path1,path2".
    Returns [(path, version), ...]. Prefer HELP_SOURCE_BASE instead.
    """
    if not env_value or not env_value.strip():
        return []
    out = []
    for part in env_value.strip().split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            p, v = part.split(":", 1)
            out.append((p.strip(), v.strip()))
        else:
            p = part
            v = Path(p).name or "default"
            out.append((p, v))
    return out


def parse_languages_env(env_value: Optional[str]) -> Optional[List[str]]:
    """
    Parse HELP_LANGUAGES: "ru" => ["ru"], "ru,en" => ["ru","en"], empty or "all" => None (all languages).
    """
    if not env_value or not env_value.strip():
        return None
    raw = env_value.strip().lower()
    if raw == "all":
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]
