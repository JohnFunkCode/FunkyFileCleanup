"""Integration tests for FileSystemScanner against the fixture tree."""
import os
from pathlib import Path

import pytest

from funkyfilecleanup.domain.nodes import DirectoryNode, FileNode
from funkyfilecleanup.infrastructure.scanner import FileSystemScanner


class TestFileSystemScanner:
    def test_returns_directory_node(self, sample_tree: Path) -> None:
        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        assert isinstance(result, DirectoryNode)

    def test_root_path_is_set_correctly(self, sample_tree: Path) -> None:
        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        assert result.path == sample_tree

    def test_total_file_count(self, sample_tree: Path) -> None:
        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        assert result.file_count == 7

    def test_total_size_bytes(self, sample_tree: Path) -> None:
        # 100 + 150 + 500 + 50 + 300 + 1000 + 25 = 2125
        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        assert result.total_size == 2125

    def test_extensions_are_lowercase(self, sample_tree: Path) -> None:
        upper_file = sample_tree / "IMAGE.JPG"
        upper_file.write_bytes(b"x" * 10)

        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)

        all_nodes = _collect_files(result)
        extensions = {n.extension for n in all_nodes}
        assert ".jpg" in extensions
        assert ".JPG" not in extensions

    def test_file_without_extension_has_empty_string_extension(
        self, sample_tree: Path
    ) -> None:
        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        all_nodes = _collect_files(result)
        no_ext = [n for n in all_nodes if n.extension == ""]
        assert len(no_ext) == 1
        assert no_ext[0].name == "noext"

    def test_file_node_has_correct_size(self, sample_tree: Path) -> None:
        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        all_nodes = _collect_files(result)
        mp4_nodes = [n for n in all_nodes if n.name == "clip.mp4"]
        assert len(mp4_nodes) == 1
        assert mp4_nodes[0].size_bytes == 1000

    def test_file_node_directory_is_parent_path(self, sample_tree: Path) -> None:
        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        all_nodes = _collect_files(result)
        mp4 = next(n for n in all_nodes if n.name == "clip.mp4")
        assert mp4.directory == sample_tree / "video"

    def test_file_node_mtime_is_populated(self, sample_tree: Path) -> None:
        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        all_nodes = _collect_files(result)
        assert all(n.mtime is not None for n in all_nodes)

    def test_dot_git_excluded_by_default(self, sample_tree: Path) -> None:
        git_dir = sample_tree / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_bytes(b"x" * 100)

        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        all_nodes = _collect_files(result)
        names = {n.name for n in all_nodes}
        assert "config" not in names

    def test_pycache_excluded_by_default(self, sample_tree: Path) -> None:
        cache_dir = sample_tree / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "module.pyc").write_bytes(b"x" * 50)

        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        all_nodes = _collect_files(result)
        names = {n.name for n in all_nodes}
        assert "module.pyc" not in names

    def test_venv_excluded_by_default(self, sample_tree: Path) -> None:
        venv_dir = sample_tree / ".venv"
        venv_dir.mkdir()
        (venv_dir / "python").write_bytes(b"x" * 200)

        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        all_nodes = _collect_files(result)
        names = {n.name for n in all_nodes}
        assert "python" not in names

    def test_custom_ignore_pattern_excludes_directory(
        self, sample_tree: Path
    ) -> None:
        scanner = FileSystemScanner(ignore_patterns=["video"])
        result = scanner.scan(sample_tree)
        all_nodes = _collect_files(result)
        names = {n.name for n in all_nodes}
        assert "clip.mp4" not in names

    def test_empty_directory_returns_zero_files(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        scanner = FileSystemScanner()
        result = scanner.scan(empty)
        assert result.file_count == 0
        assert result.total_size == 0

    def test_symlinks_are_skipped(self, sample_tree: Path, tmp_path: Path) -> None:
        link_target = tmp_path / "real_file.jpg"
        link_target.write_bytes(b"x" * 500)
        symlink = sample_tree / "linked.jpg"
        symlink.symlink_to(link_target)

        scanner = FileSystemScanner()
        result = scanner.scan(sample_tree)
        all_nodes = _collect_files(result)
        names = {n.name for n in all_nodes}
        assert "linked.jpg" not in names

    def test_file_vanishing_mid_scan_does_not_crash(self, tmp_path: Path) -> None:
        # Simulates a file that exists during os.scandir listing but is gone by
        # the time stat() is called — e.g. a log file rotated out mid-scan.
        (tmp_path / "stable.txt").write_bytes(b"x" * 100)
        ghost = tmp_path / "ghost.log"
        ghost.write_bytes(b"x" * 50)

        import unittest.mock as mock
        from contextlib import contextmanager

        original_scandir = os.scandir

        @contextmanager
        def scandir_then_delete(path):
            entries = list(original_scandir(path))
            ghost.unlink(missing_ok=True)  # vanish the ghost after listing, before stat
            yield iter(entries)

        with mock.patch("funkyfilecleanup.infrastructure.scanner.os.scandir", scandir_then_delete):
            scanner = FileSystemScanner()
            result = scanner.scan(tmp_path)

        all_nodes = _collect_files(result)
        names = {n.name for n in all_nodes}
        assert "stable.txt" in names
        assert "ghost.log" not in names

    def test_deeply_nested_structure(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "file.txt").write_bytes(b"x" * 42)

        scanner = FileSystemScanner()
        result = scanner.scan(tmp_path)
        all_nodes = _collect_files(result)
        assert len(all_nodes) == 1
        assert all_nodes[0].size_bytes == 42


def _collect_files(node: DirectoryNode) -> list[FileNode]:
    """Recursively collect all FileNodes from a DirectoryNode tree."""
    files: list[FileNode] = []
    for child in node.children:
        if isinstance(child, FileNode):
            files.append(child)
        elif isinstance(child, DirectoryNode):
            files.extend(_collect_files(child))
    return files
