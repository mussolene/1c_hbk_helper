"""Build and query Qdrant index from Markdown help."""

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

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
VECTOR_SIZE = 384  # default for all-MiniLM-L6-v2; overridden when EMBEDDING_BACKEND=openai_api
# Макс. символов в один запрос к эмбеддингам (~512 токенов у all-MiniLM-L6-v2 и многих моделей в LM Studio)
MAX_EMBEDDING_INPUT_CHARS = 2000

_embedding_model = None

_EMBEDDING_BACKEND = os.environ.get("EMBEDDING_BACKEND", "local").strip().lower()
_EMBEDDING_MODEL = (os.environ.get("EMBEDDING_MODEL") or "all-MiniLM-L6-v2").strip()
# LM Studio: популярные модели эмбеддингов по приоритету, если заданная модель не найдена на сервере
_LMSTUDIO_PREFERRED_EMBEDDING_MODELS = (
    "nomic-embed-text",
    "all-MiniLM-L6-v2",
    "text-embedding-3-small",
)
# LM Studio по умолчанию слушает порт 1234; в контейнере хост — host.docker.internal (задать в compose/env)
_EMBEDDING_API_URL = (
    os.environ.get("EMBEDDING_API_URL") or "http://localhost:1234/v1"
).strip().rstrip("/")
_EMBEDDING_API_KEY = (os.environ.get("EMBEDDING_API_KEY") or "").strip()
_EMBEDDING_DIMENSION = (os.environ.get("EMBEDDING_DIMENSION") or "").strip()

# Кэш: выбранный model id для openai_api (чтобы не дергать GET /v1/models каждый раз)
_resolved_api_model_id: Optional[str] = None
# Кэш размерности при openai_api без EMBEDDING_DIMENSION (определяется по первому ответу API)
_cached_api_dimension: Optional[int] = None
_dimension_detecting: bool = False
# Если внешний API эмбеддингов недоступен — продолжаем с плейсхолдер-векторами
_embedding_api_available: Optional[bool] = None


def _check_embedding_api_available() -> bool:
    """Проверить доступность внешнего API эмбеддингов; при недоступности пишет в stderr и возвращает False."""
    global _embedding_api_available
    if _embedding_api_available is not None:
        return _embedding_api_available
    if _EMBEDDING_BACKEND != "openai_api" or not _EMBEDDING_API_URL:
        _embedding_api_available = True
        return True
    try:
        req = urllib.request.Request(
            f"{_EMBEDDING_API_URL}/models",
            headers={"Content-Type": "application/json"}
            | ({"Authorization": f"Bearer {_EMBEDDING_API_KEY}"} if _EMBEDDING_API_KEY else {}),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
        _embedding_api_available = True
        return True
    except Exception as e:
        _embedding_api_available = False
        print(
            f"[embedding] Внешний сервис эмбеддингов недоступен ({_EMBEDDING_API_URL}): {e!r}",
            file=sys.stderr,
            flush=True,
        )
        print(
            "[embedding] Продолжаю индексирование с плейсхолдер-векторами (семантический поиск ограничен).",
            file=sys.stderr,
            flush=True,
        )
        return False


def get_embedding_dimension() -> int:
    """Return vector size for the current embedding backend (for collection creation)."""
    global _cached_api_dimension, _dimension_detecting
    if _EMBEDDING_BACKEND == "openai_api" and _EMBEDDING_DIMENSION:
        try:
            return int(_EMBEDDING_DIMENSION)
        except ValueError:
            pass
    if _EMBEDDING_BACKEND == "openai_api" and _EMBEDDING_API_URL:
        if _cached_api_dimension is not None:
            return _cached_api_dimension
        _dimension_detecting = True
        try:
            vec = _get_embedding_api(".")
            _cached_api_dimension = len(vec)
            return _cached_api_dimension
        except Exception:
            pass
        finally:
            _dimension_detecting = False
    return VECTOR_SIZE


def _resolve_openai_api_model() -> str:
    """Для openai_api: вернуть id модели — из списка на сервере (предпочтительная или первая), при необходимости загрузить через LM Studio API."""
    global _resolved_api_model_id
    if _resolved_api_model_id is not None:
        return _resolved_api_model_id
    model_ids: List[str] = []
    try:
        req = urllib.request.Request(
            f"{_EMBEDDING_API_URL}/models",
            headers={"Content-Type": "application/json"}
            | ({"Authorization": f"Bearer {_EMBEDDING_API_KEY}"} if _EMBEDDING_API_KEY else {}),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # OpenAI-формат: {"data": [{"id": "..."}, ...]}
        for item in data.get("data") or []:
            if isinstance(item, dict) and item.get("id"):
                model_ids.append(str(item["id"]))
        # Нативный LM Studio: {"models": [{"key": "...", "type": "embedding"}, ...]}
        for item in data.get("models") or []:
            if isinstance(item, dict) and item.get("key"):
                model_ids.append(str(item["key"]))
    except Exception:
        pass
    # Точное совпадение с заданной моделью
    if _EMBEDDING_MODEL in model_ids:
        _resolved_api_model_id = _EMBEDDING_MODEL
        return _resolved_api_model_id
    # Ищем предпочтительную (по подстроке в id)
    for preferred in _LMSTUDIO_PREFERRED_EMBEDDING_MODELS:
        for mid in model_ids:
            if preferred in mid or mid in preferred:
                _resolved_api_model_id = mid
                return _resolved_api_model_id
    # Первая загруженная / первая в списке
    if model_ids:
        _resolved_api_model_id = model_ids[0]
        return _resolved_api_model_id
    # Пробуем загрузить модель через нативный API LM Studio (POST /api/v1/models/load)
    base_url = _EMBEDDING_API_URL.rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    try:
        load_req = urllib.request.Request(
            f"{base_url}/api/v1/models",
            method="GET",
            headers={"Content-Type": "application/json"}
            | ({"Authorization": f"Bearer {_EMBEDDING_API_KEY}"} if _EMBEDDING_API_KEY else {}),
        )
        with urllib.request.urlopen(load_req, timeout=10) as resp:
            native = json.loads(resp.read().decode("utf-8"))
        for item in native.get("models") or []:
            if isinstance(item, dict) and item.get("type") == "embedding" and item.get("key"):
                key = str(item["key"])
                load_body = json.dumps({"model": key}).encode("utf-8")
                post = urllib.request.Request(
                    f"{base_url}/api/v1/models/load",
                    data=load_body,
                    headers={"Content-Type": "application/json"}
                    | ({"Authorization": f"Bearer {_EMBEDDING_API_KEY}"} if _EMBEDDING_API_KEY else {}),
                    method="POST",
                )
                urllib.request.urlopen(post, timeout=120)
                _resolved_api_model_id = key
                return _resolved_api_model_id
    except Exception:
        pass
    _resolved_api_model_id = _EMBEDDING_MODEL
    return _resolved_api_model_id


def _get_embedding_local(text: str) -> list[float]:
    """Embedding via sentence-transformers (cached); fallback to hash placeholder if unavailable."""
    global _embedding_model
    try:
        from sentence_transformers import SentenceTransformer

        if _embedding_model is None:
            _embedding_model = SentenceTransformer(_EMBEDDING_MODEL)
        return _embedding_model.encode(text, convert_to_numpy=True).tolist()
    except ImportError:
        import hashlib

        h = hashlib.sha256(text.encode()).digest()
        return [(h[i % len(h)] - 128) / 128.0 for i in range(VECTOR_SIZE)]


def _embedding_fallback_dim() -> int:
    """Размерность для плейсхолдера при ошибке API; без рекурсии при определении размерности."""
    return VECTOR_SIZE if _dimension_detecting else get_embedding_dimension()


def _get_embedding_api(text: str) -> list[float]:
    """Embedding via OpenAI-compatible API (LM Studio, Ollama, llama.cpp server, etc.)."""
    if not _EMBEDDING_API_URL:
        import hashlib

        h = hashlib.sha256(text.encode()).digest()
        dim = _embedding_fallback_dim()
        return [(h[i % len(h)] - 128) / 128.0 for i in range(dim)]
    if not _check_embedding_api_available():
        return _get_embedding_placeholder(text, _embedding_fallback_dim())
    model_id = _resolve_openai_api_model()
    url = f"{_EMBEDDING_API_URL}/embeddings"
    body = json.dumps({"model": model_id, "input": text[:MAX_EMBEDDING_INPUT_CHARS]}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {_EMBEDDING_API_KEY}"} if _EMBEDDING_API_KEY else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        global _resolved_api_model_id
        _resolved_api_model_id = None  # при следующем вызове попробуем снова разрешить модель
        import hashlib

        h = hashlib.sha256(text.encode()).digest()
        dim = _embedding_fallback_dim()
        return [(h[i % len(h)] - 128) / 128.0 for i in range(dim)]
    out = data.get("data") or []
    first = out[0] if out else None
    if not isinstance(first, dict) or "embedding" not in first:
        import hashlib

        h = hashlib.sha256(text.encode()).digest()
        dim = _embedding_fallback_dim()
        return [(h[i % len(h)] - 128) / 128.0 for i in range(dim)]
    return list(first["embedding"])


def _get_embedding_placeholder(text: str, dimension: int = VECTOR_SIZE) -> list[float]:
    """Deterministic placeholder vector (no model, no API). Used when backend is 'none' or fallback."""
    import hashlib

    h = hashlib.sha256(text.encode()).digest()
    return [(h[i % len(h)] - 128) / 128.0 for i in range(dimension)]


def _get_embedding(text: str) -> list[float]:
    """Produce embedding for text; backend from env: local, openai_api, or none (placeholder only)."""
    if _EMBEDDING_BACKEND == "none" or _EMBEDDING_BACKEND == "null" or _EMBEDDING_BACKEND == "off":
        return _get_embedding_placeholder(text, get_embedding_dimension())
    if _EMBEDDING_BACKEND == "openai_api":
        return _get_embedding_api(text)
    return _get_embedding_local(text)


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
    from .html2md import (
    _ENCODINGS_UTF8_FIRST,
    _looks_like_html,
    html_to_md_content,
    read_file_with_encoding_fallback,
)

    if QdrantClient is None:
        raise RuntimeError("qdrant-client is required. pip install qdrant-client")
    if _EMBEDDING_BACKEND == "openai_api":
        _check_embedding_api_available()
    client = QdrantClient(host=qdrant_host, port=qdrant_port, check_compatibility=False)
    docs_dir = Path(docs_dir)
    extra = dict(extra_payload or {})
    version = extra.get("version", "")
    language = extra.get("language", "")

    def make_point(
        path: Path, rel_str: str, text: str, title: str, point_index: int
    ) -> PointStruct:
        vector = _get_embedding(text[:MAX_EMBEDDING_INPUT_CHARS])
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
                    text = read_file_with_encoding_fallback(path, encodings=_ENCODINGS_UTF8_FIRST)
                else:
                    text = (
                        html_to_md_content(path)
                        if path.suffix == ".html" or not path.suffix
                        else ""
                    )
                    if not text:
                        try:
                            text = read_file_with_encoding_fallback(path)[:50000]
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
                        vectors_config=VectorParams(size=get_embedding_dimension(), distance=Distance.COSINE),
                    )
            else:
                client.recreate_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=get_embedding_dimension(), distance=Distance.COSINE),
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


def _path_inside_base(path: Path, base: Path) -> bool:
    """Return True if path resolves to a location under base (prevents path traversal)."""
    try:
        resolved = path.resolve()
        base_resolved = base.resolve()
        return resolved.is_relative_to(base_resolved) or resolved == base_resolved
    except (ValueError, OSError):
        return False


def get_topic_by_path(help_path, topic_path) -> str:
    """Read topic content: .md first, then .html converted to Markdown."""
    base = Path(help_path).resolve()
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
        if not _path_inside_base(p, base):
            continue
        if p.exists() and p.is_file():
            if p.suffix == ".md":
                return read_file_with_encoding_fallback(p, encodings=_ENCODINGS_UTF8_FIRST)
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
