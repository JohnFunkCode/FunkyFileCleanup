# FunkyFileCleanup

A more intelligent file cleanup utility. Built for deep analysis of large, complex
file systems — with a focus on metadata richness, structural similarity, and
eventually merging near-duplicate directory trees.

## Current Functionality

### `funky scan`

Recursively scans a directory and produces a ranked report of file types by total
space consumed, and optionally identifies directories that contain duplicate files.

- Ranks all file types by total bytes, expressed as a percentage of the grand total
- Filters out types below 1% of total
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

# Analyze duplicate directories for specific file types
python -m funkyfilecleanup.cli.main scan ~/Documents --dup-types .pdf --dup-types .jpg
```

**Output files** (named after the scanned folder and today's date):

| File             | Location                            |
|------------------|-------------------------------------|
| SQLite database  | `database/<name>-<YYYY-MM-DD>.db`   |
| HTML report      | `reports/<name>-<YYYY-MM-DD>.html`  |

**Example console output:**

```
Scanning... 246,863 dirs — done.
Building report and saving to database... done in 45.2s
  Saved 1,118,291 file records in 38.4s
Analyzing duplicate directories...
  '.pdf': 797 records
  '.jpg': 4,975 records
  Running duplicate-directory query on 2 type(s)...
  Query complete in 1.3s
 done in 1.5s
  → 131 directory pair(s) with shared files

Scan Report: /Users/johnfunk/Documents
Scanned: 609,500 files  (138.1 GB)
Largest single file: Lightroom Catalog-v13-3.lrcat  (3.2 GB)

File Type Rankings by Total Space
──────────────────────────────────────────────────────
   #  Ext           Files   Total Size  % of Total
──────────────────────────────────────────────────────
    1  (none)      474,022     44.1 GB       31.9%
    2  .zip             28     24.8 GB       18.0%
  ·  ·  ·  ·  ·  · 50th percentile · · · · ·
    3  .dng         25,951     18.7 GB       13.6%
──────────────────────────────────────────────────────
```

---

## Duplicate Directory Analysis

When `--dup-types` is specified, the HTML report gains a second section identifying
directory pairs that share files — a strong indicator of near-duplicate folder trees.

**How it works:**

- Two files are considered duplicates when they share the same **filename and file size**
  (≥ 10 KB floor to exclude trivial matches). This is cheaper than hashing and reliable
  for large binary files like photos, videos, and PDFs where size collisions are
  astronomically unlikely.
- File types with more than 50,000 stored records are automatically skipped with a
  warning — a safety guard against expensive self-joins on large extensions like `(none)`.
- Results are **grouped by top-level directory pair** so all overlap between two folder
  trees (e.g. `MyProject` ↔ `MyProject-backup`) appears together, sorted alphabetically
  by path within the group so subfolders stay adjacent.
- Groups are sorted by total recoverable space so the highest-value cleanup targets
  appear first.

**HTML report — Directories with Shared Files section:**

Each group gets a header showing the two top-level trees being compared and the total
recoverable space if one copy were removed. Each pair within the group is a collapsible
card showing the shared file count, per-pair size, and an expandable file list.

### Origin of this feature

This analysis grew out of interactive SQL exploration against the `file_records` table.
The query that first revealed the pattern:

```sql
SELECT
    directory,
    COUNT(DISTINCT file_name) AS duplicate_file_count,
    GROUP_CONCAT(DISTINCT file_name) AS duplicate_files
FROM file_records
WHERE extension = '.jpg'
  AND file_name IN (
      SELECT file_name
      FROM file_records
      WHERE extension = '.jpg'
      GROUP BY file_name
      HAVING COUNT(*) > 1
  )
GROUP BY directory
HAVING duplicate_file_count > 1
ORDER BY duplicate_file_count DESC;
```

This was then evolved into a self-join that pairs directories together and matches on
both filename and file size, implemented in `ScanRepository.find_duplicate_directory_pairs()`.

### Performance note

The self-join is O(k²) in the number of files sharing the same name. A covering index on
`(scan_run_id, extension, file_name, size_bytes, directory)` makes the join a seek rather
than a scan — reducing analysis time from minutes to seconds on a ~600k file corpus.

---

## SQLite Schema

Two tables are written per scan run:

**`scan_runs`** — one row per scan  
**`file_records`** — one row per file belonging to a top-50% type

```sql
-- Space by extension for a given run
SELECT extension, COUNT(*), SUM(size_bytes)
FROM file_records
WHERE scan_run_id = 1
GROUP BY extension
ORDER BY 3 DESC;

-- Directories sharing filenames (basis for duplicate analysis)
SELECT
    r1.directory AS directory_1,
    r2.directory AS directory_2,
    COUNT(DISTINCT r1.file_name) AS shared_file_count,
    SUM(r1.size_bytes) AS total_size_bytes
FROM file_records r1
JOIN file_records r2
    ON  r1.file_name   = r2.file_name
    AND r1.scan_run_id = r2.scan_run_id
    AND r1.directory   < r2.directory
    AND r1.size_bytes  = r2.size_bytes
WHERE r1.scan_run_id = 1
  AND r1.extension IN ('.pdf', '.jpg')
  AND r2.extension IN ('.pdf', '.jpg')
  AND r1.size_bytes >= 10240
GROUP BY r1.directory, r2.directory
HAVING shared_file_count >= 2
ORDER BY total_size_bytes DESC;
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

1. **File hashing** — SHA-256 content hashing for exact duplicate detection; also
   replaces the SQL self-join with O(n) hash-bucketing for duplicate directory analysis
2. **Metadata reading** — XMP/IPTC/EXIF via ExifTool for photo-aware analysis
3. **Similarity scoring** — compare directory trees structurally and by content
4. **Merge planning** — identify near-duplicate folder trees and plan a canonical merge
5. **Interactive merge** — guided merge with metadata union and safe quarantine
