# Design 01 — FunkyFileCleanup Core Architecture

**Status:** Approved  
**Author:** John Funk  
**Created:** 2026-04-16

---

## Purpose

FunkyFileCleanup is a tool for identifying, analyzing, and merging near-duplicate
*directory trees* — entire project or collection structures that exist in multiple
versions across a filesystem. It is not a simple file deduplicator; it understands
structural similarity, file-type semantics, and embedded metadata.

The primary domain is photo collections with rich XMP/IPTC/EXIF hierarchical tag
metadata, but the architecture is designed to generalize to any file domain (video
projects, audio albums, etc.).

**Core principle:** A file with richer metadata is categorically better than one
without, regardless of file size or modification date.

---

## High-Level Pipeline

```mermaid
flowchart LR
    A[Filesystem] -->|scan| B[Domain Trees]
    B -->|analyze| C[Similarity Scores]
    C -->|report| D[Merge Candidates]
    D -->|plan| E[Merge Plan]
    E -->|execute| F[Canonical Output]
    E -->|undo| A
```

---

## Layer Architecture

```mermaid
graph TD
    CLI[cli/\nClick commands]
    SVC[services/\nOrchestration]
    ANA[analysis/\nStrategies & Comparators]
    OPS[operations/\nCommand objects]
    INF[infrastructure/\nFilesystem · Hashing · Metadata]
    DOM[domain/\nPure models · No I/O]

    CLI --> SVC
    SVC --> ANA
    SVC --> OPS
    ANA --> DOM
    OPS --> INF
    SVC --> INF
    INF --> DOM

    style DOM fill:#2d6a4f,color:#fff
    style INF fill:#1d3557,color:#fff
```

Each layer depends only on layers below it. The domain layer has zero external
dependencies and can be unit-tested without touching the filesystem.

---

## Domain Model

```mermaid
classDiagram
    class FileSystemNode {
        <<abstract>>
        +path: Path
        +name: str
        +size_bytes: int
        +mtime: datetime
    }

    class FileNode {
        +content_hash: str
        +metadata: MetadataRecord
        +extension: str
    }

    class DirectoryNode {
        +children: list[FileSystemNode]
        +tree_hash: str
        +file_count: int
        +total_size: int
        +depth: int
    }

    class MetadataRecord {
        +source: MetadataSource
        +fields: dict
        +tag_hierarchy: TagHierarchy
        +richness_score: float
    }

    class TagHierarchy {
        +root_tags: list[TagNode]
        +depth: int
        +total_nodes: int
        +as_flat_list() list[str]
    }

    class SimilarityScore {
        +strategy: str
        +score: float
        +details: dict
    }

    class MergeCandidate {
        +trees: list[DirectoryNode]
        +scores: list[SimilarityScore]
        +composite_score: float
    }

    FileSystemNode <|-- FileNode
    FileSystemNode <|-- DirectoryNode
    DirectoryNode o-- FileSystemNode : children
    FileNode --> MetadataRecord
    MetadataRecord --> TagHierarchy
    MergeCandidate --> DirectoryNode
    MergeCandidate --> SimilarityScore
```

---

## Similarity Analysis — Strategy Pattern

```mermaid
classDiagram
    class SimilarityStrategy {
        <<abstract>>
        +score(a: DirectoryNode, b: DirectoryNode) SimilarityScore
        +name: str
    }

    class ContentHashStrategy {
        +score() SimilarityScore
    }

    class StructuralStrategy {
        +score() SimilarityScore
    }

    class FuzzyThresholdStrategy {
        +threshold: float
        +score() SimilarityScore
    }

    class SubsetDetectionStrategy {
        +score() SimilarityScore
    }

    class CompositeSimilarityStrategy {
        +strategies: list[SimilarityStrategy]
        +weights: list[float]
        +score() SimilarityScore
    }

    SimilarityStrategy <|-- ContentHashStrategy
    SimilarityStrategy <|-- StructuralStrategy
    SimilarityStrategy <|-- FuzzyThresholdStrategy
    SimilarityStrategy <|-- SubsetDetectionStrategy
    SimilarityStrategy <|-- CompositeSimilarityStrategy
    CompositeSimilarityStrategy o-- SimilarityStrategy
```

---

## File Comparators — "Best Version" Selection

```mermaid
classDiagram
    class FileComparator {
        <<abstract>>
        +better(a: FileNode, b: FileNode) FileNode
        +extensions: list[str]
    }

    class PhotoComparator {
        +better() FileNode
    }

    class AudioComparator {
        +better() FileNode
    }

    class DefaultComparator {
        +better() FileNode
    }

    class ComparatorRegistry {
        +register(comparator, extensions)
        +get(extension: str) FileComparator
    }

    FileComparator <|-- PhotoComparator
    FileComparator <|-- AudioComparator
    FileComparator <|-- DefaultComparator
    ComparatorRegistry --> FileComparator
```

**Selection priority by type:**

| Comparator | Priority Order |
|------------|---------------|
| `PhotoComparator` | metadata richness → resolution → mtime |
| `AudioComparator` | bitrate → ID3 completeness → mtime |
| `DefaultComparator` | file size → mtime |

---

## Metadata Infrastructure — Factory Pattern

```mermaid
classDiagram
    class MetadataReader {
        <<abstract>>
        +read(path: Path) MetadataRecord
        +write(path: Path, record: MetadataRecord) None
        +supported_extensions: list[str]
    }

    class ExifToolReader {
        +read() MetadataRecord
        +write() None
        +supported_extensions: list[str]
    }

    class NullMetadataReader {
        +read() MetadataRecord
        +write() None
    }

    class MetadataReaderFactory {
        +register(reader: MetadataReader) None
        +get(extension: str) MetadataReader
    }

    MetadataReader <|-- ExifToolReader
    MetadataReader <|-- NullMetadataReader
    MetadataReaderFactory --> MetadataReader
```

**Library choice:** `pyexiftool` wrapping the ExifTool binary. It is the only tool
that correctly handles hierarchical XMP keyword trees, preserves all metadata on
write, and works across every photo format. Requires `brew install exiftool`.

`NullMetadataReader` returns an empty `MetadataRecord` for unsupported file types,
keeping the rest of the pipeline uniform.

---

## Operations — Command Pattern

```mermaid
classDiagram
    class FileOperation {
        <<abstract>>
        +execute() None
        +undo() None
        +describe() str
        +is_destructive: bool
    }

    class QuarantineOperation {
        +source: Path
        +quarantine_dir: Path
        +execute() None
        +undo() None
    }

    class MergeOperation {
        +candidate: MergeCandidate
        +output_dir: Path
        +plan: MergePlan
        +execute() None
        +undo() None
    }

    class MetadataMergeOperation {
        +sources: list[FileNode]
        +target: Path
        +execute() None
        +undo() None
    }

    class OperationHistory {
        +stack: list[FileOperation]
        +execute(op: FileOperation) None
        +undo_last() None
        +undo_all() None
    }

    FileOperation <|-- QuarantineOperation
    FileOperation <|-- MergeOperation
    FileOperation <|-- MetadataMergeOperation
    OperationHistory o-- FileOperation
```

`MetadataMergeOperation` writes the union of tags from all source file versions
into the target — preserving the richest possible metadata in the merged output.

---

## Service Orchestration

```mermaid
sequenceDiagram
    participant CLI
    participant ScanService
    participant AnalysisService
    participant MergeService
    participant FileSystemScanner
    participant SimilarityStrategy
    participant FileComparator
    participant OperationHistory

    CLI->>ScanService: scan(root_paths, config)
    ScanService->>FileSystemScanner: walk(path)
    FileSystemScanner-->>ScanService: DirectoryNode trees
    ScanService-->>CLI: ScanReport

    CLI->>AnalysisService: analyze(trees, strategies)
    AnalysisService->>SimilarityStrategy: score(a, b)
    SimilarityStrategy-->>AnalysisService: SimilarityScore
    AnalysisService-->>CLI: list[MergeCandidate]

    CLI->>MergeService: plan(candidate, output_dir)
    MergeService->>FileComparator: better(a, b)
    FileComparator-->>MergeService: FileNode
    MergeService-->>CLI: MergePlan

    CLI->>OperationHistory: execute(MergeOperation)
    OperationHistory-->>CLI: done

    CLI->>OperationHistory: undo_last()
    OperationHistory-->>CLI: restored
```

---

## Iterative Build Steps

| Step | Deliverable | Patterns |
|------|-------------|----------|
| 1 | `FileSystemNode`, `FileNode`, `DirectoryNode` domain models | Composite |
| 2 | `FileSystemScanner` — build domain trees from real filesystem | Infrastructure |
| 3 | `FileHasher` — SHA-256 with caching; `TreeHasher` | Infrastructure |
| 4 | `MetadataRecord`, `TagHierarchy`, `ExifToolReader` | Factory |
| 5 | `ContentHashStrategy` — first similarity score | Strategy |
| 6 | `StructuralStrategy`, `FuzzyThresholdStrategy`, `SubsetDetectionStrategy` | Strategy |
| 7 | `CompositeSimilarityStrategy` + `ComparatorRegistry` | Strategy, Composite |
| 8 | `PhotoComparator` — metadata-aware best-file selection | Strategy |
| 9 | `QuarantineOperation` + `OperationHistory` | Command |
| 10 | `ScanService` + `AnalysisService` orchestration | Service |
| 11 | CLI: `funky scan`, `funky analyze` | CLI |
| 12+ | `MergeOperation`, `MetadataMergeOperation`, interactive TUI | Command, Observer |

After each step: review what was learned, revisit the design if needed, then proceed.

---

## Testing Strategy

| Layer | Approach |
|-------|----------|
| Domain | Pure unit tests — no filesystem; use dataclasses and factory functions |
| Infrastructure | Integration tests against a fixture directory tree in `tests/fixtures/` |
| Strategies | Property-based tests (`hypothesis`) — empty trees, identical trees, subsets |
| Operations | Execute/undo round-trip tests for every command |
| CLI | `click.testing.CliRunner` for end-to-end command tests |

---

## Open Decisions

| Decision | Current Thinking | Revisit At |
|----------|-----------------|-----------|
| Scan result persistence | JSON initially | Step 9 — switch to SQLite if scale demands |
| Async filesystem walking | Synchronous first | Step 2 — profile on large trees |
| Metadata merge conflict resolution | Interactive prompt | Step 12 |
| TUI framework | `textual` likely | Step 12 |
| Config file format | TOML | Step 10 |
