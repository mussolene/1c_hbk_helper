"""Convert 1C help HTML to Markdown (one .md per article).
Supports: (1) V8SH_* schema (Syntax Helper), (2) Legacy schema (H1–H6, tables, STRONG sections).
See docs/help_formats.md for formal spec."""

import os
import re
from pathlib import Path

from bs4 import BeautifulSoup


def _table_to_md(table) -> str:
    """Convert a <table> to Markdown table."""
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append("| " + " | ".join(cells) + " |")
    if not rows:
        return ""
    if len(rows) >= 2:
        rows.insert(1, "|" + "|".join([" --- " for _ in rows[0].split("|")[1:-1]]) + "|")
    return "\n".join(rows) + "\n\n"


def _legacy_body_to_md(body) -> str:
    """Convert legacy article body (H1–H6, P, TABLE, STRONG) to Markdown."""
    lines = []
    for elem in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "pre"]):
        tag = elem.name.lower()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            lines.append("\n" + "#" * level + " " + elem.get_text(separator=" ", strip=True) + "\n\n")
        elif tag == "table":
            tbl = _table_to_md(elem)
            if tbl:
                lines.append(tbl)
        elif tag == "pre":
            lines.append("```\n" + elem.get_text(separator="\n", strip=True) + "\n```\n\n")
        elif tag == "p":
            text = elem.get_text(separator=" ", strip=True)
            if text:
                # Inline links: keep [text](url)
                for a in elem.find_all("a", href=True):
                    a.replace_with("[" + a.get_text(strip=True) + "](" + a["href"] + ")")
                text = elem.get_text(separator=" ", strip=True)
                lines.append(text + "\n\n")
    return "\n".join(lines).strip()


def html_to_md_content(html_path) -> str:
    """
    Extract help article from HTML and return Markdown string.
    Sections: title, description, syntax, parameters, return value, examples, see also.
    """
    path = Path(html_path)
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Legacy schema: no V8SH_pagetitle → structured body (H1→#, H2–H6, tables)
    title_tag = soup.find("h1", class_="V8SH_pagetitle")
    if not title_tag:
        body = soup.find("body")
        if body:
            md_body = _legacy_body_to_md(body)
            if md_body.strip():
                return md_body.strip()
        title = "Untitled"
    else:
        title = title_tag.get_text(strip=True)

    lines: list[str] = []
    lines.append(f"# {title}\n")

    # Description
    desc_tag = soup.find("p", class_="V8SH_chapter", string=lambda t: t and "Описание:" in (t if isinstance(t, str) else t))
    if not desc_tag and soup.find("p", class_="V8SH_chapter"):
        for p in soup.find_all("p", class_="V8SH_chapter"):
            if p.get_text(strip=True) == "Описание:":
                desc_tag = p
                break
    if desc_tag:
        next_p = desc_tag.find_next_sibling()
        if next_p and next_p.name == "p":
            lines.append("## Описание\n\n")
            lines.append(next_p.get_text(separator=" ", strip=True) + "\n\n")
        else:
            n = desc_tag.find_next()
            if n and getattr(n, "get_text", None):
                lines.append("## Описание\n\n")
                lines.append(n.get_text(separator=" ", strip=True) + "\n\n")

    # Syntax
    syntax_heading = soup.find("p", class_="V8SH_chapter", string=lambda t: t and "Синтаксис:" in (t if isinstance(t, str) else t))
    if not syntax_heading:
        for p in soup.find_all("p", class_="V8SH_chapter"):
            if p.get_text(strip=True) == "Синтаксис:":
                syntax_heading = p
                break
    if syntax_heading:
        lines.append("## Синтаксис\n\n```\n")
        pre = syntax_heading.find_next("pre")
        if pre:
            lines.append(pre.get_text(separator="\n", strip=True) + "\n")
        else:
            next_ = syntax_heading.find_next(string=True)
            if next_:
                syntax_text = str(next_).strip()
                if syntax_text and syntax_text != "Синтаксис:":
                    lines.append(syntax_text + "\n")
        lines.append("```\n\n")

    # Parameters
    params_heading = soup.find("p", class_="V8SH_chapter", string=lambda t: t and "Параметры:" in (t if isinstance(t, str) else t))
    if not params_heading:
        for p in soup.find_all("p", class_="V8SH_chapter"):
            if p.get_text(strip=True) == "Параметры:":
                params_heading = p
                break
    if params_heading:
        lines.append("## Параметры\n\n")
        for div in params_heading.find_all_next("div", class_="V8SH_rubric"):
            if div.find_previous("p", class_="V8SH_chapter") != params_heading:
                break
            p_tag = div.find("p")
            a_tag = div.find("a")
            name = p_tag.get_text(strip=True) if p_tag else "—"
            typ = a_tag.get_text(strip=True) if a_tag else "—"
            lines.append(f"- **{name}** ({typ})\n")
        lines.append("\n")

    # Return value
    ret_heading = soup.find("p", class_="V8SH_chapter", string=lambda t: t and "Возвращаемое значение:" in (t if isinstance(t, str) else t))
    if not ret_heading:
        for p in soup.find_all("p", class_="V8SH_chapter"):
            if p.get_text(strip=True) == "Возвращаемое значение:":
                ret_heading = p
                break
    if ret_heading:
        next_p = ret_heading.find_next_sibling("p")
        if next_p:
            ret_text = next_p.get_text(separator=" ", strip=True)
            if ret_text:
                lines.append("## Возвращаемое значение\n\n")
                lines.append(ret_text + "\n\n")
        else:
            next_ = ret_heading.find_next(string=True)
            if next_:
                ret_text = str(next_).strip()
                if ret_text and "Возвращаемое значение" not in ret_text:
                    lines.append("## Возвращаемое значение\n\n")
                    lines.append(ret_text + "\n\n")

    # Examples
    ex_heading = soup.find("p", class_="V8SH_chapter", string=lambda t: t and "Пример:" in (t if isinstance(t, str) else t))
    if not ex_heading:
        for p in soup.find_all("p", class_="V8SH_chapter"):
            if p.get_text(strip=True) == "Пример:":
                ex_heading = p
                break
    if ex_heading:
        code_block = ex_heading.find_next("pre") or ex_heading.find_next("table")
        if code_block:
            lines.append("## Пример\n\n```\n")
            lines.append(code_block.get_text(separator="\n", strip=True) + "\n")
            lines.append("```\n\n")

    # See also
    see_heading = soup.find("p", class_="V8SH_chapter", string=lambda t: t and "См. также:" in (t if isinstance(t, str) else t))
    if not see_heading:
        for p in soup.find_all("p", class_="V8SH_chapter"):
            if p.get_text(strip=True) == "См. также:":
                see_heading = p
                break
    if see_heading:
        links = see_heading.find_all_next("a", limit=20)
        if links:
            lines.append("## См. также\n\n")
            for a in links:
                lines.append(f"- {a.get_text(strip=True)}\n")
            lines.append("\n")

    out = "".join(lines).strip()
    if not out or out == f"# {title}\n":
        # Fallback: title + body text
        body = soup.find("body")
        if body:
            out = f"# {title}\n\n" + body.get_text(separator="\n", strip=True)[:8000]
    return out


def _looks_like_html(path: Path) -> bool:
    """True if file has no extension and content starts like HTML (e.g. unpacked .hbk)."""
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:1024].lower()
        return "<html" in head or "<!doctype" in head
    except Exception:
        return False


def build_docs(project_dir, output_dir):
    """
    Walk project_dir for .html files (and extension-less HTML, e.g. from unpacked .hbk),
    convert each to .md in output_dir preserving structure.
    Returns list of created .md paths.
    """
    project_dir = Path(project_dir).resolve()
    output_dir = Path(output_dir).resolve()
    created: list[Path] = []
    for root, _, files in os.walk(project_dir):
        for name in files:
            if name.startswith(".") or name.endswith(".hbk"):
                continue
            html_path = Path(root) / name
            is_html = name.endswith(".html") or (
                "." not in name and _looks_like_html(html_path)
            )
            if not is_html:
                continue
            try:
                rel = html_path.relative_to(project_dir)
            except ValueError:
                rel = html_path.name
            out_sub = output_dir / rel.parent
            out_sub.mkdir(parents=True, exist_ok=True)
            stem = rel.stem if rel.suffix else rel.name
            md_path = out_sub / (stem + ".md")
            content = html_to_md_content(html_path)
            if content:
                md_path.write_text(content, encoding="utf-8")
                created.append(md_path)
    return created
