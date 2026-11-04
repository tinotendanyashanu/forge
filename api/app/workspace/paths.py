"""Workspace path rules. Every path a learner sends goes through ``normalise``.

Paths are POSIX, relative, at most 6 segments deep, made of safe characters,
with no empty, ``.`` or ``..`` segments and no hidden (dot) files. Workspace
files live in the database, never on disk; they are only written to disk when
the worker stages a job, and ``stage_tree`` creates regular files with
O_NOFOLLOW | O_EXCL under a fresh directory, so traversal and symlink escapes
are impossible by construction.
"""

import os
import re

from app.services.errors import Unprocessable

SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,63}$")
ALLOWED_EXTENSIONS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".txt", ".sql", ".toml",
    ".cfg", ".ini", ".css", ".html", ".yml", ".yaml",
})
MAX_DEPTH = 6
MAX_PATH = 200


def normalise(path: str) -> str:
    """Returns the canonical path or raises Unprocessable."""
    if not isinstance(path, str) or not path or len(path) > MAX_PATH:
        raise Unprocessable("Invalid file path")
    if "\\" in path or "\x00" in path or path.startswith("/"):
        raise Unprocessable("File paths must be relative and use '/'")
    parts = path.split("/")
    if len(parts) > MAX_DEPTH:
        raise Unprocessable(f"File paths can be at most {MAX_DEPTH} levels deep")
    for part in parts:
        if part in ("", ".", "..") or not SEGMENT.match(part) or part.endswith("."):
            raise Unprocessable(f"Invalid path segment '{part[:40]}'")
    if os.path.splitext(parts[-1])[1].lower() not in ALLOWED_EXTENSIONS:
        raise Unprocessable("This file type is not allowed in a workspace")
    return "/".join(parts)


def is_valid(path: str) -> bool:
    try:
        normalise(path)
        return True
    except Unprocessable:
        return False


def stage_tree(root: str, files: dict[str, str]) -> None:
    """Writes ``files`` under ``root`` (an empty directory the caller created).

    Each path is re-validated; directories are created one level at a time and
    files are opened with O_NOFOLLOW | O_EXCL, so nothing can land outside root.
    """
    real_root = os.path.realpath(root)
    for path, content in files.items():
        norm = normalise(path)
        parent = real_root
        for segment in norm.split("/")[:-1]:
            parent = os.path.join(parent, segment)
            if not os.path.isdir(parent):
                os.mkdir(parent, 0o755)
            if os.path.islink(parent) or os.path.realpath(parent) != parent:
                raise ValueError("Unsafe directory while staging")
        target = os.path.join(parent, norm.split("/")[-1])
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(target, 0o644)
