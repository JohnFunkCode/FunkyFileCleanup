from __future__ import annotations

import sqlite3
from pathlib import Path

from funkyfilecleanup.domain.nodes import FileNode
from funkyfilecleanup.domain.reports import ScanReport

_DDL = """
CREATE TABLE IF NOT EXISTS scan_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    root_path           TEXT    NOT NULL,
    scanned_at          TEXT    NOT NULL,
    total_files         INTEGER NOT NULL,
    total_bytes         INTEGER NOT NULL,
    largest_file_path   TEXT,
    largest_file_bytes  INTEGER
);

CREATE TABLE IF NOT EXISTS file_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id  INTEGER NOT NULL REFERENCES scan_runs(id),
    file_name    TEXT    NOT NULL,
    extension    TEXT    NOT NULL,
    directory    TEXT    NOT NULL,
    size_bytes   INTEGER NOT NULL,
    mtime        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_file_ext  ON file_records(extension);
CREATE INDEX IF NOT EXISTS idx_file_scan ON file_records(scan_run_id);
"""


class ScanRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self._ensure_connected()
        assert self._conn is not None
        self._conn.executescript(_DDL)
        self._conn.commit()

    def save_scan(
        self,
        report: ScanReport,
        files_by_extension: dict[str, list[FileNode]],
    ) -> int:
        self._ensure_connected()
        assert self._conn is not None

        cursor = self._conn.execute(
            """
            INSERT INTO scan_runs
                (root_path, scanned_at, total_files, total_bytes,
                 largest_file_path, largest_file_bytes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(report.root_path),
                report.scanned_at.isoformat(),
                report.total_files,
                report.total_size_bytes,
                str(report.largest_file.path),
                report.largest_file.size_bytes,
            ),
        )
        run_id = cursor.lastrowid
        assert run_id is not None

        top_extensions = {s.extension for s in report.top_types}
        records = [
            (
                run_id,
                f.name,
                f.extension,
                str(f.directory),
                f.size_bytes,
                f.mtime.isoformat(),
            )
            for ext, files in files_by_extension.items()
            if ext in top_extensions
            for f in files
        ]
        self._conn.executemany(
            """
            INSERT INTO file_records
                (scan_run_id, file_name, extension, directory, size_bytes, mtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            records,
        )
        self._conn.commit()
        return run_id

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _ensure_connected(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
