# Data Model - Linux CLI Knowledge Assistant

## Entity Overview

### KnowledgeSource
- **Purpose**: Represents any ingested document (man page or Kiwix article) that powers answer citations.
- **Key Fields**:
  - `id` (UUID) - primary key aligned with Weaviate object ID
  - `title` (string)
  - `type` (enum: `man_page`, `wiki_article`)
  - `section` (string, optional) - man page section or wiki category
  - `source_path` (string) - absolute filesystem path for local copy
  - `checksum` (string) - SHA256 for change detection
  - `ingested_at` (datetime)
  - `last_refreshed_at` (datetime, optional)
- **Relationships**:
  - Linked to `EmbeddingVector` via Weaviate vector index (external relation)
  - Referenced by `AnswerSession.sources`
- **Validation Rules**:
  - Unique combination of `title` + `section` for man pages
  - `source_path` must resolve within allowed mount (read-only check)

### AnswerSession
- **Purpose**: Captures each user query, generated answer, and supporting metadata.
- **Key Fields**:
  - `id` (UUID)
  - `query_text` (text)
  - `response_text` (text)
  - `model_used` (enum: `gemma3:1b`, `codegemma:2b`)
  - `response_time_ms` (integer)
  - `cache_hit` (boolean)
  - `created_at` (datetime)
  - `sources` (array<UUID>) - references to `KnowledgeSource`
  - `feedback_id` (UUID, optional) - link to `FeedbackEntry`
- **Relationships**:
  - Many-to-many with `KnowledgeSource`
  - Optional one-to-one with `FeedbackEntry`
- **Validation Rules**:
  - `response_time_ms` < 2000 for cold path, < 1000 for cached path (enforced via monitoring)
  - `sources` list must contain at least one entry unless explicitly marked as `no_source` (error)

### FeedbackEntry
- **Purpose**: Records user-submitted evaluation for follow-up improvements.
- **Key Fields**:
  - `id` (UUID)
  - `session_id` (UUID) - foreign key to `AnswerSession`
  - `rating` (enum: `positive`, `neutral`, `negative`)
  - `comment` (text, optional)
  - `created_at` (datetime)
  - `status` (enum: `open`, `triaged`, `resolved`)
- **Relationships**:
  - Belongs to a single `AnswerSession`
- **Validation Rules**:
  - `status` transitions: `open` -> `triaged` -> `resolved` (no backward transitions without admin override)

### IngestionJob
- **Purpose**: Audit record for data-load or refresh operations.
- **Key Fields**:
  - `id` (UUID)
  - `job_type` (enum: `initial_load`, `manual_refresh`, `scheduled_refresh`)
  - `started_at` (datetime)
  - `completed_at` (datetime, optional)
  - `man_pages_processed` (integer)
  - `wiki_articles_processed` (integer)
  - `errors` (json array)
  - `status` (enum: `running`, `completed`, `failed`)
- **Relationships**:
  - None direct; referenced by operational telemetry and reports
- **Validation Rules**:
  - `completed_at` required when `status` = `completed` or `failed`
  - `errors` entries must include `source_path` and `message`

### CacheEntry
- **Purpose**: Enforces persistent query-response caching with size limits.
- **Key Fields**:
  - `fingerprint` (string) - SHA256 of canonical query + parameters (primary key)
  - `session_id` (UUID) - references `AnswerSession`
  - `stored_at` (datetime)
  - `last_accessed_at` (datetime)
  - `size_bytes` (integer)
- **Relationships**:
  - One-to-one with `AnswerSession`
- **Validation Rules**:
  - Eviction job keeps total `size_bytes` sum <= 10% of `/var/lib/linux-rag` capacity
  - `last_accessed_at` updated on every cache hit

## State Transitions

- **FeedbackEntry.status**: `open` -> `triaged` -> `resolved`; automatic transition to `triaged` when engineering notes the issue, manual close to `resolved` once documentation updated.
- **IngestionJob.status**: Initialized as `running`; transitions to `completed` on success with metrics populated or `failed` with errors captured.
- **CacheEntry lifecycle**: Created alongside `AnswerSession`; `last_accessed_at` updates per hit; entry deleted when eviction policy triggered.

## Data Volume & Scale Assumptions

- KnowledgeSource: ~20k records (man pages + selected Kiwix).
- AnswerSession: Anticipated 1k-5k sessions stored locally per host (rolling 90-day retention).
- CacheEntry: Mirrors AnswerSession volume but trimmed by eviction once disk threshold met.
- IngestionJob: <100 historical records; used for audit/compliance.

## Constraints & Indexing

- SQLite indices on `AnswerSession.cache_hit`, `AnswerSession.created_at`, and `CacheEntry.last_accessed_at` to keep reporting performant.
- Weaviate vectors handle semantic search; store KnowledgeSource metadata for deterministic lookups.
- All timestamps stored in UTC ISO8601.
