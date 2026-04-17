from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class FileNode:
    path: Path
    name: str
    extension: str  # lowercase, e.g. ".jpg"; "" if no extension
    size_bytes: int
    mtime: datetime
    directory: Path


@dataclass
class DirectoryNode:
    path: Path
    children: list[FileSystemNode]

    @property
    def file_count(self) -> int:
        count = 0
        for child in self.children:
            if isinstance(child, FileNode):
                count += 1
            else:
                count += child.file_count
        return count

    @property
    def total_size(self) -> int:
        total = 0
        for child in self.children:
            if isinstance(child, FileNode):
                total += child.size_bytes
            else:
                total += child.total_size
        return total

    @property
    def depth(self) -> int:
        if not self.children:
            return 0
        sub_depths = [
            child.depth
            for child in self.children
            if isinstance(child, DirectoryNode)
        ]
        if not sub_depths:
            return 1  # only files, no subdirectories
        return 1 + max(sub_depths)


# Type alias after both classes are defined so isinstance() works correctly.
FileSystemNode = FileNode | DirectoryNode
