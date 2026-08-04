#!/usr/bin/env python3
"""The Victors board — self-hosted replacement for the old Boards2Go board.

Flask + SQLite. Threaded messages, handles, subject-only posts, image embeds,
search, admin tools. Run locally:

    pip install -r requirements.txt
    python app.py            # http://localhost:8080

Production:  gunicorn -b 0.0.0.0:8080 app:app
Data lives in $DATA_DIR/board.db (default ./data/board.db).
The FIRST account registered automatically becomes an admin.
"""

import os
import re
import sqlite3
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from markupsafe import Markup
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", APP_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "board.db"
SECRET_FILE = DATA_DIR / "secret_key"

THREADS_PER_PAGE = 80
BOARDS = ("main", "scores")
BOARD_TZ = ZoneInfo(os.environ.get("BOARD_TZ", "America/Detroit"))


def now_utc_iso():
    """Timestamps are stored as naive UTC; displayed in the board timezone."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

app = Flask(__name__)
# behind Render's proxy: trust X-Forwarded-For so remote_addr is the real client
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # uploaded image cap
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)  # stay logged in
if os.environ.get("SECRET_KEY"):
    app.secret_key = os.environ["SECRET_KEY"]
else:
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_hex(32))
    app.secret_key = SECRET_FILE.read_text().strip()

DEFAULT_SETTINGS = {
    "site_title": "The Victors",
    "registration_open": "1",
    "header_html": (
        "<b>Rules:</b>"
        "<ol>"
        "<li><b>No porno.</b></li>"
        "<li><b>Please use a \"*\" or \"nm\" in the subject line to denote "
        "topic only posts.</b></li>"
        "<li><b>Any post or attempt to take things \"off the board\" will result "
        "in a ban. Do not use other poster's real names or personal info.</b></li>"
        "<li><b>Don't be a Tom Izzo.</b></li>"
        "</ol>"
        "<p><b>Admins</b> - Rich, BBA, Nikos<br>"
        "<b>Ceremonial Moderator</b> - the wino<br>"
        "<b>Honorary Moderators</b> - BigLake, Blue Man</p>"
    ),
    "links_html": (
        '<a href="https://www.mgoblog.com">MGoBlog</a> || '
        '<a href="https://umhoops.com">UMHoops</a>'
    ),
}


# ----------------------------------------------------------------- database

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript((APP_DIR / "schema.sql").read_text())
    # migrations for databases created before a column existed
    for migration in ("ALTER TABLE messages ADD COLUMN edited_at TEXT",
                      "ALTER TABLE messages ADD COLUMN ip_address TEXT",
                      "ALTER TABLE messages ADD COLUMN board TEXT NOT NULL DEFAULT 'main'"):
        try:
            db.execute(migration)
        except sqlite3.OperationalError:
            pass  # column already there
    for key, value in DEFAULT_SETTINGS.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                   (key, value))
    db.commit()
    db.close()


def get_setting(key):
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else DEFAULT_SETTINGS.get(key, "")


def set_setting(key, value):
    db = get_db()
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    db.commit()


# --------------------------------------------------------------- auth utils

def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            flash("Please log in first.")
            return redirect(url_for("login", next=request.path))
        if user["is_banned"]:
            session.clear()
            flash("This account is banned.")
            return redirect(url_for("index", board_name="main"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None or not user["is_admin"]:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------- template helpers

from postmarkup import render_post


@app.template_filter("boardtime")
def boardtime(iso):
    """Stored UTC timestamp -> 'July 31, 2026 at 07:55:25 PM' in board time."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(BOARD_TZ)
    out = dt.strftime("%B %d, %Y at %I:%M:%S %p")
    return re.sub(r" 0(\d,)", r" \1", out)  # strip leading zero on day


@app.template_filter("rendertext")
def rendertext(text):
    """Render a post body: safe-HTML subset, auto-linked URLs, newlines kept."""
    return Markup(render_post(text))


@app.context_processor
def inject_globals():
    return {
        "user": current_user(),
        "site_title": get_setting("site_title"),
        "header_html": get_setting("header_html"),
        "links_html": get_setting("links_html"),
    }


def build_tree(rows):
    """rows (any order) -> list of root dicts with nested 'children' lists."""
    nodes = {r["id"]: dict(r, children=[]) for r in rows}
    roots = []
    for node in nodes.values():
        pid = node["parent_id"]
        if pid and pid in nodes:
            nodes[pid]["children"].append(node)
        else:
            roots.append(node)
    # newest replies first, matching the old board
    for node in nodes.values():
        node["children"].sort(key=lambda n: n["created_at"], reverse=True)
    return roots


# -------------------------------------------------------------------- pages

@app.route("/", defaults={"board_name": "main"})
@app.route("/scores", defaults={"board_name": "scores"})
def index(board_name):
    page = max(1, request.args.get("page", 1, type=int))
    db = get_db()
    total_roots = db.execute(
        "SELECT COUNT(*) c FROM messages WHERE parent_id IS NULL AND board = ?",
        (board_name,)).fetchone()["c"]
    pages = max(1, -(-total_roots // THREADS_PER_PAGE))
    offset = (page - 1) * THREADS_PER_PAGE
    root_ids = [r["id"] for r in db.execute(
        "SELECT id FROM messages WHERE parent_id IS NULL AND board = ? "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (board_name, THREADS_PER_PAGE, offset))]
    threads = []
    if root_ids:
        marks = ",".join("?" * len(root_ids))
        rows = db.execute(
            f"SELECT * FROM messages WHERE thread_id IN ({marks})", root_ids).fetchall()
        by_thread = {}
        for root in build_tree(rows):
            by_thread[root["id"]] = root
        threads = [by_thread[rid] for rid in root_ids if rid in by_thread]
        poll_ids = {r["message_id"] for r in db.execute(
            f"SELECT message_id FROM polls WHERE message_id IN ({marks})", root_ids)}
        game_ids = {r["message_id"] for r in db.execute(
            f"SELECT message_id FROM games WHERE message_id IN ({marks})", root_ids)}
        for t in threads:
            t["has_poll"] = t["id"] in poll_ids
            t["has_game"] = t["id"] in game_ids
    return render_template("index.html", threads=threads, page=page, pages=pages,
                           board_name=board_name)


@app.route("/message/<int:message_id>")
def message(message_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg is None:
        abort(404)
    thread_rows = db.execute(
        "SELECT * FROM messages WHERE thread_id = ?", (msg["thread_id"],)).fetchall()
    roots = build_tree(thread_rows)

    # find this message's node in the tree to list its replies
    def find_node(nodes, target):
        for n in nodes:
            if n["id"] == target:
                return n
            hit = find_node(n["children"], target)
            if hit:
                return hit
        return None

    node = find_node(roots, message_id)
    parent = None
    if msg["parent_id"]:
        parent = db.execute("SELECT * FROM messages WHERE id = ?",
                            (msg["parent_id"],)).fetchone()
    reply_subject = msg["subject"]
    if not reply_subject.lower().startswith("re"):
        reply_subject = "Re: " + reply_subject

    poll = db.execute("SELECT * FROM polls WHERE message_id = ?",
                      (message_id,)).fetchone()
    poll_options, my_vote, total_votes = [], None, 0
    if poll:
        poll_options = db.execute(
            "SELECT o.id, o.text, COUNT(v.id) votes FROM poll_options o"
            " LEFT JOIN poll_votes v ON v.option_id = o.id"
            " WHERE o.poll_id = ? GROUP BY o.id, o.text ORDER BY o.id",
            (poll["id"],)).fetchall()
        total_votes = sum(r["votes"] for r in poll_options)
        u = current_user()
        if u:
            row = db.execute(
                "SELECT option_id FROM poll_votes WHERE poll_id = ? AND user_id = ?",
                (poll["id"], u["id"])).fetchone()
            my_vote = row["option_id"] if row else None
    game = db.execute("SELECT * FROM games WHERE message_id = ?",
                      (message_id,)).fetchone()
    game_picks, my_pick, game_winners = [], None, []
    if game:
        game_picks = db.execute(
            "SELECT p.*, u.handle h FROM game_picks p JOIN users u ON u.id = p.user_id"
            " WHERE p.game_id = ? ORDER BY p.created_at", (game["id"],)).fetchall()
        u = current_user()
        if u:
            my_pick = next((p for p in game_picks if p["user_id"] == u["id"]), None)
        if game["final_a"] is not None and game_picks:
            def miss(p):
                return (abs(p["pick_a"] - game["final_a"])
                        + abs(p["pick_b"] - game["final_b"]))
            best = min(miss(p) for p in game_picks)
            game_winners = [p["h"] for p in game_picks if miss(p) == best]
    return render_template("message.html", msg=msg, parent=parent,
                           children=node["children"] if node else [],
                           reply_subject=reply_subject, poll=poll,
                           poll_options=poll_options, my_vote=my_vote,
                           total_votes=total_votes, game=game,
                           game_picks=game_picks, my_pick=my_pick,
                           game_winners=game_winners)


def save_uploaded_image():
    """Store an uploaded picture on the data disk; return its serving path."""
    f = request.files.get("image_file")
    if not f or not f.filename:
        return None
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        flash("Image uploads must be jpg, png, gif, or webp.")
        return None
    name = secrets.token_hex(8) + ext
    f.save(UPLOAD_DIR / name)
    return url_for("uploads", filename=name)


@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/post", methods=["GET", "POST"])
@app.route("/post/<int:reply_to>", methods=["GET", "POST"])
@login_required
def post(reply_to=None):
    db = get_db()
    parent = None
    if reply_to is not None:
        parent = db.execute("SELECT * FROM messages WHERE id = ?", (reply_to,)).fetchone()
        if parent is None:
            abort(404)
    board = request.form.get("board") or request.args.get("board") or "main"
    if board not in BOARDS:
        board = "main"
    if parent is not None:
        board = parent["board"]
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        image_url = request.form.get("image_url", "").strip()
        poll_lines = [ln.strip() for ln in
                      request.form.get("poll_options", "").splitlines() if ln.strip()][:10]
        if not subject:
            flash("A subject is required.")
        elif parent is None and len(poll_lines) == 1:
            flash("A poll needs at least two options (one per line).")
        else:
            if image_url and not image_url.lower().startswith(("http://", "https://")):
                image_url = ""
            uploaded = save_uploaded_image()
            if uploaded:
                image_url = uploaded
            user = current_user()
            now = now_utc_iso()
            cur = db.execute(
                "INSERT INTO messages (thread_id, parent_id, subject, body,"
                " image_url, author_name, user_id, created_at, ip_address, board)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (parent["thread_id"] if parent else None,
                 parent["id"] if parent else None,
                 subject, body or None, image_url or None,
                 user["handle"], user["id"], now, request.remote_addr, board))
            new_id = cur.lastrowid
            if parent is None:
                db.execute("UPDATE messages SET thread_id = ? WHERE id = ?",
                           (new_id, new_id))
                if len(poll_lines) >= 2:
                    pcur = db.execute(
                        "INSERT INTO polls (message_id, created_at) VALUES (?, ?)",
                        (new_id, now))
                    for line in poll_lines:
                        db.execute(
                            "INSERT INTO poll_options (poll_id, text) VALUES (?, ?)",
                            (pcur.lastrowid, line[:200]))
                team_a = request.form.get("team_a", "").strip()[:60]
                team_b = request.form.get("team_b", "").strip()[:60]
                if board == "scores" and team_a and team_b:
                    db.execute(
                        "INSERT INTO games (message_id, team_a, team_b, created_at)"
                        " VALUES (?, ?, ?, ?)", (new_id, team_a, team_b, now))
            db.commit()
            return redirect(url_for("message", message_id=new_id))
    subject_prefill = ""
    if parent is not None:
        subject_prefill = parent["subject"]
        if not subject_prefill.lower().startswith("re:"):
            subject_prefill = "Re: " + subject_prefill
    return render_template("post.html", parent=parent, subject_prefill=subject_prefill,
                           board=board)


@app.route("/poll/<int:poll_id>/vote", methods=["POST"])
@login_required
def poll_vote(poll_id):
    db = get_db()
    poll = db.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()
    if poll is None:
        abort(404)
    option_id = request.form.get("option_id", type=int)
    valid = db.execute("SELECT 1 FROM poll_options WHERE id = ? AND poll_id = ?",
                       (option_id, poll_id)).fetchone()
    if valid is None:
        flash("Pick an option to vote.")
    else:
        db.execute(
            "INSERT INTO poll_votes (poll_id, option_id, user_id, created_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(poll_id, user_id) DO UPDATE SET option_id = excluded.option_id",
            (poll_id, option_id, current_user()["id"],
             now_utc_iso()))
        db.commit()
    return redirect(url_for("message", message_id=poll["message_id"]))


@app.route("/game/<int:game_id>/pick", methods=["POST"])
@login_required
def game_pick(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        abort(404)
    if game["final_a"] is not None:
        flash("Picks are locked — the final score is in.")
        return redirect(url_for("message", message_id=game["message_id"]))
    pick_a = request.form.get("pick_a", type=int)
    pick_b = request.form.get("pick_b", type=int)
    if pick_a is None or pick_b is None or not (0 <= pick_a <= 999 and 0 <= pick_b <= 999):
        flash("Enter a score for both teams.")
    else:
        db.execute(
            "INSERT INTO game_picks (game_id, user_id, pick_a, pick_b, created_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(game_id, user_id) DO UPDATE SET"
            " pick_a = excluded.pick_a, pick_b = excluded.pick_b,"
            " created_at = excluded.created_at",
            (game_id, current_user()["id"], pick_a, pick_b, now_utc_iso()))
        db.commit()
    return redirect(url_for("message", message_id=game["message_id"]))


@app.route("/game/<int:game_id>/final", methods=["POST"])
@login_required
def game_final(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        abort(404)
    msg = db.execute("SELECT * FROM messages WHERE id = ?",
                     (game["message_id"],)).fetchone()
    user = current_user()
    if msg["user_id"] != user["id"] and not user["is_admin"]:
        abort(403)
    final_a = request.form.get("final_a", type=int)
    final_b = request.form.get("final_b", type=int)
    if final_a is None or final_b is None or not (0 <= final_a <= 999 and 0 <= final_b <= 999):
        flash("Enter the final score for both teams.")
    else:
        db.execute("UPDATE games SET final_a = ?, final_b = ? WHERE id = ?",
                   (final_a, final_b, game_id))
        db.commit()
    return redirect(url_for("message", message_id=game["message_id"]))


@app.route("/scores/leaderboard")
def leaderboard():
    db = get_db()
    finished = db.execute(
        "SELECT * FROM games WHERE final_a IS NOT NULL").fetchall()
    wins, played = {}, {}
    for gm in finished:
        picks = db.execute(
            "SELECT p.*, u.handle h FROM game_picks p JOIN users u ON u.id = p.user_id"
            " WHERE p.game_id = ?", (gm["id"],)).fetchall()
        if not picks:
            continue
        def miss(p):
            return abs(p["pick_a"] - gm["final_a"]) + abs(p["pick_b"] - gm["final_b"])
        best = min(miss(p) for p in picks)
        for p in picks:
            played[p["h"]] = played.get(p["h"], 0) + 1
            if miss(p) == best:
                wins[p["h"]] = wins.get(p["h"], 0) + 1
    rows = sorted(
        ({"handle": h, "wins": wins.get(h, 0), "played": c}
         for h, c in played.items()),
        key=lambda r: (-r["wins"], r["handle"].lower()))
    return render_template("leaderboard.html", rows=rows,
                           total_games=len(finished))


# ------------------------------------------------------------------- chat
#
# Deliberately memory-only: messages live in this process and nowhere else.
# No database writes, no logs, no search. The room holds the last 200
# messages; older ones cease to exist. A server restart empties the room.
# Requires a single worker process (see Dockerfile: --workers 1 --threads).

CHAT_MAX_MESSAGES = 200
CHAT_LOCK = threading.Lock()
CHAT_MESSAGES = deque(maxlen=CHAT_MAX_MESSAGES)
CHAT_NEXT_ID = [1]
CHAT_LAST_SEND = {}   # user_id -> monotonic time of last message (rate limit)
CHAT_PRESENCE = {}    # user_id -> monotonic time of last poll


@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html")


@app.route("/chat/messages")
@login_required
def chat_messages():
    since = request.args.get("since", 0, type=int)
    user = current_user()
    now = time.monotonic()
    with CHAT_LOCK:
        CHAT_PRESENCE[user["id"]] = now
        for uid in [u for u, t in CHAT_PRESENCE.items() if now - t > 120]:
            del CHAT_PRESENCE[uid]
        online = sum(1 for t in CHAT_PRESENCE.values() if now - t < 30)
        msgs = [m for m in CHAT_MESSAGES if m["id"] > since]
    return {"messages": msgs, "online": online}


@app.route("/chat/send", methods=["POST"])
@login_required
def chat_send():
    text = (request.form.get("text") or "").strip()[:500]
    if not text:
        return {"ok": False}
    user = current_user()
    now = time.monotonic()
    with CHAT_LOCK:
        if now - CHAT_LAST_SEND.get(user["id"], -10) < 1.0:
            return {"ok": False, "error": "slow down"}
        CHAT_LAST_SEND[user["id"]] = now
        CHAT_MESSAGES.append({
            "id": CHAT_NEXT_ID[0],
            "handle": user["handle"],
            "text": text,
            "time": datetime.now(timezone.utc).astimezone(BOARD_TZ)
                    .strftime("%I:%M %p").lstrip("0"),
        })
        CHAT_NEXT_ID[0] += 1
    return {"ok": True}


@app.route("/rss.xml")
def rss():
    from xml.sax.saxutils import escape as xesc
    rows = get_db().execute(
        "SELECT * FROM messages ORDER BY id DESC LIMIT 50").fetchall()
    root_url = request.url_root.rstrip("/")
    items = []
    for r in rows:
        link = root_url + url_for("message", message_id=r["id"])
        try:
            pub = datetime.fromisoformat(r["created_at"]).strftime(
                "%a, %d %b %Y %H:%M:%S +0000")
        except ValueError:
            pub = ""
        title = ("[Scores] " if r["board"] == "scores" else "") + r["subject"]
        desc = f"By {r['author_name']}."
        if r["body"]:
            desc += " " + render_post(r["body"])
        items.append(
            f"<item><title>{xesc(title)}</title><link>{xesc(link)}</link>"
            f"<guid>{xesc(link)}</guid><pubDate>{pub}</pubDate>"
            f"<description>{xesc(desc)}</description></item>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<rss version="2.0"><channel>'
           f"<title>{xesc(get_setting('site_title'))}</title>"
           f"<link>{xesc(root_url)}</link>"
           "<description>Latest posts</description>"
           + "".join(items) + "</channel></rss>")
    return app.response_class(xml, mimetype="application/rss+xml")


@app.route("/edit/<int:message_id>", methods=["GET", "POST"])
@login_required
def edit(message_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg is None:
        abort(404)
    user = current_user()
    if msg["user_id"] != user["id"] and not user["is_admin"]:
        abort(403)
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        image_url = request.form.get("image_url", "").strip()
        if not subject:
            flash("A subject is required.")
        else:
            if image_url and not image_url.lower().startswith(
                    ("http://", "https://", "/uploads/")):
                image_url = ""
            uploaded = save_uploaded_image()
            if uploaded:
                image_url = uploaded
            db.execute(
                "UPDATE messages SET subject = ?, body = ?, image_url = ?,"
                " edited_at = ? WHERE id = ?",
                (subject, body or None, image_url or None,
                 now_utc_iso(), message_id))
            db.commit()
            return redirect(url_for("message", message_id=message_id))
    return render_template("edit.html", msg=msg)


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        like = f"%{q}%"
        results = get_db().execute(
            "SELECT * FROM messages WHERE subject LIKE ? OR body LIKE ? "
            "OR author_name LIKE ? ORDER BY created_at DESC LIMIT 200",
            (like, like, like)).fetchall()
    return render_template("search.html", q=q, results=results)


# --------------------------------------------------------------------- auth

@app.route("/register", methods=["GET", "POST"])
def register():
    if get_setting("registration_open") != "1":
        return render_template("register.html", closed=True)
    if request.method == "POST":
        handle = request.form.get("handle", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        if not re.fullmatch(r"[A-Za-z0-9_ .@'-]{2,30}", handle or ""):
            flash("Handle must be 2-30 characters (letters, numbers, basic punctuation).")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.")
        elif db.execute("SELECT 1 FROM users WHERE handle = ?", (handle,)).fetchone():
            flash("That handle is taken.")
        else:
            first_user = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0
            cur = db.execute(
                "INSERT INTO users (handle, password_hash, is_admin, created_at)"
                " VALUES (?, ?, ?, ?)",
                (handle, generate_password_hash(password), int(first_user),
                 now_utc_iso()))
            db.commit()
            session.clear()
            session["user_id"] = cur.lastrowid
            session.permanent = True
            if first_user:
                flash("Welcome! As the first registered user you are an admin.")
            return redirect(url_for("index", board_name="main"))
    return render_template("register.html", closed=False)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        handle = request.form.get("handle", "").strip()
        password = request.form.get("password", "")
        row = get_db().execute("SELECT * FROM users WHERE handle = ?", (handle,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            if row["is_banned"]:
                flash("This account is banned.")
            else:
                session.clear()
                session["user_id"] = row["id"]
                session.permanent = True
                target = request.args.get("next") or url_for("index", board_name="main")
                if not target.startswith("/"):
                    target = url_for("index", board_name="main")
                return redirect(target)
        else:
            flash("Wrong handle or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index", board_name="main"))


# -------------------------------------------------------------------- admin

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "settings":
            set_setting("site_title", request.form.get("site_title", "The Victors"))
            set_setting("header_html", request.form.get("header_html", ""))
            set_setting("links_html", request.form.get("links_html", ""))
            set_setting("registration_open",
                        "1" if request.form.get("registration_open") else "0")
            flash("Settings saved.")
        elif action == "create_user":
            handle = request.form.get("handle", "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_ .@'-]{2,30}", handle or ""):
                flash("Handle must be 2-30 characters (letters, numbers, basic punctuation).")
            elif db.execute("SELECT 1 FROM users WHERE handle = ?", (handle,)).fetchone():
                flash("That handle is taken.")
            else:
                new_pw = secrets.token_urlsafe(8)
                db.execute(
                    "INSERT INTO users (handle, password_hash, created_at) VALUES (?, ?, ?)",
                    (handle, generate_password_hash(new_pw),
                     now_utc_iso()))
                db.commit()
                flash(f"Created {handle} with password: {new_pw} "
                      f"(share it with them privately; they can keep it or you can "
                      f"reset it later)")
        elif action == "delete_user":
            uid = request.form.get("user_id", type=int)
            target = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            if target is None:
                flash("No such user.")
            elif target["is_admin"]:
                flash("Admins can't be deleted.")
            else:
                # posts keep their author name; the handle becomes free again
                db.execute("UPDATE messages SET user_id = NULL WHERE user_id = ?", (uid,))
                db.execute("DELETE FROM users WHERE id = ?", (uid,))
                db.commit()
                flash(f"Deleted account {target['handle']} (their posts remain, "
                      f"the handle is free to register again).")
        elif action in ("ban", "unban", "make_admin", "reset_password"):
            uid = request.form.get("user_id", type=int)
            target = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            if target is None:
                flash("No such user.")
            elif action == "ban":
                db.execute("UPDATE users SET is_banned = 1 WHERE id = ?", (uid,))
                db.commit()
                flash(f"Banned {target['handle']}.")
            elif action == "unban":
                db.execute("UPDATE users SET is_banned = 0 WHERE id = ?", (uid,))
                db.commit()
                flash(f"Unbanned {target['handle']}.")
            elif action == "make_admin":
                db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (uid,))
                db.commit()
                flash(f"{target['handle']} is now an admin.")
            elif action == "reset_password":
                new_pw = secrets.token_urlsafe(8)
                db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                           (generate_password_hash(new_pw), uid))
                db.commit()
                flash(f"New password for {target['handle']}: {new_pw} "
                      f"(share it with them privately)")
        return redirect(url_for("admin"))
    users = db.execute("SELECT * FROM users ORDER BY handle COLLATE NOCASE").fetchall()
    counts = db.execute("SELECT COUNT(*) total FROM messages").fetchone()
    return render_template("admin.html", users=users, counts=counts,
                           registration_open=get_setting("registration_open") == "1")


@app.route("/admin/delete/<int:message_id>", methods=["POST"])
@admin_required
def delete_message(message_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg is None:
        abort(404)
    # delete the message and all descendants
    ids = [message_id]
    frontier = [message_id]
    while frontier:
        marks = ",".join("?" * len(frontier))
        children = [r["id"] for r in db.execute(
            f"SELECT id FROM messages WHERE parent_id IN ({marks})", frontier)]
        ids.extend(children)
        frontier = children
    marks = ",".join("?" * len(ids))
    db.execute(f"DELETE FROM poll_votes WHERE poll_id IN "
               f"(SELECT id FROM polls WHERE message_id IN ({marks}))", ids)
    db.execute(f"DELETE FROM poll_options WHERE poll_id IN "
               f"(SELECT id FROM polls WHERE message_id IN ({marks}))", ids)
    db.execute(f"DELETE FROM polls WHERE message_id IN ({marks})", ids)
    db.execute(f"DELETE FROM game_picks WHERE game_id IN "
               f"(SELECT id FROM games WHERE message_id IN ({marks}))", ids)
    db.execute(f"DELETE FROM games WHERE message_id IN ({marks})", ids)
    db.execute(f"DELETE FROM messages WHERE id IN ({marks})", ids)
    db.commit()
    flash(f"Deleted {len(ids)} message(s).")
    if msg["parent_id"]:
        return redirect(url_for("message", message_id=msg["parent_id"]))
    return redirect(url_for("index", board_name="main"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
