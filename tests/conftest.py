"""Pytest fixtures."""

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def help_sample_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "help_sample"


@pytest.fixture
def sample_html(help_sample_dir: Path) -> Path:
    return help_sample_dir / "field626.html"


@pytest.fixture
def categories_file(help_sample_dir: Path) -> Path:
    return help_sample_dir / "__categories__"


@pytest.fixture(autouse=True)
def embedding_backend_none_for_network_tests(request):
    """Use EMBEDDING_BACKEND=none in indexer/embedding tests to avoid HuggingFace download."""
    path = str(getattr(request, "fspath", None) or "")
    if "test_indexer" in path or "test_embedding" in path:
        with patch.dict("os.environ", {"EMBEDDING_BACKEND": "none"}, clear=False):
            import onec_help.embedding as emb

            importlib.reload(emb)
            yield
    else:
        yield
