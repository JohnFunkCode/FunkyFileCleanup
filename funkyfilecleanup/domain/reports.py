from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from funkyfilecleanup.domain.nodes import FileNode


@dataclass(frozen=True)
class FileTypeStats:
    extension: str
    file_count: int
    total_size_bytes: int
    largest_file_size_bytes: int
    largest_file_path: Path
    rank: int
    pct_of_total: float  # share of the grand total across all scanned files (0.0–1.0)


@dataclass(frozen=True)
class ScanReport:
    root_path: Path
    scanned_at: datetime
    total_files: int
    total_size_bytes: int
    largest_file: FileNode
    type_stats: list[FileTypeStats]  # ordered by rank ascending (rank 1 first)
    threshold_rank: int              # last rank included in top 50%

    @property
    def top_types(self) -> list[FileTypeStats]:
        return self.type_stats[: self.threshold_rank]
