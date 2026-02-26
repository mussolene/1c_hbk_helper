"""Tests for .nosync/bsl_processor — run when .nosync exists."""

import importlib.util
from pathlib import Path

import pytest

NOSYNC = Path(__file__).resolve().parent.parent / ".nosync"
BSL_PROCESSOR = NOSYNC / "bsl_processor.py"


@pytest.mark.skipif(not BSL_PROCESSOR.exists(), reason=".nosync/bsl_processor.py not present")
def test_bsl_processor_import_and_error() -> None:
    """BSLProcessor imports and BSLProcessorError is a proper Exception."""
    spec = importlib.util.spec_from_file_location("bsl_processor", BSL_PROCESSOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert issubclass(mod.BSLProcessorError, Exception)
    assert mod.BSLProcessorError is not Exception

    proc = mod.BSLProcessor(root_path=".", use_pool=False)
    assert proc.main_bsl_files
    assert "ObjectModule.bsl" in proc.main_bsl_files
