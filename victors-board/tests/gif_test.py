"""GIF page links show the GIF. Giphy's page carries the id, so the picture
is built at render time. Tenor's page is read once at post time for its
picture (og:image), best effort. Run from anywhere:

    python3 victors-board/tests/gif_test.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="gif_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import postmarkup
import app as appmod
from werkzeug.security import generate_password_hash

fails = []
R = postmarkup.render_post

# --- Giphy: page link -> its GIF, link still to the page
for page, gid in (("https://giphy.com/gifs/michigan-football-go-blue-xT9IgzoKnwFNmISR8I", "xT9IgzoKnwFNmISR8I"),
                  ("https://giphy.com/gifs/l0HlNaQ6gWfllcjDO", "l0HlNaQ6gWfllcjDO"),
                  ("https://www.giphy.com/gifs/a-b-c-3o7TKSjRrfIPjeiVyM?utm=x", "3o7TKSjRrfIPjeiVyM")):
    out = R("look " + page)
    if f'<img src="https://media.giphy.com/media/{gid}/giphy.gif"' not in out or f'href="{page}"' not in out:
        fails.append("giphy page not embedded: %s -> %s" % (page, out))
if "<img" in R("https://giphy.com/explore/michigan"):
    fails.append("a non-GIF giphy page was embedded")
if '<img src="https://media.giphy.com/media/abc/giphy.gif"' not in R("https://media.giphy.com/media/abc/giphy.gif"):
    fails.append("a plain giphy media link stopped embedding")

# --- Tenor: the page is read once at post time
calls = []
def fake_fetch(url):
    calls.append(url)
    if "fails" in url:
        raise RuntimeError("down")
    if "nopic" in url:
        return "<html><head><title>x</title></head></html>"
    return ('<html><head><meta property="og:image" content="https://media1.tenor.com/m/abcDEF/go-blue.gif">'
            '<meta property="og:title" content="Go Blue GIF"></head></html>')
postmarkup._fetch_page = fake_fetch

body = "hail https://tenor.com/view/michigan-go-blue-gif-27345678 yes"
got = postmarkup.resolve_gif_pages(body)
if got != "hail https://media1.tenor.com/m/abcDEF/go-blue.gif yes":
    fails.append("tenor page not swapped: %r" % got)
if calls != ["https://tenor.com/view/michigan-go-blue-gif-27345678"]:
    fails.append("fetched the wrong thing: %r" % calls)
if '<img src="https://media1.tenor.com/m/abcDEF/go-blue.gif"' not in R(got):
    fails.append("the swapped tenor picture does not render")
# language-prefixed pages, and a page with a query string
got = postmarkup.resolve_gif_pages("https://tenor.com/en-GB/view/wolverine-gif-123?x=1 and https://tenor.com/es/view/a-gif-9")
if got != "https://media1.tenor.com/m/abcDEF/go-blue.gif and https://media1.tenor.com/m/abcDEF/go-blue.gif":
    fails.append("tenor variants: %r" % got)
# failures keep the link as typed
for raw in ("https://tenor.com/view/fails-gif-1", "https://tenor.com/view/nopic-gif-2"):
    if postmarkup.resolve_gif_pages(raw) != raw:
        fails.append("a failed lookup did not keep the link: %r" % raw)
# text without tenor never fetches; tenor's own short .gif links already embed
n = len(calls)
postmarkup.resolve_gif_pages("nothing to see https://giphy.com/gifs/x-abc")
if len(calls) != n:
    fails.append("fetched for a post with no tenor link")
if "<img" not in R("https://tenor.com/bXJ1T.gif"):
    fails.append("a tenor short .gif link does not embed")

# --- Google share links: followed to the image viewer, whose address carries the picture
trails = {
    "https://share.google/f3FTdws9AVuBbngik": [
        "https://share.google/f3FTdws9AVuBbngik",
        "https://www.google.com/imgres?imgurl=https%3A%2F%2Fmedia.tenor.com%2Fxyz%2Fharbaugh.gif&imgrefurl=https%3A%2F%2Ftenor.com%2Fview%2Fh-gif-1&tbnid=abc"],
    "https://images.app.goo.gl/AbC123": [
        "https://images.app.goo.gl/AbC123", "https://tenor.com/view/wolverine-gif-77"],
    "https://share.google/togiphy": [
        "https://share.google/togiphy", "https://giphy.com/gifs/go-blue-l0HlNaQ6gWfllcjDO"],
    "https://share.google/nothing": [
        "https://share.google/nothing", "https://www.google.com/search?q=michigan"],
    "https://share.google/down": None,
}
def fake_follow(url):
    t = trails.get(url)
    if t is None:
        raise RuntimeError("down")
    return t
postmarkup._follow = fake_follow
cases = {
    "see https://share.google/f3FTdws9AVuBbngik ok": "see https://media.tenor.com/xyz/harbaugh.gif ok",
    "https://images.app.goo.gl/AbC123": "https://media1.tenor.com/m/abcDEF/go-blue.gif",
    "https://share.google/togiphy": "https://giphy.com/gifs/go-blue-l0HlNaQ6gWfllcjDO",
    "https://share.google/nothing": "https://share.google/nothing",
    "https://share.google/down": "https://share.google/down",
}
for raw, want in cases.items():
    got = postmarkup.resolve_gif_pages(raw)
    if got != want:
        fails.append("google share: %r -> %r, wanted %r" % (raw, got, want))
if "<img" not in R(postmarkup.resolve_gif_pages("https://share.google/f3FTdws9AVuBbngik")):
    fails.append("the resolved google share link does not render as a picture")

# --- through the board: a post with a Tenor page link lands with the picture
appmod.app.config["TESTING"] = True
with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    db.execute("INSERT INTO users (handle, password_hash, created_at) VALUES (?, ?, ?)",
               ("suede", generate_password_hash("pw"), appmod.now_utc_iso()))
    db.commit()
c = appmod.app.test_client()
c.post("/login", data={"handle": "suede", "password": "pw"})
c.post("/post", data={"subject": "boomer test", "body": "https://tenor.com/view/old-man-gif-555"}, follow_redirects=True)
with appmod.app.app_context():
    saved = appmod.get_db().execute("SELECT id, body FROM messages ORDER BY id DESC LIMIT 1").fetchone()
if saved["body"] != "https://media1.tenor.com/m/abcDEF/go-blue.gif":
    fails.append("the posted body kept the page link: %r" % saved["body"])
page = c.get("/message/%d" % saved["id"]).get_data(as_text=True)
if '<img src="https://media1.tenor.com/m/abcDEF/go-blue.gif"' not in page:
    fails.append("the post does not show the GIF")
# and the edit path
c.post("/edit/%d" % saved["id"], data={"subject": "boomer test", "body": "again https://tenor.com/view/x-gif-7"}, follow_redirects=True)
with appmod.app.app_context():
    edited = appmod.get_db().execute("SELECT body FROM messages WHERE id = ?", (saved["id"],)).fetchone()["body"]
if edited != "again https://media1.tenor.com/m/abcDEF/go-blue.gif":
    fails.append("the edit path kept the page link: %r" % edited)

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
