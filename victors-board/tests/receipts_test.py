"""The Receipts page: every flag in receipts.json renders as a link to its
post, the season strip has a chip per game, the running total adds up, and
the Fire Kyle count is read live from the board. Run from anywhere:

    python3 victors-board/tests/receipts_test.py
"""
import json, os, re, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="rc_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
data = json.loads((Path(appmod.__file__).parent / "receipts.json").read_text())
ids = [b["id"] for b in data["before"]] + [r["id"] for g in data["games"] for r in g["receipts"]]
if len(ids) != len(set(ids)):
    fails.append("a post is listed twice")

with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    db.execute("INSERT INTO users (handle, password_hash, created_at) VALUES (?, ?, ?)",
               ("suede", generate_password_hash("pw"), appmod.now_utc_iso()))
    db.commit()
c = appmod.app.test_client()

# before anyone has said it: the count is zero and the page still renders
page = c.get("/receipts").get_data(as_text=True)
if 'id="fired">0<' not in page:
    fails.append("the live count did not start at zero")

c.post("/login", data={"handle": "suede", "password": "pw"})
c.post("/post", data={"subject": "Fire Kyle Whittingham. (nm)", "body": ""}, follow_redirects=True)
c.post("/post", data={"subject": "I would fire Kyle Whittingham. (nm)", "body": ""}, follow_redirects=True)
c.post("/post", data={"subject": "Would you fire Kyle Whittingham? (nm)", "body": ""}, follow_redirects=True)
c.post("/post", data={"subject": "nothing to see here*", "body": ""}, follow_redirects=True)
r = c.get("/receipts")
if r.status_code != 200:
    fails.append("the page did not load: %d" % r.status_code)
page = r.get_data(as_text=True)

if "<title>The Receipts</title>" not in page:
    fails.append("no title")
if 'id="fired">3<' not in page:
    fails.append("the live count did not count the three subjects (page says %s)"
                 % re.search(r'id="fired">(\d+)<', page).group(1))
if "the first on " not in page:
    fails.append("the first one's date is missing")
missing = [i for i in ids if ('href="/message/%d"' % i) not in page]
if missing:
    fails.append("receipts without a link to their post: %s" % missing)
chips = re.findall(r'class="chip[^"]*" href="#', page)
if len(chips) != len(data["games"]) + 1:
    fails.append("strip has %d chips for %d games" % (len(chips), len(data["games"])))
for g in data["games"]:
    if ('id="%s"' % g["key"]) not in page:
        fails.append("no section for %s" % g["key"])
total = sum(len(g["receipts"]) for g in data["games"])
if ("&middot; %d running" % total) not in page:
    fails.append("the running total does not reach %d" % total)
wins = sum(1 for g in data["games"] if g["result"] == "W")
losses = sum(1 for g in data["games"] if g["result"] == "L")
if ("%d–%d" % (wins, losses)) not in page:
    fails.append("the record is wrong")
if 'class="receipt first"' not in page:
    fails.append("the first Fire Kyle is not marked")
# the quotes carry apostrophes and quote marks: they must come through escaped, not raw
if "<script>alert" in page or re.search(r"<q>[^<]*<[^/q]", page):
    fails.append("a quote leaked markup")
# a logged-out reader can see the page
c.get("/logout")
if c.get("/receipts").status_code != 200:
    fails.append("the page needs a login")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
