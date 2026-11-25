"""Days since our last humiliation: an admin sets the date and what it
was, the sign counts up under the header, blank takes it down, a bad
date is refused. Run from anywhere:

    python3 victors-board/tests/sign_test.py
"""
import os, re, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="sg_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    db.execute("INSERT INTO users (handle, password_hash, created_at, is_admin) VALUES (?, ?, ?, 1)",
               ("Nikos", generate_password_hash("pw"), appmod.now_utc_iso()))
    db.commit()
c = appmod.app.test_client()

# no sign until an admin sets one
if 'class="sign"' in c.get("/").get_data(as_text=True):
    fails.append("the sign shows with nothing set")

c.post("/login", data={"handle": "Nikos", "password": "pw"})
today = datetime.now(timezone.utc).astimezone(appmod.BOARD_TZ).date()
ten_ago = (today - timedelta(days=10)).isoformat()
settings = {"site_title": "The Victors", "header_html": "", "links_html": "", "hof_threshold": "5",
            "podcast_channel_id": "", "podcast_title_filter": "", "countdown_at": "", "countdown_label": ""}
c.post("/admin/settings", data=dict(settings, action="settings", humiliation_at=ten_ago,
                                    humiliation_what="Oregon 31–7"), follow_redirects=True)
home = c.get("/").get_data(as_text=True)
m = re.search(r'<span class="sign-days">(\d+)</span>', home)
if not m or m.group(1) != "10":
    fails.append("the sign does not count ten days: %s" % (m and m.group(1)))
if "days since our last humiliation" not in home or "Oregon 31–7" not in home:
    fails.append("the sign's words are off")
# logged out, same sign
c.get("/logout")
if 'class="sign-days">10<' not in c.get("/").get_data(as_text=True):
    fails.append("a reader does not see the sign")
c.post("/login", data={"handle": "Nikos", "password": "pw"})

# today: zero days, singular handled; one day: singular
c.post("/admin/settings", data=dict(settings, action="settings", humiliation_at=today.isoformat(), humiliation_what=""),
       follow_redirects=True)
home = c.get("/").get_data(as_text=True)
if 'class="sign-days">0<' not in home or "days since" not in home:
    fails.append("day zero is wrong")
c.post("/admin/settings", data=dict(settings, action="settings", humiliation_at=(today - timedelta(days=1)).isoformat(),
                                    humiliation_what=""), follow_redirects=True)
if "1</span>\n  <span class=\"sign-label\">day since" not in c.get("/").get_data(as_text=True):
    fails.append("one day is not singular")

# a bad date is refused and the old one kept; blank takes it down
r = c.post("/admin/settings", data=dict(settings, action="settings", humiliation_at="last saturday", humiliation_what=""),
           follow_redirects=True)
if "humiliation date isn" not in r.get_data(as_text=True) or 'class="sign-days">1<' not in c.get("/").get_data(as_text=True):
    fails.append("a bad date was not refused, or the old date was lost")
c.post("/admin/settings", data=dict(settings, action="settings", humiliation_at="", humiliation_what=""), follow_redirects=True)
if 'class="sign"' in c.get("/").get_data(as_text=True):
    fails.append("blank did not take the sign down")
# the admin page shows the fields
st = c.get("/admin/settings").get_data(as_text=True)
if 'name="humiliation_at"' not in st or 'name="humiliation_what"' not in st:
    fails.append("the admin page lacks the fields")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
