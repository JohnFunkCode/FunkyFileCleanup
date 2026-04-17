from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from itertools import groupby
from pathlib import Path
from typing import Generator

import click
from jinja2 import Environment, FileSystemLoader

from funkyfilecleanup.domain.reports import ScanReport
from funkyfilecleanup.infrastructure.repository import ScanRepository
from funkyfilecleanup.infrastructure.scanner import FileSystemScanner
from funkyfilecleanup.services.scan_service import ScanService

_MIN_PCT = 0.01
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_REPORTS_DIR = Path("reports")
_DATABASE_DIR = Path("database")


@contextmanager
def _phase(label: str) -> Generator[None, None, None]:
    print(f"{label}...", end="", flush=True, file=sys.stderr)
    t0 = time.perf_counter()
    yield
    elapsed = time.perf_counter() - t0
    print(f" done in {elapsed:.1f}s", file=sys.stderr)


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--db", default=None, type=click.Path(path_type=Path),
              help="SQLite output path (default: database/<name>-<date>.db)")
@click.option("--ignore", multiple=True, metavar="PATTERN",
              help="Directory name to ignore (repeatable)")
@click.option("--dup-types", multiple=True, metavar="EXT",
              help="File extension to analyze for duplicate directories (e.g. .jpg). Repeatable.")
def scan(path: Path, db: Path | None, ignore: tuple[str, ...], dup_types: tuple[str, ...]) -> None:
    """Scan PATH and report file types ranked by total space consumed."""
    from datetime import date
    stem = _report_stem(path, date.today())
    if db is None:
        _DATABASE_DIR.mkdir(exist_ok=True)
        db = _DATABASE_DIR / f"{stem}.db"

    scanner = FileSystemScanner(ignore_patterns=list(ignore) if ignore else None)
    repository = ScanRepository(db)
    repository.initialize()

    service = ScanService(repository=repository, scanner=scanner)

    with _phase("Building report and saving to database"):
        report, run_id = service.run(path)

    dup_pairs: list[dict] = []
    if dup_types:
        with _phase("Analyzing duplicate directories"):
            dup_pairs = repository.find_duplicate_directory_pairs(run_id, list(dup_types))
        click.echo(f"  → {len(dup_pairs):,} directory pair(s) with shared files", file=sys.stderr)
    else:
        click.echo(
            "  (Skipping duplicate analysis — use --dup-types .ext to enable)",
            file=sys.stderr,
        )

    repository.close()

    _print_report(report, db)

    with _phase("Writing HTML report"):
        html_path = _write_html_report(report, db, dup_pairs, list(dup_types))
    click.echo(f"HTML report  →  {html_path}")


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _report_stem(root: Path, date: object) -> str:
    """Shared filename stem: <folder-name>-<YYYY-MM-DD>."""
    return f"{root.name}-{date}"


def _human(size: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# ── Console report ────────────────────────────────────────────────────────────

def _print_report(report: ScanReport, db: Path) -> None:
    visible = [s for s in report.type_stats if s.pct_of_total >= _MIN_PCT]
    hidden_count = len(report.type_stats) - len(visible)

    click.echo(f"\nScan Report: {report.root_path}")
    click.echo(f"Scanned: {report.total_files:,} files  ({_human(report.total_size_bytes)})")
    click.echo(
        f"Largest single file: {report.largest_file.name}"
        f"  ({_human(report.largest_file.size_bytes)})"
    )
    click.echo()
    click.echo("File Type Rankings by Total Space")
    click.echo("─" * 50)
    click.echo(f" {'#':>3}  {'Ext':<10}  {'Files':>7}  {'Total Size':>11}  {'% of Total':>10}")
    click.echo("─" * 50)

    for stats in visible:
        ext_label = stats.extension if stats.extension else "(none)"
        if stats.rank == report.threshold_rank + 1:
            click.echo(f"  {'·':>3}  {'· · · · 50th percentile · · · ·'}")
        click.echo(
            f"  {stats.rank:>3}  {ext_label:<10}  {stats.file_count:>7,}"
            f"  {_human(stats.total_size_bytes):>11}"
            f"  {stats.pct_of_total * 100:>9.1f}%"
        )

    click.echo("─" * 50)
    top_file_count = sum(s.file_count for s in report.top_types)
    click.echo(
        f"Stored {len(report.top_types)} type(s) · "
        f"{top_file_count:,} file record(s)  →  {db}"
    )
    if hidden_count:
        click.echo(f"({hidden_count} type(s) below 1% not shown)")
    click.echo()


# ── Duplicate pair grouping ───────────────────────────────────────────────────

def _group_dup_pairs(pairs: list[dict], root: Path) -> list[dict]:
    """Group and sort duplicate pairs by their top-level directory under root.

    Within each group pairs are sorted alphabetically by path so subfolders of
    the same tree stay together.  Groups are sorted by total recoverable bytes.
    """
    root_depth = len(root.parts)

    def _top(directory: str) -> str:
        parts = Path(directory).parts
        return parts[root_depth] if len(parts) > root_depth else parts[-1]

    def _normalize(pair: dict) -> dict:
        d1, d2 = pair["directory_1"], pair["directory_2"]
        if d1 > d2:
            return {**pair, "directory_1": d2, "directory_2": d1}
        return pair

    normalized = sorted(
        (_normalize(p) for p in pairs),
        key=lambda p: (p["directory_1"], p["directory_2"]),
    )

    def _group_key(pair: dict) -> tuple[str, str]:
        a, b = _top(pair["directory_1"]), _top(pair["directory_2"])
        return (min(a, b), max(a, b))

    groups = []
    for key, group_iter in groupby(normalized, key=_group_key):
        group_pairs = list(group_iter)
        a, b = key
        label = f"{a}  ↔  {b}" if a != b else a
        total_bytes = sum(p["total_size_bytes"] for p in group_pairs)
        groups.append({
            "label": label,
            "total_size_bytes": total_bytes,
            "pairs": group_pairs,
        })

    groups.sort(key=lambda g: g["total_size_bytes"], reverse=True)
    return groups


# ── HTML report ───────────────────────────────────────────────────────────────

def _write_html_report(report: ScanReport, db: Path, dup_pairs: list[dict], dup_types: list[str]) -> Path:
    visible = [s for s in report.type_stats if s.pct_of_total >= _MIN_PCT]
    hidden_count = len(report.type_stats) - len(visible)

    env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)
    env.filters["human_size"] = _human
    env.filters["format_int"] = lambda n: f"{n:,}"

    grouped_pairs = _group_dup_pairs(dup_pairs, report.root_path)
    total_pairs = sum(len(g["pairs"]) for g in grouped_pairs)

    template = env.get_template("scan_report.html")
    html = template.render(
        report=report,
        visible_stats=visible,
        hidden_count=hidden_count,
        threshold_rank=report.threshold_rank,
        db_path=db,
        grouped_pairs=grouped_pairs,
        total_pairs=total_pairs,
        dup_types=dup_types,
    )

    _REPORTS_DIR.mkdir(exist_ok=True)
    stem = _report_stem(report.root_path, report.scanned_at.strftime("%Y-%m-%d"))
    output_path = _REPORTS_DIR / f"{stem}.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    cli()
