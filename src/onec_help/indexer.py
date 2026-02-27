"""Build and query Qdrant index from Markdown help."""

import os
import re
from pathlib import Path
from typing import Any

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchAny,
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
    MatchAny = None  # type: ignore
    MatchValue = None  # type: ignore

from ._utils import path_inside_base, safe_error_message

COLLECTION_NAME = "onec_help"
SNIPPET_MAX_CHARS = 850

# Regex for CamelCase and Cyrillic identifiers (min 3 chars) for keyword extraction
_KEYWORDS_PATTERN = re.compile(r"[А-Яа-яA-Za-z][А-Яа-яA-Za-z0-9]{2,}")


def _extract_keywords(text: str, max_tokens: int = 50) -> list[str]:
    """Extract CamelCase and Cyrillic identifiers from text for payload.keywords."""
    if not text:
        return []
    tokens = _KEYWORDS_PATTERN.findall(text)
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        tl = t.lower()
        if tl not in seen and len(out) < max_tokens:
            seen.add(tl)
            out.append(t)
    return out


def get_embedding_dimension() -> int:
    """Return vector size for the current embedding backend (for collection creation). Lazy import."""
    from . import embedding

    return embedding.get_embedding_dimension()


def _path_to_point_id(rel_path: str, version: str = "", language: str = "") -> int:
    """Stable integer id from path (and optional version/language) for incremental upsert."""
    import hashlib

    key = f"{version}|{language}|{rel_path}"
    h = hashlib.sha256(key.encode()).hexdigest()[:14]
    return int(h, 16) % (2**63)


def _build_path_to_section(
    nodes: list, base_path: str = "", breadcrumb: list[str] | None = None
) -> dict[str, tuple[str, list[str]]]:
    """Traverse tree from build_tree; return {rel_path_or_stem: (section_path, breadcrumb)}."""
    result: dict[str, tuple[str, list[str]]] = {}
    breadcrumb = breadcrumb or []
    for node in nodes or []:
        title = node.get("title", "")
        path = node.get("path", "")
        children = node.get("children", [])
        if path:
            stem = Path(path).stem
            result[path.replace("\\", "/")] = (base_path, list(breadcrumb))
            result[stem] = (base_path, list(breadcrumb))
        section_path = (base_path + "/" + title) if base_path and title else (title or base_path)
        child_breadcrumb = breadcrumb + ([title] if title else [])
        result.update(_build_path_to_section(children, section_path, child_breadcrumb))
    return result


def build_index(
    docs_dir,
    qdrant_host="localhost",
    qdrant_port=6333,
    collection=COLLECTION_NAME,
    incremental=False,
    extra_payload: dict[str, Any] | None = None,
    batch_size: int = 500,
    embedding_batch_size: int | None = None,
    embedding_workers: int | None = None,
    source_dir: str | None = None,
) -> int:
    """Index .md (and optionally .html) files from docs_dir into Qdrant in batches. Returns total points.
    extra_payload: merged into each point (e.g. {"version": "8.3", "language": "ru"}).
    incremental: if True, do not recreate collection; upsert by path (add new, update changed).
    source_dir: optional path to unpacked HTML with __categories__ for section_path/breadcrumb in payload.
    embedding_batch_size: texts per embedding batch (env EMBEDDING_BATCH_SIZE).
    embedding_workers: parallel API requests for openai_api (env EMBEDDING_WORKERS)."""
    from . import embedding
    from .categories import build_tree, find_categories_root, parse_content_file
    from .html2md import (
        _ENCODINGS_UTF8_FIRST,
        _looks_like_html,
        extract_links_from_markdown,
        extract_outgoing_links,
        html_to_md_content,
        read_file_with_encoding_fallback,
    )

    if QdrantClient is None:
        raise RuntimeError("qdrant-client is required. pip install qdrant-client")
    client = QdrantClient(host=qdrant_host, port=qdrant_port, check_compatibility=False)
    docs_dir = Path(docs_dir)
    extra = dict(extra_payload or {})
    version = extra.get("version", "")
    language = extra.get("language", "")
    max_input_chars = embedding.MAX_EMBEDDING_INPUT_CHARS

    path_to_section: dict[str, tuple[str, list[str]]] = {}
    if source_dir:
        root = find_categories_root(Path(source_dir))
        if root:
            try:
                struct = parse_content_file(root / "__categories__")
                tree = build_tree(root, struct)
                path_to_section = _build_path_to_section(tree)
            except Exception:
                pass

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

    if embedding_batch_size is None:
        embedding_batch_size = embedding._embedding_batch_size()
    if embedding_workers is None:
        embedding_workers = embedding._embedding_workers()

    collection_created = False
    total = 0
    for batch_start in range(0, len(paths_to_index), batch_size):
        batch_paths = paths_to_index[batch_start : batch_start + batch_size]
        items: list[
            tuple[str, str, str, int, list[dict[str, Any]]]
        ] = []  # (rel_str, text, title, point_index, outgoing_links)
        base_for_links = Path(source_dir) if source_dir else docs_dir
        for path in batch_paths:
            try:
                outgoing_links: list[dict[str, Any]] = []
                if path.suffix == ".md":
                    text = read_file_with_encoding_fallback(path, encodings=_ENCODINGS_UTF8_FIRST)
                    if source_dir:
                        html_path = Path(source_dir) / path.relative_to(docs_dir).with_suffix(
                            ".html"
                        )
                        if html_path.exists():
                            outgoing_links = extract_outgoing_links(html_path, Path(source_dir))
                    if not outgoing_links and text:
                        md_links = extract_links_from_markdown(text, path, docs_dir)
                        if md_links:
                            outgoing_links = md_links
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
                    if path.suffix in (".html", "") or not path.suffix:
                        outgoing_links = extract_outgoing_links(path, base_for_links)
                if not text.strip():
                    continue
                rel = path.relative_to(docs_dir)
                rel_str = str(rel).replace("\\", "/")
                title = text.split("\n")[0].strip().lstrip("#").strip() or (
                    path.stem if path.suffix else path.name
                )
                point_index = total + len(items)
                items.append((rel_str, text, title, point_index, outgoing_links))
            except Exception:
                continue
        if not items:
            continue
        texts_for_embedding = [it[1][:max_input_chars] for it in items]
        vectors = embedding.get_embedding_batch(
            texts_for_embedding,
            batch_size=embedding_batch_size,
            workers=embedding_workers,
        )
        if len(vectors) != len(items):
            continue
        points = []
        for idx_in_items, (rel_str, text, title, point_index, outgoing_links) in enumerate(items):
            vector = vectors[idx_in_items]
            point_id = (
                _path_to_point_id(rel_str, version=version, language=language)
                if incremental
                else point_index
            )
            payload = {"path": rel_str, "text": text[:50000], "title": title}
            payload.update(extra)
            if outgoing_links:
                payload["outgoing_links"] = outgoing_links
            first_para = text.split("\n\n")[0] if text else ""
            kw = list(
                dict.fromkeys(_extract_keywords(title) + _extract_keywords(first_para[:800]))
            )[:50]
            if kw:
                payload["keywords"] = kw
            stem = Path(rel_str).stem
            if path_to_section:
                for key in (rel_str, stem, rel_str.replace(".md", ".html")):
                    if key in path_to_section:
                        section_path, breadcrumb = path_to_section[key]
                        payload["section_path"] = section_path
                        payload["breadcrumb"] = breadcrumb
                        break
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))
        if not collection_created:
            dim = embedding.get_embedding_dimension()
            if incremental:
                if not client.collection_exists(collection):
                    client.create_collection(
                        collection_name=collection,
                        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                    )
            else:
                client.recreate_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
            collection_created = True
        client.upsert(collection_name=collection, points=points)
        total += len(points)
    return total


def get_index_status(
    qdrant_host: str | None = None,
    qdrant_port: int | None = None,
    collection: str = COLLECTION_NAME,
    sample_size: int = 500,
) -> dict[str, Any]:
    """Return index status: exists, points_count, and optional version/language breakdown from payload."""
    if QdrantClient is None:
        return {"error": "qdrant-client not available", "exists": False, "points_count": 0}
    host = qdrant_host or os.environ.get("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    try:
        client = QdrantClient(host=host, port=port, check_compatibility=False)
    except Exception as e:
        return {"error": safe_error_message(e), "exists": False, "points_count": 0}
    if not client.collection_exists(collection):
        return {"exists": False, "points_count": 0, "collection": collection}
    try:
        info = client.get_collection(collection)
        points_count = getattr(info, "points_count", None) or getattr(info, "pointsCount", 0)
    except Exception as e:
        return {"exists": True, "points_count": None, "error": safe_error_message(e), "collection": collection}
    out: dict[str, Any] = {
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
    version: str | None = None,
    language: str | None = None,
):
    """Search Qdrant; return list of payloads with path, title, text snippet.
    version, language: optional payload filters."""
    from . import embedding

    host = qdrant_host or os.environ.get("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    if QdrantClient is None:
        return []
    client = QdrantClient(host=host, port=port, check_compatibility=False)
    vector = embedding.get_embedding(query)

    must = []
    if version and Filter and FieldCondition and MatchValue:
        must.append(FieldCondition(key="version", match=MatchValue(value=version)))
    if language and Filter and FieldCondition and MatchValue:
        must.append(FieldCondition(key="language", match=MatchValue(value=language)))
    qfilter = Filter(must=must) if must and Filter else None

    kwargs: dict[str, Any] = {"collection_name": collection, "limit": limit}
    if hasattr(client, "query_points"):
        kwargs["query"] = vector
        if qfilter is not None:
            kwargs["query_filter"] = qfilter
        response = client.query_points(**kwargs)
        hits = getattr(response, "points", [])
    else:
        kwargs["query_vector"] = vector
        if qfilter is not None:
            kwargs["query_filter"] = qfilter
        hits = client.search(**kwargs)
    _SNIPPET_LEN = 550
    raw = []
    for h in hits:
        payload = getattr(h, "payload", None) or {}
        text = (payload.get("text") or "")[:_SNIPPET_LEN]
        links = payload.get("outgoing_links") or []
        if links:
            titles = [lnk.get("target_title") or lnk.get("link_text", "") for lnk in links[:5]]
            text = (text + "\nСвязанные: " + ", ".join(t for t in titles if t)).strip()
        raw.append(
            {
                "path": payload.get("path", ""),
                "title": payload.get("title", ""),
                "text": text,
                "score": getattr(h, "score", None),
            }
        )
    if not version and not language:
        seen: set[str] = set()
        deduped = []
        for r in raw:
            p = r.get("path", "")
            if p and p not in seen:
                seen.add(p)
                deduped.append(r)
        return deduped
    return raw


def get_topic_from_index(
    topic_path: str,
    qdrant_host: str | None = None,
    qdrant_port: int | None = None,
    collection: str = COLLECTION_NAME,
    version: str | None = None,
    language: str | None = None,
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
            must_cond = [FieldCondition(key="path", match=MatchValue(value=pv))]
            if version:
                must_cond.append(FieldCondition(key="version", match=MatchValue(value=version)))
            if language:
                must_cond.append(FieldCondition(key="language", match=MatchValue(value=language)))
            res, _ = client.scroll(
                collection_name=collection,
                scroll_filter=Filter(must=must_cond),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if res and len(res) > 0:
                payload = getattr(res[0], "payload", None) or {}
                text = payload.get("text") or ""
                if text:
                    return _apply_outgoing_links(text, payload)
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
                    return _apply_outgoing_links(text, payload)
    except Exception:
        pass
    return ""


def search_index_keyword(
    query: str,
    qdrant_host: str | None = None,
    qdrant_port: int | None = None,
    collection: str = COLLECTION_NAME,
    limit: int = 15,
    batch_size: int = 500,
    version: str | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Search by keyword (payload.keywords) or substring in title/text (no embedding).
    Finds exact terms (API names, identifiers)."""
    if QdrantClient is None:
        return []
    host = qdrant_host or os.environ.get("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    client = QdrantClient(host=host, port=port, check_compatibility=False)
    q_lower = query.strip().lower()
    if not q_lower:
        return []

    # Type.Method pattern (e.g. HTTPСоединение.Получить): use substring search to preserve exact match
    use_type_method_mode = "." in query

    must: list[Any] = []
    if version and Filter and FieldCondition and MatchValue:
        must.append(FieldCondition(key="version", match=MatchValue(value=version)))
    if language and Filter and FieldCondition and MatchValue:
        must.append(FieldCondition(key="language", match=MatchValue(value=language)))

    query_keywords = _extract_keywords(query, max_tokens=20)
    use_keyword_filter = (
        not use_type_method_mode
        and bool(query_keywords)
        and Filter
        and FieldCondition
        and MatchAny
    )
    if use_keyword_filter:
        must.append(
            FieldCondition(key="keywords", match=MatchAny(any=query_keywords))
        )
    scroll_filter = Filter(must=must) if must and Filter else None

    out: list[dict[str, Any]] = []
    offset = None
    seen_paths: set[str] = set()
    scroll_kwargs: dict[str, Any] = {
        "collection_name": collection,
        "limit": batch_size,
        "with_payload": True,
        "with_vectors": False,
    }
    if scroll_filter is not None:
        scroll_kwargs["scroll_filter"] = scroll_filter

    def _matches(payload: dict[str, Any]) -> bool:
        title = (payload.get("title") or "").lower()
        text = (payload.get("text") or "").lower()
        return q_lower in title or q_lower in text

    def _collect(res: list) -> None:
        nonlocal out, seen_paths
        for point in res:
            payload = getattr(point, "payload", None) or {}
            path = payload.get("path", "")
            if path in seen_paths:
                continue
            if not use_keyword_filter and not _matches(payload):
                continue
            seen_paths.add(path)
            snippet = (payload.get("text") or "")[:SNIPPET_MAX_CHARS]
            links = payload.get("outgoing_links") or []
            if links:
                titles = [
                    lnk.get("target_title") or lnk.get("link_text", "") for lnk in links[:5]
                ]
                snippet = (
                    snippet + "\nСвязанные: " + ", ".join(t for t in titles if t)
                ).strip()
            out.append(
                {
                    "path": path,
                    "title": payload.get("title", ""),
                    "text": snippet,
                    "score": None,
                }
            )
            if len(out) >= limit:
                break

    while len(out) < limit:
        try:
            kwargs = dict(scroll_kwargs)
            if offset is not None:
                kwargs["offset"] = offset
            res, next_offset = client.scroll(**kwargs)
        except Exception:
            break
        if not res:
            break
        _collect(res)
        if next_offset is None:
            break
        offset = next_offset

    # Fallback: if keyword filter returned nothing, retry with substring search
    if not out and use_keyword_filter:
        use_keyword_filter = False
        must.pop()  # remove keywords condition
        scroll_filter = Filter(must=must) if must and Filter else None
        scroll_kwargs["scroll_filter"] = scroll_filter
        if scroll_kwargs.get("scroll_filter") is None:
            scroll_kwargs.pop("scroll_filter", None)
        offset = None
        while len(out) < limit:
            try:
                kwargs = dict(scroll_kwargs)
                if offset is not None:
                    kwargs["offset"] = offset
                res, next_offset = client.scroll(**kwargs)
            except Exception:
                break
            if not res:
                break
            _collect(res)
            if next_offset is None:
                break
            offset = next_offset

    # Type.Method mode: rank title matches above text-only matches
    if use_type_method_mode and out:
        title_lower = q_lower
        out.sort(key=lambda r: (title_lower not in (r.get("title") or "").lower(),))

    return out


def list_index_titles(
    qdrant_host: str | None = None,
    qdrant_port: int | None = None,
    collection: str = COLLECTION_NAME,
    limit: int = 200,
    path_prefix: str = "",
) -> list[dict[str, Any]]:
    """List (title, path) from index for browsing. path_prefix filters by path start (e.g. 'zif').
    Deduplicates by path (one entry per path when multiple versions exist)."""
    if QdrantClient is None:
        return []
    host = qdrant_host or os.environ.get("QDRANT_HOST", "localhost")
    port = qdrant_port or int(os.environ.get("QDRANT_PORT", "6333"))
    client = QdrantClient(host=host, port=port, check_compatibility=False)
    out: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
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
            if path in seen_paths:
                continue
            if prefix and not path.lower().startswith(prefix):
                continue
            seen_paths.add(path)
            out.append({"title": payload.get("title", ""), "path": path})
        if next_offset is None:
            break
        offset = next_offset
    return out[:limit]


def _apply_outgoing_links(text: str, payload: dict[str, Any]) -> str:
    """Substitute hrefs with resolved_path and append Связанные темы section."""
    import re

    links = payload.get("outgoing_links") or []
    for lnk in links:
        href = lnk.get("href", "")
        resolved = lnk.get("resolved_path")
        if not href or not resolved:
            continue
        # Substitute [anything](href) -> [anything](resolved_path)
        escaped_href = re.escape(href)
        text = re.sub(r"\[([^\]]*)\]\(\s*" + escaped_href + r"\s*\)", rf"[\1]({resolved})", text)
    # Append related section for links with resolved_path
    with_resolved = [lnk for lnk in links if lnk.get("resolved_path")]
    if with_resolved:
        lines = ["\n\n## Связанные темы\n"]
        for lnk in with_resolved[:20]:
            rp = lnk.get("resolved_path", "")
            title = lnk.get("target_title") or lnk.get("link_text", "")
            if rp:
                lines.append(f"- [{title}]({rp})")
        text = text + "\n".join(lines)
    return text


def get_topic_by_path(help_path, topic_path) -> str:
    """Read topic content: .md first, then .html converted to Markdown."""
    from .html2md import (
        _ENCODINGS_UTF8_FIRST,
        html_to_md_content,
        read_file_with_encoding_fallback,
    )

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
        if not path_inside_base(p, base):
            continue
        if p.exists() and p.is_file():
            if p.suffix == ".md":
                return read_file_with_encoding_fallback(p, encodings=_ENCODINGS_UTF8_FIRST)
            if p.suffix == ".html":
                return html_to_md_content(p)
    return ""


def get_topic_content(
    help_path,
    topic_path: str,
    qdrant_host: str | None = None,
    qdrant_port: int | None = None,
    collection: str = COLLECTION_NAME,
    version: str | None = None,
    language: str | None = None,
    prefer_index: bool = False,
) -> str:
    """Get topic text: first from disk (help_path), then from Qdrant payload if not found.
    prefer_index: if True, skip disk and read only from Qdrant."""
    if not prefer_index:
        content = get_topic_by_path(help_path, topic_path)
        if content:
            return content
    return get_topic_from_index(
        topic_path,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        collection=collection,
        version=version,
        language=language,
    )


def get_1c_help_related(
    topic_path: str,
    qdrant_host: str | None = None,
    qdrant_port: int | None = None,
    collection: str = COLLECTION_NAME,
    version: str | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Return list of related topics for a given path: [{path, title}] from outgoing_links."""
    if QdrantClient is None or Filter is None or FieldCondition is None or MatchValue is None:
        return []
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
            must_cond = [FieldCondition(key="path", match=MatchValue(value=pv))]
            if version:
                must_cond.append(FieldCondition(key="version", match=MatchValue(value=version)))
            if language:
                must_cond.append(FieldCondition(key="language", match=MatchValue(value=language)))
            res, _ = client.scroll(
                collection_name=collection,
                scroll_filter=Filter(must=must_cond),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if res and len(res) > 0:
                payload = getattr(res[0], "payload", None) or {}
                links = payload.get("outgoing_links") or []
                return [
                    {
                        "path": lnk.get("resolved_path", ""),
                        "title": lnk.get("target_title") or lnk.get("link_text", ""),
                    }
                    for lnk in links
                    if lnk.get("resolved_path")
                ]
        except Exception:
            continue
    return []


def compare_1c_help(
    topic_path_or_query: str,
    version_left: str,
    version_right: str,
    qdrant_host: str | None = None,
    qdrant_port: int | None = None,
    collection: str = COLLECTION_NAME,
    language: str | None = None,
    include_diff: bool = False,
) -> str:
    """Compare topic content between two versions. Returns formatted comparison or diff."""
    path = topic_path_or_query.strip()
    if ".md" not in path and ".html" not in path:
        results = search_index(
            path,
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            collection=collection,
            limit=1,
            version=version_left,
            language=language,
        )
        if not results:
            results = search_index(
                path,
                qdrant_host=qdrant_host,
                qdrant_port=qdrant_port,
                collection=collection,
                limit=1,
                language=language,
            )
        if not results:
            return f"Topic not found for query: {path}"
        path = results[0].get("path", "")
    content_left = get_topic_content(
        "",
        path,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        collection=collection,
        version=version_left,
        language=language,
        prefer_index=True,
    )
    content_right = get_topic_content(
        "",
        path,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        collection=collection,
        version=version_right,
        language=language,
        prefer_index=True,
    )
    if not content_left and not content_right:
        return f"Topic not found in either version for path: {path}"
    out = f"## Версия {version_left}\n\n{content_left or '(нет контента)'}\n\n---\n\n## Версия {version_right}\n\n{content_right or '(нет контента)'}"
    if include_diff and content_left and content_right:
        import difflib

        lines_left = content_left.splitlines(keepends=True)
        lines_right = content_right.splitlines(keepends=True)
        diff = difflib.unified_diff(
            lines_left,
            lines_right,
            fromfile=f"v{version_left}",
            tofile=f"v{version_right}",
            lineterm="",
        )
        out += "\n\n---\n\n## Diff\n\n```\n" + "".join(diff) + "\n```"
    return out
