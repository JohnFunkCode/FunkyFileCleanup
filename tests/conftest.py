"""
Shared pytest fixtures for FunkyFileCleanup tests.

Fixture tree (sample_tree) has deterministic file sizes to enable exact assertions:

    sample_tree/
    ├── photos/
    │   ├── portrait.jpg    (100 bytes)
    │   ├── landscape.jpg   (150 bytes)
    │   └── raw_shot.cr3    (500 bytes)
    ├── docs/
    │   ├── notes.txt        (50 bytes)
    │   └── report.pdf      (300 bytes)
    ├── video/
    │   └── clip.mp4       (1000 bytes)
    └── noext                (25 bytes)

    7 files · 2125 bytes total
    Extension totals (desc): .mp4=1000, .cr3=500, .pdf=300, .jpg=250, .txt=50, (none)=25
    Top 50% of 6 types = top 3: .mp4, .cr3, .pdf  →  3 file records stored
"""
from datetime import datetime
from pathlib import Path

import pytest

from funkyfilecleanup.domain.nodes import DirectoryNode, FileNode


FIXED_MTIME = datetime(2024, 1, 15, 12, 0, 0)


@pytest.fixture
def fixed_mtime() -> datetime:
    return FIXED_MTIME


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    root = tmp_path / "sample_tree"
    (root / "photos").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "video").mkdir(parents=True)

    (root / "photos" / "portrait.jpg").write_bytes(b"J" * 100)
    (root / "photos" / "landscape.jpg").write_bytes(b"J" * 150)
    (root / "photos" / "raw_shot.cr3").write_bytes(b"C" * 500)
    (root / "docs" / "notes.txt").write_bytes(b"T" * 50)
    (root / "docs" / "report.pdf").write_bytes(b"P" * 300)
    (root / "video" / "clip.mp4").write_bytes(b"M" * 1000)
    (root / "noext").write_bytes(b"N" * 25)

    return root


@pytest.fixture
def single_file_node(fixed_mtime: datetime) -> FileNode:
    path = Path("/photos/portrait.jpg")
    return FileNode(
        path=path,
        name="portrait.jpg",
        extension=".jpg",
        size_bytes=1024,
        mtime=fixed_mtime,
        directory=path.parent,
    )


@pytest.fixture
def flat_directory(fixed_mtime: datetime) -> DirectoryNode:
    """A directory containing three files directly, no subdirectories."""
    def _file(name: str, ext: str, size: int) -> FileNode:
        path = Path(f"/root/{name}")
        return FileNode(
            path=path,
            name=name,
            extension=ext,
            size_bytes=size,
            mtime=fixed_mtime,
            directory=path.parent,
        )

    return DirectoryNode(
        path=Path("/root"),
        children=[
            _file("a.jpg", ".jpg", 100),
            _file("b.jpg", ".jpg", 200),
            _file("c.txt", ".txt", 50),
        ],
    )


@pytest.fixture
def nested_directory(fixed_mtime: datetime) -> DirectoryNode:
    """
    A two-level directory tree:

        /root/
        ├── top.txt        (10 bytes)
        └── sub/
            ├── mid.jpg    (200 bytes)
            └── deep/
                └── bottom.cr3  (500 bytes)
    """
    def _file(parent: str, name: str, ext: str, size: int) -> FileNode:
        path = Path(f"{parent}/{name}")
        return FileNode(
            path=path,
            name=name,
            extension=ext,
            size_bytes=size,
            mtime=fixed_mtime,
            directory=path.parent,
        )

    deep = DirectoryNode(
        path=Path("/root/sub/deep"),
        children=[_file("/root/sub/deep", "bottom.cr3", ".cr3", 500)],
    )
    sub = DirectoryNode(
        path=Path("/root/sub"),
        children=[
            _file("/root/sub", "mid.jpg", ".jpg", 200),
            deep,
        ],
    )
    return DirectoryNode(
        path=Path("/root"),
        children=[
            _file("/root", "top.txt", ".txt", 10),
            sub,
        ],
    )
