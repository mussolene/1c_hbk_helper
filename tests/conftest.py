"""Pytest fixtures."""
from pathlib import Path

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
