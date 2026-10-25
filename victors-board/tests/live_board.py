"""Seed a board with a few realistic posts and serve it on :5099, so a real
MCP client (or a browser) can talk to it over an actual socket. Data goes in a
fresh temporary directory; nothing touches the real board.

    python3 victors-board/tests/live_board.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="live_"))
if os.environ.get("VOICE_FAKE"):      # voice on, with a pretend relay (see below)
    os.environ.setdefault("CF_REALTIME_APP_ID", "fake-app")
    os.environ.setdefault("CF_REALTIME_TOKEN", "fake-token")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

if os.environ.get("VOICE_FAKE"):
    # A stand-in for Cloudflare's relay: answers the way the real one does,
    # with SDP that only a stand-in PeerConnection (the browser test's)
    # would accept. Lets the whole voice flow run without the network.
    import itertools
    _n = itertools.count(1)
    _mids = {}   # session -> remote mids handed out, "r1", "r2"... per session

    def _fake_cf(path, body=None, method="POST"):
        sid = path.split("/")[2] if path.startswith("/sessions/") else None
        if path.endswith("/sessions/new"):
            return {"sessionId": "fake-session-%d" % next(_n)}
        if path.endswith("/tracks/new"):
            tracks = body["tracks"]
            if tracks[0]["location"] == "local":
                return {"sessionDescription": {"type": "answer", "sdp": "v=0 fake answer"},
                        "tracks": [{"mid": t["mid"], "trackName": t["trackName"]} for t in tracks]}
            out = []
            for t in tracks:
                _mids[sid] = _mids.get(sid, 0) + 1
                out.append({"mid": "r%d" % _mids[sid], "trackName": t["trackName"],
                            "sessionId": t["sessionId"]})
            # the stand-in PeerConnection reads the track count off the "SDP"
            return {"sessionDescription": {"type": "offer", "sdp": "v=0 fake offer tracks=%d" % len(out)},
                    "requiresImmediateRenegotiation": True, "tracks": out}
        if path.endswith("/renegotiate"):
            return {}
        raise RuntimeError("unexpected relay call " + path)
    appmod._cf = _fake_cf

with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    if not db.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]:
        uids = {}
        for h in ("Nikos", "Ken", "Rich", "danny", "jjwalker", "chief"):
            uids[h] = db.execute(
                "INSERT INTO users (handle, password_hash, created_at)"
                " VALUES (?, ?, ?)",
                (h, generate_password_hash("pw"), appmod.now_utc_iso())).lastrowid
        db.execute("UPDATE users SET is_admin = 1 WHERE handle = 'Nikos'")

        def post(subject, body, who, parent=None, board="main", hof=None, alias=None):
            mid = db.execute(
                "INSERT INTO messages (thread_id, parent_id, subject, body,"
                " author_name, user_id, created_at, ip_address, board, hof_at, alias)"
                " VALUES (NULL,?,?,?,?,?,?,?,?,?,?)",
                (parent, subject, body, who, uids.get(who),
                 appmod.now_utc_iso(), "198.51.100.9", board, hof, alias)).lastrowid
            root = mid if parent is None else db.execute(
                "SELECT thread_id FROM messages WHERE id = ?",
                (parent,)).fetchone()["thread_id"]
            db.execute("UPDATE messages SET thread_id = ? WHERE id = ?", (root, mid))
            return mid

        t1 = post("The 1969 upset, 57 years on",
                  "<p>Bo's first year and we knock off the number one team in "
                  "the country. Nothing since has topped it &amp; nothing will.</p>",
                  "Nikos")
        post("Re: The 1969 upset", "My dad took me. I was nine.", "Ken", t1)
        post("Re: The 1969 upset", "Still get chills reading about it", "Rich", t1)
        post("Probation countdown*", "", "danny")
        post("Obituaries, week of September 26", "Sad news this week.", "danny",
             alias="Obitman")
        post("The greatest post this board ever produced",
             "I would like my ampersand back.", "Rich", hof=appmod.now_utc_iso())
        post("Michigan vs Oklahoma — pick 'em",
             "Post your score. Closest to the final wins, win or lose.",
             "Skeeps", board="scores")
        db.execute("INSERT INTO traffic (day, pageviews, uniques)"
                   " VALUES ('2026-09-06', 35104, 912)")
        db.commit()

appmod.app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5099)),
               debug=False, threaded=True)
