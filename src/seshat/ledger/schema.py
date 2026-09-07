"""The ledger DDL, from plan.md §4, applied once per database.

No migrations framework — `schema_version` is stamped at 1 and stays there for
phase one (task non-scope).
"""

from __future__ import annotations

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    commit_sha TEXT,
    started_at TEXT,
    finished_at TEXT,
    model TEXT,
    thinking INTEGER NOT NULL DEFAULT 0,
    workers INTEGER NOT NULL DEFAULT 1,
    budget_units INTEGER,
    budget_minutes INTEGER,
    budget_tokens INTEGER,
    units_done INTEGER NOT NULL DEFAULT 0,
    claims_confirmed INTEGER NOT NULL DEFAULT 0,
    claims_refuted INTEGER NOT NULL DEFAULT 0,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS units (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    ast_hash TEXT NOT NULL,
    inbound_calls INTEGER NOT NULL DEFAULT 0,
    first_seen_run TEXT NOT NULL,
    last_seen_run TEXT NOT NULL,
    last_scanned_run TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (first_seen_run) REFERENCES runs (id),
    FOREIGN KEY (last_seen_run) REFERENCES runs (id),
    FOREIGN KEY (last_scanned_run) REFERENCES runs (id)
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    text TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    candidate_rule INTEGER NOT NULL DEFAULT 0,
    rule_sightings INTEGER NOT NULL DEFAULT 0,
    created_run TEXT NOT NULL,
    verified_run TEXT,
    verified_sha TEXT,
    retries INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (unit_id) REFERENCES units (id),
    FOREIGN KEY (created_run) REFERENCES runs (id),
    FOREIGN KEY (verified_run) REFERENCES runs (id)
);

CREATE TABLE IF NOT EXISTS verifiers (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    source TEXT NOT NULL,
    expected TEXT NOT NULL,
    depends_on TEXT NOT NULL,
    last_run TEXT,
    last_status TEXT,
    last_error TEXT,
    FOREIGN KEY (claim_id) REFERENCES claims (id),
    FOREIGN KEY (last_run) REFERENCES runs (id)
);

CREATE TABLE IF NOT EXISTS concepts (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_run TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (created_run) REFERENCES runs (id)
);

CREATE TABLE IF NOT EXISTS concept_evidence (
    concept_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    PRIMARY KEY (concept_id, claim_id),
    FOREIGN KEY (concept_id) REFERENCES concepts (id),
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

-- FTS5 over claims.text, kept in sync by triggers on insert/update/delete.
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5 (
    text,
    content='claims',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS claims_fts_ai AFTER INSERT ON claims BEGIN
    INSERT INTO claims_fts (rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS claims_fts_ad AFTER DELETE ON claims BEGIN
    INSERT INTO claims_fts (claims_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS claims_fts_au AFTER UPDATE ON claims BEGIN
    INSERT INTO claims_fts (claims_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO claims_fts (rowid, text) VALUES (new.rowid, new.text);
END;

-- FTS5 over concepts.title || body, kept in sync by triggers on insert/update/delete.
CREATE VIRTUAL TABLE IF NOT EXISTS concepts_fts USING fts5 (
    title,
    body,
    content='concepts',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS concepts_fts_ai AFTER INSERT ON concepts BEGIN
    INSERT INTO concepts_fts (rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS concepts_fts_ad AFTER DELETE ON concepts BEGIN
    INSERT INTO concepts_fts (concepts_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS concepts_fts_au AFTER UPDATE ON concepts BEGIN
    INSERT INTO concepts_fts (concepts_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body);
    INSERT INTO concepts_fts (rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;
"""


def apply_schema(conn) -> None:
    """Apply the DDL and stamp schema_version=1, once. Idempotent."""
    conn.executescript(DDL)
    row = conn.execute('SELECT version FROM schema_version').fetchone()
    if row is None:
        conn.execute('INSERT INTO schema_version (version) VALUES (?)', (SCHEMA_VERSION,))
    conn.commit()
