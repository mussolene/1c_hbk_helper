"""Tests for parse_helpf."""

from onec_help.parse_helpf import _extract_faq_links, _extract_file_links


def test_extract_faq_links_absolute_path() -> None:
    """Extract FAQ links with absolute href /faq/view/ID.html (page 1)."""
    html = '<a href="/faq/view/1922.html">Программная проверка счета</a>'
    items = _extract_faq_links(html)
    assert len(items) == 1
    assert items[0][0] == "Программная проверка счета"
    assert items[0][1] == "https://helpf.pro/faq/view/1922.html"


def test_extract_faq_links_relative_path() -> None:
    """Extract FAQ links with relative href faq/view/ID.html (page 2+)."""
    html = '<a href="faq/view/1912.html">Другой FAQ</a>'
    items = _extract_faq_links(html)
    assert len(items) == 1
    assert items[0][1] == "https://helpf.pro/faq/view/1912.html"


def test_extract_file_links() -> None:
    """Extract file links with /file/view/ or file/view/."""
    html = '<a href="file/view/some-file.html">Полезный файл</a>'
    items = _extract_file_links(html)
    assert len(items) == 1
    assert items[0][1] == "https://helpf.pro/file/view/some-file.html"


def test_extract_faq_links_regex_fallback() -> None:
    """When BeautifulSoup finds no <a> with matching href, regex fallback extracts URLs."""
    # HTML without proper <a> structure (e.g. JS-rendered or bot-blocked)
    html = """<div>Some text and hidden link: "/faq/view/9999.html"</div>"""
    items = _extract_faq_links(html)
    assert len(items) == 1
    assert items[0][1] == "https://helpf.pro/faq/view/9999.html"
    assert "9999" in items[0][0]
