"""Pinning: any post, a reply included. The header links to the pinned post
itself; a thread's first post still pins the way it always did.

Run from anywhere:  python3 victors-board/tests/pin_test.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="pin_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    for h in ("Nikos", "danny"):
        db.execute("INSERT INTO users (handle, password_hash, created_at) VALUES (?, ?, ?)",
                   (h, generate_password_hash("pw"), appmod.now_utc_iso()))
    db.execute("UPDATE users SET is_admin = 1 WHERE handle = 'Nikos'")
    db.commit()


def client(handle):
    c = appmod.app.test_client()
    c.post("/login", data={"handle": handle, "password": "pw"}, follow_redirects=True)
    return c


nikos, danny = client("Nikos"), client("danny")


def pinned_row(c):
    """The header's pinned line only (the board below links to every post)."""
    page = c.get("/").get_data(as_text=True)
    if 'class="pinned-row"' not in page:
        return ""
    start = page.index('class="pinned-row"')
    return page[start:page.index("</p>", start)]

danny.post("/post", data={"subject": "What should Bacon title his book?*", "body": ""}, follow_redirects=True)
with appmod.app.app_context():
    root = appmod.get_db().execute("SELECT id FROM messages ORDER BY id DESC LIMIT 1").fetchone()["id"]
danny.post("/post/%d" % root, data={"subject": "The Book of Moron (nm)", "body": ""}, follow_redirects=True)
with appmod.app.app_context():
    reply = appmod.get_db().execute("SELECT id, parent_id FROM messages ORDER BY id DESC LIMIT 1").fetchone()
    if reply["parent_id"] != root:
        fails.append("the reply did not land under the thread")
    reply = reply["id"]

# the reply's page offers the pin to an admin, not to a member
page = nikos.get("/message/%d" % reply).get_data(as_text=True)
if "Pin to top" not in page:
    fails.append("no pin button on a reply for the admin")
if "Pin to top" in danny.get("/message/%d" % reply).get_data(as_text=True):
    fails.append("a member sees the pin button")
if danny.post("/admin/pin/%d" % reply).status_code not in (302, 403):
    fails.append("a member could pin")

# pin the reply: the header links to the reply itself, on every page
r = nikos.post("/admin/pin/%d" % reply, follow_redirects=True)
home = nikos.get("/").get_data(as_text=True)
if ('href="/message/%d">The Book of Moron (nm)</a>' % reply) not in pinned_row(nikos):
    fails.append("the header does not link to the pinned reply")
if "Pinned to the top of the board." not in r.get_data(as_text=True):
    fails.append("no confirmation after pinning")
if "Unpin" not in nikos.get("/message/%d" % reply).get_data(as_text=True):
    fails.append("the pinned reply does not offer Unpin")
if "📌" not in nikos.get("/").get_data(as_text=True) and "&#128204;" not in home:
    fails.append("no pin mark on the board")

# a logged-out reader sees it too
if ('href="/message/%d">' % reply) not in pinned_row(appmod.app.test_client()):
    fails.append("readers do not see the pinned reply")

# unpin; and the thread's first post still pins as before
nikos.post("/admin/pin/%d" % reply)
if ('href="/message/%d">' % reply) in pinned_row(nikos):
    fails.append("unpin did not take")
nikos.post("/admin/pin/%d" % root)
if ('href="/message/%d">What should Bacon title his book?*</a>' % root) not in pinned_row(nikos):
    fails.append("the thread's first post no longer pins")
if nikos.post("/admin/pin/999999").status_code != 404:
    fails.append("pinning a missing post is not a 404")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
