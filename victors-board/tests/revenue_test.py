"""Keeping the lights on: the tip link, the Amazon tag and the tickets link
are all off until the environment sets them, and each does only its one
thing when it is on. Run from anywhere:

    python3 victors-board/tests/revenue_test.py
"""
import os, re, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="rv_")
for k in ("TIP_URL", "AMAZON_TAG", "TICKETS_URL"):
    os.environ.pop(k, None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
import postmarkup
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    db.execute("INSERT INTO users (handle, password_hash, created_at) VALUES (?, ?, ?)",
               ("Rich", generate_password_hash("pw"), appmod.now_utc_iso()))
    db.commit()
c = appmod.app.test_client()
c.post("/login", data={"handle": "Rich", "password": "pw"})
BOOK = "https://www.amazon.com/dp/0345337662"
TAGGED = "https://www.amazon.com/dp/0345337662?ref=x&tag=somebody-20"
c.post("/post", data={"subject": "the book", "body": "read this %s and this %s and https://mgoblog.com/" % (BOOK, TAGGED)},
       follow_redirects=True)
with appmod.app.app_context():
    mid = appmod.get_db().execute("SELECT id FROM messages WHERE subject='the book'").fetchone()["id"]

# --- off: nothing shows, links untouched
home = c.get("/").get_data(as_text=True)
page = c.get("/message/%d" % mid).get_data(as_text=True)
if "Buy the server a beer" in home or "Amazon Associate" in home:
    fails.append("footer shows the tip or the disclosure with nothing set")
if 'href="%s"' % BOOK not in page or "tag=victors-20" in page:
    fails.append("an Amazon link was touched with no tag set")

# --- on
appmod.TIP_URL = "https://ko-fi.com/victorsboard"
appmod.TICKETS_URL = "https://vividseats.example/aff/victors"
postmarkup.AMAZON_TAG = "victors-20"
home = c.get("/").get_data(as_text=True)
page = c.get("/message/%d" % mid).get_data(as_text=True)
if 'href="https://ko-fi.com/victorsboard"' not in home or "Buy the server a beer" not in home:
    fails.append("no tip link in the footer")
if "As an Amazon Associate" not in home:
    fails.append("no disclosure in the footer")
hrefs = re.findall(r'href="([^"]+)"', page)
if "https://www.amazon.com/dp/0345337662?tag=victors-20" not in hrefs:
    fails.append("the plain Amazon link did not get the tag: %s" % [h for h in hrefs if "amazon" in h])
if "https://www.amazon.com/dp/0345337662?ref=x&amp;tag=victors-20" not in page:
    fails.append("somebody else's tag was not replaced")
if ">%s<" % BOOK not in page:
    fails.append("the link text changed")
if 'href="https://mgoblog.com/"' not in page:
    fails.append("a non-Amazon link was touched")
# the stored post is untouched: the tag is applied on the way out
with appmod.app.app_context():
    body = appmod.get_db().execute("SELECT body FROM messages WHERE id=?", (mid,)).fetchone()["body"]
if "victors-20" in body:
    fails.append("the tag was written into the post itself")

# the tickets link on the week line, with a pick 'em in hand
with appmod.app.test_request_context("/"):
    appmod.g._database = None
    from flask import render_template
    try:
        html = render_template("index.html", threads=[], page=1, pages=1, board_name="main",
                               gameday=None, pod=None, bowl=None, pickem={
                                   "kind": "pre", "mid": mid, "matchup": "Michigan vs UCLA",
                                   "day": "Saturday", "when": "Sat 3:30 PM EST on CBS",
                                   "text": "Pick 'em is open — 12 picks in"})
        if 'href="https://vividseats.example/aff/victors"' not in html or ">tickets</a>" not in html:
            fails.append("no tickets link on the week line")
        if 'rel="nofollow noopener sponsored"' not in html:
            fails.append("the tickets link is not marked sponsored")
    except Exception as e:   # the template wants something this harness didn't pass
        fails.append("could not render the week line: %r" % e)

# off again, in the same process
appmod.TIP_URL = appmod.TICKETS_URL = None
postmarkup.AMAZON_TAG = None
home = c.get("/").get_data(as_text=True)
if "Buy the server a beer" in home:
    fails.append("the tip link stayed after unsetting")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
