"""Keeping the lights on: the tip link, the Amazon tag and the tickets link
are all off until the environment sets them, and each does only its one
thing when it is on. Run from anywhere:

    python3 victors-board/tests/revenue_test.py
"""
import os, re, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="rv_")
for k in ("KOFI_URL", "TIP_URL", "AMAZON_ASSOCIATE_TAG", "AMAZON_TAG",
          "TICKETS_AFFILIATE_URL", "TICKETS_URL", "TICKETS_PROGRAM_NAME"):
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
THEIRS = "https://www.amazon.com/dp/0345337662?ref=x&tag=somebody-20"
SHORT = "https://a.co/d/abc123"
LOOKALIKE = "https://amazon.com.evil.example/dp/1"
body = "read this %s and %s and %s and %s and https://mgoblog.com/" % (BOOK, THEIRS, SHORT, LOOKALIKE)
c.post("/post", data={"subject": "the book", "body": body}, follow_redirects=True)
with appmod.app.app_context():
    mid = appmod.get_db().execute("SELECT id FROM messages WHERE subject='the book'").fetchone()["id"]

# --- off: nothing shows, links untouched, pages identical
home_off = c.get("/").get_data(as_text=True)
page_off = c.get("/message/%d" % mid).get_data(as_text=True)
for word in ("Server cost", "Amazon Associate", "affiliate link"):
    if word in home_off:
        fails.append("footer shows %r with nothing set" % word)
if 'href="%s"' % BOOK not in page_off or "tag=victors" in page_off or "sponsored" in page_off:
    fails.append("an Amazon link was touched with no tag set")

# --- only the tip link
appmod.TIP_URL = "https://ko-fi.com/victorsboard"
home = c.get("/").get_data(as_text=True)
if 'href="https://ko-fi.com/victorsboard" rel="noopener" target="_blank">Server cost</a>' not in home:
    fails.append("no tip link in the footer, or the wrong words")
if "Amazon Associate" in home or "affiliate link" in home:
    fails.append("the tip link brought company")
if c.get("/message/%d" % mid).get_data(as_text=True).count("amazon") != page_off.count("amazon"):
    fails.append("the tip link changed a post")

# --- the Amazon tag
postmarkup.AMAZON_TAG = "victors0ff-20"
home = c.get("/").get_data(as_text=True)
page = c.get("/message/%d" % mid).get_data(as_text=True)
if "As an Amazon Associate I earn from qualifying purchases." not in home:
    fails.append("the disclosure sentence is missing or not exact")
if ('<a href="https://www.amazon.com/dp/0345337662?tag=victors0ff-20" rel="sponsored nofollow noopener" target="_blank">%s</a>' % BOOK) not in page:
    fails.append("the product link did not get the tag, the rel, and the untouched text: %s"
                 % [h for h in re.findall(r'<a href="[^"]*amazon[^"]*"[^>]*>', page)])
if 'href="https://www.amazon.com/dp/0345337662?ref=x&amp;tag=somebody-20" rel="nofollow noopener"' not in page:
    fails.append("a link that already carried a tag was changed")
for untouched in (SHORT, LOOKALIKE, "https://mgoblog.com/"):
    if ('href="%s" rel="nofollow noopener"' % untouched) not in page:
        fails.append("touched a link it should not have: %s" % untouched)
with appmod.app.app_context():
    stored = appmod.get_db().execute("SELECT body FROM messages WHERE id=?", (mid,)).fetchone()["body"]
if "victors0ff" in stored:
    fails.append("the tag was written into the post itself")
rss = c.get("/rss.xml").get_data(as_text=True)
if "victors0ff" in rss:
    fails.append("the tag leaked into the RSS feed")
if "amazon.com/dp/0345337662" not in rss:
    fails.append("the feed lost the link altogether")

# --- the tickets link, with and without the program's name
appmod.TICKETS_URL = "https://vividseats.example/aff/victors"
home = c.get("/").get_data(as_text=True)
if '<a href="https://vividseats.example/aff/victors" rel="sponsored noopener" target="_blank">Tickets (affiliate link)</a>' not in home:
    fails.append("no tickets link, or the wrong label without a name")
appmod.TICKETS_NAME = "Vivid Seats"
home = c.get("/").get_data(as_text=True)
if ">Tickets on Vivid Seats (affiliate link)</a>" not in home:
    fails.append("the tickets label does not carry the program's name")
# and on the week line, when there is one
with appmod.app.test_request_context("/"):
    from flask import render_template
    try:
        html = render_template("index.html", threads=[], page=1, pages=1, board_name="main",
                               gameday=None, pod=None, bowl=None, pickem={
                                   "kind": "pre", "mid": mid, "matchup": "Michigan vs UCLA",
                                   "day": "Saturday", "when": "Sat 3:30 PM EST on CBS",
                                   "text": "Pick 'em is open — 12 picks in"})
        if 'href="https://vividseats.example/aff/victors" rel="nofollow noopener sponsored" target="_blank">tickets</a>' not in html:
            fails.append("no tickets link on the week line")
    except Exception as e:
        fails.append("could not render the week line: %r" % e)

# --- off again, in the same process
appmod.TIP_URL = appmod.TICKETS_URL = appmod.TICKETS_NAME = None
postmarkup.AMAZON_TAG = None
if c.get("/message/%d" % mid).get_data(as_text=True).count("amazon") != page_off.count("amazon"):
    fails.append("unsetting the tag did not put the links back")
if "Server cost" in c.get("/").get_data(as_text=True):
    fails.append("the tip link stayed after unsetting")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
