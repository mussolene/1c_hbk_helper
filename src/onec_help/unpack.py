"""Unpack .hbk using 7z (p7zip-full). No hardcoded paths."""

import os
import subprocess
from pathlib import Path


def ensure_dir(path) -> None:
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def unpack_hbk(path_to_hbk, output_dir) -> None:
    """
    Unpack .hbk (or archive) with 7z, preserving full paths.
    Uses: 7z x <archive> -o<output_dir> -y
    """
    path_to_hbk = Path(path_to_hbk).resolve()
    output_dir = Path(output_dir).resolve()
    if not path_to_hbk.is_file():
        raise FileNotFoundError(f"Archive not found: {path_to_hbk}")
    ensure_dir(output_dir)
    # -o with no space: -o/path or -oC:\path
    cmd = ["7z", "x", str(path_to_hbk), f"-o{output_dir}", "-y"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Try with -t* if format not recognized
        cmd_alt = ["7z", "x", "-t*", str(path_to_hbk), f"-o{output_dir}", "-y"]
        result = subprocess.run(cmd_alt, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"7z failed (exit {result.returncode}): {result.stderr or result.stdout}"
        )
