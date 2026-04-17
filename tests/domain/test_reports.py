"""Tests for FileTypeStats and ScanReport domain models."""
from datetime import datetime
from pathlib import Path

import pytest

from funkyfilecleanup.domain.nodes import FileNode
from funkyfilecleanup.domain.reports import FileTypeStats, ScanReport


def _make_stats(
    extension: str,
    total_size: int,
    rank: int,
    grand_total: int,
    file_count: int = 1,
) -> FileTypeStats:
    return FileTypeStats(
        extension=extension,
        file_count=file_count,
        total_size_bytes=total_size,
        largest_file_size_bytes=total_size,
        largest_file_path=Path(f"/fake/{extension.lstrip('.')}_file{extension}"),
        rank=rank,
        pct_of_total=total_size / grand_total,
    )


def _make_file_node(name: str, size: int, mtime: datetime) -> FileNode:
    path = Path(f"/fake/{name}")
    return FileNode(
        path=path,
        name=name,
        extension=Path(name).suffix.lower(),
        size_bytes=size,
        mtime=mtime,
        directory=path.parent,
    )


class TestFileTypeStats:
    def test_sole_type_has_pct_of_total_one(self) -> None:
        stats = _make_stats(".mp4", total_size=1000, rank=1, grand_total=1000)
        assert stats.pct_of_total == pytest.approx(1.0)

    def test_pct_of_total_is_share_of_grand_total(self) -> None:
        # .cr3 is 500 out of 2000 total → 25%
        stats = _make_stats(".cr3", total_size=500, rank=2, grand_total=2000)
        assert stats.pct_of_total == pytest.approx(0.25)

    def test_small_type_has_low_pct(self) -> None:
        stats = _make_stats(".txt", total_size=25, rank=5, grand_total=1000)
        assert stats.pct_of_total == pytest.approx(0.025)

    def test_fields_stored_correctly(self) -> None:
        path = Path("/video/clip.mp4")
        stats = FileTypeStats(
            extension=".mp4",
            file_count=3,
            total_size_bytes=3000,
            largest_file_size_bytes=1500,
            largest_file_path=path,
            rank=1,
            pct_of_total=0.6,
        )
        assert stats.extension == ".mp4"
        assert stats.file_count == 3
        assert stats.total_size_bytes == 3000
        assert stats.largest_file_size_bytes == 1500
        assert stats.largest_file_path == path
        assert stats.rank == 1


class TestScanReport:
    def _make_report(
        self,
        type_stats: list[FileTypeStats],
        threshold_rank: int,
        mtime: datetime,
    ) -> ScanReport:
        largest = _make_file_node("clip.mp4", 1000, mtime)
        return ScanReport(
            root_path=Path("/data"),
            scanned_at=mtime,
            total_files=10,
            total_size_bytes=5000,
            largest_file=largest,
            type_stats=type_stats,
            threshold_rank=threshold_rank,
        )

    def test_top_types_returns_correct_slice(self, fixed_mtime: datetime) -> None:
        stats = [
            _make_stats(".mp4", 1000, 1, 1000),
            _make_stats(".cr3", 500, 2, 1000),
            _make_stats(".pdf", 300, 3, 1000),
            _make_stats(".jpg", 250, 4, 1000),
            _make_stats(".txt", 50, 5, 1000),
            _make_stats("", 25, 6, 1000),
        ]
        report = self._make_report(stats, threshold_rank=3, mtime=fixed_mtime)
        top = report.top_types
        assert len(top) == 3
        assert top[0].extension == ".mp4"
        assert top[1].extension == ".cr3"
        assert top[2].extension == ".pdf"

    def test_top_types_excludes_below_threshold(self, fixed_mtime: datetime) -> None:
        stats = [
            _make_stats(".mp4", 1000, 1, 1000),
            _make_stats(".cr3", 500, 2, 1000),
            _make_stats(".pdf", 300, 3, 1000),
            _make_stats(".jpg", 250, 4, 1000),
        ]
        report = self._make_report(stats, threshold_rank=2, mtime=fixed_mtime)
        top = report.top_types
        assert len(top) == 2
        assert all(s.extension not in {".pdf", ".jpg"} for s in top)

    def test_top_types_with_single_type(self, fixed_mtime: datetime) -> None:
        stats = [_make_stats(".jpg", 500, 1, 500)]
        report = self._make_report(stats, threshold_rank=1, mtime=fixed_mtime)
        assert len(report.top_types) == 1

    def test_top_types_with_odd_type_count(self, fixed_mtime: datetime) -> None:
        stats = [
            _make_stats(".mp4", 1000, 1, 1000),
            _make_stats(".cr3", 500, 2, 1000),
            _make_stats(".jpg", 250, 3, 1000),
            _make_stats(".txt", 50, 4, 1000),
            _make_stats("", 25, 5, 1000),
        ]
        # ceil(5 / 2) = 3
        report = self._make_report(stats, threshold_rank=3, mtime=fixed_mtime)
        assert len(report.top_types) == 3

    def test_largest_file_is_accessible(self, fixed_mtime: datetime) -> None:
        stats = [_make_stats(".mp4", 1000, 1, 1000)]
        report = self._make_report(stats, threshold_rank=1, mtime=fixed_mtime)
        assert report.largest_file.name == "clip.mp4"
        assert report.largest_file.size_bytes == 1000

    def test_all_type_stats_accessible(self, fixed_mtime: datetime) -> None:
        stats = [
            _make_stats(".mp4", 1000, 1, 1000),
            _make_stats(".cr3", 500, 2, 1000),
        ]
        report = self._make_report(stats, threshold_rank=1, mtime=fixed_mtime)
        assert len(report.type_stats) == 2
