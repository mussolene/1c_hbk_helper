"""Tests for web module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from onec_help.web import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["BASE_DIR"] = None
    return app.test_client()


def test_ready(client) -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    assert b"ok" in r.data


def test_index_get(client) -> None:
    r = client.get("/")
    assert r.status_code == 200


def test_content_no_dir(client) -> None:
    r = client.get("/content/some.html")
    assert r.status_code == 400


def test_content_with_dir(client, help_sample_dir: Path) -> None:
    from onec_help.web import app

    app.config["BASE_DIR"] = str(help_sample_dir)
    r = client.get("/content/field626.html")
    assert r.status_code == 200
    data = r.get_json()
    assert "content" in data


def test_content_exception_returns_500(client, help_sample_dir: Path) -> None:
    from onec_help.web import app

    app.config["BASE_DIR"] = str(help_sample_dir)
    with patch("onec_help.web.get_html_content") as mock_get:
        mock_get.side_effect = OSError("file not found")
        r = client.get("/content/missing.html")
    assert r.status_code == 500
    data = r.get_json()
    assert "error" in data


def test_index_post_success(client, help_sample_dir: Path) -> None:
    r = client.post("/", data={"directory": str(help_sample_dir)})
    assert r.status_code == 200
    assert b"tree_elements" in r.data or b"tree" in r.data


def test_index_post_invalid_dir(client, tmp_path: Path) -> None:
    r = client.post("/", data={"directory": str(tmp_path / "nonexistent")})
    assert r.status_code == 200
    assert b"Invalid" in r.data or b"error" in r.data.lower()


def test_download_no_dir(client) -> None:
    r = client.get("/download/some.html")
    assert r.status_code == 400


def test_download_with_dir(client, help_sample_dir: Path) -> None:
    from onec_help.web import app

    app.config["BASE_DIR"] = str(help_sample_dir)
    r = client.get("/download/field626.html")
    assert r.status_code == 200
