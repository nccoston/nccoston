"""The board as an MCP server.

Two things matter here and they're different. One: does it actually speak the
protocol, so a real client can talk to it. Two: can anything reach data that a
logged-out browser can't already see — because the answer has to be no, and
"I was careful" is not an answer.

Run from anywhere:  python3 victors-board/tests/mcp_test.py
"""
import json, os, re, sqlite3, sys, tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="mcp_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as appmod
import mcp_server
from werkzeug.security import generate_password_hash

appmod.app.config["TESTING"] = True
fails = []
SECRET_IP = "203.0.113.77"
SECRET_PW = "hunter2-the-password"
LONG = ("This is the Hall of Fame post and it goes on at some length. " * 60).strip()

with appmod.app.app_context():
    appmod.init_db()
    db = appmod.get_db()
    uids = {}
    for h, admin in (("Nikos", 1), ("Ken", 0), ("Rich", 0)):
        cur = db.execute(
            "INSERT INTO users (handle, password_hash, created_at, is_admin,"
            " session_token) VALUES (?, ?, ?, ?, ?)",
            (h, generate_password_hash(SECRET_PW), appmod.now_utc_iso(), admin,
             "session-token-" + h))
        uids[h] = cur.lastrowid

    def post(subject, body, author, board="main", parent=None, hof=None,
             alias=None, when=None):
        cur = db.execute(
            "INSERT INTO messages (thread_id, parent_id, subject, body,"
            " author_name, user_id, created_at, ip_address, board, hof_at, alias)"
            " VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (parent, subject, body, author, uids.get(author),
             when or appmod.now_utc_iso(), SECRET_IP, board, hof, alias))
        mid = cur.lastrowid
        root = mid if parent is None else db.execute(
            "SELECT thread_id FROM messages WHERE id = ?", (parent,)
        ).fetchone()["thread_id"]
        db.execute("UPDATE messages SET thread_id = ? WHERE id = ?", (root, mid))
        return mid

    root = post("Bo Schembechler and the 1969 upset",
                "<p>Greatest day in <b>Michigan</b> history &amp; nobody "
                "can tell me otherwise</p>", "Nikos", when="2026-09-26T16:00:00")
    post("Re: Bo", "Agreed, watched it with my dad", "Ken", parent=root,
         when="2026-09-26T16:05:00")
    post("Re: Bo", "I was there in the stands", "Rich", parent=root,
         when="2026-09-26T16:10:00")
    post("Ohio State week*", "", "Rich", when="2026-09-27T12:00:00")
    gem = post("The greatest post ever written", LONG, "Ken",
               hof=appmod.now_utc_iso(), when="2026-09-27T13:00:00")
    post("Michigan vs Oklahoma", "game thread", "Skeeps", board="scores",
         when="2026-09-27T14:00:00")
    costume = post("Obituaries*", "", "Ken", alias="Obitman", when="2026-09-27T15:00:00")
    gone = post("to be deleted*", "", "Rich", when="2026-09-27T16:00:00")
    for i in range(30):
        post("filler %d about Bo*" % i, "", "Ken", when="2026-09-28T%02d:00:00" % (i % 24))
    db.execute("DELETE FROM messages WHERE id = ?", (gone,))
    db.execute("INSERT INTO traffic (day, pageviews, uniques)"
               " VALUES ('2026-09-06', 35000, 900)")
    db.execute("INSERT INTO traffic_visitors (day, visitor)"
               " VALUES ('2026-09-14', 'deadbeefvisitor')")
    db.execute("INSERT INTO message_reads (user_id, message_id) VALUES (?, ?)",
               (uids["Ken"], root))
    db.execute("INSERT INTO bowl_scores (user_id, games, wins, best_w,"
               " longest_td, most_points, updated_at) VALUES (?,?,?,?,?,?,?)",
               (uids["Ken"], 9, 7, 7, 63, 45, appmod.now_utc_iso()))
    db.commit()

c = appmod.app.test_client()
_id = [0]


def rpc(method, params=None, notify=False, raw=None):
    mcp_server._hits.clear()            # the rate limiter is tested separately
    if raw is not None:
        body = raw
    else:
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notify:
            _id[0] += 1
            body["id"] = _id[0]
    r = c.post("/mcp", data=json.dumps(body), content_type="application/json")
    if r.status_code == 202 or not r.data:
        return r, None
    return r, json.loads(r.data)


def call(name, **args):
    r, out = rpc("tools/call", {"name": name, "arguments": args})
    if out is None or "result" not in out:
        fails.append("%s returned no result: %s" % (name, out))
        return {}
    res = out["result"]
    if res.get("isError"):
        return {"__error__": res["content"][0]["text"]}
    return json.loads(res["content"][0]["text"])


# ------------------------------------------------------------ the protocol

r, out = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                            "clientInfo": {"name": "t", "version": "1"}})
init = (out or {}).get("result", {})
if init.get("protocolVersion") != "2025-06-18":
    fails.append("initialize did not echo the client's protocol version: %s" % init)
if "tools" not in init.get("capabilities", {}):
    fails.append("does not advertise tools capability")
instr = init.get("instructions", "")
if str(mcp_server.RATE_LIMIT) not in instr or "a minute" not in instr:
    fails.append("instructions do not state the rate limit")
if "2026-08-03" not in instr or "thirty years" in instr:
    fails.append("instructions misstate what the archive holds")
if "subject_only" not in instr:
    fails.append("instructions do not explain subject_only")

_, out = rpc("initialize", {"protocolVersion": "1999-01-01"})
if out["result"]["protocolVersion"] != mcp_server.LATEST:
    fails.append("an unknown version is not answered with ours")
r, out = rpc("notifications/initialized", {}, notify=True)
if r.status_code != 202 or r.data:
    fails.append("notification answered with %d" % r.status_code)
_, out = rpc("ping")
if out.get("result") != {}:
    fails.append("ping did not answer {}")

_, out = rpc("tools/list")
tools = out["result"]["tools"]
names = {t["name"] for t in tools}
expected = {"search_board", "get_posts", "get_post", "get_thread", "recent_threads",
            "hall_of_fame", "board_stats", "pickem_standings", "arcade_stats"}
if names != expected:
    fails.append("tool list is %s" % sorted(names ^ expected))
for t in tools:
    if "fn" in t:
        fails.append("%s leaked its python callable" % t["name"])
    if t["name"] == "search_board" and "thirty years" in t["description"]:
        fails.append("search_board still promises thirty years of posts")
    if t["name"] == "search_board" and "2026-08-03" not in t["description"]:
        fails.append("search_board does not say when the archive begins")

_, out = rpc("resources/read", {"uri": "victors://about"})
about = out["result"]["contents"][0]["text"]
for want in ("asterisk", "Skeeps", "closest to the final score", "3 August 2026",
             "alias", "deleted"):
    if want not in about:
        fails.append("the about resource never mentions %r" % want)
if "carrying its history" in about:
    fails.append("the about resource still implies the old posts survived")

_, out = rpc("does/not/exist")
if out.get("error", {}).get("code") != -32601:
    fails.append("unknown method should be -32601")
mcp_server._hits.clear()
if c.post("/mcp", data="{not json", content_type="application/json").status_code != 400:
    fails.append("malformed json should be 400")
mcp_server._hits.clear()
r = c.post("/mcp", content_type="application/json", data=json.dumps([
    {"jsonrpc": "2.0", "id": 90, "method": "ping"},
    {"jsonrpc": "2.0", "id": 91, "method": "tools/list"}]))
if not isinstance(json.loads(r.data), list):
    fails.append("batch request mishandled")
mcp_server._hits.clear()
if c.get("/mcp").status_code != 405:
    fails.append("GET /mcp should be 405")

# ------------------------------------------------------------------ the data

res = call("search_board", query="Schembechler")
if res.get("matches") != 1 or res.get("returned") != 1:
    fails.append("search missed the Bo post: %s" % res)
hit = res["results"][0]
if "<b>" in hit["body"] or "&amp;" in hit["body"]:
    fails.append("html reached the model raw: %r" % hit["body"])
if hit.get("subject_only") is not False or hit.get("parent_id") is not None:
    fails.append("root post fields wrong: %s" % hit)

# subject-only is data, not a parse of the asterisk
res = call("search_board", query="Ohio State week")
if res["results"][0].get("subject_only") is not True:
    fails.append("an empty-body post is not marked subject_only")

# --- 1. full bodies where a post is read whole; trimmed in lists ---------
thread = call("get_thread", thread_id=gem)
if thread["thread"]["body"] != LONG:
    fails.append("get_thread trims the Hall of Fame post (%d chars)" % len(thread["thread"]["body"]))
lst = call("search_board", query="goes on at some length")["results"][0]
if len(lst["body"]) > mcp_server.BODY_CHARS + 2 or not lst["body"].endswith("…"):
    fails.append("search results are not trimmed: %d chars" % len(lst["body"]))
one = call("get_post", post_id=gem)
if one["body"] != LONG or one.get("hall_of_fame") is not True:
    fails.append("get_post does not return the whole post")
hof = call("hall_of_fame")["posts"][0]
if len(hof["body"]) > mcp_server.BODY_CHARS + 2:
    fails.append("the HOF list is not trimmed")

# --- 3. reading in order: get_posts pages the archive by id ---------------
page1 = call("get_posts", since_id=0, limit=10)
if page1["returned"] != 10 or not page1["has_more"] or page1["posts"][0]["id"] != 1:
    fails.append("get_posts first page wrong: %s" % {k: page1[k] for k in ("returned", "has_more")})
if page1["posts"][0]["id"] > page1["posts"][-1]["id"]:
    fails.append("get_posts is not oldest first")
seen, since, calls_ = [], 0, 0
while True:
    pg = call("get_posts", since_id=since, limit=10)
    calls_ += 1
    seen += [p["id"] for p in pg["posts"]]
    if not pg["has_more"]:
        break
    since = pg["next_since_id"]
with appmod.app.app_context():
    all_ids = [r["id"] for r in appmod.get_db().execute("SELECT id FROM messages ORDER BY id")]
if seen != all_ids:
    fails.append("walking get_posts did not visit every post exactly once")
if pg["newest_id"] != all_ids[-1]:
    fails.append("newest_id is wrong")
if gone in seen:
    fails.append("a deleted post came back from get_posts")
if len(call("get_posts", limit=9999)["posts"]) > mcp_server.MAX_BULK:
    fails.append("get_posts limit is not clamped")
rep = [p for p in call("get_posts", since_id=root, limit=3)["posts"] if p["parent_id"] == root]
if len(rep) != 2:
    fails.append("replies do not carry parent_id in get_posts")

# --- 7. deleted says deleted; not-yet says not yet ------------------------
d = call("get_post", post_id=gone)
if d.get("deleted") is not True:
    fails.append("a deleted post is not reported as deleted: %s" % d)
far = call("get_post", post_id=all_ids[-1] + 50)
if "__error__" not in far or "newest" not in far["__error__"]:
    fails.append("a not-yet id is not explained: %s" % far)
t = call("get_thread", thread_id=gone)
if "__error__" not in t or "deleted" not in t["__error__"]:
    fails.append("get_thread on a deleted id does not say deleted: %s" % t)

# --- 4. search paging and a day filter ------------------------------------
p1 = call("search_board", query="about Bo", limit=10)
if p1["matches"] != 30 or p1["returned"] != 10 or not p1["has_more"] or p1.get("next_offset") != 10:
    fails.append("search paging page 1 wrong: %s" % {k: p1.get(k) for k in ("matches", "has_more", "next_offset")})
p2 = call("search_board", query="about Bo", limit=10, offset=10)
if p2["offset"] != 10 or {r["id"] for r in p1["results"]} & {r["id"] for r in p2["results"]}:
    fails.append("search page 2 overlaps page 1")
last = call("search_board", query="about Bo", limit=25, offset=25)
if last["has_more"] or last["returned"] != 5 or last["matches"] != 30:
    fails.append("search last page wrong: returned=%s matches=%s has_more=%s" % (last["returned"], last["matches"], last["has_more"]))
day = call("search_board", query="Bo", day="2026-09-26")
if {r["id"] for r in day["results"]} != {root, root + 1, root + 2}:
    fails.append("the day filter returned the wrong posts: %s" % [r["id"] for r in day["results"]])
if "__error__" not in call("search_board", query="Bo", day="yesterday"):
    fails.append("a bad day was not refused")
# board time: "filler 0" is stored 2026-09-28T00:00 UTC, which is 8pm on
# the 27th in Ann Arbor — the day filter has to say so
if call("search_board", query="filler 0", day="2026-09-27")["matches"] != 1:
    fails.append("day filter is not in board time (UTC midnight is still yesterday)")
if call("search_board", query="filler 0", day="2026-09-28")["matches"] != 0:
    fails.append("day filter is in UTC, not board time")

# --- 6. aliases carry both names ------------------------------------------
a = call("get_post", post_id=costume)
if a["author"] != "Ken" or a.get("alias") != "Obitman":
    fails.append("alias post should be author=member, alias=shown: %s" % a)
if "alias" in call("get_post", post_id=root):
    fails.append("a plain post carries an alias field")
# a reply links to itself; the thread is a separate link
rep1 = call("get_post", post_id=root + 1)
if not rep1["url"].endswith("/message/%d" % (root + 1)) or not rep1["thread_url"].endswith("/message/%d" % root):
    fails.append("reply url/thread_url wrong: %s %s" % (rep1["url"], rep1["thread_url"]))
if call("search_board", query="Obituaries", author="Obitman")["matches"] != 1:
    fails.append("author filter does not match an alias")

# --- caps and the rate limit ----------------------------------------------
if len(call("search_board", query="e", limit=999)["results"]) > mcp_server.MAX_RESULTS:
    fails.append("search limit is not clamped")
mcp_server._hits.clear()
codes = [c.post("/mcp", content_type="application/json",
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
                ).status_code for _ in range(mcp_server.RATE_LIMIT + 5)]
if 429 not in codes or codes[0] != 200:
    fails.append("the rate limit did not fire correctly")
mcp_server._hits.clear()

# ------------------------------------------------- read-only, and no leaks

with appmod.app.test_request_context("/mcp"):
    try:
        mcp_server._db().execute(
            "INSERT INTO messages (subject, author_name, created_at)"
            " VALUES ('hijack', 'nobody', '2026-01-01')")
        fails.append("the MCP connection accepted a write")
    except sqlite3.OperationalError:
        pass

harvest = []
for name, args in (
        ("search_board", {"query": "e", "limit": 25}),
        ("search_board", {"query": "e", "limit": 25, "offset": 25}),
        ("get_posts", {"since_id": 0, "limit": 200}),
        ("get_post", {"post_id": root}),
        ("get_thread", {"thread_id": root}),
        ("recent_threads", {"limit": 50}),
        ("hall_of_fame", {"limit": 25}),
        ("board_stats", {}),
        ("pickem_standings", {}),
        ("arcade_stats", {})):
    mcp_server._hits.clear()
    _, out = rpc("tools/call", {"name": name, "arguments": args})
    harvest.append(json.dumps(out))
blob = "\n".join(harvest)
for probe, what in ((SECRET_IP, "ip_address"), (SECRET_PW, "password_hash"),
                    ("session-token", "session_token"), ("deadbeefvisitor", "visitor hashes")):
    if call("search_board", query=probe).get("matches"):
        fails.append("LEAK — search reaches %s" % what)
for needle, what in ((SECRET_IP, "a poster's IP address"), ("pbkdf2:", "a password hash"),
                     ("scrypt:", "a password hash"), ("session-token-", "a session token"),
                     ("deadbeefvisitor", "a visitor hash"), ("password_hash", "the password column"),
                     ("ip_address", "the address column"), ("is_admin", "account flags")):
    if needle in blob:
        fails.append("LEAK — %s reached a tool response" % what)
for handle in ("Ken", "Rich", "Nikos"):
    if handle in json.dumps(call("arcade_stats")):
        fails.append("arcade_stats named %s — that table needs a login" % handle)
for path in ("/", "/scores", "/stats", "/message/%d" % root):
    if c.get(path).status_code != 200:
        fails.append("mounting the MCP server broke %s" % path)

print("%d tools, protocol %s" % (len(mcp_server.TOOLS), mcp_server.LATEST))
print("FAILURES:\n  " + "\n  ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
