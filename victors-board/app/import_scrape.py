#!/usr/bin/env python3
"""Import a scraper archive (threads.json) into the board's SQLite database.

Usage:
    python import_scrape.py path/to/scrape_output/threads.json

Safe to re-run: messages already imported (matched by their old Boards2Go id)
are skipped, so you can re-scrape and re-import to pick up anything new.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sanitize import sanitize_html

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", APP_DIR / "data"))
DB_PATH = DATA_DIR / "board.db"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    threads_file = Path(sys.argv[1])
    data = json.loads(threads_file.read_text())
    messages = data.get("messages", {})
    if not messages:
        sys.exit("No messages found in that file.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript((APP_DIR / "schema.sql").read_text())

    existing = {row["legacy_id"] for row in
                db.execute("SELECT legacy_id FROM messages WHERE legacy_id IS NOT NULL")}

    # Sort by date (undated messages last, in id order) so parents usually
    # come before children; a second pass fixes any remaining links.
    def sort_key(item):
        mid, m = item
        date = m.get("date") or "9999"
        num = int(mid) if str(mid).isdigit() else 0
        return (date, num)

    fallback_time = datetime.now().isoformat(timespec="seconds")
    id_map = {}     # legacy id -> new db id
    inserted = 0
    skipped = 0

    ordered = sorted(messages.items(), key=sort_key)
    for legacy_id, m in ordered:
        legacy_id = str(legacy_id)
        if legacy_id in existing:
            row = db.execute("SELECT id FROM messages WHERE legacy_id = ?",
                             (legacy_id,)).fetchone()
            id_map[legacy_id] = row["id"]
            skipped += 1
            continue
        subject = (m.get("subject") or "").strip() or "(no subject)"
        author = (m.get("author") or "").strip() or "unknown"
        body = sanitize_html(m.get("body_html") or "")
        created = m.get("date") or fallback_time
        cur = db.execute(
            "INSERT INTO messages (thread_id, parent_id, subject, body, is_legacy,"
            " author_name, created_at, legacy_id, legacy_url)"
            " VALUES (NULL, NULL, ?, ?, 1, ?, ?, ?, ?)",
            (subject, body or None, author, created, legacy_id, m.get("url")))
        id_map[legacy_id] = cur.lastrowid
        inserted += 1

    # Second pass: wire up parent links now that every message has a db id.
    for legacy_id, m in ordered:
        parent_legacy = m.get("parent_id")
        if parent_legacy and str(parent_legacy) in id_map:
            db.execute("UPDATE messages SET parent_id = ? WHERE id = ?",
                       (id_map[str(parent_legacy)], id_map[str(legacy_id)]))

    # Third pass: set thread_id (root of each message's parent chain).
    def find_root(db_id, parents):
        seen = set()
        while parents.get(db_id) and db_id not in seen:
            seen.add(db_id)
            db_id = parents[db_id]
        return db_id

    parents = {row["id"]: row["parent_id"] for row in
               db.execute("SELECT id, parent_id FROM messages")}
    for db_id in parents:
        db.execute("UPDATE messages SET thread_id = ? WHERE id = ?",
                   (find_root(db_id, parents), db_id))

    db.commit()
    total = db.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
    roots = db.execute(
        "SELECT COUNT(*) c FROM messages WHERE parent_id IS NULL").fetchone()["c"]
    db.close()
    print(f"Imported {inserted} messages ({skipped} already present).")
    print(f"Board now has {total} messages in {roots} threads -> {DB_PATH}")


if __name__ == "__main__":
    main()
