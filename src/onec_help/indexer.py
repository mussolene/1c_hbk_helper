"""Build and query Qdrant index from Markdown help."""

import os
from pathlib import Path
from typing import Any

# Optional: use sentence-transformers or a small embedding model
# For minimal deps we use a simple hash-based placeholder; replace with real embeddings for production.
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
except ImportError:
    QdrantClient = None  # type: ignore
    PointStruct = None  # type: ignore
    VectorParams = None  # type: ignore
    Distance = None  # type: ignore


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


def _path_to_point_id(rel_path: str) -> int:
    """Stable integer id from path for incremental upsert (hash in 2^63 range)."""
    import hashlib
    h = hashlib.sha256(rel_path.encode()).hexdigest()[:14]
    return int(h, 16) % (2**63)


def build_index(
    docs_dir,
    qdrant_host="localhost",
    qdrant_port=6333,
    collection=COLLECTION_NAME,
    incremental=False,
) -> int:
    """Index .md (and optionally .html) files from docs_dir into Qdrant. Returns number of points.
    Multi-file: recursively indexes all .md under docs_dir, or .html if no .md.
    incremental: if True, do not recreate collection; upsert by path (add new, update changed).
    New files in folder will appear in index after next build-index run (or build-index --incremental)."""
    if QdrantClient is None:
        raise RuntimeError("qdrant-client is required. pip install qdrant-client")
    client = QdrantClient(host=qdrant_host, port=qdrant_port, check_compatibility=False)
    docs_dir = Path(docs_dir)
    points: list[PointStruct] = []
    # Collect .md files (recursive)
    for path in docs_dir.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = path.relative_to(docs_dir)
        rel_str = str(rel).replace("\\", "/")
        vector = _get_embedding(text[:8000])
        point_id = _path_to_point_id(rel_str) if incremental else len(points)
        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "path": rel_str,
                    "text": text[:12000],
                    "title": text.split("\n")[0].strip().lstrip("#").strip() or path.stem,
                },
            )
        )
    if not points:
        # Fallback: index .html as plain text chunks
        for path in docs_dir.rglob("*.html"):
            try:
                from .html2md import html_to_md_content
                text = html_to_md_content(path)
            except Exception:
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")[:8000]
                except Exception:
                    continue
            if not text.strip():
                continue
            rel = path.relative_to(docs_dir)
            rel_str = str(rel).replace("\\", "/")
            vector = _get_embedding(text[:8000])
            point_id = _path_to_point_id(rel_str) if incremental else len(points)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "path": rel_str,
                        "text": text[:12000],
                        "title": path.stem,
                    },
                )
            )
    if not points:
        return 0
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
    client.upsert(collection_name=collection, points=points)
    return len(points)


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
