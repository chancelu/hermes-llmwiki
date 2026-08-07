"""Atomic file writes and path utilities."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write *content* to *path* atomically via a temp file + rename.

    On Windows we use os.replace(); on Unix we can use rename(2) directly.
    This avoids half-written files if the process crashes mid-write.
    """
    path = Path(path)
    ensure_dir(path.parent)

    # Write to a temp file in the same directory so rename is atomic
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(fd)
    except Exception:
        # Clean up temp file on failure
        try:
            os.close(fd)
        except OSError:
            pass
        Path(tmp_path).unlink(missing_ok=True)
        raise

    # Atomic replace
    os.replace(tmp_path, path)


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, creating parents if needed."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def expand_path(path_str: str) -> Path:
    """Expand ~ and env vars in a path string."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "_")
    name = name.strip(". ")
    return name or "untitled"
