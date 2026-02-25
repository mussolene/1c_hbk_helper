"""Build and query Qdrant index from Markdown help."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Optional: use sentence-transformers or a small embedding model
# For minimal deps we use a simple hash-based placeholder; replace with real embeddings for production.
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )
except ImportError:
    QdrantClient = None  # type: ignore
    PointStruct = None  # type: ignore
    VectorParams = None  # type: ignore
    Distance = None  # type: ignore
    FieldCondition = None  # type: ignore
    Filter = None  # type: ignore
    MatchValue = None  # type: ignore


COLLECTION_NAME = "onec_help"
VECTOR_SIZE = 384  # default for all-MiniLM-L6-v2; use same in search


def _get_embedding(text: str) -> list[float]:
    """Produce embedding for text. Prefer sentence-transformers; fallback to simple placeholder."""
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(text, convert_to_numpy=True).tolist()
    except ImportError:
        # Placeholder: deterministic pseudo-vector so tests/indexing work without the model
        import hashlib

        h = hashlib.sha256(text.encode()).digest()
        # Extend to VECTOR_SIZE by repeating
        return [(h[i % len(h)] - 128) / 128.0 for i in range(VECTOR_SIZE)]


def _path_to_point_id(rel_path: str, version: str = "", language: str = "") -> int:
    """Stable integer id from path (and optional version/language) for incremental upsert."""
    import hashlib

    key = f"{version}|{language}|{rel_path}"
    h = hashlib.sha256(key.encode()).hexdigest()[:14]
    return int(h, 16) % (2**63)


def build_index(
    docs_dir,
    qdrant_host="localhost",
    qdrant_port=6333,
    collection=COLLECTION_NAME,
    incremental=False,
    extra_payload: Optional[Dict[str, Any]] = None,
    batch_size: int = 500,
) -> int:
    """Index .md (and optionally .html) files from docs_dir into Qdrant in batches. Returns total points.
    extra_payload: merged into each point (e.g. {"version": "8.3", "language": "ru"}).
    incremental: if True, do not recreate collection; upsert by path (add new, update changed).
    batch_size: upsert every N files to avoid one huge blocking call."""
    from .html2md import _looks_like_html, html_to_md_content

    if QdrantClient is None:
        raise RuntimeError("qdrant-client is required. pip install qdrant-client")
    client = QdrantClient(host=qdrant_host, port=qdrant_port, check_compatibility=False)
    docs_dir = Path(docs_dir)
    extra = dict(extra_payload or {})
    version = extra.get("version", "")
    language = extra.get("language", "")

    def make_point(
        path: Path, rel_str: str, text: str, title: str, point_index: int
    ) -> PointStruct:
        vector = _get_embedding(text[:8000])
        point_id = (
            _path_to_point_id(rel_str, version=version, language=language)
            if incremental
            else point_index
        )
        payload = {"path": rel_str, "text": text[:50000], "title": title}
        payload.update(extra)
        return PointStruct(id=point_id, vector=vector, payload=payload)

    paths_to_index: list[Path] = []
    for path in docs_dir.rglob("*.md"):
        if path.is_file():
            paths_to_index.append(path)
    if not paths_to_index:
        html_paths = list(docs_dir.rglob("*.html"))
        for p in docs_dir.rglob("*"):
            if not p.is_file():
                continue
            if "." in p.name or p.name == ".gitkeep":
                continue
            if _looks_like_html(p) and p not in html_paths:
                html_paths.append(p)
        paths_to_index = html_paths

    if not paths_to_index:
        return 0

    collection_created = False
    total = 0
    for batch_start in range(0, len(paths_to_index), batch_size):
        batch_paths = paths_to_index[batch_start : batch_start + batch_size]
        points: list[PointStruct] = []
        for idx, path in enumerate(batch_paths):
            try:
                if path.suffix == ".md":
                    text = path.read_text(encoding="utf-8")
                else:
                    text = (
                        html_to_md_content(path)
                        if path.suffix == ".html" or not path.suffix
                        else ""
                    )
                    if not text:
                        try:
                            text = path.read_text(encoding="utf-8", errors="ignore")[:8000]
                        except Exception:
                            continue
                if not text.strip():
                    continue
                rel = path.relative_to(docs_dir)
                rel_str = str(rel).replace("\\", "/")
                title = text.split("\n")[0].strip().lstrip("#").strip() or (
                    path.stem if path.suffix else path.name
                )
                points.append(make_point(path, rel_str, text, title, total + len(points)))
            except Exception:
                continue
        if not points:
            continue
        if not collection_created:
            if incremental:
                if not client.collection_exists(collection):
                    client.create_collection(
                        collection_name=collection,
                        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
                    )
            else:
                client.recreate_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
                )
            collection_created = True
        client.upsert(collection_name=collection, points=points)
        total += len(points)
    return total


def get_index_status(
    qdrant_host: Optional[str] = None,
    qdrant_port: Optional[int] = None,
    collection: str = COLLECTION_NAME,
    sample_size: int = 500,
) -> Dict[str, Any]:
    """Return index status: exists, points_count, and optional version/language breakdown from payload."""
    if QdrantClient is None:
        return {"error": "qdrant-client not available", "exists": False, "points_count": 0}
    host = qdrant_host or os.environ.get("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    try:
        client = QdrantClient(host=host, port=port, check_compatibility=False)
    except Exception as e:
        return {"error": str(e), "exists": False, "points_count": 0}
    if not client.collection_exists(collection):
        return {"exists": False, "points_count": 0, "collection": collection}
    try:
        info = client.get_collection(collection)
        points_count = getattr(info, "points_count", None) or getattr(info, "pointsCount", 0)
    except Exception as e:
        return {"exists": True, "points_count": None, "error": str(e), "collection": collection}
    out: Dict[str, Any] = {
        "exists": True,
        "points_count": points_count,
        "collection": collection,
    }
    try:
        res, _ = client.scroll(
            collection_name=collection,
            limit=min(sample_size, points_count or 0),
            with_payload=True,
            with_vectors=False,
        )
        versions: set = set()
        languages: set = set()
        for point in res or []:
            p = getattr(point, "payload", None) or {}
            if p.get("version"):
                versions.add(p["version"])
            if p.get("language"):
                languages.add(p["language"])
        if versions:
            out["versions"] = sorted(versions)
        if languages:
            out["languages"] = sorted(languages)
    except Exception:
        pass
    return out


def search_index(
    query,
    qdrant_host=None,
    qdrant_port=None,
    collection=COLLECTION_NAME,
    limit=10,
):
    """Search Qdrant; return list of payloads with path, title, text snippet."""
    host = qdrant_host or os.environ.get("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    if QdrantClient is None:
        return []
    client = QdrantClient(host=host, port=port, check_compatibility=False)
    vector = _get_embedding(query)
    # qdrant-client 2.x: query_points(query=...); 1.x: search(query_vector=...)
    if hasattr(client, "query_points"):
        response = client.query_points(
            collection_name=collection,
            query=vector,
            limit=limit,
        )
        hits = getattr(response, "points", [])
    else:
        hits = client.search(
            collection_name=collection,
            query_vector=vector,
            limit=limit,
        )
    return [
        {
            "path": (getattr(h, "payload", None) or {}).get("path", ""),
            "title": (getattr(h, "payload", None) or {}).get("title", ""),
            "text": ((getattr(h, "payload", None) or {}).get("text") or "")[:500],
            "score": getattr(h, "score", None),
        }
        for h in hits
    ]


def get_topic_from_index(
    topic_path: str,
    qdrant_host: Optional[str] = None,
    qdrant_port: Optional[int] = None,
    collection: str = COLLECTION_NAME,
) -> str:
    """Return full topic text from Qdrant payload by path (when file is not on disk)."""
    if QdrantClient is None or Filter is None or FieldCondition is None or MatchValue is None:
        return ""
    host = qdrant_host or os.environ.get("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    topic_path = topic_path.lstrip("/")
    path_variants = [topic_path]
    if not topic_path.endswith(".md") and not topic_path.endswith(".html"):
        path_variants.append(topic_path + ".md")
        path_variants.append(topic_path + ".html")
    client = QdrantClient(host=host, port=port, check_compatibility=False)
    for pv in path_variants:
        try:
            res, _ = client.scroll(
                collection_name=collection,
                scroll_filter=Filter(must=[FieldCondition(key="path", match=MatchValue(value=pv))]),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if res and len(res) > 0:
                payload = getattr(res[0], "payload", None) or {}
                text = payload.get("text") or ""
                if text:
                    return text
        except Exception:
            continue
    # Fallback: scroll and match path by suffix (handles version/language prefixes)
    try:
        res, _ = client.scroll(
            collection_name=collection,
            limit=200,
            with_payload=True,
            with_vectors=False,
        )
        topic_path_norm = topic_path.replace("\\", "/")
        for point in res or []:
            payload = getattr(point, "payload", None) or {}
            p = (payload.get("path") or "").replace("\\", "/")
            if (
                p == topic_path_norm
                or p.endswith("/" + topic_path_norm)
                or p.endswith(topic_path_norm)
            ):
                text = payload.get("text") or ""
                if text:
                    return text
    except Exception:
        pass
    return ""


def search_index_keyword(
    query: str,
    qdrant_host: Optional[str] = None,
    qdrant_port: Optional[int] = None,
    collection: str = COLLECTION_NAME,
    limit: int = 15,
    batch_size: int = 500,
) -> List[Dict[str, Any]]:
    """Search by substring in title and text (no embedding). Finds exact terms like МенеджерКриптографии."""
    if QdrantClient is None:
        return []
    host = qdrant_host or os.environ.get("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    client = QdrantClient(host=host, port=port, check_compatibility=False)
    q_lower = query.strip().lower()
    if not q_lower:
        return []
    out: List[Dict[str, Any]] = []
    offset = None
    seen_paths: set[str] = set()
    while len(out) < limit:
        try:
            res, next_offset = client.scroll(
                collection_name=collection,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            break
        if not res:
            break
        for point in res:
            payload = getattr(point, "payload", None) or {}
            path = payload.get("path", "")
            if path in seen_paths:
                continue
            title = (payload.get("title") or "").lower()
            text = (payload.get("text") or "").lower()
            if q_lower in title or q_lower in text:
                seen_paths.add(path)
                out.append(
                    {
                        "path": path,
                        "title": payload.get("title", ""),
                        "text": (payload.get("text") or "")[:500],
                        "score": None,
                    }
                )
                if len(out) >= limit:
                    break
        if next_offset is None:
            break
        offset = next_offset
    return out


def list_index_titles(
    qdrant_host: Optional[str] = None,
    qdrant_port: Optional[int] = None,
    collection: str = COLLECTION_NAME,
    limit: int = 200,
    path_prefix: str = "",
) -> List[Dict[str, Any]]:
    """List (title, path) from index for browsing. path_prefix filters by path start (e.g. 'zif')."""
    if QdrantClient is None:
        return []
    host = qdrant_host or os.environ.get("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    client = QdrantClient(host=host, port=port, check_compatibility=False)
    out: List[Dict[str, Any]] = []
    offset = None
    prefix = (path_prefix or "").strip().lower()
    while len(out) < limit:
        try:
            res, next_offset = client.scroll(
                collection_name=collection,
                limit=min(500, limit - len(out) + 100),
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            break
        if not res:
            break
        for point in res:
            if len(out) >= limit:
                break
            payload = getattr(point, "payload", None) or {}
            path = payload.get("path", "")
            if prefix and not path.lower().startswith(prefix):
                continue
            out.append({"title": payload.get("title", ""), "path": path})
        if next_offset is None:
            break
        offset = next_offset
    return out[:limit]


def get_topic_by_path(help_path, topic_path) -> str:
    """Read topic content: .md first, then .html converted to Markdown."""
    base = Path(help_path)
    topic_path = topic_path.lstrip("/")
    # Try as given, then .md, then .html
    candidates = [base / topic_path]
    stem = (base / topic_path).stem
    parent = (base / topic_path).parent
    if stem and str(parent) != ".":
        candidates.append(parent / f"{stem}.md")
        candidates.append(parent / f"{stem}.html")
    if not topic_path.endswith(".md") and not topic_path.endswith(".html"):
        candidates.append(base / f"{topic_path}.md")
        candidates.append(base / f"{topic_path}.html")
    for p in candidates:
        if p.exists() and p.is_file():
            if p.suffix == ".md":
                return p.read_text(encoding="utf-8")
            if p.suffix == ".html":
                from .html2md import html_to_md_content

                return html_to_md_content(p)
    return ""


def get_topic_content(
    help_path,
    topic_path: str,
    qdrant_host: Optional[str] = None,
    qdrant_port: Optional[int] = None,
    collection: str = COLLECTION_NAME,
) -> str:
    """Get topic text: first from disk (help_path), then from Qdrant payload if not found."""
    content = get_topic_by_path(help_path, topic_path)
    if content:
        return content
    return get_topic_from_index(
        topic_path,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        collection=collection,
    )
