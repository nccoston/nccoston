"""Chat: the page carries the ease-of-use pieces (fit-to-screen, new-messages
pill, roster fold, tap-a-name, send key) and the room itself still works —
send, read, presence, the admin clear. Run from anywhere:

    python3 victors-board/tests/chat_test.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="chat_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    for h in ("Ken", "Rich"):
        db.execute("INSERT INTO users (handle, password_hash, created_at) VALUES (?, ?, ?)",
                   (h, generate_password_hash("pw"), appmod.now_utc_iso()))
    db.commit()


def client(handle):
    c = appmod.app.test_client()
    c.post("/login", data={"handle": handle, "password": "pw"})
    return c


ken, rich = client("Ken"), client("Rich")
page = ken.get("/chat").get_data(as_text=True)

for want, why in (('id="chat-new"', "no new-messages pill"),
                  ('enterkeyhint="send"', "the phone keyboard's Enter is not a Send key"),
                  ('id="chat-online" role="button"', "the count is not a roster toggle"),
                  ('class="chat-main"', "no wrapper for the pill to sit in"),
                  ("visualViewport", "the box does not follow the keyboard"),
                  ('"chat-handle"', "names are not tappable"),
                  ('getElementById("chat-roster").addEventListener("click", tapName)',
                   "names in the room are not tappable")):
    if want not in page:
        fails.append(why)
if "65vh" in page:
    fails.append("the fixed 65vh height is still in the page")
# no explanatory copy for members
for noise in ("tap a name", "Tap a name", "swipe up", "keyboard"):
    body = page[page.index("<body"):page.index("<script")]
    if noise in body:
        fails.append("explanatory copy on the page: %r" % noise)

# the room still works
if ken.post("/chat/send", data={"text": "anyone here"}).get_json() != {"ok": True}:
    fails.append("Ken could not send")
if rich.post("/chat/send", data={"text": "Ken yes"}).get_json() != {"ok": True}:
    fails.append("Rich could not send")
rich.get("/chat/messages?since=0")   # presence comes from reading, not sending
d = ken.get("/chat/messages?since=0").get_json()
if [m["handle"] for m in d["messages"]] != ["Ken", "Rich"]:
    fails.append("messages did not come back in order: %r" % d["messages"])
if sorted(d["names"]) != ["Ken", "Rich"] or d["online"] != 2:
    fails.append("presence is off: %r" % d)
if ken.get("/chat/messages?since=%d" % d["messages"][-1]["id"]).get_json()["messages"]:
    fails.append("since= did not filter")
if ken.post("/chat/send", data={"text": "too fast"}).get_json().get("error") != "slow down":
    fails.append("the one-a-second limit is gone")
if appmod.app.test_client().get("/chat").status_code == 200:
    fails.append("the room is open to readers without an account")

# --- live polls: "/poll question? option, option"
P = appmod.parse_chat_poll
cases = {
    "Do we beat Iowa? Yes, No, Nobody wins": ("Do we beat Iowa?", ["Yes", "No", "Nobody wins"]),
    "Best QB: Harbaugh, Henne,  Brady": ("Best QB", ["Harbaugh", "Henne", "Brady"]),
    "Do we beat Iowa?": ("Do we beat Iowa?", ["Yes", "No"]),
    "beer run": ("beer run", ["Yes", "No"]),
    "Pick one? a, A, b": ("Pick one?", ["a", "b"]),
    "Too many? 1,2,3,4,5,6,7,8": ("Too many?", ["1", "2", "3", "4", "5", "6"]),
    "   ": None,
}
for raw, want in cases.items():
    got = P(raw)
    got = (got["q"], got["options"]) if got else None
    if got != want:
        fails.append("parse %r -> %r, wanted %r" % (raw, got, want))

import time as _t; _t.sleep(1.05)
ken.post("/chat/send", data={"text": "/poll Do we beat Iowa? Yes, No, Nobody wins"})
d = rich.get("/chat/messages?since=0").get_json()
pm = d["messages"][-1]
if pm.get("poll") != {"q": "Do we beat Iowa?", "options": ["Yes", "No", "Nobody wins"]} or pm["text"]:
    fails.append("the poll message is off: %r" % pm)
if "votes" in pm:
    fails.append("votes leaked into the message itself")
if d["polls"] != {str(pm["id"]): []}:
    fails.append("fresh poll should ride along with no votes: %r" % d["polls"])
pid = pm["id"]
rich.post("/chat/vote", data={"id": pid, "option": 0})
ken.post("/chat/vote", data={"id": pid, "option": 2})
rich.post("/chat/vote", data={"id": pid, "option": 1})          # Rich changes his mind
if ken.get("/chat/messages?since=999").get_json()["polls"] != {str(pid): [["Ken", 2], ["Rich", 1]]}:
    fails.append("votes did not tally/change: %r" % ken.get("/chat/messages?since=999").get_json()["polls"])
ken.post("/chat/vote", data={"id": pid, "option": 2})          # Ken taps his own choice: vote back
if ken.get("/chat/messages?since=999").get_json()["polls"] != {str(pid): [["Rich", 1]]}:
    fails.append("tapping your own choice did not take the vote back")
for bad in ({"id": pid, "option": 7}, {"id": pid, "option": -1}, {"id": 999, "option": 0}, {"id": pid}):
    if ken.post("/chat/vote", data=bad).get_json() != {"ok": False}:
        fails.append("bad vote accepted: %r" % bad)
_t.sleep(1.05)
rich.post("/chat/send", data={"text": "/polls are fun"})
if "poll" in rich.get("/chat/messages?since=%d" % pid).get_json()["messages"][-1]:
    fails.append("'/polls are fun' became a poll")
for want in ('"/chat/vote"', "drawVotes(d.polls", 'className = "chat-poll-opt"'):
    if want not in page:
        fails.append("the page lacks %s" % want)

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
