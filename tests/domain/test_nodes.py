"""Tests for FileNode and DirectoryNode domain models."""
from datetime import datetime
from pathlib import Path

import pytest

from funkyfilecleanup.domain.nodes import DirectoryNode, FileNode, FileSystemNode


class TestFileNode:
    def test_construction_stores_all_fields(self, fixed_mtime: datetime) -> None:
        path = Path("/photos/shot.jpg")
        node = FileNode(
            path=path,
            name="shot.jpg",
            extension=".jpg",
            size_bytes=2048,
            mtime=fixed_mtime,
            directory=Path("/photos"),
        )
        assert node.path == path
        assert node.name == "shot.jpg"
        assert node.extension == ".jpg"
        assert node.size_bytes == 2048
        assert node.mtime == fixed_mtime
        assert node.directory == Path("/photos")

    def test_is_immutable(self, single_file_node: FileNode) -> None:
        with pytest.raises(Exception):
            single_file_node.size_bytes = 9999  # type: ignore[misc]

    def test_no_extension_stored_as_empty_string(self, fixed_mtime: datetime) -> None:
        path = Path("/data/noext")
        node = FileNode(
            path=path,
            name="noext",
            extension="",
            size_bytes=100,
            mtime=fixed_mtime,
            directory=path.parent,
        )
        assert node.extension == ""

    def test_extension_is_lowercase(self, fixed_mtime: datetime) -> None:
        path = Path("/data/IMAGE.JPG")
        node = FileNode(
            path=path,
            name="IMAGE.JPG",
            extension=".jpg",
            size_bytes=100,
            mtime=fixed_mtime,
            directory=path.parent,
        )
        assert node.extension == ".jpg"

    def test_is_instance_of_filesystemnode(self, single_file_node: FileNode) -> None:
        assert isinstance(single_file_node, FileSystemNode)

    def test_equality_by_value(self, fixed_mtime: datetime) -> None:
        path = Path("/photos/shot.jpg")
        kwargs = dict(
            path=path,
            name="shot.jpg",
            extension=".jpg",
            size_bytes=512,
            mtime=fixed_mtime,
            directory=path.parent,
        )
        assert FileNode(**kwargs) == FileNode(**kwargs)

    def test_zero_byte_file(self, fixed_mtime: datetime) -> None:
        path = Path("/empty/file.txt")
        node = FileNode(
            path=path,
            name="file.txt",
            extension=".txt",
            size_bytes=0,
            mtime=fixed_mtime,
            directory=path.parent,
        )
        assert node.size_bytes == 0


class TestDirectoryNode:
    def test_construction_stores_path_and_children(
        self, flat_directory: DirectoryNode
    ) -> None:
        assert flat_directory.path == Path("/root")
        assert len(flat_directory.children) == 3

    def test_is_instance_of_filesystemnode(
        self, flat_directory: DirectoryNode
    ) -> None:
        assert isinstance(flat_directory, FileSystemNode)

    def test_file_count_flat(self, flat_directory: DirectoryNode) -> None:
        assert flat_directory.file_count == 3

    def test_file_count_nested(self, nested_directory: DirectoryNode) -> None:
        # /root has 1 file + /root/sub has 1 file + /root/sub/deep has 1 file = 3
        assert nested_directory.file_count == 3

    def test_file_count_empty_directory(self) -> None:
        empty = DirectoryNode(path=Path("/empty"), children=[])
        assert empty.file_count == 0

    def test_total_size_flat(self, flat_directory: DirectoryNode) -> None:
        # 100 + 200 + 50 = 350
        assert flat_directory.total_size == 350

    def test_total_size_nested(self, nested_directory: DirectoryNode) -> None:
        # 10 + 200 + 500 = 710
        assert nested_directory.total_size == 710

    def test_total_size_empty_directory(self) -> None:
        empty = DirectoryNode(path=Path("/empty"), children=[])
        assert empty.total_size == 0

    def test_depth_flat(self, flat_directory: DirectoryNode) -> None:
        # root contains only files → depth 1
        assert flat_directory.depth == 1

    def test_depth_nested(self, nested_directory: DirectoryNode) -> None:
        # root → sub → deep → files: depth 3
        assert nested_directory.depth == 3

    def test_depth_empty_directory(self) -> None:
        empty = DirectoryNode(path=Path("/empty"), children=[])
        assert empty.depth == 0

    def test_children_can_be_mixed_files_and_directories(
        self, nested_directory: DirectoryNode
    ) -> None:
        child_types = {type(c) for c in nested_directory.children}
        assert FileNode in child_types
        assert DirectoryNode in child_types
