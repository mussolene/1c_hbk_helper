"""Tests for onec_help package __init__."""

import sys
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch


def test_version_when_package_installed() -> None:
    """__version__ is set when package is installed."""
    import onec_help

    assert hasattr(onec_help, "__version__")
    assert onec_help.__version__ != ""


def test_version_package_not_found() -> None:
    """__version__ uses fallback when version() raises PackageNotFoundError."""
    if "onec_help" in sys.modules:
        del sys.modules["onec_help"]
    with patch("importlib.metadata.version", side_effect=PackageNotFoundError("nce-help")):
        import onec_help

        assert onec_help.__version__ == "0.0.0.dev0"
