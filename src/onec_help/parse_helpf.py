"""Parse HelpF.pro FAQ (https://helpf.pro) into snippets JSON.

Listing pages show truncated content. Detail pages are fetched for full text and code.
"""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.request
from pathlib import Path
from typing import Any

from ._utils import progress_done, progress_line

_BASE_URL = "https://helpf.pro"
_FAQ_VIEW_RE = re.compile(r"/faq/view/(\d+)\.html")
_FILE_VIEW_RE = re.compile(r"/file/view/([^/]+)\.html")
_PAGES_RE = re.compile(r"на\s+(\d+)\s+страницах", re.I)
_FAQ_PAGE_LINK_RE = re.compile(r"/faq/(\d+)\.html")
_FILE_PAGE_LINK_RE = re.compile(r"/file/(\d+)\.html")


def _detect_faq_pages(opener: urllib.request.OpenerDirector) -> list[int]:
    """Fetch faq.html, parse total pages from 'на N страницах' or pagination links."""
    html = _fetch_faq_listing(1, opener)
    m = _PAGES_RE.search(html)
    if m:
        total = int(m.group(1))
        return list(range(1, total + 1))
    pages: set[int] = {1}
    for m in _FAQ_PAGE_LINK_RE.finditer(html):
        pages.add(int(m.group(1)))
    return sorted(pages) if pages else [1]


def _detect_file_pages(opener: urllib.request.OpenerDirector) -> list[int]:
    """Fetch file.html, parse total pages from text or pagination links."""
    html = _fetch_file_listing(1, opener)
    m = _PAGES_RE.search(html)
    if m:
        total = int(m.group(1))
        return list(range(1, total + 1))
    pages: set[int] = {1}
    for m in _FILE_PAGE_LINK_RE.finditer(html):
        pages.add(int(m.group(1)))
    return sorted(pages) if pages else [1]


def _create_opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def _fetch_url(url: str, opener: urllib.request.OpenerDirector) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; 1c-help-parser)"}
    )
    with opener.open(req, timeout=30) as r:
        return r.read().decode("utf-8")


def _fetch_faq_listing(page: int, opener: urllib.request.OpenerDirector) -> str:
    if page <= 1:
        url = f"{_BASE_URL}/faq.html"
    else:
        url = f"{_BASE_URL}/faq/{page}.html"
    return _fetch_url(url, opener)


def _fetch_file_listing(page: int, opener: urllib.request.OpenerDirector) -> str:
    if page <= 1:
        url = f"{_BASE_URL}/file.html"
    else:
        url = f"{_BASE_URL}/file/{page}.html"
    return _fetch_url(url, opener)


def _extract_faq_links(html: str) -> list[tuple[str, str]]:
    """Extract (title, url) from FAQ listing. Deduplicates by URL."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        m = _FAQ_VIEW_RE.search(href)
        if not m or "?" in href.split("#")[0]:
            continue
        full_url = _BASE_URL + href.split("?")[0].split("#")[0]
        if full_url in seen:
            continue
        seen.add(full_url)
        title = a.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        result.append((title[:300], full_url))
    return result


def _extract_file_links(html: str) -> list[tuple[str, str]]:
    """Extract (title, url) from Files listing."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/file/view/" not in href or "?" in href.split("#")[0]:
            continue
        full_url = _BASE_URL + href.split("?")[0].split("#")[0]
        if full_url in seen:
            continue
        seen.add(full_url)
        title = a.get_text(strip=True)
        if not title or len(title) < 3 or title in ("Подробнее", "s"):
            continue
        result.append((title[:300], full_url))
    return result


def parse_faq_detail(html: str, title: str) -> tuple[str, str]:
    """Extract description and code from FAQ detail page. Returns (desc, code)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    desc_parts: list[str] = []
    h1 = soup.find("h1")
    if h1:
        h1_text = h1.get_text(strip=True)
        if h1_text and h1_text != title:
            desc_parts.append(h1_text)

    for p in soup.find_all("p"):
        t = p.get_text(strip=True)
        if t and len(t) > 20 and "Разместил:" not in t and "Подробнее" not in t:
            desc_parts.append(t)

    desc = " ".join(desc_parts)[:800].strip() or title

    blocks: list[str] = []
    for pre in soup.find_all("pre"):
        code = pre.get_text().strip()
        if code and len(code) > 15:
            code = re.sub(r"<br\s*/?>", "\n", code, flags=re.I)
            blocks.append(code)
    code = "\n\n".join(blocks) if blocks else ""
    return (desc, code)


def parse_file_detail(html: str, title: str) -> tuple[str, str]:
    """Extract description from File detail page. Files usually have no code inline."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    desc_parts: list[str] = [title]
    for p in soup.find_all("p"):
        t = p.get_text(strip=True)
        if t and len(t) > 20:
            desc_parts.append(t)
    desc = " ".join(desc_parts)[:800].strip()
    blocks: list[str] = []
    for pre in soup.find_all("pre"):
        code = pre.get_text().strip()
        if code and len(code) > 15:
            blocks.append(code)
    code = "\n\n".join(blocks) if blocks else ""
    return (desc, code)


def run_parse(
    out: Path,
    source: str = "faq",
    pages: list[int] | None = None,
    max_items: int = 0,
    delay: float = 1.0,
    fetch_detail: bool = True,
) -> int:
    """Fetch HelpF.pro FAQ and/or Files, parse into snippets JSON.

    source: 'faq' | 'file' | 'all'
    pages: listing pages to fetch (default: [1] for faq, [1] for file)
    max_items: max items to fetch detail for (0 = all)
    fetch_detail: fetch each detail page for full content
    """
    opener = _create_opener()
    all_items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    list_err = 0
    detail_err = 0

    sources = ["faq", "file"] if source == "all" else [source]
    if pages is None or not pages:
        progress_line("parse-helpf │ Detecting total pages...")
        try:
            if source == "all":
                faq_p = _detect_faq_pages(opener)
                time.sleep(delay)
                file_p = _detect_file_pages(opener)
                pages_by_src = {"faq": faq_p, "file": file_p}
            elif source == "faq":
                pages = _detect_faq_pages(opener)
                pages_by_src = {"faq": pages}
            else:
                pages = _detect_file_pages(opener)
                pages_by_src = {"file": pages}
        except Exception:
            pages_by_src = {src: [1] for src in sources}
        total = sum(len(p) for p in pages_by_src.values())
        progress_done(f"parse-helpf │ detected {total} pages total")
        time.sleep(delay)
    else:
        pages_by_src = {src: pages for src in sources}

    for src in sources:
        src_pages = pages_by_src[src]
        fetch_listing = _fetch_faq_listing if src == "faq" else _fetch_file_listing
        extract_links = _extract_faq_links if src == "faq" else _extract_file_links
        label = "FAQ" if src == "faq" else "Files"

        progress_line(f"parse-helpf │ {label} listing 0/{len(src_pages)} │ 0 items │ 0 err")

        for i, page in enumerate(src_pages):
            try:
                html = fetch_listing(page, opener)
            except Exception:
                list_err += 1
                progress_done(f"parse-helpf │ {label} page {page} fetch error")
                continue
            links = extract_links(html)
            for title, url in links:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                all_items.append(
                    {
                        "title": title,
                        "description": "",
                        "code_snippet": "",
                        "source_url": url,
                        "source": src,
                    }
                )
            progress_line(
                f"parse-helpf │ {label} listing {i + 1}/{len(src_pages)} │ {len(all_items)} items │ {list_err} err"
            )
            if i < len(src_pages) - 1:
                time.sleep(delay)

    if fetch_detail and all_items:
        to_fetch = [(idx, it) for idx, it in enumerate(all_items) if it.get("source_url")]
        if max_items > 0:
            to_fetch = to_fetch[:max_items]
        total_detail = len(to_fetch)
        progress_done(f"parse-helpf │ Detail 0/{total_detail} │ fetching...")
        for di, (idx, it) in enumerate(to_fetch):
            url = it.get("source_url", "")
            if not url:
                continue
            parse_fn = parse_faq_detail if it.get("source") == "faq" else parse_file_detail
            try:
                detail_html = _fetch_url(url, opener)
                desc, code = parse_fn(detail_html, it.get("title", ""))
                if desc:
                    all_items[idx]["description"] = desc[:500]
                if code:
                    all_items[idx]["code_snippet"] = code
            except Exception:
                detail_err += 1
            progress_line(
                f"parse-helpf │ Detail {di + 1}/{total_detail} │ {di + 1 - detail_err} ok │ {detail_err} err"
            )
            time.sleep(delay)

    for it in all_items:
        if it.get("source_url"):
            it["detail_url"] = it.pop("source_url")
        it.pop("source", None)
        if not it.get("code_snippet") and not it.get("description"):
            it["description"] = (it.get("title", "") or "")[:500]

    from .snippet_classifier import classify_snippet_vs_reference

    snippets_n = 0
    for it in all_items:
        it["type"] = classify_snippet_vs_reference(
            it.get("title", ""),
            it.get("description", ""),
            it.get("code_snippet", ""),
        )
        if it["type"] == "snippet":
            snippets_n += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8")

    ref_n = len(all_items) - snippets_n
    summary = (
        f"parse-helpf │ ✓ {len(all_items)} items ({snippets_n} snippets, {ref_n} ref) → {out.name}"
    )
    if list_err or detail_err:
        summary += f" │ {list_err} list err, {detail_err} detail err"
    progress_done(summary)
    return 0
