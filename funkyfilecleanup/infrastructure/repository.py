from __future__ import annotations

import sqlite3
import sys
import time
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

CREATE INDEX IF NOT EXISTS idx_file_ext    ON file_records(extension);
CREATE INDEX IF NOT EXISTS idx_file_scan   ON file_records(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_file_lookup ON file_records(scan_run_id, extension, file_name, size_bytes, directory);
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

        total = len(records)
        print(f"\r  Saving {total:,} file records to database...", file=sys.stderr)
        _BATCH = 50_000
        t0 = time.perf_counter()
        for i in range(0, total, _BATCH):
            self._conn.executemany(
                """
                INSERT INTO file_records
                    (scan_run_id, file_name, extension, directory, size_bytes, mtime)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                records[i : i + _BATCH],
            )
            done = min(i + _BATCH, total)
            pct = done / total * 100 if total else 100
            print(
                f"\r  Saving file records... {done:,}/{total:,} ({pct:.0f}%)",
                end="", flush=True, file=sys.stderr,
            )
        self._conn.commit()
        elapsed = time.perf_counter() - t0
        print(f"\r  Saved {total:,} file records in {elapsed:.1f}s        ", file=sys.stderr)
        return run_id

    def find_duplicate_directory_pairs(
        self,
        scan_run_id: int,
        extensions: list[str],
        min_shared: int = 2,
        max_per_type: int = 50_000,
        min_size_bytes: int = 10_240,
    ) -> list[dict]:
        self._ensure_connected()
        assert self._conn is not None

        qualifying: list[str] = []
        for ext in extensions:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM file_records"
                " WHERE scan_run_id = ? AND extension = ? AND size_bytes >= ?",
                (scan_run_id, ext, min_size_bytes),
            ).fetchone()[0]
            if count == 0:
                print(f"  WARNING: '{ext}' — no records found, skipping", file=sys.stderr)
            elif count > max_per_type:
                print(
                    f"  WARNING: '{ext}' — {count:,} records exceeds threshold of "
                    f"{max_per_type:,}, skipping",
                    file=sys.stderr,
                )
            else:
                print(f"  '{ext}': {count:,} records", file=sys.stderr)
                qualifying.append(ext)

        if not qualifying:
            print("  No qualifying extensions — duplicate analysis skipped.", file=sys.stderr)
            return []

        placeholders = ",".join("?" * len(qualifying))
        print(
            f"  Running duplicate-directory query on {len(qualifying)} type(s)...",
            flush=True, file=sys.stderr,
        )
        t0 = time.perf_counter()
        rows = self._conn.execute(
            f"""
            SELECT
                r1.directory        AS directory_1,
                r2.directory        AS directory_2,
                COUNT(DISTINCT r1.file_name)            AS shared_file_count,
                SUM(r1.size_bytes)                      AS total_size_bytes,
                GROUP_CONCAT(DISTINCT r1.file_name)     AS shared_files
            FROM file_records r1
            JOIN file_records r2
                ON  r1.file_name    = r2.file_name
                AND r1.scan_run_id  = r2.scan_run_id
                AND r1.directory    < r2.directory
            WHERE r1.scan_run_id = ?
              AND r1.extension IN ({placeholders})
              AND r2.extension IN ({placeholders})
              AND r1.size_bytes >= ?
              AND r1.size_bytes = r2.size_bytes
            GROUP BY r1.directory, r2.directory
            HAVING shared_file_count >= ?
            ORDER BY total_size_bytes DESC
            """,
            (scan_run_id, *qualifying, *qualifying, min_size_bytes, min_shared),
        ).fetchall()
        elapsed = time.perf_counter() - t0
        print(f"  Query complete in {elapsed:.1f}s", file=sys.stderr)
        return [
            {
                "directory_1": row[0],
                "directory_2": row[1],
                "shared_file_count": row[2],
                "total_size_bytes": row[3],
                "shared_files": row[4].split(","),
            }
            for row in rows
        ]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _ensure_connected(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
