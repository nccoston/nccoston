"""Replies to you: a count beside your handle for replies to your posts you
haven't opened (last week), a page listing them, "seen them all", and the
per-device off switch in Settings. Run from anywhere:

    python3 victors-board/tests/replies_test.py
"""
import os, re, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="rp_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    for h in ("Karl", "Rich", "danny"):
        db.execute("INSERT INTO users (handle, password_hash, created_at) VALUES (?, ?, ?)",
                   (h, generate_password_hash("pw"), appmod.now_utc_iso()))
    db.commit()


def client(handle):
    c = appmod.app.test_client()
    c.post("/login", data={"handle": handle, "password": "pw"}, follow_redirects=True)
    return c


def nav(c, path="/"):
    page = c.get(path).get_data(as_text=True)
    m = re.search(r'\[ Karl(.*?) \]', page, re.S)
    return (m.group(1) if m else None), page


karl, rich, danny = client("Karl"), client("Rich"), client("danny")

# nothing yet: no count, nothing in the brackets but the handle
inside, page = nav(karl)
if inside != "":
    fails.append("a count shows with no replies: %r" % inside)

# Karl posts; Rich and danny reply; Karl replies to himself (doesn't count)
karl.post("/post", data={"subject": "Is Whitt gone yet?*", "body": ""}, follow_redirects=True)
with appmod.app.app_context():
    root = appmod.get_db().execute("SELECT id FROM messages ORDER BY id DESC LIMIT 1").fetchone()["id"]
rich.post("/post/%d" % root, data={"subject": "No*", "body": ""}, follow_redirects=True)
danny.post("/post/%d" % root, data={"subject": "Soon*", "body": ""}, follow_redirects=True)
karl.post("/post/%d" % root, data={"subject": "Re: Is Whitt gone yet?", "body": "asking for a friend"}, follow_redirects=True)
with appmod.app.app_context():
    ids = [r["id"] for r in appmod.get_db().execute("SELECT id FROM messages WHERE parent_id = ? ORDER BY id", (root,))]
rich_reply, danny_reply = ids[0], ids[1]

inside, page = nav(karl)
if not inside or 'class="replies-count"' not in inside or ">2</a>" not in inside:
    fails.append("the count should be 2: %r" % inside)
if 'href="/replies"' not in page:
    fails.append("the count does not link to the page")
# other pages carry it too; readers and other members don't see Karl's
if ">2</a>" not in karl.get("/stats").get_data(as_text=True):
    fails.append("the count is missing on other pages")
if 'class="replies-count"' in rich.get("/").get_data(as_text=True):
    fails.append("Rich sees a count he hasn't earned")

# the page lists both, newest first, with who and where
rp = karl.get("/replies").get_data(as_text=True)
if rp.index("Soon*") > rp.index("No*"):
    fails.append("replies are not newest first")
if "danny" not in rp or "Rich" not in rp or "Is Whitt gone yet?" not in rp:
    fails.append("the page is missing who or where")
if "Seen them all" not in rp:
    fails.append("no way to clear them all")

# opening one marks it read: the count drops
karl.get("/message/%d" % rich_reply)
inside, _ = nav(karl)
if ">1</a>" not in (inside or ""):
    fails.append("opening a reply did not drop the count: %r" % inside)

# seen them all: count gone, page empty
karl.post("/replies/seen", follow_redirects=True)
inside, _ = nav(karl)
if inside != "":
    fails.append("seen-them-all left a count: %r" % inside)
if "Nothing new" not in karl.get("/replies").get_data(as_text=True):
    fails.append("the page is not empty after seen-them-all")

# a reply older than the window does not count
with appmod.app.app_context():
    db = appmod.get_db()
    db.execute("INSERT INTO messages (thread_id, parent_id, subject, body, author_name, user_id, created_at)"
               " VALUES (?, ?, 'ancient*', '', 'Rich', 2, '2026-01-01T00:00:00')", (root, root))
    db.commit()
inside, _ = nav(karl)
if inside != "":
    fails.append("an old reply counted: %r" % inside)

# off by default: the count is in the page but hidden until a member turns it on in Settings
st = karl.get("/settings").get_data(as_text=True)
if 'id="set-replies"' not in st or 'data-replies-choice="on"' not in st:
    fails.append("Settings lacks the replies switch")
if 'localStorage.getItem("replies") === "on"' not in page or 'dataset.replies = "on"' not in page:
    fails.append("the head script does not honor the on switch")
css = open(Path(appmod.__file__).parent / "static" / "style.css").read()
if ".replies-count { display: none; }" not in css or ':root[data-replies="on"] .replies-count { display: inline; }' not in css:
    fails.append("the count is not hidden by default and shown when on")

# readers without an account: no page
if appmod.app.test_client().get("/replies").status_code == 200:
    fails.append("the replies page is open to readers")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
