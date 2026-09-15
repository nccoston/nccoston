#!/usr/bin/env python3
"""An MCP server for The Victors, mounted on the board itself.

Model Context Protocol lets an AI assistant call tools over the network. This
module turns the board into one: point Claude (or any MCP client) at
https://<board>/mcp and it can search thirty years of posts, read a thread,
and look up the standings.

Three decisions worth writing down, because they're the whole design:

1. READ ONLY, STRUCTURALLY. Not "I was careful not to write any INSERTs" —
   this module opens its own SQLite connection in `mode=ro`, so the database
   driver itself refuses a write. Nothing here can post, edit, or delete,
   even if a future edit to this file tried to.

2. NOTHING PRIVATE, BY A RULE THAT CAN BE TESTED. The board is already
   readable logged out: threads, search, the Hall of Fame, the pick 'em
   standings and /stats are all public URLs with an RSS feed alongside them.
   So the rule is: this server may return exactly what a logged-out browser
   can already see, and nothing else. Both arcade leaderboards are behind a
   login, so those come back as counts with no handles attached. Addresses,
   password hashes, session tokens, read marks and visitor hashes are not
   reachable from any tool here.

3. NO NEW SERVICE AND NO NEW DEPENDENCY. It's a Flask blueprint on the
   existing app, so it deploys with the board and costs nothing extra. MCP's
   Streamable HTTP transport is JSON-RPC 2.0 over a single POST endpoint,
   which is about two hundred lines — cheaper than bolting an ASGI server
   onto a synchronous WSGI app that runs one worker in 512MB.

The board pays for its own bandwidth, so every tool has a hard ceiling on
how much it will return and there's a per-address rate limit in front.
"""

import json
import re
import sqlite3
import threading
import time
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape

from flask import Blueprint, Response, g, jsonify, request

# MCP revisions this server understands. A client asking for one of these
# gets it back; anything else is answered with our newest and the client
# decides whether to continue.
SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST = SUPPORTED[0]

SERVER_NAME = "the-victors-board"
SERVER_VERSION = "1.0.0"

# Ceilings. The board is on a $7 instance with a monthly bandwidth
# allowance it has already blown through once, so nothing here is unbounded.
MAX_RESULTS = 25          # search hits, HOF posts
MAX_THREADS = 50          # recent threads
MAX_REPLIES = 200         # replies returned for one thread
BODY_CHARS = 1200         # a post is truncated past this
RATE_LIMIT = 30           # requests...
RATE_WINDOW = 60          # ...per address per minute

mcp = Blueprint("mcp", __name__)

_hits = defaultdict(deque)
_hits_lock = threading.Lock()

_config = {"db_path": None, "site_url": "", "token": None}


# ------------------------------------------------------------------ plumbing

def _db():
    """A private, read-only handle. Separate from the board's own connection
    on purpose: `mode=ro` is enforced by SQLite, not by this file's good
    intentions. Opened per request — it's a local file, so it's cheap."""
    conn = getattr(g, "_mcp_db", None)
    if conn is None:
        conn = sqlite3.connect("file:%s?mode=ro" % _config["db_path"],
                               uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        g._mcp_db = conn
    return conn


@mcp.teardown_request
def _close_db(_exc):
    conn = g.pop("_mcp_db", None)
    if conn is not None:
        conn.close()


def _caller():
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "?"


def _rate_limited():
    now = time.time()
    with _hits_lock:
        q = _hits[_caller()]
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return True
        q.append(now)
        # don't let the table grow forever on a board that gets crawled
        if len(_hits) > 2000:
            for addr in [a for a, d in _hits.items() if not d]:
                del _hits[addr]
    return False


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _plain(text, limit=BODY_CHARS):
    """Posts may contain safe HTML and the old board's markup. An AI wants
    the words, not the tags."""
    if not text:
        return ""
    flat = _WS.sub(" ", unescape(_TAG.sub(" ", text))).strip()
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


def _when(stamp):
    """Timestamps are stored naive UTC. Hand out something unambiguous."""
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(stamp)
    except ValueError:
        return stamp
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _url(path):
    return (_config["site_url"] or "").rstrip("/") + path


def _post(row, body=True):
    out = {
        "id": row["id"],
        "thread_id": row["thread_id"],
        "subject": row["subject"],
        "author": row["author_name"],
        "posted_at": _when(row["created_at"]),
        "board": row["board"] if "board" in row.keys() else "main",
        "url": _url("/message/%d" % (row["thread_id"] or row["id"])),
    }
    if body:
        out["body"] = _plain(row["body"])
    if "hof_at" in row.keys() and row["hof_at"]:
        out["hall_of_fame"] = True
    return out


# -------------------------------------------------------------------- tools
#
# Every one of these is a SELECT against the read-only handle, and every one
# returns only what /, /message, /search, /hof, /stats and /scores/leaderboard
# already show to a logged-out visitor.

BOARD_NAMES = ("main", "scores", "cards")


def t_search_board(query="", board=None, author=None, limit=10):
    """Subject, body and author, newest first — the same LIKE the board's own
    search box runs."""
    query = (query or "").strip()
    if not query:
        raise ValueError("query is required")
    limit = max(1, min(int(limit or 10), MAX_RESULTS))
    sql = ("SELECT id, thread_id, subject, body, author_name, created_at,"
           " board, hof_at FROM messages WHERE (subject LIKE ? OR body LIKE ?)")
    like = "%%%s%%" % query
    args = [like, like]
    if board:
        if board not in BOARD_NAMES:
            raise ValueError("board must be one of: %s" % ", ".join(BOARD_NAMES))
        sql += " AND board = ?"
        args.append(board)
    if author:
        sql += " AND author_name LIKE ?"
        args.append("%%%s%%" % author)
    # id breaks the tie: on game day a dozen posts can share a second, and
    # without it "newest first" is whatever order SQLite feels like
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(limit)
    rows = _db().execute(sql, args).fetchall()
    return {"query": query, "matches": len(rows),
            "results": [_post(r) for r in rows]}


def t_get_thread(thread_id, limit=MAX_REPLIES):
    """A whole conversation in order, root first."""
    limit = max(1, min(int(limit or MAX_REPLIES), MAX_REPLIES))
    db = _db()
    root = db.execute(
        "SELECT id, thread_id, subject, body, author_name, created_at, board,"
        " hof_at FROM messages WHERE id = ? AND parent_id IS NULL",
        (int(thread_id),)).fetchone()
    if root is None:
        # they may have handed us a reply's id; find its thread
        child = db.execute("SELECT thread_id FROM messages WHERE id = ?",
                           (int(thread_id),)).fetchone()
        if child is None or child["thread_id"] is None:
            raise ValueError("no thread with id %s" % thread_id)
        return t_get_thread(child["thread_id"], limit)
    replies = db.execute(
        "SELECT id, thread_id, subject, body, author_name, created_at, board,"
        " hof_at FROM messages WHERE thread_id = ? AND id != ?"
        " ORDER BY created_at LIMIT ?", (root["id"], root["id"], limit)).fetchall()
    total = db.execute(
        "SELECT COUNT(*) c FROM messages WHERE thread_id = ? AND id != ?",
        (root["id"], root["id"])).fetchone()["c"]
    return {"thread": _post(root), "reply_count": total,
            "replies_returned": len(replies),
            "replies": [_post(r) for r in replies]}


def t_recent_threads(board="main", limit=15):
    """What the board is talking about right now."""
    board = board or "main"
    if board not in BOARD_NAMES:
        raise ValueError("board must be one of: %s" % ", ".join(BOARD_NAMES))
    limit = max(1, min(int(limit or 15), MAX_THREADS))
    rows = _db().execute(
        "SELECT m.id, m.thread_id, m.subject, m.body, m.author_name,"
        " m.created_at, m.board, m.hof_at,"
        " (SELECT COUNT(*) FROM messages r WHERE r.thread_id = m.id"
        "  AND r.id != m.id) replies,"
        " (SELECT MAX(r.created_at) FROM messages r WHERE r.thread_id = m.id) last_at"
        " FROM messages m WHERE m.parent_id IS NULL AND m.board = ?"
        " ORDER BY m.created_at DESC, m.id DESC LIMIT ?", (board, limit)).fetchall()
    out = []
    for r in rows:
        item = _post(r, body=False)
        item["replies"] = r["replies"]
        item["last_activity"] = _when(r["last_at"])
        out.append(item)
    return {"board": board, "threads": out}


def t_hall_of_fame(limit=10):
    """Posts the members voted in. The board's own canon."""
    limit = max(1, min(int(limit or 10), MAX_RESULTS))
    db = _db()
    rows = db.execute(
        "SELECT id, thread_id, subject, body, author_name, created_at, board,"
        " hof_at FROM messages WHERE hof_at IS NOT NULL"
        " ORDER BY hof_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
    total = db.execute("SELECT COUNT(*) c FROM messages"
                       " WHERE hof_at IS NOT NULL").fetchone()["c"]
    posts = []
    for r in rows:
        p = _post(r)
        p["enshrined_at"] = _when(r["hof_at"])
        posts.append(p)
    return {"total_enshrined": total, "posts": posts}


def t_board_stats():
    """The same figures /stats puts on a public page."""
    db = _db()
    one = lambda sql: db.execute(sql).fetchone()["c"]
    first = db.execute("SELECT MIN(created_at) c FROM messages").fetchone()["c"]
    today = db.execute("SELECT day, pageviews, uniques FROM traffic"
                       " ORDER BY day DESC LIMIT 1").fetchone()
    busiest = db.execute("SELECT day, pageviews FROM traffic"
                         " ORDER BY pageviews DESC LIMIT 1").fetchone()
    top = db.execute("SELECT author_name, COUNT(*) c FROM messages"
                     " GROUP BY author_name ORDER BY c DESC, author_name"
                     " LIMIT 10").fetchall()
    return {
        "members": one("SELECT COUNT(*) c FROM users"),
        "messages": one("SELECT COUNT(*) c FROM messages"),
        "threads": one("SELECT COUNT(*) c FROM messages WHERE parent_id IS NULL"),
        "hall_of_fame_posts": one("SELECT COUNT(*) c FROM messages"
                                  " WHERE hof_at IS NOT NULL"),
        "oldest_post": _when(first),
        "latest_day": ({"day": today["day"], "pageviews": today["pageviews"],
                        "unique_visitors": today["uniques"]} if today else None),
        "busiest_day": ({"day": busiest["day"], "pageviews": busiest["pageviews"]}
                        if busiest else None),
        "top_posters": [{"handle": r["author_name"], "posts": r["c"]} for r in top],
        "url": _url("/stats"),
    }


def t_pickem_standings(limit=25):
    """The weekly score-prediction game. Scoring is closest to the final
    total, win or lose — which is how this board has always done it, and is
    not the same thing as picking the winner."""
    limit = max(1, min(int(limit or 25), MAX_RESULTS))
    db = _db()
    decided = db.execute(
        "SELECT id, team_a, team_b, final_a, final_b FROM games"
        " WHERE final_a IS NOT NULL AND final_b IS NOT NULL").fetchall()
    won = defaultdict(int)
    entered = defaultdict(int)
    for game in decided:
        picks = db.execute(
            "SELECT p.pick_a, p.pick_b, u.handle FROM game_picks p"
            " JOIN users u ON u.id = p.user_id WHERE p.game_id = ?",
            (game["id"],)).fetchall()
        if not picks:
            continue
        best, winners = None, []
        for p in picks:
            entered[p["handle"]] += 1
            off = (abs(p["pick_a"] - game["final_a"])
                   + abs(p["pick_b"] - game["final_b"]))
            if best is None or off < best:
                best, winners = off, [p["handle"]]
            elif off == best:
                winners.append(p["handle"])
        for h in winners:
            won[h] += 1
    table = sorted(entered, key=lambda h: (-won[h], -entered[h], h))[:limit]
    return {
        "games_decided": len(decided),
        "scoring": "closest to the final score, win or lose",
        "standings": [{"handle": h, "weeks_won": won[h],
                       "weeks_entered": entered[h]} for h in table],
        "url": _url("/scores/leaderboard"),
    }


def t_arcade_stats():
    """Both arcade leaderboards are behind a login on the board, so this
    returns totals only — no handles, no per-member rows."""
    db = _db()
    def agg(sql, default=None):
        try:
            return db.execute(sql).fetchone()
        except sqlite3.Error:
            return default
    bowl = agg("SELECT COUNT(*) players, SUM(games) games, MAX(best_w) best_w,"
               " MAX(longest_td) longest_td, MAX(most_points) most_points"
               " FROM bowl_scores WHERE games > 0")
    stad = agg("SELECT COUNT(*) players, SUM(games) games, SUM(rounds) rounds,"
               " MAX(best) best, MIN(closest) closest, SUM(bullseyes) bullseyes"
               " FROM stadium_scores WHERE games > 0")
    out = {"note": "totals only — the leaderboards themselves require a login"}
    if bowl and bowl["players"]:
        out["victard_bowl"] = {
            "players": bowl["players"], "games_played": bowl["games"] or 0,
            "best_season_wins": bowl["best_w"] or 0,
            "longest_play_yards": bowl["longest_td"] or 0,
            "most_points_in_a_game": bowl["most_points"] or 0,
        }
    if stad and stad["players"]:
        out["stadium_guesser"] = {
            "players": stad["players"], "games_played": stad["games"] or 0,
            "rounds_played": stad["rounds"] or 0,
            "best_round_of_five": stad["best"] or 0,
            "closest_guess_miles": (round(stad["closest"], 1)
                                    if stad["closest"] is not None else None),
            "bullseyes_within_25_miles": stad["bullseyes"] or 0,
        }
    out["url"] = _url("/games")
    return out


TOOLS = [
    {
        "name": "search_board",
        "title": "Search the board",
        "description": (
            "Search thirty years of posts on The Victors, a Michigan football "
            "message board running since 1995. Matches subject and body, "
            "newest first. Optionally narrow to one board or one author."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "Text to look for in subjects and bodies."},
                "board": {"type": "string", "enum": list(BOARD_NAMES),
                          "description": "main (general), scores (game threads "
                                         "and pick 'em), or cards."},
                "author": {"type": "string",
                           "description": "Restrict to posts by this handle."},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS,
                          "default": 10},
            },
            "required": ["query"],
        },
        "fn": t_search_board,
    },
    {
        "name": "get_thread",
        "title": "Read a thread",
        "description": ("Return a whole conversation — the opening post and its "
                        "replies in order. Accepts a thread id or any reply's id."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "integer",
                              "description": "Message id, from a search result."},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_REPLIES,
                          "default": MAX_REPLIES},
            },
            "required": ["thread_id"],
        },
        "fn": t_get_thread,
    },
    {
        "name": "recent_threads",
        "title": "What's being discussed",
        "description": ("The newest threads on a board, with reply counts and "
                        "last activity. Use this to see what the community is "
                        "talking about now."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "board": {"type": "string", "enum": list(BOARD_NAMES),
                          "default": "main"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_THREADS,
                          "default": 15},
            },
        },
        "fn": t_recent_threads,
    },
    {
        "name": "hall_of_fame",
        "title": "Hall of Fame posts",
        "description": ("Posts the members voted into the board's Hall of Fame. "
                        "The best single answer to 'what is this community like'."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS,
                          "default": 10},
            },
        },
        "fn": t_hall_of_fame,
    },
    {
        "name": "board_stats",
        "title": "Board statistics",
        "description": ("Members, posts, threads, traffic for the latest and "
                        "busiest days, and the most prolific posters."),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": t_board_stats,
    },
    {
        "name": "pickem_standings",
        "title": "Pick 'em standings",
        "description": ("Standings for the weekly score-prediction game. Scored "
                        "by closest to the final score, win or lose — picking "
                        "the winning team is not what scores."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS,
                          "default": 25},
            },
        },
        "fn": t_pickem_standings,
    },
    {
        "name": "arcade_stats",
        "title": "Arcade totals",
        "description": ("Totals for the two games built for the board — Victard "
                        "Bowl and Stadium Guesser. Counts only; the leaderboards "
                        "themselves are behind a member login."),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": t_arcade_stats,
    },
]

BY_NAME = {t["name"]: t for t in TOOLS}


# ---------------------------------------------------------------- resources

ABOUT = """The Victors — a Michigan football message board, continuously
running since 1995.

The community began on a fan-run recruiting board in 1995, moved to the
"VV board" in 1996, became The Victors around 1999, and spent decades on a
free 1998-era host. In the summer of 2026 that host died without warning and
without an export. The board was rebuilt in six evenings and self-hosted from
August 2026, carrying its history with it.

It has three boards: main (general discussion), scores (game threads, the
live college scoreboard, and the weekly pick 'em) and cards.

Conventions that will otherwise look like bugs:
- A subject line ending in an asterisk means the subject IS the whole post.
  There is no body to fetch.
- "Skeeps" is a reserved account, not a person. It posts the weekly pick 'em
  thread and the monthly arcade standings.
- The pick 'em is scored by closest to the final score, win or lose. Picking
  the winning team is not what scores, which confuses nearly everyone once.
- The board tracks Slippery Rock, a Division II school in Pennsylvania, for
  reasons every Michigan fan understands and nobody else ever will.
"""


RESOURCES = [
    {"uri": "victors://about",
     "name": "About The Victors",
     "description": "What this community is, and the conventions an outsider "
                    "will misread.",
     "mimeType": "text/plain",
     "text": lambda: ABOUT},
    {"uri": "victors://boards",
     "name": "Boards and post counts",
     "description": "The three boards and how much is on each.",
     "mimeType": "application/json",
     "text": lambda: json.dumps({
         "boards": [
             {"name": r["board"], "posts": r["c"],
              "url": _url("/" if r["board"] == "main" else "/" + r["board"])}
             for r in _db().execute(
                 "SELECT board, COUNT(*) c FROM messages GROUP BY board"
                 " ORDER BY c DESC")
         ]}, indent=2)},
]

BY_URI = {r["uri"]: r for r in RESOURCES}


# -------------------------------------------------------------- the protocol

def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code, message, data=None):
    body = {"code": code, "message": message}
    if data is not None:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": body}


def _handle(msg):
    """One JSON-RPC message in, one response out — or None for a
    notification, which by the spec gets no reply."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _err(None, -32600, "Not a JSON-RPC 2.0 message")
    method = msg.get("method")
    rid = msg.get("id")
    params = msg.get("params") or {}
    is_notification = "id" not in msg

    if method == "initialize":
        asked = (params.get("protocolVersion") or "").strip()
        return _ok(rid, {
            "protocolVersion": asked if asked in SUPPORTED else LATEST,
            "capabilities": {"tools": {"listChanged": False},
                             "resources": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION,
                           "title": "The Victors"},
            "instructions": (
                "Read-only access to a Michigan football message board running "
                "since 1995. Start with recent_threads to see what's live, or "
                "search_board for history. Read victors://about first if you "
                "plan to interpret anything — the board has conventions that "
                "look like data errors and aren't."),
        })

    if is_notification:
        return None            # initialized, cancelled, progress: nothing to say

    if method == "ping":
        return _ok(rid, {})

    if method == "tools/list":
        return _ok(rid, {"tools": [
            {k: t[k] for k in ("name", "title", "description", "inputSchema")}
            for t in TOOLS]})

    if method == "tools/call":
        name = params.get("name")
        tool = BY_NAME.get(name)
        if tool is None:
            return _err(rid, -32602, "No such tool: %s" % name)
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _err(rid, -32602, "arguments must be an object")
        try:
            payload = tool["fn"](**args)
        except TypeError as e:
            return _err(rid, -32602, "Bad arguments for %s: %s" % (name, e))
        except ValueError as e:
            # the model's fault, not the server's — hand it back as tool
            # output so it can correct itself rather than as a transport error
            return _ok(rid, {"content": [{"type": "text", "text": str(e)}],
                             "isError": True})
        except sqlite3.Error as e:
            return _err(rid, -32603, "Database error: %s" % e)
        return _ok(rid, {
            "content": [{"type": "text",
                         "text": json.dumps(payload, indent=2, default=str)}],
            "isError": False})

    if method == "resources/list":
        return _ok(rid, {"resources": [
            {k: r[k] for k in ("uri", "name", "description", "mimeType")}
            for r in RESOURCES]})

    if method == "resources/read":
        uri = params.get("uri")
        res = BY_URI.get(uri)
        if res is None:
            return _err(rid, -32602, "No such resource: %s" % uri)
        return _ok(rid, {"contents": [{"uri": uri, "mimeType": res["mimeType"],
                                       "text": res["text"]()}]})

    if method in ("prompts/list", "resources/templates/list"):
        return _ok(rid, {"prompts": []} if method.startswith("prompts")
                   else {"resourceTemplates": []})

    return _err(rid, -32601, "Method not found: %s" % method)


@mcp.route("/mcp", methods=["POST"])
def endpoint():
    if _config["token"]:
        sent = request.headers.get("Authorization", "")
        if sent != "Bearer " + _config["token"]:
            return jsonify({"error": "unauthorized"}), 401
    if _rate_limited():
        return (jsonify(_err(None, -32000, "Rate limit: %d requests a minute."
                             % RATE_LIMIT)), 429, {"Retry-After": "60"})
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify(_err(None, -32700, "Parse error")), 400

    batch = isinstance(payload, list)
    messages = payload if batch else [payload]
    if batch and not messages:
        return jsonify(_err(None, -32600, "Empty batch")), 400

    replies = [r for r in (_handle(m) for m in messages) if r is not None]
    headers = {"MCP-Protocol-Version": LATEST}
    if not replies:
        # everything was a notification; the spec wants 202 and no body
        return Response(status=202, headers=headers)
    body = replies if batch else replies[0]
    return Response(json.dumps(body), status=200, headers=headers,
                    mimetype="application/json")


@mcp.route("/mcp", methods=["GET"])
def no_stream():
    """Streamable HTTP lets a server offer a server-initiated SSE stream on
    GET. This one has nothing to push, and the spec says say so plainly."""
    return (jsonify({"error": "This server does not offer an event stream. "
                              "POST JSON-RPC to this same URL."}), 405,
            {"Allow": "POST"})


def register_mcp(app, db_path, site_url="", token=None):
    """Mount the server on the board. Called once from app.py."""
    _config["db_path"] = str(db_path)
    _config["site_url"] = site_url or ""
    _config["token"] = token or None
    app.register_blueprint(mcp)
    return mcp
