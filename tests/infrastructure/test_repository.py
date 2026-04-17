"""Tests for ScanRepository (SQLite persistence)."""
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from funkyfilecleanup.domain.nodes import FileNode
from funkyfilecleanup.domain.reports import FileTypeStats, ScanReport
from funkyfilecleanup.infrastructure.repository import ScanRepository


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


def _make_stats(
    ext: str, total: int, rank: int, top_total: int, count: int = 1
) -> FileTypeStats:
    return FileTypeStats(
        extension=ext,
        file_count=count,
        total_size_bytes=total,
        largest_file_size_bytes=total,
        largest_file_path=Path(f"/fake/file{ext}"),
        rank=rank,
        pct_of_total=total / top_total,
    )


def _make_scan_report(
    stats: list[FileTypeStats],
    threshold_rank: int,
    mtime: datetime,
    files_by_extension: dict[str, list[FileNode]],
) -> ScanReport:
    largest = max(
        (f for nodes in files_by_extension.values() for f in nodes),
        key=lambda f: f.size_bytes,
    )
    return ScanReport(
        root_path=Path("/data"),
        scanned_at=mtime,
        total_files=sum(len(v) for v in files_by_extension.values()),
        total_size_bytes=sum(f.size_bytes for nodes in files_by_extension.values() for f in nodes),
        largest_file=largest,
        type_stats=stats,
        threshold_rank=threshold_rank,
    )


class TestScanRepository:
    def test_initialize_creates_scan_runs_table(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        repo = ScanRepository(db_path)
        repo.initialize()

        conn = sqlite3.connect(db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        repo.close()

        assert "scan_runs" in tables

    def test_initialize_creates_file_records_table(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        repo = ScanRepository(db_path)
        repo.initialize()

        conn = sqlite3.connect(db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        repo.close()

        assert "file_records" in tables

    def test_initialize_is_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        repo = ScanRepository(db_path)
        repo.initialize()
        repo.initialize()  # must not raise
        repo.close()

    def test_save_scan_returns_integer_id(
        self, tmp_path: Path, fixed_mtime: datetime
    ) -> None:
        db_path = tmp_path / "test.db"
        repo = ScanRepository(db_path)
        repo.initialize()

        mp4 = _make_file_node("clip.mp4", 1000, fixed_mtime)
        stats = [_make_stats(".mp4", 1000, 1, 1000)]
        report = _make_scan_report(
            stats, threshold_rank=1, mtime=fixed_mtime,
            files_by_extension={".mp4": [mp4]},
        )

        run_id = repo.save_scan(report, files_by_extension={".mp4": [mp4]})
        repo.close()

        assert isinstance(run_id, int)
        assert run_id >= 1

    def test_save_scan_inserts_scan_run_row(
        self, tmp_path: Path, fixed_mtime: datetime
    ) -> None:
        db_path = tmp_path / "test.db"
        repo = ScanRepository(db_path)
        repo.initialize()

        mp4 = _make_file_node("clip.mp4", 1000, fixed_mtime)
        stats = [_make_stats(".mp4", 1000, 1, 1000)]
        report = _make_scan_report(
            stats, threshold_rank=1, mtime=fixed_mtime,
            files_by_extension={".mp4": [mp4]},
        )
        repo.save_scan(report, files_by_extension={".mp4": [mp4]})
        repo.close()

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT root_path, total_files FROM scan_runs").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0][0] == str(Path("/data"))
        assert rows[0][1] == 1

    def test_save_scan_stores_only_top_50_percent_files(
        self, tmp_path: Path, fixed_mtime: datetime
    ) -> None:
        """
        6 types, threshold_rank=3 → only files of top 3 types stored.
        Top 3: .mp4 (1 file), .cr3 (1 file), .pdf (1 file) = 3 records.
        Bottom 3: .jpg (2 files), .txt (1 file), no-ext (1 file) = excluded.
        """
        db_path = tmp_path / "test.db"
        repo = ScanRepository(db_path)
        repo.initialize()

        files_by_ext = {
            ".mp4": [_make_file_node("clip.mp4", 1000, fixed_mtime)],
            ".cr3": [_make_file_node("raw.cr3", 500, fixed_mtime)],
            ".pdf": [_make_file_node("doc.pdf", 300, fixed_mtime)],
            ".jpg": [
                _make_file_node("a.jpg", 125, fixed_mtime),
                _make_file_node("b.jpg", 125, fixed_mtime),
            ],
            ".txt": [_make_file_node("notes.txt", 50, fixed_mtime)],
            "": [_make_file_node("noext", 25, fixed_mtime)],
        }
        stats = [
            _make_stats(".mp4", 1000, 1, 1000),
            _make_stats(".cr3", 500, 2, 1000),
            _make_stats(".pdf", 300, 3, 1000),
            _make_stats(".jpg", 250, 4, 1000, count=2),
            _make_stats(".txt", 50, 5, 1000),
            _make_stats("", 25, 6, 1000),
        ]
        report = _make_scan_report(
            stats, threshold_rank=3, mtime=fixed_mtime,
            files_by_extension=files_by_ext,
        )
        repo.save_scan(report, files_by_extension=files_by_ext)
        repo.close()

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM file_records").fetchone()[0]
        extensions = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT extension FROM file_records"
            ).fetchall()
        }
        conn.close()

        assert count == 3
        assert extensions == {".mp4", ".cr3", ".pdf"}

    def test_save_scan_stores_correct_file_fields(
        self, tmp_path: Path, fixed_mtime: datetime
    ) -> None:
        db_path = tmp_path / "test.db"
        repo = ScanRepository(db_path)
        repo.initialize()

        mp4 = _make_file_node("clip.mp4", 1000, fixed_mtime)
        stats = [_make_stats(".mp4", 1000, 1, 1000)]
        report = _make_scan_report(
            stats, threshold_rank=1, mtime=fixed_mtime,
            files_by_extension={".mp4": [mp4]},
        )
        repo.save_scan(report, files_by_extension={".mp4": [mp4]})
        repo.close()

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT file_name, extension, directory, size_bytes FROM file_records"
        ).fetchone()
        conn.close()

        assert row[0] == "clip.mp4"
        assert row[1] == ".mp4"
        assert row[2] == str(Path("/fake"))
        assert row[3] == 1000

    def test_multiple_scans_get_sequential_ids(
        self, tmp_path: Path, fixed_mtime: datetime
    ) -> None:
        db_path = tmp_path / "test.db"
        repo = ScanRepository(db_path)
        repo.initialize()

        mp4 = _make_file_node("clip.mp4", 1000, fixed_mtime)
        stats = [_make_stats(".mp4", 1000, 1, 1000)]
        files = {".mp4": [mp4]}

        report = _make_scan_report(stats, threshold_rank=1, mtime=fixed_mtime,
                                   files_by_extension=files)

        id1 = repo.save_scan(report, files_by_extension=files)
        id2 = repo.save_scan(report, files_by_extension=files)
        repo.close()

        assert id2 > id1
