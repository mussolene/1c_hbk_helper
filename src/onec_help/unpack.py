"""Unpack .hbk (or archive) with 7z, then fallback: Python zipfile, unzip. No hardcoded paths."""

import os
import subprocess
import zipfile
from pathlib import Path


def ensure_dir(path) -> None:
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def _try_zipfile(archive_path: Path, output_dir: Path) -> bool:
    """Try unpacking as ZIP (Python stdlib). Returns True if successful."""
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(output_dir)
        return True
    except (zipfile.BadZipFile, OSError, ValueError):
        return False


def _try_unzip(archive_path: Path, output_dir: Path) -> bool:
    """Try unpacking with unzip command. Returns True if successful."""
    result = subprocess.run(
        ["unzip", "-o", "-q", str(archive_path), "-d", str(output_dir)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def unpack_hbk(path_to_hbk, output_dir) -> None:
    """
    Unpack .hbk (or archive): try 7z, then Python zipfile, then unzip.
    Preserves full paths where the format allows.
    """
    path_to_hbk = Path(path_to_hbk).resolve()
    output_dir = Path(output_dir).resolve()
    if not path_to_hbk.is_file():
        raise FileNotFoundError(f"Archive not found: {path_to_hbk}")
    ensure_dir(output_dir)

    def _7z_extracted() -> bool:
        """True if output_dir has at least one file (7z may return 2 but still extract)."""
        try:
            return any(output_dir.iterdir())
        except OSError:
            return False

    # 1) 7z
    cmd = ["7z", "x", str(path_to_hbk), f"-o{output_dir}", "-y"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 or _7z_extracted():
        return
    cmd_alt = ["7z", "x", "-t*", str(path_to_hbk), f"-o{output_dir}", "-y"]
    result = subprocess.run(cmd_alt, capture_output=True, text=True)
    if result.returncode == 0 or _7z_extracted():
        return

    # 2) Python zipfile (ZIP/deflate)
    if _try_zipfile(path_to_hbk, output_dir):
        return

    # 3) unzip command
    if _try_unzip(path_to_hbk, output_dir):
        return

    err = (result.stderr or result.stdout or "").strip()
    tried = "Tried: 7z, Python zipfile, unzip."
    if path_to_hbk.suffix.lower() == ".hbk":
        raise RuntimeError(
            f"All unpack methods failed. {tried} "
            "Try unpacking the .hbk manually (e.g. 7z x file.hbk -o./out), then use the unpacked folder. "
            f"Last 7z output: {err}"
        )
    raise RuntimeError(f"All unpack methods failed. {tried} Last 7z output: {err}")
