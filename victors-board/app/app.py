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

import hashlib
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
                   send_file, send_from_directory, session, url_for)
from markupsafe import Markup
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", APP_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "board.db"
HANDLE_RE = r"[A-Za-z0-9_ .@&'-]{2,30}"   # the old board allowed LS&Play
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_KEEP = 7   # nightly database snapshots kept on disk
SECRET_FILE = DATA_DIR / "secret_key"

THREADS_PER_PAGE = 80
BOARDS = ("main", "scores", "cards")
BOARD_LABELS = {"scores": "Scores", "cards": "Cards"}
BOARD_TZ = ZoneInfo(os.environ.get("BOARD_TZ", "America/Detroit"))


def now_utc_iso():
    """Timestamps are stored as naive UTC; displayed in the board timezone."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def client_ip():
    """The visitor's real address: Cloudflare fronts the site and supplies it
    in CF-Connecting-IP; remote_addr is just the relay."""
    return request.headers.get("CF-Connecting-IP") or request.remote_addr

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".webm"}

app = Flask(__name__)
# behind Render's proxy: trust X-Forwarded-For so remote_addr is the real client
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # upload cap (videos)
LOCAL_VIDEO_CAP = 16 * 1024 * 1024  # fallback cap when hosting clips ourselves

# with Streamable credentials set, video uploads forward there instead of disk
STREAMABLE_EMAIL = os.environ.get("STREAMABLE_EMAIL")
STREAMABLE_PASSWORD = os.environ.get("STREAMABLE_PASSWORD")
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
    "hof_threshold": "5",
    "podcast_channel_id": "UCHqmAEJVsfJizpN8wHLI05Q",
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
                      "ALTER TABLE messages ADD COLUMN board TEXT NOT NULL DEFAULT 'main'",
                      "ALTER TABLE messages ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0",
                      "ALTER TABLE users ADD COLUMN session_token TEXT",
                      "ALTER TABLE messages ADD COLUMN hof_at TEXT",
                      "ALTER TABLE messages ADD COLUMN image_size TEXT"):
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
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None:
        return None
    # a rotated session_token (set on password reset) invalidates any session
    # that doesn't carry the current one — kicks stale logins immediately
    if row["session_token"] and session.get("token") != row["session_token"]:
        return None
    return row


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


@app.template_filter("boarddate")
def boarddate(iso):
    """Date only — 'August 3, 2026' — for dense tables."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    out = dt.astimezone(BOARD_TZ).strftime("%B %d, %Y")
    return re.sub(r" 0(\d,)", r" \1", out)


@app.template_filter("rendertext")
def rendertext(text):
    """Render a post body: safe-HTML subset, auto-linked URLs, newlines kept."""
    return Markup(render_post(text))


@app.context_processor
def inject_globals():
    pinned = get_db().execute(
        "SELECT id, subject FROM messages WHERE pinned = 1 AND parent_id IS NULL"
        " ORDER BY created_at DESC").fetchall()
    return {
        "user": current_user(),
        "site_title": get_setting("site_title"),
        "header_html": get_setting("header_html"),
        "links_html": get_setting("links_html"),
        "pinned_threads": pinned,
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


# ------------------------------------------------------------------ backups
#
# Layered: (1) a gzipped nightly database snapshot on the disk, last
# BACKUP_KEEP kept, taken on the first request of each board day;
# (2) Render's own disk snapshots; (3) the admin "download full backup"
# button, which is the true offsite copy — database plus every photo.

def snapshot_db_to(path):
    """Write a consistent copy of the live database to path (SQLite backup
    API, safe while the board is running). Uses its own connection — the
    backup can never finish from a connection with an open transaction."""
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def nightly_snapshot(day):
    BACKUP_DIR.mkdir(exist_ok=True)
    dest = BACKUP_DIR / f"board-{day}.db.gz"
    if not dest.exists():
        import gzip
        import shutil
        tmp = BACKUP_DIR / f".building-{day}.db"
        try:
            snapshot_db_to(tmp)
            with open(tmp, "rb") as src, gzip.open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
        finally:
            tmp.unlink(missing_ok=True)
    keep = sorted(BACKUP_DIR.glob("board-*.db.gz"))
    for old in keep[:-BACKUP_KEEP]:
        old.unlink(missing_ok=True)


REDDIT_SHARE_RE = re.compile(
    r"https?://(?:www\.)?reddit\.com/r/[^/\s]+/s/[A-Za-z0-9]+")


def resolve_reddit_links(text):
    """Reddit's mobile share links (/r/x/s/abc) are redirects; embeds only
    work on the real post URL. Resolve them once at post time, best effort —
    on any failure the original link is kept."""
    if not text or "/s/" not in text:
        return text
    import requests

    def swap(m):
        try:
            r = requests.get(m.group(0), timeout=4, allow_redirects=False,
                             headers={"User-Agent": "Mozilla/5.0"})
            loc = r.headers.get("Location", "")
            if loc.startswith("http") and "/comments/" in loc:
                return loc.split("?")[0]
        except Exception:
            pass
        return m.group(0)

    return REDDIT_SHARE_RE.sub(swap, text)


def user_read_ids(db, u):
    """Message ids this member has opened on any device (empty for guests)."""
    if not u:
        return set()
    return {r["message_id"] for r in db.execute(
        "SELECT message_id FROM message_reads WHERE user_id = ?", (u["id"],))}


# ----------------------------------------------------------- traffic counts

UNCOUNTED_PATHS = ("/static", "/uploads", "/chat/messages", "/favicon",
                   "/apple-touch", "/rss")


@app.before_request
def count_traffic():
    """Counts only. The visitor hash is salted with the day and the app
    secret, so it can't be reversed to an address or linked across days,
    and it's pruned as each day rolls over. No connection to accounts."""
    if request.method != "GET" or request.path.startswith(UNCOUNTED_PATHS):
        return
    day = datetime.now(timezone.utc).astimezone(BOARD_TZ).strftime("%Y-%m-%d")
    visitor = hashlib.sha256(
        f"{day}|{app.secret_key}|{client_ip()}|"
        f"{request.user_agent.string}".encode()).hexdigest()[:16]
    db = get_db()
    new_day = db.execute(
        "INSERT OR IGNORE INTO traffic (day) VALUES (?)", (day,)).rowcount
    if new_day:
        # daily housekeeping: read marks for old messages age out
        cutoff = (datetime.now(timezone.utc) - timedelta(days=60)) \
            .replace(tzinfo=None).isoformat(timespec="seconds")
        db.execute("DELETE FROM message_reads WHERE message_id IN"
                   " (SELECT id FROM messages WHERE created_at < ?)", (cutoff,))
    db.execute("UPDATE traffic SET pageviews = pageviews + 1 WHERE day = ?", (day,))
    cur = db.execute(
        "INSERT OR IGNORE INTO traffic_visitors (day, visitor) VALUES (?, ?)",
        (day, visitor))
    if cur.rowcount:
        db.execute("UPDATE traffic SET uniques = uniques + 1 WHERE day = ?", (day,))
        db.execute("DELETE FROM traffic_visitors WHERE day != ?", (day,))
    db.commit()
    if new_day:
        try:
            nightly_snapshot(day)   # after commit: backup needs a quiet db
        except Exception:
            pass   # a failed snapshot must never take down the board


# -------------------------------------------------------------------- pages

@app.route("/", defaults={"board_name": "main"})
@app.route("/scores", defaults={"board_name": "scores"})
@app.route("/cards", defaults={"board_name": "cards"})
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
                           board_name=board_name,
                           gameday=gameday_banner() if board_name == "main" else None,
                           pod=pod_box() if board_name == "main" else None,
                           rocking=chat_rocking(),
                           read_ids=user_read_ids(db, current_user()))


@app.route("/message/<int:message_id>")
def message(message_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg is None:
        abort(404)
    thread_rows = db.execute(
        "SELECT * FROM messages WHERE thread_id = ?", (msg["thread_id"],)).fetchall()
    roots = build_tree(thread_rows)
    thread = roots[0] if roots else None
    reply_subject = msg["subject"]
    if not reply_subject.lower().startswith("re"):
        reply_subject = "Re: " + reply_subject

    poll = db.execute("SELECT * FROM polls WHERE message_id = ?",
                      (message_id,)).fetchone()
    poll_options, my_vote, total_votes, top_votes = [], None, 0, 0
    if poll:
        poll_options = db.execute(
            "SELECT o.id, o.text, COUNT(v.id) votes FROM poll_options o"
            " LEFT JOIN poll_votes v ON v.option_id = o.id"
            " WHERE o.poll_id = ? GROUP BY o.id, o.text ORDER BY o.id",
            (poll["id"],)).fetchall()
        total_votes = sum(r["votes"] for r in poll_options)
        top_votes = max((r["votes"] for r in poll_options), default=0)
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
    hof_votes = db.execute("SELECT COUNT(*) c FROM hof_votes WHERE message_id = ?",
                           (message_id,)).fetchone()["c"]
    u = current_user()
    my_hof_vote = bool(u and db.execute(
        "SELECT 1 FROM hof_votes WHERE message_id = ? AND user_id = ?",
        (message_id, u["id"])).fetchone())
    if u:
        # cross-device read sync: this link shows as read on their other devices
        db.execute("INSERT OR IGNORE INTO message_reads (user_id, message_id)"
                   " VALUES (?, ?)", (u["id"], message_id))
        db.commit()
    return render_template("message.html", msg=msg, thread=thread,
                           read_ids=user_read_ids(db, u),
                           hof_votes=hof_votes, my_hof_vote=my_hof_vote,
                           hof_threshold=int(get_setting("hof_threshold") or 5),
                           reply_subject=reply_subject, poll=poll,
                           poll_options=poll_options, my_vote=my_vote,
                           total_votes=total_votes, top_votes=top_votes,
                           game=game,
                           game_picks=game_picks, my_pick=my_pick,
                           game_winners=game_winners)


def upload_to_streamable(path):
    """Forward a clip to Streamable; returns its page URL."""
    import requests
    with open(path, "rb") as fh:
        resp = requests.post(
            "https://api.streamable.com/upload",
            auth=(STREAMABLE_EMAIL, STREAMABLE_PASSWORD),
            files={"file": (path.name, fh)},
            timeout=180)
    resp.raise_for_status()
    code = resp.json().get("shortcode")
    if not code:
        raise ValueError("no shortcode in Streamable response")
    return f"https://streamable.com/{code}"


def save_uploaded_image():
    """First upload only (or None) — the edit page replaces the attachment."""
    files = [f for f in request.files.getlist("image_file") if f and f.filename]
    return _save_one_upload(files[0]) if files else None


def save_uploaded_images(limit=6):
    """All uploads in order, as serving URLs. One video max per post — extra
    clips are skipped so a single request can't sit on the video service."""
    files = [f for f in request.files.getlist("image_file") if f and f.filename]
    if len(files) > limit:
        flash(f"{limit} pictures max per post — kept the first {limit}.")
        files = files[:limit]
    urls, video_done = [], False
    for f in files:
        if Path(f.filename).suffix.lower() in ALLOWED_VIDEO_EXT:
            if video_done:
                flash("One video clip per post — extra clips were skipped.")
                continue
            video_done = True
        u = _save_one_upload(f)
        if u:
            urls.append(u)
    return urls


def _save_one_upload(f):
    """Store one uploaded picture/clip on the data disk; return its URL.

    Non-GIF images are downscaled to 1600px max and recompressed, which
    turns multi-MB phone photos into a few hundred KB. GIFs pass through
    untouched to preserve animation.
    """
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT | ALLOWED_VIDEO_EXT:
        flash("Uploads must be a picture (jpg, png, gif, webp) or a short "
              "video clip (mp4, mov, webm).")
        return None
    name = secrets.token_hex(8) + ext
    path = UPLOAD_DIR / name
    f.save(path)
    if ext in ALLOWED_VIDEO_EXT:
        if STREAMABLE_EMAIL and STREAMABLE_PASSWORD:
            try:
                url = upload_to_streamable(path)
                path.unlink(missing_ok=True)
                return url
            except Exception:
                if path.stat().st_size <= LOCAL_VIDEO_CAP:
                    flash("The video service hiccuped — hosted this clip on "
                          "the board instead.")
                    return url_for("uploads", filename=name)
                path.unlink(missing_ok=True)
                flash("The video service isn't responding and this clip is too "
                      "big to host here — try again later, or put it on "
                      "YouTube and paste the link.")
                return None
        if path.stat().st_size > LOCAL_VIDEO_CAP:
            path.unlink(missing_ok=True)
            flash("Clips over 16MB need the video service, which isn't set up "
                  "— put it on YouTube and paste the link.")
            return None
        return url_for("uploads", filename=name)
    if ext != ".gif":
        try:
            from PIL import Image, ImageOps
            img = Image.open(path)
            # apply the EXIF orientation flag so portrait phone photos stay
            # upright after recompression strips the metadata
            img = ImageOps.exif_transpose(img)
            img.thumbnail((1600, 1600))
            if img.mode in ("RGBA", "LA", "P"):
                img.save(path)  # keep transparency in original format
            else:
                jpg_path = path.with_suffix(".jpg")
                img.convert("RGB").save(jpg_path, "JPEG", quality=85)
                if jpg_path != path:
                    path.unlink()
                    path, name = jpg_path, jpg_path.name
        except Exception:
            pass  # unreadable as an image? keep the file as uploaded
    return url_for("uploads", filename=name)


@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.errorhandler(413)
def too_large(_e):
    flash("That file is too big — 100MB max. For anything bigger, put it on "
          "YouTube and paste the link.")
    return redirect(request.referrer or url_for("index", board_name="main"))


# iOS and some browsers request these fixed root paths directly
@app.route("/favicon.ico")
def favicon_ico():
    return send_from_directory(APP_DIR / "static", "favicon.ico")


@app.route("/apple-touch-icon.png")
@app.route("/apple-touch-icon-precomposed.png")
def apple_touch_icon():
    return send_from_directory(APP_DIR / "static", "apple-touch-icon.png")


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
        body = resolve_reddit_links(request.form.get("body", "").strip())
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
            uploaded = save_uploaded_images()
            if uploaded:
                image_url = uploaded[0]
                if len(uploaded) > 1:
                    # extra pictures go inline in the body, absolute so the
                    # renderer embeds them
                    root = request.url_root.rstrip("/")
                    extras = "\n".join(
                        u if u.startswith("http") else root + u
                        for u in uploaded[1:])
                    body = (body + "\n\n" + extras).strip()
            user = current_user()
            now = now_utc_iso()
            # double-post guard: identical post by the same user in the last
            # two minutes (double-clicked button, back-button resubmit) just
            # lands on the existing message instead of inserting again
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=2)) \
                .replace(tzinfo=None).isoformat(timespec="seconds")
            dupe = db.execute(
                "SELECT id FROM messages WHERE user_id = ? AND subject = ?"
                " AND COALESCE(body, '') = COALESCE(?, '')"
                " AND COALESCE(parent_id, 0) = COALESCE(?, 0)"
                " AND created_at >= ?",
                (user["id"], subject, body or None,
                 parent["id"] if parent else None, cutoff)).fetchone()
            if dupe:
                flash("⚠️ No double posting, moron! ⚠️", "success")
                return redirect(url_for("message", message_id=dupe["id"]))
            image_size = request.form.get("image_size")
            if image_size not in ("small", "medium", "large"):
                image_size = None   # full size, the default
            cur = db.execute(
                "INSERT INTO messages (thread_id, parent_id, subject, body,"
                " image_url, author_name, user_id, created_at, ip_address,"
                " board, image_size)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (parent["thread_id"] if parent else None,
                 parent["id"] if parent else None,
                 subject, body or None, image_url or None,
                 user["handle"], user["id"], now, client_ip(), board,
                 image_size))
            new_id = cur.lastrowid
            flash("Posted! Go Blue!", "goblue")
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


# ------------------------------------------------------- live scoreboard

SCOREBOARD_URLS = {
    "CFB": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
    "CBB": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
}
SCORE_CACHE = {"at": -999.0, "games": []}
SCORE_LOCK = threading.Lock()
STATE_ORDER = {"in": 0, "pre": 1, "post": 2}


def fetch_scoreboards():
    """Today's CFB/CBB slates from ESPN's public scoreboard feed."""
    import requests
    games = []
    for sport, url in SCOREBOARD_URLS.items():
        try:
            data = requests.get(url, timeout=6).json()
            for ev in data.get("events", []):
                comp = ev["competitions"][0]
                home = next(c for c in comp["competitors"]
                            if c.get("homeAway") == "home")
                away = next(c for c in comp["competitors"]
                            if c.get("homeAway") == "away")
                st = ev.get("status", {}).get("type", {})
                games.append({
                    "sport": sport,
                    "away": away["team"].get("abbreviation", "?"),
                    "home": home["team"].get("abbreviation", "?"),
                    "away_score": away.get("score", ""),
                    "home_score": home.get("score", ""),
                    "status": st.get("shortDetail", ""),
                    "state": st.get("state", "pre"),
                    "date": ev.get("date", ""),
                })
        except Exception:
            continue  # one sport failing shouldn't blank the other
    games.sort(key=lambda gm: STATE_ORDER.get(gm["state"], 3))
    return games


# The Slippery Rock score has been announced at Michigan Stadium since the
# 1950s. The board carries it too, on Saturdays, with no explanation — same
# as the stadium. Division II is group 57 in ESPN's scoreboard feed.
SRU_URL = ("https://site.api.espn.com/apis/site/v2/sports/football/"
           "college-football/scoreboard?groups=57&limit=200")
SRU_CACHE = {"at": -1e9, "game": None}
SRU_LOCK = threading.Lock()


def fetch_slippery_rock():
    """Slippery Rock's game today, or None."""
    import requests
    try:
        data = requests.get(SRU_URL, timeout=6).json()
    except Exception:
        return None
    for ev in data.get("events", []):
        try:
            teams = ev["competitions"][0]["competitors"]
            rock = next((c for c in teams
                         if "slippery rock" in c["team"].get("displayName", "").lower()),
                        None)
            if rock is None:
                continue
            other = next(c for c in teams if c is not rock)
            st = ev.get("status", {}).get("type", {})
            return {
                "opponent": (other["team"].get("abbreviation")
                             or other["team"].get("displayName", "?")),
                "at_home": rock.get("homeAway") == "home",
                "score": rock.get("score", ""),
                "opp_score": other.get("score", ""),
                "status": st.get("shortDetail", ""),
                "state": st.get("state", "pre"),
            }
        except Exception:
            continue
    return None


def slippery_rock_line():
    """One rendered line for the scoreboard, Saturdays only, or None."""
    now_local = datetime.now(timezone.utc).astimezone(BOARD_TZ)
    if now_local.weekday() != 5:   # Saturday
        return None
    now = time.monotonic()
    with SRU_LOCK:
        if now - SRU_CACHE["at"] > 300:
            SRU_CACHE["game"] = fetch_slippery_rock()
            SRU_CACHE["at"] = now
        gm = SRU_CACHE["game"]
    if not gm:
        return None
    versus = "vs" if gm["at_home"] else "at"
    if gm["state"] == "pre":
        return f"Slippery Rock {versus} {gm['opponent']} · {gm['status']}"
    return (f"Slippery Rock {gm['score']} — {gm['opponent']} {gm['opp_score']}"
            f" · {gm['status']}")


def live_games():
    """The cached scoreboard slate, refreshed at most once a minute."""
    now = time.monotonic()
    with SCORE_LOCK:
        if now - SCORE_CACHE["at"] > 60:
            fresh = fetch_scoreboards()
            if fresh or not SCORE_CACHE["games"]:
                SCORE_CACHE["games"] = fresh
            SCORE_CACHE["at"] = now
        return SCORE_CACHE["games"]


def gameday_banner():
    """Michigan's game on today's slate, shaped for the homepage banner —
    None on the ~340 days a year there isn't one."""
    today = datetime.now(timezone.utc).astimezone(BOARD_TZ).date()
    best = None
    for gm in live_games():
        if "MICH" not in (gm["away"], gm["home"]):
            continue
        try:
            gd = datetime.fromisoformat(
                gm["date"].replace("Z", "+00:00")).astimezone(BOARD_TZ).date()
        except ValueError:
            continue
        if gd != today:
            continue
        if gm["state"] == "in":
            best = gm
            break
        if best is None or (gm["state"] == "pre" and best["state"] == "post"):
            best = gm   # an upcoming game outranks an earlier final
    if best is None:
        return None
    home = best["home"] == "MICH"
    opp = best["away"] if home else best["home"]
    if best["state"] == "pre":
        line = f"Michigan {'vs' if home else 'at'} {opp} · {best['status']}"
    elif best["state"] == "in":
        mich = best["home_score"] if home else best["away_score"]
        theirs = best["away_score"] if home else best["home_score"]
        line = f"MICH {mich} — {opp} {theirs} · {best['status']}"
    else:
        mich = best["home_score"] if home else best["away_score"]
        theirs = best["away_score"] if home else best["home_score"]
        line = f"FINAL: MICH {mich} — {opp} {theirs}"
    now_m = time.monotonic()
    with CHAT_LOCK:
        in_chat = sum(1 for _, t in CHAT_PRESENCE.values() if now_m - t < 30)
    return {"line": line, "state": best["state"], "chat": in_chat}


# ---------------------------------------------------------------- pod day
#
# The Victors Pod (Nikos & gbmcq) publishes to YouTube every Wednesday.
# The channel's built-in RSS feed tells us the newest upload; the homepage
# shows a collapsed player only on Wednesdays (board time) and only when
# the episode is fresh, so a skipped week means no box at all.

POD_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
POD_CACHE = {"at": -1e9, "video": None}
POD_LOCK = threading.Lock()


def fetch_latest_pod():
    """Newest upload on the pod channel: dict(video_id, title, published)."""
    import requests
    import xml.etree.ElementTree as ET
    cid = (get_setting("podcast_channel_id") or "").strip()
    if not cid:
        return None
    try:
        raw = requests.get(POD_FEED.format(cid=cid), timeout=8).text
        root = ET.fromstring(raw)
        ns = {"a": "http://www.w3.org/2005/Atom",
              "yt": "http://www.youtube.com/xml/schemas/2015"}
        best = None
        for entry in root.findall("a:entry", ns):
            vid = entry.findtext("yt:videoId", "", ns)
            pub = entry.findtext("a:published", "", ns)
            if not vid or not pub:
                continue
            when = datetime.fromisoformat(pub)
            if best is None or when > best["published"]:
                best = {"video_id": vid,
                        "title": entry.findtext("a:title", "", ns),
                        "published": when}
        return best
    except Exception:
        return None


def pod_box():
    """The homepage pod box, or None. Strictly Wednesdays, board time."""
    if datetime.now(timezone.utc).astimezone(BOARD_TZ).weekday() != 2:
        return None
    now = time.monotonic()
    with POD_LOCK:
        # 15-minute cache: fetches only happen on Wednesdays, and the box
        # should flip to the new episode soon after it uploads
        if now - POD_CACHE["at"] > 900:
            POD_CACHE["video"] = fetch_latest_pod()
            POD_CACHE["at"] = now
        video = POD_CACHE["video"]
    if not video:
        return None
    if datetime.now(timezone.utc) - video["published"] > timedelta(hours=48):
        return None   # no fresh episode this week
    return video


@app.route("/scores/live.json")
def scores_live():
    return {"games": live_games(), "sru": slippery_rock_line()}


@app.route("/admin/sru-check")
@admin_required
def sru_check():
    """One-off: does ESPN's D-II feed carry Slippery Rock today?"""
    with SRU_LOCK:
        SRU_CACHE["at"] = -1e9
    raw = fetch_slippery_rock()
    return {"found": bool(raw), "game": raw, "line_shown_now": slippery_rock_line(),
            "note": "line only renders on Saturdays"}


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
CHAT_EPOCH = [1]      # bumped when an admin clears the room; clients wipe on change
CHAT_LAST_SEND = {}   # user_id -> monotonic time of last message (rate limit)
CHAT_PRESENCE = {}    # user_id -> (handle, monotonic time of last poll)

# "Chat is rocking": the boards advertise the room when it's genuinely
# lively — enough people AND enough recent messages, not one idler
ROCKING_PEOPLE = 3
ROCKING_MSGS = 10
ROCKING_WINDOW = 300   # seconds


def chat_rocking():
    now = time.monotonic()
    with CHAT_LOCK:
        people = sum(1 for _, t in CHAT_PRESENCE.values() if now - t < 30)
        recent = sum(1 for m in CHAT_MESSAGES
                     if now - m.get("at", -1e9) < ROCKING_WINDOW)
    if people >= ROCKING_PEOPLE and recent >= ROCKING_MSGS:
        return {"people": people, "recent": recent}
    return None


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
        CHAT_PRESENCE[user["id"]] = (user["handle"], now)
        for uid in [u for u, (_, t) in CHAT_PRESENCE.items() if now - t > 120]:
            del CHAT_PRESENCE[uid]
        names = sorted((h for h, t in CHAT_PRESENCE.values() if now - t < 30),
                       key=str.lower)
        msgs = [{k: v for k, v in m.items() if k != "at"}
                for m in CHAT_MESSAGES if m["id"] > since]
        epoch = CHAT_EPOCH[0]
    return {"messages": msgs, "online": len(names), "names": names,
            "epoch": epoch}


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
            "at": now,   # monotonic; feeds the "chat is rocking" banner
            "time": datetime.now(timezone.utc).astimezone(BOARD_TZ)
                    .strftime("%I:%M %p").lstrip("0"),
        })
        CHAT_NEXT_ID[0] += 1
    return {"ok": True}


@app.route("/chat/clear", methods=["POST"])
@login_required
def chat_clear():
    user = current_user()
    if not user["is_admin"]:
        abort(403)
    with CHAT_LOCK:
        CHAT_MESSAGES.clear()
        CHAT_MESSAGES.append({
            "id": CHAT_NEXT_ID[0],
            "sys": True,
            "text": f"— the room was cleared by {user['handle']} —",
            "time": datetime.now(timezone.utc).astimezone(BOARD_TZ)
                    .strftime("%I:%M %p").lstrip("0"),
        })
        CHAT_NEXT_ID[0] += 1
        CHAT_EPOCH[0] += 1
    return {"ok": True}


@app.route("/story")
def story():
    """The rescue case study — fully unlisted, no links anywhere.
    Stats are queried live so the page proves itself."""
    db = get_db()
    members = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    messages = db.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
    yesterday = (datetime.now(timezone.utc).astimezone(BOARD_TZ)
                 - timedelta(days=1)).strftime("%Y-%m-%d")
    row = db.execute("SELECT pageviews FROM traffic WHERE day = ?",
                     (yesterday,)).fetchone()
    hof = db.execute("SELECT COUNT(*) c FROM messages"
                     " WHERE hof_at IS NOT NULL").fetchone()["c"]
    games = db.execute("SELECT COUNT(*) c FROM polls").fetchone()["c"] \
        + db.execute("SELECT COUNT(*) c FROM games").fetchone()["c"]
    photos = sum(1 for p in UPLOAD_DIR.glob("*") if p.is_file())
    launched = datetime(2026, 8, 3, tzinfo=BOARD_TZ)
    days_live = (datetime.now(timezone.utc).astimezone(BOARD_TZ)
                 - launched).days
    week = db.execute(
        "SELECT day, pageviews FROM traffic ORDER BY day DESC LIMIT 15"
    ).fetchall()
    chart = [dict(r) for r in reversed(week)][:-1]   # last 14 full days
    chart_max = max((c["pageviews"] for c in chart), default=1)
    loc = (APP_DIR / "app.py").read_text().count("\n")
    return render_template("story.html", members=members, messages=messages,
                           pageviews=row["pageviews"] if row else 0,
                           hof=hof, games=games, photos=photos,
                           days_live=days_live, chart=chart,
                           chart_max=chart_max, loc=loc)


@app.route("/stats")
def stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
    members = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    top_posters = db.execute(
        "SELECT author_name, COUNT(*) c FROM messages"
        " GROUP BY author_name ORDER BY c DESC, author_name LIMIT 20").fetchall()
    top_threads = db.execute(
        "SELECT m.id, m.subject, m.author_name, COUNT(r.id) replies"
        " FROM messages m JOIN messages r ON r.thread_id = m.id AND r.id != m.id"
        " WHERE m.parent_id IS NULL GROUP BY m.id"
        " ORDER BY replies DESC LIMIT 10").fetchall()

    # rush hour needs board-timezone hours; compute in Python
    hour_counts = [0] * 24
    for row in db.execute("SELECT created_at FROM messages"):
        try:
            dt = datetime.fromisoformat(row["created_at"])
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hour_counts[dt.astimezone(BOARD_TZ).hour] += 1
    rush_hour = max(range(24), key=lambda h: hour_counts[h]) if total else 0
    rush_label = datetime(2000, 1, 1, rush_hour).strftime("%I %p").lstrip("0")

    traffic_days = db.execute(
        "SELECT * FROM traffic ORDER BY day DESC LIMIT 14").fetchall()
    month_prefix = datetime.now(timezone.utc).astimezone(BOARD_TZ).strftime("%Y-%m")
    month = db.execute(
        "SELECT COALESCE(SUM(pageviews), 0) pv, COALESCE(SUM(uniques), 0) uv"
        " FROM traffic WHERE day LIKE ?", (month_prefix + "%",)).fetchone()
    return render_template("stats.html", total=total, members=members,
                           top_posters=top_posters, top_threads=top_threads,
                           rush_label=rush_label, rush_count=hour_counts[rush_hour],
                           traffic_days=traffic_days, month=month,
                           month_name=datetime.now(timezone.utc)
                               .astimezone(BOARD_TZ).strftime("%B"))


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
        label = BOARD_LABELS.get(r["board"])
        title = (f"[{label}] " if label else "") + r["subject"]
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
        body = resolve_reddit_links(request.form.get("body", "").strip())
        image_url = request.form.get("image_url", "").strip()
        if not subject:
            flash("A subject is required.")
        else:
            if image_url and not image_url.lower().startswith(
                    ("http://", "https://", "/uploads/")):
                image_url = ""
            uploaded = save_uploaded_images()
            if uploaded:
                image_url = uploaded[0]
                if len(uploaded) > 1:
                    root = request.url_root.rstrip("/")
                    extras = "\n".join(
                        u if u.startswith("http") else root + u
                        for u in uploaded[1:])
                    body = (body + "\n\n" + extras).strip()
            image_size = request.form.get("image_size")
            if image_size not in ("small", "medium", "large"):
                image_size = None
            db.execute(
                "UPDATE messages SET subject = ?, body = ?, image_url = ?,"
                " image_size = ?, edited_at = ? WHERE id = ?",
                (subject, body or None, image_url or None, image_size,
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
        if not re.fullmatch(HANDLE_RE, handle or ""):
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


# login rate limit: after LOGIN_MAX_FAILS failed tries from one address,
# that address waits out LOGIN_COOLDOWN before trying again
LOGIN_FAILS = {}          # ip -> [monotonic times of recent failures]
LOGIN_LOCK = threading.Lock()
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW = 900        # failures older than this stop counting
LOGIN_COOLDOWN = 900


def login_blocked(ip):
    now = time.monotonic()
    with LOGIN_LOCK:
        fails = [t for t in LOGIN_FAILS.get(ip, []) if now - t < LOGIN_WINDOW]
        LOGIN_FAILS[ip] = fails
        if len(LOGIN_FAILS) > 5000:   # bot-swarm memory backstop
            LOGIN_FAILS.clear()
        return len(fails) >= LOGIN_MAX_FAILS


def login_failed(ip):
    with LOGIN_LOCK:
        LOGIN_FAILS.setdefault(ip, []).append(time.monotonic())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if login_blocked(client_ip()):
            flash("Too many failed tries — wait 15 minutes and try again "
                  "(or email the admins for a password reset).")
            return render_template("login.html")
        handle = request.form.get("handle", "").strip()
        password = request.form.get("password", "")
        row = get_db().execute("SELECT * FROM users WHERE handle = ?", (handle,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            if row["is_banned"]:
                flash("This account is banned.")
            else:
                session.clear()
                session["user_id"] = row["id"]
                if row["session_token"]:
                    session["token"] = row["session_token"]
                session.permanent = True
                target = request.args.get("next") or url_for("index", board_name="main")
                if not target.startswith("/"):
                    target = url_for("index", board_name="main")
                return redirect(target)
        else:
            login_failed(client_ip())
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
            threshold = request.form.get("hof_threshold", type=int)
            if threshold and 1 <= threshold <= 99:
                set_setting("hof_threshold", str(threshold))
            set_setting("podcast_channel_id",
                        request.form.get("podcast_channel_id", "").strip())
            flash("Settings saved.")
        elif action == "create_user":
            handle = request.form.get("handle", "").strip()
            if not re.fullmatch(HANDLE_RE, handle or ""):
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
                db.execute("DELETE FROM message_reads WHERE user_id = ?", (uid,))
                db.execute("DELETE FROM users WHERE id = ?", (uid,))
                db.commit()
                flash(f"Deleted account {target['handle']} (their posts remain, "
                      f"the handle is free to register again).")
        elif action == "rename":
            uid = request.form.get("user_id", type=int)
            new = request.form.get("new_handle", "").strip()
            target = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            if target is None:
                flash("No such user.")
            elif not re.fullmatch(HANDLE_RE, new):
                flash("Handle must be 2-30 characters (letters, numbers, "
                      "basic punctuation).")
            elif db.execute("SELECT 1 FROM users WHERE handle = ? AND id != ?",
                            (new, uid)).fetchone():
                flash("That handle is taken.")
            elif new == target["handle"]:
                flash("That's already their handle.")
            else:
                db.execute("UPDATE users SET handle = ? WHERE id = ?", (new, uid))
                # their posts carry the handle denormalized — bring history along
                db.execute("UPDATE messages SET author_name = ? WHERE user_id = ?",
                           (new, uid))
                db.commit()
                flash(f"Renamed {target['handle']} to {new} — all their posts "
                      f"now show the new handle; password and login unchanged.")
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
                # rotating the session token logs the user out everywhere
                db.execute("UPDATE users SET password_hash = ?, session_token = ?"
                           " WHERE id = ?",
                           (generate_password_hash(new_pw), secrets.token_hex(16), uid))
                db.commit()
                flash(f"New password for {target['handle']}: {new_pw} "
                      f"(share it with them privately). Their existing logins "
                      f"were signed out.")
        return redirect(url_for("admin"))
    users = db.execute("SELECT * FROM users ORDER BY handle COLLATE NOCASE").fetchall()
    counts = db.execute("SELECT COUNT(*) total FROM messages").fetchone()
    upload_files = [p for p in UPLOAD_DIR.glob("*") if p.is_file()]
    disk = {
        "db_mb": round(DB_PATH.stat().st_size / 1e6, 1) if DB_PATH.exists() else 0,
        "uploads_mb": round(sum(p.stat().st_size for p in upload_files) / 1e6, 1),
        "upload_count": len(upload_files),
    }
    snapshots = sorted(BACKUP_DIR.glob("board-*.db.gz"), reverse=True) \
        if BACKUP_DIR.exists() else []
    return render_template("admin.html", users=users, counts=counts, disk=disk,
                           hof_threshold=get_setting("hof_threshold"),
                           podcast_channel_id=get_setting("podcast_channel_id"),
                           snapshots=[{"name": p.name,
                                       "mb": round(p.stat().st_size / 1e6, 2)}
                                      for p in snapshots],
                           registration_open=get_setting("registration_open") == "1")


@app.route("/admin/backup")
@admin_required
def admin_backup():
    """Full offsite backup: consistent database copy plus every upload."""
    import tarfile
    import tempfile
    stamp = datetime.now(timezone.utc).astimezone(BOARD_TZ).strftime("%Y-%m-%d")
    snap = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    snap.close()
    bundle = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    bundle.close()
    try:
        snapshot_db_to(snap.name)
        with tarfile.open(bundle.name, "w:gz") as tar:
            tar.add(snap.name, arcname="board.db")
            if UPLOAD_DIR.exists():
                tar.add(UPLOAD_DIR, arcname="uploads")
    finally:
        os.unlink(snap.name)
    resp = send_file(bundle.name, as_attachment=True,
                     download_name=f"victors-backup-{stamp}.tar.gz")
    resp.call_on_close(lambda: os.unlink(bundle.name))
    return resp


@app.route("/admin/backup/nightly/<name>")
@admin_required
def admin_backup_nightly(name):
    if not re.fullmatch(r"board-\d{4}-\d{2}-\d{2}\.db\.gz", name) \
            or not (BACKUP_DIR / name).exists():
        abort(404)
    return send_file(BACKUP_DIR / name, as_attachment=True, download_name=name)


@app.route("/hof")
def hof():
    posts = get_db().execute(
        "SELECT * FROM messages WHERE hof_at IS NOT NULL"
        " ORDER BY hof_at DESC").fetchall()
    return render_template("hof.html", posts=posts)


@app.route("/hof/nominate/<int:message_id>", methods=["POST"])
@login_required
def hof_nominate(message_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg is None:
        abort(404)
    user = current_user()
    existing = db.execute(
        "SELECT id FROM hof_votes WHERE message_id = ? AND user_id = ?",
        (message_id, user["id"])).fetchone()
    if existing:
        db.execute("DELETE FROM hof_votes WHERE id = ?", (existing["id"],))
        flash("Nomination withdrawn.")
    else:
        db.execute(
            "INSERT INTO hof_votes (message_id, user_id, created_at) VALUES (?, ?, ?)",
            (message_id, user["id"], now_utc_iso()))
        count = db.execute("SELECT COUNT(*) c FROM hof_votes WHERE message_id = ?",
                           (message_id,)).fetchone()["c"]
        threshold = int(get_setting("hof_threshold") or 5)
        if count >= threshold and not msg["hof_at"]:
            db.execute("UPDATE messages SET hof_at = ? WHERE id = ?",
                       (now_utc_iso(), message_id))
            flash("🏆 THE PEOPLE HAVE SPOKEN — this post is enshrined in the "
                  "Hall of Fame.")
        else:
            flash(f"🏆 Nominated for the Hall of Fame ({count} of {threshold} "
                  f"votes needed).")
    db.commit()
    return redirect(url_for("message", message_id=message_id))


@app.route("/admin/hof/<int:message_id>", methods=["POST"])
@admin_required
def hof_toggle(message_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg is None:
        abort(404)
    if msg["hof_at"]:
        db.execute("UPDATE messages SET hof_at = NULL WHERE id = ?", (message_id,))
        flash("Removed from the Hall of Fame.")
    else:
        db.execute("UPDATE messages SET hof_at = ? WHERE id = ?",
                   (now_utc_iso(), message_id))
        flash("🏆 Enshrined in the Hall of Fame.")
    db.commit()
    return redirect(url_for("message", message_id=message_id))


@app.route("/admin/pin/<int:message_id>", methods=["POST"])
@admin_required
def pin_message(message_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg is None or msg["parent_id"] is not None:
        abort(404)
    db.execute("UPDATE messages SET pinned = ? WHERE id = ?",
               (0 if msg["pinned"] else 1, message_id))
    db.commit()
    flash("Thread unpinned." if msg["pinned"] else
          "Thread pinned to the top of the board.")
    return redirect(url_for("message", message_id=message_id))


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
    db.execute(f"DELETE FROM hof_votes WHERE message_id IN ({marks})", ids)
    db.execute(f"DELETE FROM message_reads WHERE message_id IN ({marks})", ids)
    db.execute(f"DELETE FROM messages WHERE id IN ({marks})", ids)
    db.commit()
    flash(f"Deleted {len(ids)} message(s).")
    if msg["parent_id"]:
        return redirect(url_for("message", message_id=msg["parent_id"]))
    return redirect(url_for("index", board_name="main"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
