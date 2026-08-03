CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    handle        TEXT UNIQUE COLLATE NOCASE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    is_banned     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY,
    thread_id   INTEGER,                          -- id of the root message
    parent_id   INTEGER REFERENCES messages(id),  -- NULL for thread roots
    subject     TEXT NOT NULL,
    body        TEXT,           -- HTML for imported legacy posts (pre-sanitized),
                                -- plain text for new posts
    is_legacy   INTEGER NOT NULL DEFAULT 0,
    image_url   TEXT,
    author_name TEXT NOT NULL,
    user_id     INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL,  -- ISO 8601
    legacy_id   TEXT UNIQUE,    -- Boards2Go message id, for imported posts
    legacy_url  TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_id);
CREATE INDEX IF NOT EXISTS idx_messages_root
    ON messages(created_at DESC) WHERE parent_id IS NULL;

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
