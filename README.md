# FunkyFileCleanup

A more intelligent file cleanup utility. Built for deep analysis of large, complex
file systems — with a focus on metadata richness, structural similarity, and
eventually merging near-duplicate directory trees.

## Current Functionality

### `funky scan`

Recursively scans a directory and produces a ranked report of file types by total
space consumed.

- Ranks all file types by total bytes, expressed as a percentage of the grand total
- Filters out types below 1% of total (configurable)
- Stores detailed file records for the top 50% of types (by space) to SQLite for
  further analysis
- Generates a console report and an HTML report
- Skips symlinks; tolerates files that vanish mid-scan (e.g. log rotation)
- Ignores `.git`, `.venv`, `__pycache__`, `node_modules` by default

**Usage:**

```bash
source .venv/bin/activate

# Scan with default output locations
python -m funkyfilecleanup.cli.main scan ~/Documents

# Specify a custom database path
python -m funkyfilecleanup.cli.main scan ~/Documents --db /tmp/docs.db

# Add extra ignore patterns
python -m funkyfilecleanup.cli.main scan ~/Documents --ignore node_modules --ignore dist
```

**Output files** (named after the scanned folder and today's date):

| File             | Location                            |
|------------------|-------------------------------------|
| SQLite database  | `database/<name>-<YYYY-MM-DD>.db`   |
| HTML report      | `reports/<name>-<YYYY-MM-DD>.html`  |

**Example console output:**

```
Scanning... 246,863 dirs — done.

Scan Report: /Users/johnfunk
Scanned: 1,561,675 files  (432.8 GB)
Largest single file: Windows11.iso  (5.6 GB)

File Type Rankings by Total Space
──────────────────────────────────────────────────────
   #  Ext           Files   Total Size  % of Total
──────────────────────────────────────────────────────
    1  .vmdk            54    134.7 GB       31.1%
    2  (none)    1,118,237     86.0 GB       19.9%
    3  .zip            592     30.4 GB        7.0%
  ·  ·  ·  ·  ·  · 50th percentile · · · · ·
    4  .pdf          1,558     21.8 GB        5.0%
──────────────────────────────────────────────────────
```

## SQLite Schema

Two tables are written per scan run:

**`scan_runs`** — one row per scan  
**`file_records`** — one row per file belonging to a top-50% type

```sql
SELECT extension, COUNT(*), SUM(size_bytes)
FROM file_records
WHERE scan_run_id = 1
GROUP BY extension
ORDER BY 3 DESC;
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install click jinja2
```

Python 3.14+ required.

## Project Structure

```
funkyfilecleanup/
├── domain/          # Pure data models — no I/O
├── infrastructure/  # Filesystem scanner, SQLite repository
├── services/        # Orchestration
└── cli/             # Click commands, Jinja2 HTML report

docs/
├── designs/         # Approved architecture designs
├── proposals/       # Concept proposals under consideration
└── adr/             # Architecture Decision Records
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Roadmap

This is the first increment of a larger vision. Planned phases:

1. **File hashing** — SHA-256 content hashing for exact duplicate detection
2. **Metadata reading** — XMP/IPTC/EXIF via ExifTool for photo-aware analysis
3. **Similarity scoring** — compare directory trees structurally and by content
4. **Merge planning** — identify near-duplicate folder trees and plan a canonical merge
5. **Interactive merge** — guided merge with metadata union and safe quarantine
