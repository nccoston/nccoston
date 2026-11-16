"""'nm' in the message box: the server keeps it out of the body and marks
the subject, on a new post and on an edit. A real message is left alone.
Run from anywhere:

    python3 victors-board/tests/nm_test.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="nm_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    db.execute("INSERT INTO users (handle, password_hash, created_at) VALUES (?, ?, ?)",
               ("AStep313", generate_password_hash("pw"), appmod.now_utc_iso()))
    db.commit()
c = appmod.app.test_client()
c.post("/login", data={"handle": "AStep313", "password": "pw"})

def stored(subject):
    with appmod.app.app_context():
        return appmod.get_db().execute(
            "SELECT id, subject, body FROM messages WHERE subject LIKE ? ORDER BY id DESC LIMIT 1",
            (subject + "%",)).fetchone()

cases = [   # subject typed, body typed -> subject stored, body stored
    ("Can anyone steelman the case?", "nm", "Can anyone steelman the case?*", None),
    ("Rule 2", "(nm)", "Rule 2*", None),
    ("already marked*", "nm", "already marked*", None),
    ("just a star", "*", "just a star*", None),
    ("a real message", "nm, that's what I said", "a real message", "nm, that's what I said"),
    ("dots", "...", "dots", "..."),
]
for subj, body, want_s, want_b in cases:
    c.post("/post", data={"subject": subj, "body": body}, follow_redirects=True)
    row = stored(subj.rstrip("*"))
    if row is None or row["subject"] != want_s or row["body"] != want_b:
        fails.append("%r / %r stored as %r / %r" % (subj, body, row and row["subject"], row and row["body"]))

# the same on an edit
row = stored("a real message")
c.post("/edit/%d" % row["id"], data={"subject": "a real message", "body": "nm"}, follow_redirects=True)
row = stored("a real message")
if row["subject"] != "a real message*" or row["body"] is not None:
    fails.append("edit to nm stored as %r / %r" % (row["subject"], row["body"]))

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
