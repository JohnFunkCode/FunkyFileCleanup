from __future__ import annotations

from pathlib import Path

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


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--db", default=None, type=click.Path(path_type=Path),
              help="SQLite output path (default: database/<name>-<date>.db)")
@click.option("--ignore", multiple=True, metavar="PATTERN",
              help="Directory name to ignore (repeatable)")
def scan(path: Path, db: Path | None, ignore: tuple[str, ...]) -> None:
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
    report = service.run(path)
    repository.close()

    _print_report(report, db)
    html_path = _write_html_report(report, db)
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


# ── HTML report ───────────────────────────────────────────────────────────────

def _write_html_report(report: ScanReport, db: Path) -> Path:
    visible = [s for s in report.type_stats if s.pct_of_total >= _MIN_PCT]
    hidden_count = len(report.type_stats) - len(visible)

    env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)
    env.filters["human_size"] = _human
    env.filters["format_int"] = lambda n: f"{n:,}"

    template = env.get_template("scan_report.html")
    html = template.render(
        report=report,
        visible_stats=visible,
        hidden_count=hidden_count,
        threshold_rank=report.threshold_rank,
        db_path=db,
    )

    _REPORTS_DIR.mkdir(exist_ok=True)
    stem = _report_stem(report.root_path, report.scanned_at.strftime("%Y-%m-%d"))
    output_path = _REPORTS_DIR / f"{stem}.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    cli()
