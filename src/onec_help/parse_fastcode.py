"""Parse FastCode templates (https://fastcode.im/Templates) into snippets JSON.

Listing pages show truncated code. Items with detail links are fetched for full code.
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

_DETAIL_LINK_RE = re.compile(r"/Templates/(\d+)/")


def _create_opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def _fetch_url(url: str, opener: urllib.request.OpenerDirector) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; 1c-help-parser)"})
    with opener.open(req, timeout=30) as r:
        return r.read().decode("utf-8")


def _fetch_page(page: int, opener: urllib.request.OpenerDirector) -> str:
    url = f"https://fastcode.im/Templates?Page={page}"
    return _fetch_url(url, opener)


def _extract_desc_from_code(code: str) -> str:
    """Extract description from leading // comments in code."""
    lines = code.split("\n")
    parts = []
    for line in lines:
        s = line.strip()
        if s.startswith("//"):
            parts.append(s.lstrip("/").strip())
        elif parts:
            break
    return " ".join(parts)[:500].strip()


def _extract_detail_links(soup: Any) -> dict[str, str]:
    """Build title -> detail_url mapping from links with /Templates/ID/slug."""
    mapping: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if _DETAIL_LINK_RE.search(href) and "?" not in href.split("#")[0]:
            h3 = a.find_previous("h3")
            if h3:
                title = h3.get_text(strip=True)
                if title and title not in mapping:
                    full = "https://fastcode.im" + href.split("?")[0] if href.startswith("/") else href.split("?")[0]
                    mapping[title] = full
    return mapping


def parse_detail_page(html: str) -> tuple[str, str]:
    """Extract full description and code from detail page. Returns (desc, code)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    desc = ""
    for span in soup.find_all("span", class_=lambda c: c and "break-word" in c):
        t = span.get_text(strip=True)
        if len(t) > len(desc) and len(t) < 1000:
            desc = t
    if not desc and soup.find("h1"):
        desc = soup.find("h1").get_text(strip=True)

    blocks: list[str] = []
    for pre in soup.find_all("pre"):
        code = pre.get_text().strip()
        if code and len(code) > 20:
            blocks.append(code)
    code = "\n\n".join(blocks) if blocks else ""
    return (desc, code)


def parse_page(html: str) -> list[dict[str, Any]]:
    """Parse listing page into list of {title, description, code_snippet, detail_url?}."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    detail_links = _extract_detail_links(soup)

    h3_to_pre: dict = {}
    for pre in soup.find_all("pre"):
        h3 = pre.find_previous("h3")
        if not h3:
            continue
        title = h3.get_text(strip=True)
        if title and title not in h3_to_pre:
            h3_to_pre[title] = pre

    for h3 in soup.find_all("h3"):
        title = h3.get_text(strip=True)
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        pre = h3_to_pre.get(title)
        code = pre.get_text().strip() if pre else ""

        desc = ""
        for tag in h3.find_all_next():
            if tag == pre or (pre and tag.name == "pre"):
                break
            if tag.name == "h3" and tag != h3:
                break
            if tag.name == "span" and "break-word" in (tag.get("class") or []):
                desc = tag.get_text(strip=True)
                break
        if not desc and code:
            desc = _extract_desc_from_code(code)
        if not desc:
            desc = title

        item: dict[str, Any] = {
            "title": title,
            "description": desc[:500] if desc else "",
            "code_snippet": code,
        }
        if title in detail_links:
            item["detail_url"] = detail_links[title]
        items.append(item)
    return items


def run_parse(
    out: Path,
    pages: list[int],
    delay: float = 1.0,
    fetch_detail: bool = True,
) -> int:
    """Fetch listing pages, optionally fetch detail pages for full code. Returns 0 on success."""
    opener = _create_opener()
    all_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    list_err = 0
    detail_err = 0

    total_pages = len(pages)
    progress_line("parse-fastcode │ Listing 0/{} │ 0 items │ 0 err".format(total_pages))

    for i, page in enumerate(pages):
        try:
            html = _fetch_page(page, opener)
        except Exception:
            list_err += 1
            progress_done(f"parse-fastcode │ Page {page} fetch error")
            continue
        page_items = parse_page(html)
        added = 0
        for it in page_items:
            key = (it["title"] or "").strip()
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            all_items.append(it)
            added += 1
        progress_line(
            "parse-fastcode │ Listing {}/{} │ {} items │ {} err".format(
                i + 1, total_pages, len(all_items), list_err
            )
        )
        if i < len(pages) - 1:
            time.sleep(delay)

    if fetch_detail:
        to_fetch = [(idx, it) for idx, it in enumerate(all_items) if it.get("detail_url")]
        total_detail = len(to_fetch)
        if total_detail > 0:
            progress_done(
                "parse-fastcode │ Detail 0/{} │ fetching full code...".format(total_detail)
            )
        for di, (idx, it) in enumerate(to_fetch):
            url = it.pop("detail_url", None)
            if not url:
                continue
            try:
                detail_html = _fetch_url(url, opener)
                desc, code = parse_detail_page(detail_html)
                if code:
                    all_items[idx]["code_snippet"] = code
                if desc:
                    all_items[idx]["description"] = desc[:500]
            except Exception:
                detail_err += 1
            progress_line(
                "parse-fastcode │ Detail {}/{} │ {} ok │ {} err".format(
                    di + 1, total_detail, di + 1 - detail_err, detail_err
                )
            )
            time.sleep(delay)

    for it in all_items:
        it.pop("detail_url", None)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = "parse-fastcode │ ✓ {} snippets → {}".format(len(all_items), out.name)
    if list_err or detail_err:
        summary += " │ {} list err, {} detail err".format(list_err, detail_err)
    progress_done(summary)
    return 0
