"""Tests for ScanService — grouping, ranking, threshold, and orchestration."""
import math
from datetime import datetime
from pathlib import Path

import pytest

from funkyfilecleanup.domain.nodes import DirectoryNode, FileNode
from funkyfilecleanup.domain.reports import ScanReport
from funkyfilecleanup.infrastructure.repository import ScanRepository
from funkyfilecleanup.services.scan_service import ScanService


class FakeScanRepository:
    """In-memory stand-in for ScanRepository. Records calls for assertion."""

    def __init__(self) -> None:
        self.initialized = False
        self.saved: list[tuple[ScanReport, dict]] = []
        self._next_id = 1

    def initialize(self) -> None:
        self.initialized = True

    def save_scan(
        self, report: ScanReport, files_by_extension: dict
    ) -> int:
        self.saved.append((report, files_by_extension))
        run_id = self._next_id
        self._next_id += 1
        return run_id

    def close(self) -> None:
        pass


def _file(parent: str, name: str, size: int, mtime: datetime) -> FileNode:
    path = Path(f"{parent}/{name}")
    return FileNode(
        path=path,
        name=name,
        extension=Path(name).suffix.lower(),
        size_bytes=size,
        mtime=mtime,
        directory=path.parent,
    )


def _build_tree(files: list[FileNode]) -> DirectoryNode:
    return DirectoryNode(path=Path("/root"), children=files)


class TestScanServiceGroupingAndRanking:
    def test_returns_scan_report(self, fixed_mtime: datetime) -> None:
        tree = _build_tree([
            _file("/root", "a.jpg", 100, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)
        assert isinstance(report, ScanReport)

    def test_groups_files_by_extension(self, fixed_mtime: datetime) -> None:
        tree = _build_tree([
            _file("/root", "a.jpg", 100, fixed_mtime),
            _file("/root", "b.jpg", 200, fixed_mtime),
            _file("/root", "c.mp4", 500, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        extensions = {s.extension for s in report.type_stats}
        assert extensions == {".jpg", ".mp4"}

    def test_ranks_by_total_size_descending(self, fixed_mtime: datetime) -> None:
        tree = _build_tree([
            _file("/root", "a.jpg", 100, fixed_mtime),
            _file("/root", "b.jpg", 150, fixed_mtime),  # .jpg total = 250
            _file("/root", "c.mp4", 1000, fixed_mtime),  # .mp4 total = 1000
            _file("/root", "d.txt", 50, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        assert report.type_stats[0].extension == ".mp4"
        assert report.type_stats[1].extension == ".jpg"
        assert report.type_stats[2].extension == ".txt"

    def test_rank_one_pct_of_total_is_share_of_grand_total(
        self, fixed_mtime: datetime
    ) -> None:
        # .mp4=1000, .jpg=400 → grand total=1400; .mp4 = 1000/1400 ≈ 71.4%
        tree = _build_tree([
            _file("/root", "a.mp4", 1000, fixed_mtime),
            _file("/root", "b.jpg", 400, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        assert report.type_stats[0].pct_of_total == pytest.approx(1000 / 1400)

    def test_rank_two_pct_of_total_is_correct_ratio(
        self, fixed_mtime: datetime
    ) -> None:
        # .mp4=1000, .jpg=400 → grand total=1400; .jpg = 400/1400 ≈ 28.6%
        tree = _build_tree([
            _file("/root", "a.mp4", 1000, fixed_mtime),
            _file("/root", "b.jpg", 400, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        assert report.type_stats[1].pct_of_total == pytest.approx(400 / 1400)

    def test_file_count_per_type_is_correct(self, fixed_mtime: datetime) -> None:
        tree = _build_tree([
            _file("/root", "a.jpg", 100, fixed_mtime),
            _file("/root", "b.jpg", 200, fixed_mtime),
            _file("/root", "c.jpg", 300, fixed_mtime),
            _file("/root", "d.mp4", 1000, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        jpg_stats = next(s for s in report.type_stats if s.extension == ".jpg")
        assert jpg_stats.file_count == 3

    def test_total_size_per_type_is_summed(self, fixed_mtime: datetime) -> None:
        tree = _build_tree([
            _file("/root", "a.jpg", 100, fixed_mtime),
            _file("/root", "b.jpg", 200, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        jpg_stats = next(s for s in report.type_stats if s.extension == ".jpg")
        assert jpg_stats.total_size_bytes == 300

    def test_largest_file_within_type_is_tracked(
        self, fixed_mtime: datetime
    ) -> None:
        tree = _build_tree([
            _file("/root", "small.jpg", 100, fixed_mtime),
            _file("/root", "large.jpg", 800, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        jpg_stats = next(s for s in report.type_stats if s.extension == ".jpg")
        assert jpg_stats.largest_file_size_bytes == 800
        assert jpg_stats.largest_file_path.name == "large.jpg"


class TestScanServiceThreshold:
    def test_threshold_rank_is_ceil_of_half(self, fixed_mtime: datetime) -> None:
        # 6 types → ceil(6/2) = 3
        tree = _build_tree([
            _file("/root", "a.mp4", 1000, fixed_mtime),
            _file("/root", "b.cr3", 500, fixed_mtime),
            _file("/root", "c.pdf", 300, fixed_mtime),
            _file("/root", "d.jpg", 200, fixed_mtime),
            _file("/root", "e.txt", 50, fixed_mtime),
            _file("/root", "noext", 25, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        assert report.threshold_rank == math.ceil(6 / 2)

    def test_threshold_rank_with_odd_type_count(
        self, fixed_mtime: datetime
    ) -> None:
        # 5 types → ceil(5/2) = 3
        tree = _build_tree([
            _file("/root", "a.mp4", 1000, fixed_mtime),
            _file("/root", "b.cr3", 500, fixed_mtime),
            _file("/root", "c.pdf", 300, fixed_mtime),
            _file("/root", "d.jpg", 200, fixed_mtime),
            _file("/root", "e.txt", 50, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        assert report.threshold_rank == math.ceil(5 / 2)

    def test_threshold_rank_with_single_type(self, fixed_mtime: datetime) -> None:
        tree = _build_tree([_file("/root", "a.jpg", 100, fixed_mtime)])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        assert report.threshold_rank == 1


class TestScanServiceLargestFile:
    def test_largest_file_is_the_single_biggest_file(
        self, fixed_mtime: datetime
    ) -> None:
        tree = _build_tree([
            _file("/root", "small.jpg", 100, fixed_mtime),
            _file("/root", "big.cr3", 5000, fixed_mtime),
            _file("/root", "medium.mp4", 1000, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        assert report.largest_file.name == "big.cr3"
        assert report.largest_file.size_bytes == 5000

    def test_report_total_files_is_correct(self, fixed_mtime: datetime) -> None:
        tree = _build_tree([
            _file("/root", "a.jpg", 100, fixed_mtime),
            _file("/root", "b.jpg", 200, fixed_mtime),
            _file("/root", "c.mp4", 500, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        assert report.total_files == 3

    def test_report_total_size_is_correct(self, fixed_mtime: datetime) -> None:
        tree = _build_tree([
            _file("/root", "a.jpg", 100, fixed_mtime),
            _file("/root", "b.mp4", 500, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        assert report.total_size_bytes == 600


class TestScanServiceRepositoryInteraction:
    def test_repository_save_scan_called_once(
        self, fixed_mtime: datetime
    ) -> None:
        tree = _build_tree([_file("/root", "a.jpg", 100, fixed_mtime)])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        service.run(Path("/root"), tree=tree)

        assert len(repo.saved) == 1

    def test_repository_receives_correct_report(
        self, fixed_mtime: datetime
    ) -> None:
        tree = _build_tree([_file("/root", "a.jpg", 100, fixed_mtime)])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        report = service.run(Path("/root"), tree=tree)

        saved_report, _ = repo.saved[0]
        assert saved_report is report

    def test_repository_receives_files_by_extension_dict(
        self, fixed_mtime: datetime
    ) -> None:
        tree = _build_tree([
            _file("/root", "a.jpg", 100, fixed_mtime),
            _file("/root", "b.mp4", 500, fixed_mtime),
        ])
        repo = FakeScanRepository()
        service = ScanService(repository=repo)
        service.run(Path("/root"), tree=tree)

        _, files_by_ext = repo.saved[0]
        assert ".jpg" in files_by_ext
        assert ".mp4" in files_by_ext
