from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from funkyfilecleanup.domain.nodes import DirectoryNode, FileNode

DEFAULT_IGNORE: frozenset[str] = frozenset({".git", ".venv", "__pycache__", "node_modules"})


class FileSystemScanner:
    def __init__(self, ignore_patterns: list[str] | None = None) -> None:
        self._ignore = (
            frozenset(ignore_patterns) if ignore_patterns is not None else DEFAULT_IGNORE
        )
        self._dir_count = 0

    def scan(self, root: Path) -> DirectoryNode:
        self._dir_count = 0
        result = self._scan_dir(root)
        # Clear the progress line when done
        print(f"\rScanning... {self._dir_count:,} dirs — done.          ", file=sys.stderr)
        return result

    def _scan_dir(self, path: Path) -> DirectoryNode:
        self._dir_count += 1
        print(f"\rScanning... {self._dir_count:,} dirs", end="", flush=True, file=sys.stderr)
        children: list = []
        try:
            with os.scandir(path) as entries:
                for entry in sorted(entries, key=lambda e: e.name):
                    if entry.name in self._ignore:
                        continue
                    if entry.is_symlink():
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            children.append(self._scan_dir(Path(entry.path)))
                        elif entry.is_file(follow_symlinks=False):
                            children.append(self._make_file_node(entry))
                    except OSError:
                        pass  # file vanished or became unreadable mid-scan
        except OSError:
            pass  # directory unreadable or vanished
        return DirectoryNode(path=path, children=children)

    def _make_file_node(self, entry: os.DirEntry) -> FileNode:
        path = Path(entry.path)
        stat = entry.stat(follow_symlinks=False)
        return FileNode(
            path=path,
            name=entry.name,
            extension=path.suffix.lower(),
            size_bytes=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime),
            directory=path.parent,
        )
