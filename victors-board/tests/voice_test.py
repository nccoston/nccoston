"""Live voice in chat, server side: the relay is brokered here with a
stand-in, so this covers sessions, publishing, pulling, the heartbeat,
leaving, the admin clear, and that nothing exists without the two keys.

Run from anywhere:  python3 victors-board/tests/voice_test.py
"""
import json, os, sys, tempfile, time
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="vc_")
os.environ["CF_REALTIME_APP_ID"] = "app-test"
os.environ["CF_REALTIME_TOKEN"] = "token-test"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
calls = []
n = [0]


def fake_cf(path, body=None, method="POST"):
    calls.append((method, path, body))
    if path.endswith("/sessions/new"):
        n[0] += 1
        return {"sessionId": "s%d" % n[0]}
    if path.endswith("/tracks/new"):
        if body["tracks"][0]["location"] == "local":
            return {"sessionDescription": {"type": "answer", "sdp": "ANSWER"},
                    "tracks": [{"mid": t["mid"], "trackName": t["trackName"]} for t in body["tracks"]]}
        return {"sessionDescription": {"type": "offer", "sdp": "OFFER"},
                "requiresImmediateRenegotiation": True,
                "tracks": [{"mid": str(i), "trackName": t["trackName"], "sessionId": t["sessionId"]}
                           for i, t in enumerate(body["tracks"])]}
    if path.endswith("/renegotiate"):
        return {}
    raise AssertionError("unexpected relay call " + path)


appmod._cf = fake_cf

with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    for h in ("Ken", "Rich", "Nikos"):
        db.execute("INSERT INTO users (handle, password_hash, created_at) VALUES (?, ?, ?)",
                   (h, generate_password_hash("pw"), appmod.now_utc_iso()))
    db.execute("UPDATE users SET is_admin = 1 WHERE handle = 'Nikos'")
    db.commit()


def client(handle):
    c = appmod.app.test_client()
    c.post("/login", data={"handle": handle, "password": "pw"})
    return c


def voice(c):
    return c.get("/chat/messages?since=999").get_json()["voice"]


ken, rich, nikos = client("Ken"), client("Rich"), client("Nikos")

# the link is on the page, and the relay's secret is not
page = ken.get("/chat").get_data(as_text=True)
if 'id="voice-join"' not in page or "chatvoice.js" not in page:
    fails.append("no voice link on the chat page")
if "token-test" in page:
    fails.append("the relay secret reached the page")
if voice(ken) != {"epoch": 1, "me": False, "count": 0, "talking": [], "tracks": []}:
    fails.append("empty voice state is off: %r" % voice(ken))

# Ken listens: a relay session, nothing to pull yet
d = ken.post("/chat/voice/join").get_json()
if d != {"ok": True, "sid": "s1"}:
    fails.append("join: %r" % d)
if ken.post("/chat/voice/join").get_json() != {"ok": True, "sid": "s1"}:
    fails.append("a second join did not reuse the session")
v = voice(ken)
if not (v["me"] and v["count"] == 1 and v["tracks"] == [] and v["talking"] == []):
    fails.append("after Ken joins: %r" % v)
if ken.post("/chat/voice/pull", data={"tracks": "[]"}).get_json() != {"ok": False}:
    fails.append("an empty pull should be refused")

# Rich joins and talks: his offer goes to the relay, the answer comes back
rich.post("/chat/voice/join")
d = rich.post("/chat/voice/publish", data={"sdp": "RICH OFFER", "mid": "0"}).get_json()
if d != {"ok": True, "sdp": "ANSWER"}:
    fails.append("publish: %r" % d)
m, p, body = calls[-1]
if not (p == "/sessions/s2/tracks/new" and body["sessionDescription"] == {"type": "offer", "sdp": "RICH OFFER"}
        and body["tracks"][0]["location"] == "local" and body["tracks"][0]["mid"] == "0"
        and body["tracks"][0]["trackName"].startswith("mic-")):
    fails.append("the publish call to the relay is off: %r" % ((p, body),))
track = body["tracks"][0]["trackName"]
v = voice(ken)
if v["talking"] != ["Rich"] or v["tracks"] != [{"sid": "s2", "track": track, "handle": "Rich"}]:
    fails.append("Ken does not see Rich talking: %r" % v)
if voice(rich)["tracks"] != []:
    fails.append("Rich was offered his own track")

# Ken pulls Rich: the relay's offer comes back, Ken answers, it's renegotiated
d = ken.post("/chat/voice/pull", data={"tracks": json.dumps([{"sid": "s2", "track": track}])}).get_json()
if not (d["ok"] and d["sdp"] == "OFFER" and d["type"] == "offer" and d["renegotiate"]
        and d["tracks"] == [{"mid": "0", "track": track, "sid": "s2"}]):
    fails.append("pull: %r" % d)
if calls[-1][1] != "/sessions/s1/tracks/new" or calls[-1][2] != {"tracks": [
        {"location": "remote", "sessionId": "s2", "trackName": track}]}:
    fails.append("the pull call to the relay is off: %r" % (calls[-1],))
if ken.post("/chat/voice/answer", data={"sdp": "KEN ANSWER"}).get_json() != {"ok": True}:
    fails.append("answer refused")
if calls[-1] != ("PUT", "/sessions/s1/renegotiate", {"sessionDescription": {"type": "answer", "sdp": "KEN ANSWER"}}):
    fails.append("the renegotiate call is off: %r" % (calls[-1],))
# a made-up track, or your own, is never forwarded to the relay
before = len(calls)
for bad in ([{"sid": "s9", "track": "mic-x"}], [{"sid": "s1", "track": track}], "not json"):
    if ken.post("/chat/voice/pull", data={"tracks": json.dumps(bad) if not isinstance(bad, str) else bad}).get_json() != {"ok": False}:
        fails.append("bad pull accepted: %r" % (bad,))
if len(calls) != before:
    fails.append("a bad pull reached the relay")

# mute and unmute are just the flag; leaving is just the entry
rich.post("/chat/voice/talking", data={"on": "0"})
if voice(ken)["talking"] != []:
    fails.append("mute did not clear the talking line")
rich.post("/chat/voice/talking", data={"on": "1"})
if voice(ken)["talking"] != ["Rich"]:
    fails.append("unmute did not restore the talking line")
if ken.post("/chat/voice/talking", data={"on": "1"}).get_json() != {"ok": False}:
    fails.append("a listener with no mic could be marked talking")
ken.post("/chat/voice/leave")
v = voice(rich)
if v["count"] != 1 or voice(ken)["me"]:
    fails.append("leave did not take: %r" % v)

# a member whose page went away drops out after 30 seconds without a poll
t = appmod.VOICE_PEERS[next(u for u, p in appmod.VOICE_PEERS.items() if p["handle"] == "Rich")]
t["t"] -= 31
if voice(nikos)["count"] != 0:
    fails.append("a silent member did not time out")

# the admin clear empties the voice room and bumps its epoch
ken.post("/chat/voice/join"); rich.post("/chat/voice/join")
nikos.post("/chat/clear")
v = voice(ken)
if v["count"] != 0 or v["epoch"] != 2 or v["me"]:
    fails.append("clear did not empty the voice room: %r" % v)

# the relay failing is an answer, not a crash
def broken(path, body=None, method="POST"):
    raise RuntimeError("down")
appmod._cf = broken
if ken.post("/chat/voice/join").get_json() != {"ok": False, "error": "the voice relay is not answering"}:
    fails.append("a dead relay did not come back as a plain error")
appmod._cf = fake_cf

# a full room
appmod.VOICE_PEERS.update({9000 + i: {"handle": "x%d" % i, "sid": "x", "track": None,
                                       "talking": False, "t": time.monotonic()} for i in range(appmod.VOICE_MAX)})
if ken.post("/chat/voice/join").get_json() != {"ok": False, "error": "the voice room is full"}:
    fails.append("the room cap is not enforced")
appmod.VOICE_PEERS.clear()

# without the keys: no link, no script, no voice in the poll, no endpoints
appmod.VOICE_APP_ID = None
page = ken.get("/chat").get_data(as_text=True)
if 'id="voice"' in page or "chatvoice.js" in page:
    fails.append("the voice link shows without the keys")
if voice(ken) is not None:
    fails.append("voice rides on the poll without the keys")
if ken.post("/chat/voice/join").status_code != 404:
    fails.append("join is open without the keys")

print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
