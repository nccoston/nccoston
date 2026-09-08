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
    body        TEXT,
    image_url   TEXT,
    author_name TEXT NOT NULL,
    user_id     INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL,  -- ISO 8601
    edited_at   TEXT,
    ip_address  TEXT,           -- shown to admins only
    board       TEXT NOT NULL DEFAULT 'main',  -- 'main' or 'scores'
    image_size  TEXT           -- small/medium/large; NULL = full size
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_id);
CREATE INDEX IF NOT EXISTS idx_messages_root
    ON messages(created_at DESC) WHERE parent_id IS NULL;

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS polls (
    id         INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL UNIQUE REFERENCES messages(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poll_options (
    id      INTEGER PRIMARY KEY,
    poll_id INTEGER NOT NULL REFERENCES polls(id),
    text    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poll_votes (
    id         INTEGER PRIMARY KEY,
    poll_id    INTEGER NOT NULL REFERENCES polls(id),
    option_id  INTEGER NOT NULL REFERENCES poll_options(id),
    user_id    INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(poll_id, user_id)   -- one vote per member, changeable
);

-- Daily traffic counters. Counts only: the visitor table holds a salted
-- daily hash used solely to count uniques, is unlinkable across days,
-- and is pruned as each new day begins. Nothing ties to accounts.
CREATE TABLE IF NOT EXISTS traffic (
    day       TEXT PRIMARY KEY,   -- YYYY-MM-DD board time
    pageviews INTEGER NOT NULL DEFAULT 0,
    uniques   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS traffic_visitors (
    day     TEXT NOT NULL,
    visitor TEXT NOT NULL,
    UNIQUE(day, visitor)
);

-- Cross-device read sync: which message links a member has opened, so
-- blue-vs-purple carries from phone to laptop. Rows for old messages are
-- pruned daily; this is never displayed to anyone, admins included.
CREATE TABLE IF NOT EXISTS message_reads (
    user_id    INTEGER NOT NULL REFERENCES users(id),
    message_id INTEGER NOT NULL REFERENCES messages(id),
    PRIMARY KEY (user_id, message_id)
) WITHOUT ROWID;

-- Hall of Fame nominations: enough votes enshrines a post automatically
CREATE TABLE IF NOT EXISTS hof_votes (
    id         INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id),
    user_id    INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    UNIQUE(message_id, user_id)
);

-- Pick 'em: score-prediction games on the Scores board
CREATE TABLE IF NOT EXISTS games (
    id         INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL UNIQUE REFERENCES messages(id),
    team_a     TEXT NOT NULL,
    team_b     TEXT NOT NULL,
    final_a    INTEGER,       -- NULL until the final score is entered
    final_b    INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_picks (
    id         INTEGER PRIMARY KEY,
    game_id    INTEGER NOT NULL REFERENCES games(id),
    user_id    INTEGER NOT NULL REFERENCES users(id),
    pick_a     INTEGER NOT NULL,
    pick_b     INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(game_id, user_id)   -- one pick per member, changeable until final
);

-- Victard Bowl: one row per member, holding their bests. Written by the
-- game after each game; read by /bowl/leaderboard.
CREATE TABLE IF NOT EXISTS bowl_scores (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id),
    games       INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    losses      INTEGER NOT NULL DEFAULT 0,
    seasons     INTEGER NOT NULL DEFAULT 0,
    best_w      INTEGER NOT NULL DEFAULT 0,   -- best completed season
    best_l      INTEGER NOT NULL DEFAULT 0,
    biggest_win INTEGER NOT NULL DEFAULT 0,   -- margin, in points
    longest_td  INTEGER NOT NULL DEFAULT 0,   -- longest gain, in yards
    most_points INTEGER NOT NULL DEFAULT 0,   -- most scored in one game
    updated_at  TEXT NOT NULL,
    -- a row exists as soon as somebody OPENS the game, with games = 0.
    -- The leaderboard and the standings both filter on games > 0, so
    -- looking and leaving is recorded without putting anyone on a table.
    opens       INTEGER NOT NULL DEFAULT 0,    -- page loads of /bowl
    first_at    TEXT,                          -- first time they opened it
    last_at     TEXT                           -- last open or finished game
);

-- Stadium Guesser: one row per member. Unlike the Bowl, whose season lives
-- in the browser, every round here is scored on the server, so this is the
-- only copy — the same account plays the same career from any device.
CREATE TABLE IF NOT EXISTS stadium_scores (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id),
    games      INTEGER NOT NULL DEFAULT 0,
    rounds     INTEGER NOT NULL DEFAULT 0,
    best       INTEGER NOT NULL DEFAULT 0,   -- best 5-round total, of 25000
    total      INTEGER NOT NULL DEFAULT 0,   -- points across every round
    closest    REAL,                         -- nearest guess ever, in miles
    bullseyes  INTEGER NOT NULL DEFAULT 0,   -- rounds inside 25 miles
    opens      INTEGER NOT NULL DEFAULT 0,
    first_at   TEXT,
    last_at    TEXT,
    updated_at TEXT NOT NULL
);
