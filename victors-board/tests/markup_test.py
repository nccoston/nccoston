"""Post metadata is in the page as data, not just as words: a <time datetime>
on every byline and the member in data-author, so a page can be read by a
program — or rescued, if a host ever dies again — without parsing prose.

Run from anywhere:  python3 victors-board/tests/markup_test.py
"""
import os, re, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="mk_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []

with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    for h in ("Nikos", "Ken"):
        db.execute("INSERT INTO users (handle, password_hash, created_at)"
                   " VALUES (?, ?, ?)", (h, generate_password_hash("pw"),
                                         appmod.now_utc_iso()))
    db.commit()


def client(handle):
    c = appmod.app.test_client()
    c.post("/login", data={"handle": handle, "password": "pw"}, follow_redirects=True)
    return c


nik, ken = client("Nikos"), client("Ken")
# a subject that reads like a byline — the thing that broke a parser
nik.post("/post", data={"subject": "Posted on Friday by a guy who should know better",
                        "body": "the words are not the data"}, follow_redirects=True)
ken.post("/post", data={"subject": "a costume*", "body": "", "alias": "Obitman"},
         follow_redirects=True)
with appmod.app.app_context():
    rows = appmod.get_db().execute(
        "SELECT id, created_at FROM messages ORDER BY id").fetchall()
first, second = rows[0], rows[1]

anon = appmod.app.test_client()
home = anon.get("/").get_data(as_text=True)
page = anon.get("/message/%d" % first["id"]).get_data(as_text=True)

# every byline carries a machine-readable time, UTC, unambiguous
times = re.findall(r'<time datetime="([^"]+)">', home)
if len(times) < 2:
    fails.append("the front page bylines lack <time datetime>: %d found" % len(times))
for t in times:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", t):
        fails.append("datetime is not UTC ISO: %r" % t)
        break
if ('<time datetime="%sZ">' % first["created_at"]) not in home:
    fails.append("the datetime does not match the stored timestamp")
if '<p class="byline">Posted on <time datetime="%sZ">' % first["created_at"] not in page:
    fails.append("the message page byline lacks <time datetime>")

# the member is an attribute, on plain posts and alias posts alike
if 'data-author="Nikos">Nikos</b>' not in home:
    fails.append("a plain post lacks data-author")
if 'data-author="Ken" data-real="Ken"' not in home or ">Obitman</b>" not in home:
    fails.append("an alias post lacks data-author for the member")

# the byline-shaped subject is just a subject
if home.count("Posted on Friday by a guy") != 1:
    fails.append("the decoy subject is missing or duplicated")

# search and the hall of fame carry the same markup
s = anon.get("/search?q=costume").get_data(as_text=True)
if '<time datetime="' not in s or 'data-author="Ken"' not in s:
    fails.append("search results lack the metadata")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
