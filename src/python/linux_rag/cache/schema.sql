-- linux_rag/cache/schema.sql
-- Schema version: 1
-- Purpose: Initialize SQLite tables for answer sessions, cache metadata,
-- and citation linkage used by the Linux RAG assistant.

PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO schema_migrations (version, description)
SELECT 1, 'Initial cache and session schema'
WHERE NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = 1
);

CREATE TABLE IF NOT EXISTS answer_sessions (
    id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    model_used TEXT NOT NULL,
    response_time_ms INTEGER NOT NULL CHECK (response_time_ms >= 0),
    cache_hit INTEGER NOT NULL CHECK (cache_hit IN (0, 1)),
    created_at TEXT NOT NULL,
    feedback_id TEXT
);

CREATE TABLE IF NOT EXISTS answer_session_sources (
    session_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    PRIMARY KEY (session_id, source_id),
    FOREIGN KEY (session_id) REFERENCES answer_sessions(id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cache_entries (
    fingerprint TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    stored_at TEXT NOT NULL,
    last_accessed_at TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    FOREIGN KEY (session_id) REFERENCES answer_sessions(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_answer_sessions_created_at
    ON answer_sessions (created_at);

CREATE INDEX IF NOT EXISTS idx_answer_sessions_cache_hit
    ON answer_sessions (cache_hit);

CREATE INDEX IF NOT EXISTS idx_cache_entries_last_accessed
    ON cache_entries (last_accessed_at);

COMMIT;
