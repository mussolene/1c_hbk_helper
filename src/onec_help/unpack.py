"""Unpack .hbk (or archive) with 7z, then fallback: Python zipfile, zip from offset, unzip. No hardcoded paths."""

import os
import subprocess
import zipfile
from io import BytesIO
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


def _try_zipfile_from_offset(
    archive_path: Path, output_dir: Path, offset: int = 0, truncate_tail: int = 0
) -> bool:
    """Try unpacking as ZIP from byte offset (e.g. .hbk with header). truncate_tail = bytes to ignore at end."""
    try:
        with open(archive_path, "rb") as f:
            f.seek(offset)
            data = f.read()
        if truncate_tail and len(data) > truncate_tail:
            data = data[:-truncate_tail]
        if not data:
            return False
        with zipfile.ZipFile(BytesIO(data), "r") as zf:
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

    # 1) 7z (may be missing; then fall through to zipfile)
    result = None
    try:
        cmd = ["7z", "x", str(path_to_hbk), f"-o{output_dir}", "-y"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 or _7z_extracted():
            return
        cmd_alt = ["7z", "x", "-t*", str(path_to_hbk), f"-o{output_dir}", "-y"]
        result = subprocess.run(cmd_alt, capture_output=True, text=True)
        if result.returncode == 0 or _7z_extracted():
            return
    except FileNotFoundError:
        result = None

    # 2) Python zipfile (ZIP/deflate)
    if _try_zipfile(path_to_hbk, output_dir):
        return

    # 3) ZIP with header offset (some .hbk: "Headers Error", "data after end" — ZIP may start at offset)
    file_size = path_to_hbk.stat().st_size
    for skip, tail in [(1656, 39274), (1656, 0), (2048, 0), (1024, 0), (512, 0)]:
        if skip < file_size and file_size - skip > tail:
            if _try_zipfile_from_offset(path_to_hbk, output_dir, offset=skip, truncate_tail=tail):
                return

    # 4) unzip command
    if _try_unzip(path_to_hbk, output_dir):
        return

    err = (result.stderr or result.stdout or "").strip() if result else ""
    tried = "Tried: 7z, Python zipfile, zip from offset, unzip."
    if path_to_hbk.suffix.lower() == ".hbk":
        raise RuntimeError(
            f"All unpack methods failed. {tried} "
            "Try unpacking the .hbk manually (e.g. 7z x file.hbk -o./out), then use the unpacked folder. "
            f"Last 7z output: {err}"
        )
    raise RuntimeError(f"All unpack methods failed. {tried} Last 7z output: {err}")
