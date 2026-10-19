"""'Is the site slow?' gets an answer with numbers: /admin/latency, and a
robots.txt that keeps crawlers out of the pages that aren't content.

Run from anywhere:  python3 victors-board/tests/latency_test.py
"""
import json, os, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="lt_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    for h, admin in (("Nikos", 1), ("Ken", 0)):
        db.execute("INSERT INTO users (handle, password_hash, created_at, is_admin)"
                   " VALUES (?, ?, ?, ?)",
                   (h, generate_password_hash("pw"), appmod.now_utc_iso(), admin))
    db.commit()


def client(handle):
    c = appmod.app.test_client()
    c.post("/login", data={"handle": handle, "password": "pw"}, follow_redirects=True)
    return c


nik, ken, anon = client("Nikos"), client("Ken"), appmod.app.test_client()
for _ in range(3):
    anon.get("/")
anon.get("/stats")
anon.get("/static/style.css")

if ken.get("/admin/latency").status_code != 403 or anon.get("/admin/latency").status_code != 403:
    fails.append("the latency check is not admin-only")
r = nik.get("/admin/latency")
if r.status_code != 200 or not r.mimetype.startswith("application/json"):
    fails.append("the latency check did not answer JSON")
out = json.loads(r.get_data(as_text=True))
for k in ("requests", "p50_ms", "p95_ms", "max_ms", "slowest", "by_route", "caches", "threads"):
    if k not in out:
        fails.append("latency report lacks %r" % k)
if out["requests"] < 4:
    fails.append("the report counted %d requests, expected the pages we loaded" % out["requests"])
if any(s["path"].startswith("/static") for s in out["slowest"]):
    fails.append("static files are being timed")
routes = {r_["route"] for r_ in out["by_route"]}
if "/" not in routes or "/stats" not in routes:
    fails.append("by_route is missing the pages we loaded: %s" % routes)
if set(out["caches"]) != {"scoreboard", "week_game", "slippery_rock", "pod", "schedule"}:
    fails.append("cache states missing: %s" % list(out["caches"]))
if not all(isinstance(s["ms"], int) and s["ms"] >= 0 for s in out["slowest"]):
    fails.append("timings are not whole milliseconds")
# ids are folded so /message/1 and /message/2 are one route
nik.post("/post", data={"subject": "a*", "body": ""}, follow_redirects=True)
anon.get("/message/1")
out = json.loads(nik.get("/admin/latency").get_data(as_text=True))
if not any(r_["route"] == "/message/N" for r_ in out["by_route"]):
    fails.append("message pages are not folded into one route")

# robots.txt: public, plain text, keeps crawlers off the non-content pages
r = anon.get("/robots.txt")
if r.status_code != 200 or not r.mimetype.startswith("text/plain"):
    fails.append("robots.txt is not served as plain text")
body = r.get_data(as_text=True)
for want in ("Disallow: /search", "Disallow: /admin", "Disallow: /mcp", "Crawl-delay: 5"):
    if want not in body:
        fails.append("robots.txt lacks %r" % want)
if "Disallow: /message" in body or "Disallow: /\n" in body:
    fails.append("robots.txt hides the board's content")
# and fetching it isn't a pageview
with appmod.app.app_context():
    before = appmod.get_db().execute("SELECT pageviews FROM traffic ORDER BY day DESC LIMIT 1").fetchone()[0]
anon.get("/robots.txt")
with appmod.app.app_context():
    after = appmod.get_db().execute("SELECT pageviews FROM traffic ORDER BY day DESC LIMIT 1").fetchone()[0]
if after != before:
    fails.append("robots.txt counted as a pageview")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
