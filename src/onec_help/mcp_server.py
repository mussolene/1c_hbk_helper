"""MCP server for 1C Help: search_1c_help, get_1c_help_topic, get_1c_function_info."""

import os
from pathlib import Path
from typing import Any

SNIPPET_MAX_CHARS = 550

# Prefer fastmcp; fallback to mcp package
try:
    from fastmcp import FastMCP

    _HAS_FASTMCP = True
except ImportError:
    FastMCP = None  # type: ignore
    _HAS_FASTMCP = False

_HELP_PATH = None  # Path | None


def _get_help_path() -> Path:
    if _HELP_PATH is None:
        import os

        p = os.environ.get("HELP_PATH")
        if not p:
            raise RuntimeError("HELP_PATH not set")
        return Path(p)
    return _HELP_PATH


def _search(
    query: str,
    limit: int = 10,
    version: str | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    from .indexer import search_index

    return search_index(query, limit=limit, version=version, language=language)


def _search_keyword(
    query: str,
    limit: int = 15,
    version: str | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    from .indexer import search_index_keyword

    return search_index_keyword(query, limit=limit, version=version, language=language)


def _list_titles(limit: int = 100, path_prefix: str = "") -> list[dict[str, Any]]:
    from .indexer import list_index_titles

    return list_index_titles(limit=limit, path_prefix=path_prefix or "")


def _index_status() -> dict[str, Any]:
    from .indexer import get_index_status

    return get_index_status()


def _get_topic(
    topic_path: str,
    version: str | None = None,
    language: str | None = None,
    prefer_index: bool = False,
) -> str:
    from .indexer import get_topic_content

    base = _get_help_path()
    return get_topic_content(
        base,
        topic_path,
        version=version,
        language=language,
        prefer_index=prefer_index,
    )


def run_mcp(
    help_path: Path,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 5050,
    path: str = "/mcp",
) -> None:
    """Run MCP server. help_path: directory with .md or HTML.
    transport: stdio | sse | http | streamable-http. For http/sse, host/port/path used."""
    global _HELP_PATH
    _HELP_PATH = help_path.resolve()

    if not _HAS_FASTMCP:
        raise RuntimeError("fastmcp required: pip install fastmcp")

    mcp = FastMCP("1C Help")

    @mcp.tool()
    def search_1c_help(
        query: str,
        limit: int = 10,
        version: str | None = None,
        language: str | None = None,
        include_user_memory: bool = False,
    ) -> str:
        """Search 1C help by natural language (semantic). Returns list of relevant topics with title, path, and snippet.
        query: search text (e.g. 'Формат', 'Запрос.ПакетПолучения', 'синтаксис ОбъединитьПериоды').
        limit: max number of results (default 10).
        version: optional filter by platform version (e.g. '8.3.27.1859').
        language: optional filter by language (e.g. 'ru').
        include_user_memory: if True, also search user memory (saved snippets, topics) and mark source."""
        results = _search(query, limit=limit, version=version, language=language)
        memory_results: list[dict[str, Any]] = []
        if include_user_memory:
            try:
                from .memory import get_memory_store

                memory_results = get_memory_store().search_long(query, limit=min(5, limit))
            except Exception:
                pass
        if not results and not memory_results:
            return "No results found. Ensure build-index was run and Qdrant is available."
        lines = []
        idx = 1
        suffix = " [help]" if memory_results else ""
        for r in results:
            lines.append(f"{idx}. **{r.get('title', '')}** (path: {r.get('path', '')}){suffix}")
            text = r.get("text", "")[:SNIPPET_MAX_CHARS]
            lines.append(f"   {text}...")
            idx += 1
        for m in memory_results:
            payload = m.get("payload", {})
            title = payload.get("title", "") or payload.get("summary", "")[:80]
            lines.append(f"{idx}. **{title}** [memory]")
            lines.append(f"   {str(payload)[:SNIPPET_MAX_CHARS]}...")
            idx += 1
        return "\n".join(lines)

    @mcp.tool()
    def search_1c_help_keyword(
        query: str,
        limit: int = 15,
        version: str | None = None,
        language: str | None = None,
    ) -> str:
        """Search 1C help by exact substring in title and text (e.g. 'МенеджерКриптографии', 'интерактивный режим').
        Use when semantic search misses specific terms. limit: max results (default 15).
        version: optional filter by platform version. language: optional filter by language."""
        results = _search_keyword(
            query.strip(),
            limit=limit,
            version=version,
            language=language,
        )
        if not results:
            return "No keyword matches. Try search_1c_help for semantic search."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.get('title', '')}** (path: {r.get('path', '')})")
            text = r.get("text", "")[:SNIPPET_MAX_CHARS]
            lines.append(f"   {text}...")
        return "\n".join(lines)

    @mcp.tool()
    def search_1c_help_with_content(
        query: str,
        limit: int = 3,
        version: str | None = None,
        language: str | None = None,
    ) -> str:
        """Search 1C help and return full content of top results in one call.
        Combines search + get_topic for each result. query: search text.
        limit: max topics with full content (default 3). version, language: optional filters."""
        results = _search(query, limit=limit, version=version, language=language)
        if not results:
            return "No results found. Ensure build-index was run and Qdrant is available."
        parts = []
        for _i, r in enumerate(results, 1):
            path = r.get("path", "")
            if not path:
                continue
            content = _get_topic(path, version=version, language=language, prefer_index=False)
            if content:
                parts.append(f"---\n## {path}\n\n{content}")
        return "\n\n".join(parts) if parts else "No content could be retrieved."

    @mcp.tool()
    def get_1c_help_topic(
        topic_path: str,
        version: str | None = None,
        language: str | None = None,
        prefer_index: bool = False,
    ) -> str:
        """Get full help topic content in Markdown by path. Path from search results (e.g. 'zif3_CryptoManager.md').
        Content is read from disk or from index if files were not persisted.
        version, language: optional filters when reading from index.
        prefer_index: if True, read only from index (skip disk)."""
        content = _get_topic(
            topic_path,
            version=version,
            language=language,
            prefer_index=prefer_index,
        )
        if content:
            try:
                from .memory import get_memory_store

                title = content.split("\n")[0].strip().lstrip("#").strip() or ""
                get_memory_store().write_event(
                    "get_topic",
                    {"topic_path": topic_path, "title": title},
                )
            except Exception:
                pass
            return content
        return "Topic not found."

    @mcp.tool()
    def save_1c_snippet(code_snippet: str, description: str = "") -> str:
        """Save a 1C code snippet to user memory for future context.
        code_snippet: the code to remember. description: short explanation of what it does."""
        try:
            from .memory import get_memory_store

            get_memory_store().write_event(
                "save_snippet",
                {"code_snippet": code_snippet, "description": description},
            )
            return "Snippet saved to memory."
        except Exception as e:
            return f"Failed to save: {e}"

    @mcp.tool()
    def get_1c_help_related(
        topic_path: str,
        version: str | None = None,
        language: str | None = None,
    ) -> str:
        """Get list of related topics for a given help topic path.
        Returns paths and titles from outgoing links in the topic.
        topic_path: path from search results (e.g. 'Format971.md').
        version, language: optional filters when reading from index."""
        from .indexer import get_1c_help_related as _get_related

        items = _get_related(
            topic_path,
            version=version,
            language=language,
        )
        if not items:
            return "No related topics found for this path."
        lines = [f"- **{r.get('title', '')}** — `{r.get('path', '')}`" for r in items]
        return "\n".join(lines)

    @mcp.tool()
    def list_1c_help_titles(limit: int = 100, path_prefix: str = "") -> str:
        """List topic titles and paths for browsing. path_prefix: filter by path start (e.g. 'zif' for command-line params)."""
        items = _list_titles(limit=limit, path_prefix=path_prefix)
        if not items:
            return "No topics in index or prefix filter too strict."
        lines = [
            f"{i}. **{r.get('title', '')}** — `{r.get('path', '')}`" for i, r in enumerate(items, 1)
        ]
        return "\n".join(lines)

    @mcp.tool()
    def compare_1c_help(
        topic_path_or_query: str,
        version_left: str,
        version_right: str,
        language: str | None = None,
        include_diff: bool = False,
    ) -> str:
        """Compare a help topic between two platform versions.
        topic_path_or_query: path (e.g. 'Format971.md') or search query to find topic.
        version_left, version_right: version labels (e.g. '8.3.27.1859', '8.3.27.1719').
        include_diff: if True, append unified diff of the two versions."""
        from .indexer import compare_1c_help as _compare

        return _compare(
            topic_path_or_query,
            version_left,
            version_right,
            language=language,
            include_diff=include_diff,
        )

    @mcp.tool()
    def trigger_reindex() -> str:
        """Trigger full reindex (ingest) in the background. Use when help sources changed.
        Returns immediately; indexing runs asynchronously. Check progress with get_1c_help_index_status."""
        import subprocess
        import sys

        try:
            subprocess.Popen(
                [sys.executable, "-m", "onec_help", "ingest"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return "Reindex started in background. Check get_1c_help_index_status for progress."
        except Exception as e:
            return f"Failed to start reindex: {e}"

    @mcp.tool()
    def get_1c_help_index_status() -> str:
        """Check if 1C help is indexed: returns total topics count, collection name, and (if present) versions and languages.
        Use to verify that ingest completed successfully."""
        s = _index_status()
        err = s.get("error")
        if err:
            return f"Error: {err}"
        if not s.get("exists"):
            return "Index does not exist. Run ingest to index the help (e.g. docker compose exec mcp python -m onec_help ingest)."
        count = s.get("points_count")
        name = s.get("collection", "onec_help")
        lines = [
            f"Collection: **{name}**",
            f"Topics indexed: **{count}**",
            f"Embeddings: **{count}**",
        ]
        storage_path = os.environ.get("QDRANT_STORAGE_PATH")
        if storage_path and os.path.isdir(storage_path):
            try:
                total = 0
                for dirpath, _dirnames, filenames in os.walk(storage_path):
                    for f in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, f))
                        except OSError:
                            pass
                lines.append(f"DB size: **{total / (1024 * 1024):.1f} MB**")
            except OSError:
                pass
        if s.get("versions"):
            lines.append(f"Versions (sample): {', '.join(s['versions'])}")
        if s.get("languages"):
            lines.append(f"Languages (sample): {', '.join(s['languages'])}")
        return "\n".join(lines)

    def _match_priority(name_lower: str, title_lower: str) -> int:
        """Lower = better. 0=exact, 1=startswith+space/(, 2=in, 3=no match."""
        if title_lower == name_lower:
            return 0
        if title_lower.startswith(name_lower + " ") or title_lower.startswith(name_lower + "("):
            return 1
        if name_lower in title_lower:
            return 2
        return 3

    @mcp.tool()
    def get_1c_function_info(name: str, path: str | None = None) -> str:
        """Get description, syntax, parameters, return value, and examples for a 1C function/method by name.
        name: function or method name (e.g. 'Формат', 'МенеджерКриптографии').
        path: optional - when given, fetch only this topic path (e.g. 'Format971.md')."""
        name_clean = name.strip()
        if not name_clean:
            return "Provide a function or method name."
        if path:
            content = _get_topic(path)
            return content or "Topic not found."
        results = _search_keyword(name_clean, limit=20)
        if not results:
            results = _search(name_clean, limit=20)
        name_lower = name_clean.lower()
        scored = [(r, _match_priority(name_lower, (r.get("title") or "").lower())) for r in results]
        relevant = [(r, p) for r, p in scored if p <= 2]
        if not relevant:
            relevant = scored
        relevant.sort(key=lambda x: x[1])
        best_priority = relevant[0][1] if relevant else 3
        best = [r for r, p in relevant if p == best_priority]
        if len(best) > 1:
            lines = ["Найдено несколько совпадений:"]
            for r in best[:10]:
                lines.append(f"- {r.get('path', '')}: {r.get('title', '')}")
            content = _get_topic(best[0]["path"])
            if content:
                lines.append("\n---\nКонтент первого совпадения:\n\n" + content)
            return "\n".join(lines)
        if best:
            content = _get_topic(best[0]["path"])
            if content:
                return content
        return "No topic found for this name. Try search_1c_help or search_1c_help_keyword first."

    if transport in ("sse", "http", "streamable-http"):
        path_val = (path or "/mcp").rstrip("/") or "/mcp"
        mcp.run(transport=transport, host=host, port=port, path=path_val)
    else:
        mcp.run(transport="stdio")
