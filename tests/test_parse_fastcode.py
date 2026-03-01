"""Tests for parse_fastcode."""

from unittest.mock import MagicMock, patch

from onec_help.parse_fastcode import _detect_total_pages, _is_safe_fastcode_detail_url


def test_detect_total_pages_sliding_window() -> None:
    """_detect_total_pages follows pagination when FastCode shows ~6 links per page (51 total)."""
    TOTAL = 51

    def fake_html(page: int) -> str:
        # Sliding window: on page p show links to p-2..p+3 (excluding p), capped to 1..TOTAL
        links = []
        for delta in range(-2, 4):
            if delta == 0:
                continue
            q = page + delta
            if 1 <= q <= TOTAL:
                links.append(q)
        return " ".join(f"?Page={p}" for p in links)

    fetch_calls: list[int] = []

    def mock_fetch(p: int, _opener) -> str:
        fetch_calls.append(p)
        return fake_html(p)

    with (
        patch("onec_help.parse_fastcode._fetch_page", side_effect=mock_fetch),
        patch("onec_help.parse_fastcode.time.sleep"),
    ):
        opener = MagicMock()
        pages = _detect_total_pages(opener)

    assert len(pages) == TOTAL, f"Expected {TOTAL} pages, got {len(pages)}"
    assert pages[0] == 1 and pages[-1] == TOTAL
    # Sliding window (~5 links/page): ~18 probes for 51 pages is expected
    assert len(fetch_calls) <= 25, f"Too many probes: {fetch_calls}"


def test_is_safe_fastcode_detail_url_relative() -> None:
    """Relative /Templates/123/slug is allowed."""
    assert (
        _is_safe_fastcode_detail_url("/Templates/123/slug")
        == "https://fastcode.im/Templates/123/slug"
    )


def test_is_safe_fastcode_detail_url_absolute() -> None:
    """Absolute https://fastcode.im/... is allowed."""
    assert (
        _is_safe_fastcode_detail_url("https://fastcode.im/Templates/456/foo")
        == "https://fastcode.im/Templates/456/foo"
    )


def test_is_safe_fastcode_detail_url_rejects_protocol_relative() -> None:
    """Protocol-relative //evil.com/... is rejected."""
    assert _is_safe_fastcode_detail_url("//evil.com/Templates/1/x") is None


def test_is_safe_fastcode_detail_url_rejects_other_host() -> None:
    """Other hosts are rejected."""
    assert _is_safe_fastcode_detail_url("https://other.com/Templates/1/x") is None


def test_is_safe_fastcode_detail_url_rejects_javascript() -> None:
    """javascript: scheme is rejected."""
    assert _is_safe_fastcode_detail_url("javascript:alert(1)") is None


def test_is_safe_fastcode_detail_url_rejects_query() -> None:
    """URLs with query string are rejected (stricter)."""
    assert _is_safe_fastcode_detail_url("/Templates/1/x?foo=1") is None
