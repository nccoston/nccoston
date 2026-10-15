"""Seed a board with a few realistic posts and serve it on :5099, so a real
MCP client (or a browser) can talk to it over an actual socket. Data goes in a
fresh temporary directory; nothing touches the real board.

    python3 victors-board/tests/live_board.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="live_"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
from werkzeug.security import generate_password_hash

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
