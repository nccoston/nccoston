"""The pinned pick 'em says when and where: 'Sat 12:30 PM EDT on BTN',
from what ESPN gave the board. Nothing shows while the time is TBA, and
a TBA placeholder never becomes the pick-lock time.

Run from anywhere:  python3 victors-board/tests/kickoff_test.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="ko_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod

appmod.app.config["TESTING"] = True
fails = []


def espn_event(date, network="BTN", time_valid=True):
    ev = {"date": date, "timeValid": time_valid,
          "status": {"type": {"shortDetail": "10/31 - 12:30 PM EDT", "state": "pre"}},
          "competitions": [{"competitors": [
              {"homeAway": "home", "team": {"abbreviation": "MICH", "shortDisplayName": "Michigan"}, "score": ""},
              {"homeAway": "away", "team": {"abbreviation": "PUR", "shortDisplayName": "Purdue"}, "score": ""}]}]}
    if network:
        ev["competitions"][0]["broadcasts"] = [{"market": "national", "names": [network]}]
    return ev


# the parser picks up the network and the TBA flag
gm = appmod._parse_event("CFB", espn_event("2026-10-31T16:30Z"))
if gm["network"] != "BTN" or gm["time_valid"] is not True:
    fails.append("parse: %r" % gm)
gm_tba = appmod._parse_event("CFB", espn_event("2026-10-31T04:00Z", network="", time_valid=False))
if gm_tba["network"] != "" or gm_tba["time_valid"] is not False:
    fails.append("parse TBA: %r" % gm_tba)
geo = espn_event("2026-10-31T16:30Z", network="")
geo["competitions"][0]["geoBroadcasts"] = [{"media": {"shortName": "FOX"}}]
if appmod._parse_event("CFB", geo)["network"] != "FOX":
    fails.append("geoBroadcasts fallback did not give the network")

# the label
if appmod.kickoff_label("2026-10-31T16:30:00") != "Sat 12:30 PM EDT":
    fails.append("label: %r" % appmod.kickoff_label("2026-10-31T16:30:00"))
if appmod.kickoff_label("2026-10-31T16:30:00", "BTN") != "Sat 12:30 PM EDT on BTN":
    fails.append("label with network: %r" % appmod.kickoff_label("2026-10-31T16:30:00", "BTN"))
if appmod.kickoff_label("2026-11-21T17:00:00", "CBS") != "Sat 12:00 PM EST on CBS":
    fails.append("label after the clocks change: %r" % appmod.kickoff_label("2026-11-21T17:00:00", "CBS"))
if appmod.kickoff_label(None) != "" or appmod.kickoff_label("junk") != "":
    fails.append("an empty or bad kickoff did not give an empty label")

with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()

    # Monday: ESPN lists the game with a TBA time. The thread is seeded, pinned,
    # with no kickoff on record (so picks don't lock on the placeholder)
    mid = appmod.seed_gameday_pickem(db, gm_tba)
    g = db.execute("SELECT * FROM games WHERE message_id = ?", (mid,)).fetchone()
    if g["kickoff_at"] is not None or g["network"]:
        fails.append("a TBA placeholder was stored as the kickoff: %r" % dict(g))
    c = appmod.app.test_client()
    home = c.get("/").get_data(as_text=True)
    row = home[home.index('class="pinned-row"'):home.index("</p>", home.index('class="pinned-row"'))]
    if "Michigan vs Purdue" not in row:
        fails.append("the pick 'em is not pinned")
    if " on " in row or "PM" in row:
        fails.append("a time shows while ESPN says TBA: %r" % row)

    # later in the week: the real time and the network arrive; the pin says so
    mid2 = appmod.seed_gameday_pickem(db, gm)
    if mid2 != mid:
        fails.append("the real time made a second thread")
    g = db.execute("SELECT * FROM games WHERE message_id = ?", (mid,)).fetchone()
    if g["kickoff_at"] != "2026-10-31T16:30:00" or g["network"] != "BTN":
        fails.append("the kickoff/network backfill did not take: %r" % dict(g))
    home = c.get("/").get_data(as_text=True)
    row = home[home.index('class="pinned-row"'):home.index("</p>", home.index('class="pinned-row"'))]
    if "Michigan vs Purdue*</a> &middot; Sat 12:30 PM EDT on BTN" not in row:
        fails.append("the pin does not say when: %r" % row)
    # every page, logged out too
    if "Sat 12:30 PM EDT on BTN" not in c.get("/stats").get_data(as_text=True):
        fails.append("the kickoff is missing from other pages")

    # a network that shows up later does not overwrite one on record
    other = dict(gm, network="FOX")
    appmod.seed_gameday_pickem(db, other)
    if db.execute("SELECT network FROM games WHERE message_id = ?", (mid,)).fetchone()["network"] != "BTN":
        fails.append("a later network overwrote the first")

    # an ordinary pinned post carries no time
    db.execute("INSERT INTO messages (thread_id, parent_id, subject, body, author_name, created_at, pinned)"
               " VALUES (NULL, NULL, 'To register, email the mods*', '', 'Nikos', ?, 1)", (appmod.now_utc_iso(),))
    db.commit()
    home = c.get("/").get_data(as_text=True)
    row = home[home.index('class="pinned-row"'):home.index("</p>", home.index('class="pinned-row"'))]
    if row.count(" on BTN") != 1 or "email the mods*</a><br>" not in row.replace("\n", ""):
        fails.append("the plain pin picked up a time, or lost its line: %r" % row)

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
