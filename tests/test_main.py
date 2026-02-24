"""Test __main__ entry point."""
from unittest.mock import patch
import pytest


def test_main_entry() -> None:
    with patch("sys.argv", ["onec_help", "build-docs", "--help"]):
        from onec_help.__main__ import main
        with pytest.raises(SystemExit):
            main()
