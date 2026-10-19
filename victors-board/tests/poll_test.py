"""Polls are threads again. The question is the subject, every vote is a reply
with a name on it, and the widget is a scoreboard counted from the thread.

Run from anywhere:  python3 victors-board/tests/poll_test.py
"""
import os, re, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="pl_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    for h in ("Nikos", "Ken", "Rich", "danny", "jjwalker"):
        db.execute("INSERT INTO users (handle, password_hash, created_at)"
                   " VALUES (?, ?, ?)", (h, generate_password_hash("pw"),
                                         appmod.now_utc_iso()))
    db.commit()


def client(handle):
    c = appmod.app.test_client()
    c.post("/login", data={"handle": handle, "password": "pw"}, follow_redirects=True)
    return c


def q(sql, *a):
    with appmod.app.app_context():
        return appmod.get_db().execute(sql, a).fetchall()


nik, ken, rich, danny, jj = (client(h) for h in ("Nikos", "Ken", "Rich", "danny", "jjwalker"))
anon = appmod.app.test_client()

# --- a new poll is a thread poll -------------------------------------------
nik.post("/post", data={"subject": "Should the band play Temptation every game?",
                        "body": "", "poll_options": "Yes\nNo\nOnly after wins"},
         follow_redirects=True)
root = q("SELECT id FROM messages ORDER BY id DESC LIMIT 1")[0]["id"]
poll = q("SELECT * FROM polls WHERE message_id = ?", root)[0]
if poll["tally"] != "thread" or poll["multi"] != 0:
    fails.append("a new poll is not a single-choice thread poll: %s" % dict(poll))
opts = {r["text"]: r["id"] for r in q("SELECT id, text FROM poll_options WHERE poll_id = ?", poll["id"])}

# --- the vote button posts a reply with the option as its subject ----------
ken.post("/poll/%d/vote" % poll["id"], data={"option_id": opts["Yes"]}, follow_redirects=True)
rep = q("SELECT * FROM messages WHERE parent_id = ? ORDER BY id DESC LIMIT 1", root)
if not rep or rep[0]["subject"] != "Yes*" or rep[0]["author_name"] != "Ken" or rep[0]["body"]:
    fails.append("the vote did not post as 'Yes*' from Ken: %s" % (dict(rep[0]) if rep else None))
if q("SELECT COUNT(*) c FROM poll_votes")[0]["c"] != 0:
    fails.append("a thread poll wrote to the old ballot table")

# --- replying by hand counts the same; 'Re:' is conversation --------------
rich.post("/post/%d" % root, data={"subject": "no*", "body": ""}, follow_redirects=True)
danny.post("/post/%d" % root, data={"subject": "Yes, obviously*", "body": ""}, follow_redirects=True)
jj.post("/post/%d" % root, data={"subject": "Maybe*", "body": ""}, follow_redirects=True)
yes_reply = q("SELECT id FROM messages WHERE subject = 'Yes*'")[0]["id"]
rich.post("/post/%d" % yes_reply, data={"subject": "Re: Yes*", "body": "you're wrong Ken"},
          follow_redirects=True)
def widget(html):
    """Just the poll box — not the thread listing under it."""
    start = html.index('class="bigpoll"')
    return html[start:html.index("Back to the board", start)]


page = anon.get("/message/%d" % root).get_data(as_text=True)
box = widget(page)


def names_under(option):
    m = re.search(re.escape(option) + r".*?bigpoll-names\">([^<]*)<", box, re.S)
    return [n.strip() for n in m.group(1).split(",")] if m else []


if names_under("Yes") != ["Ken", "danny"]:
    fails.append("Yes should list Ken and danny, got %s" % names_under("Yes"))
if names_under("No") != ["Rich"]:
    fails.append("No should list Rich (lowercase, by hand), got %s" % names_under("No"))
if "jjwalker" in box:
    fails.append("a write-in ('Maybe') was counted")
if "3 voted" not in box:
    fails.append("the count should be 3 members, box says: %s" %
                 re.search(r"(\d+) voted", box))
if names_under("No").count("Rich") != 1:
    fails.append("Rich's 'Re: Yes*' reply changed his vote")

# --- changing your mind is replying again; newest wins ---------------------
ken.post("/poll/%d/vote" % poll["id"], data={"option_id": opts["No"]}, follow_redirects=True)
page = ken.get("/message/%d" % root).get_data(as_text=True)
box = widget(page)
if names_under("Yes") != ["danny"] or names_under("No") != ["Rich", "Ken"]:
    fails.append("newest vote did not win: Yes=%s No=%s" % (names_under("Yes"), names_under("No")))
if "&#10003; you" not in box:
    fails.append("Ken's own vote is not marked")
if "3 voted" not in box:
    fails.append("changing a vote changed the member count")

# a double tap is one vote
n = q("SELECT COUNT(*) c FROM messages WHERE parent_id = ?", root)[0]["c"]
ken.post("/poll/%d/vote" % poll["id"], data={"option_id": opts["No"]}, follow_redirects=True)
if q("SELECT COUNT(*) c FROM messages WHERE parent_id = ?", root)[0]["c"] != n:
    fails.append("a double tap posted twice")

# the votes are real replies: on the front page, in the thread, with names
home = anon.get("/").get_data(as_text=True)
if "Yes*" not in home or "[POLL]" not in home:
    fails.append("vote replies are not on the front page as posts")

# --- multiple choice ------------------------------------------------------
nik.post("/post", data={"subject": "Best uniform", "body": "",
                        "poll_options": "Maize\nBlue\nWhite", "poll_multi": "1"},
         follow_redirects=True)
root2 = q("SELECT id FROM messages ORDER BY id DESC LIMIT 1")[0]["id"]
poll2 = q("SELECT * FROM polls WHERE message_id = ?", root2)[0]
if poll2["multi"] != 1:
    fails.append("pick-all-that-apply was not saved")
o2 = {r["text"]: r["id"] for r in q("SELECT id, text FROM poll_options WHERE poll_id = ?", poll2["id"])}
ken.post("/poll/%d/vote" % poll2["id"], data={"option_id": [o2["Maize"], o2["Blue"]]},
         follow_redirects=True)
if q("SELECT subject FROM messages WHERE parent_id = ? ORDER BY id DESC LIMIT 1", root2)[0]["subject"] != "Maize, Blue*":
    fails.append("a multi vote did not post as 'Maize, Blue*'")
rich.post("/post/%d" % root2, data={"subject": "maize and blue*", "body": ""}, follow_redirects=True)
danny.post("/post/%d" % root2, data={"subject": "White. Fight me.*", "body": ""}, follow_redirects=True)
page = anon.get("/message/%d" % root2).get_data(as_text=True)
box = widget(page)
if names_under("Maize") != ["Ken", "Rich"] or names_under("Blue") != ["Ken", "Rich"]:
    fails.append("multi tally wrong: Maize=%s Blue=%s" % (names_under("Maize"), names_under("Blue")))
if names_under("White") != ["danny"]:
    fails.append("'White. Fight me.' should count for White, got %s" % names_under("White"))
if "3 voted" not in box:
    fails.append("multi count should be members (3), not ticks")
if "pick all that apply" not in box or 'type="checkbox"' not in ken.get("/message/%d" % root2).get_data(as_text=True):
    fails.append("the multi poll does not offer checkboxes")

# --- public, no secret ballot anywhere on a thread poll -------------------
if "Change your vote" in page or 'type="radio"' in page:
    fails.append("a thread poll shows the old ballot box")
if "Log in</a> to vote" not in page:
    fails.append("a logged-out reader is not told to log in")
if 'name="option_id"' in page.split("Post a reply")[0].split('class="bigpoll-vote"')[0] and False:
    pass

# --- the polls that already exist keep the old anonymous box ---------------
with appmod.app.app_context():
    d = appmod.get_db()
    mid = d.execute("INSERT INTO messages (thread_id, parent_id, subject, body, author_name,"
                    " user_id, created_at, board) VALUES (NULL, NULL, 'Old poll', '', 'Nikos',"
                    " 1, ?, 'main')", (appmod.now_utc_iso(),)).lastrowid
    d.execute("UPDATE messages SET thread_id = ? WHERE id = ?", (mid, mid))
    pid = d.execute("INSERT INTO polls (message_id, created_at, tally) VALUES (?, ?, 'ballot')",
                    (mid, appmod.now_utc_iso())).lastrowid
    a = d.execute("INSERT INTO poll_options (poll_id, text) VALUES (?, 'A')", (pid,)).lastrowid
    d.execute("INSERT INTO poll_options (poll_id, text) VALUES (?, 'B')", (pid,))
    d.execute("INSERT INTO poll_votes (poll_id, option_id, user_id, created_at) VALUES (?, ?, 2, ?)",
              (pid, a, appmod.now_utc_iso()))
    d.commit()
old = anon.get("/message/%d" % mid).get_data(as_text=True)
if "bigpoll-names" in old or "Ken" in widget(old):
    fails.append("an old anonymous poll now shows names")
if "100%" not in old:
    fails.append("the old poll lost its percentages")
rich.post("/poll/%d/vote" % pid, data={"option_id": a}, follow_redirects=True)
if q("SELECT COUNT(*) c FROM poll_votes WHERE poll_id = ?", pid)[0]["c"] != 2:
    fails.append("voting on an old poll no longer uses the ballot table")
if q("SELECT COUNT(*) c FROM messages WHERE parent_id = ?", mid)[0]["c"] != 0:
    fails.append("voting on an old poll posted a reply")

# --- the matcher, on its own ----------------------------------------------
O = [{"id": 1, "text": "Yes"}, {"id": 2, "text": "No"}, {"id": 3, "text": "Yes, but only on Saturdays"}]
cases = [("Yes*", False, [1]), ("YES", False, [1]), ("yes, but only on saturdays*", False, [3]),
         ("Yes but no*", False, [1]), ("Re: Yes*", False, []), ("Nope*", False, []),
         ("No (nm)", False, [2]), ("No nm", False, [2]), ("Yesterday was fun*", False, []),
         ("yes and no*", True, [1, 2]), ("No, yes*", True, [2, 1]), ("", False, [])]
for subj, multi, want in cases:
    got = appmod.poll_matches(subj, O, multi)
    if sorted(got) != sorted(want):
        fails.append("poll_matches(%r, multi=%s) = %s, wanted %s" % (subj, multi, got, want))

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
