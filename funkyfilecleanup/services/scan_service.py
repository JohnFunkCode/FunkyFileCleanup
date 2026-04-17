from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from funkyfilecleanup.domain.nodes import DirectoryNode, FileNode
from funkyfilecleanup.domain.reports import FileTypeStats, ScanReport
from funkyfilecleanup.infrastructure.repository import ScanRepository
from funkyfilecleanup.infrastructure.scanner import FileSystemScanner


class ScanService:
    def __init__(
        self,
        repository: ScanRepository,
        scanner: FileSystemScanner | None = None,
    ) -> None:
        self._repository = repository
        self._scanner = scanner or FileSystemScanner()

    def run(
        self,
        root: Path,
        tree: DirectoryNode | None = None,
    ) -> ScanReport:
        if tree is None:
            tree = self._scanner.scan(root)

        all_files = _collect_files(tree)
        files_by_extension = _group_by_extension(all_files)
        type_stats = _build_type_stats(files_by_extension)
        threshold_rank = math.ceil(len(type_stats) / 2) if type_stats else 0
        largest_file = max(all_files, key=lambda f: f.size_bytes)

        report = ScanReport(
            root_path=root,
            scanned_at=datetime.now(),
            total_files=len(all_files),
            total_size_bytes=sum(f.size_bytes for f in all_files),
            largest_file=largest_file,
            type_stats=type_stats,
            threshold_rank=threshold_rank,
        )
        self._repository.save_scan(report, files_by_extension=files_by_extension)
        return report


def _collect_files(node: DirectoryNode) -> list[FileNode]:
    files: list[FileNode] = []
    for child in node.children:
        if isinstance(child, FileNode):
            files.append(child)
        else:
            files.extend(_collect_files(child))
    return files


def _group_by_extension(files: list[FileNode]) -> dict[str, list[FileNode]]:
    groups: dict[str, list[FileNode]] = {}
    for f in files:
        groups.setdefault(f.extension, []).append(f)
    return groups


def _build_type_stats(
    files_by_extension: dict[str, list[FileNode]],
) -> list[FileTypeStats]:
    if not files_by_extension:
        return []

    ranked = sorted(
        files_by_extension.items(),
        key=lambda item: sum(f.size_bytes for f in item[1]),
        reverse=True,
    )
    grand_total = sum(f.size_bytes for item in ranked for f in item[1])

    stats = []
    for rank, (ext, files) in enumerate(ranked, start=1):
        total = sum(f.size_bytes for f in files)
        largest = max(files, key=lambda f: f.size_bytes)
        stats.append(
            FileTypeStats(
                extension=ext,
                file_count=len(files),
                total_size_bytes=total,
                largest_file_size_bytes=largest.size_bytes,
                largest_file_path=largest.path,
                rank=rank,
                pct_of_total=total / grand_total,
            )
        )
    return stats
