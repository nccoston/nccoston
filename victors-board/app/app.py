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
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", APP_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "board.db"
SECRET_FILE = DATA_DIR / "secret_key"

THREADS_PER_PAGE = 25

app = Flask(__name__)
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
        "<li><b>DON'T POST ANY PORN, YOU WILL BE BANNED.</b></li>"
        "<li><b>Please use a \"*\" or \"nm\" in the subject line to denote "
        "topic only posts.</b></li>"
        "<li><b>Any post or attempt to take things \"off the board\" will result "
        "in a ban. Do not use other poster's real names or personal info.</b></li>"
        "<li><b>Don't be a jerk.</b></li>"
        "<li><b>Please learn how to copy the URL of pictures and use the image "
        "embedding field to post pictures of celebrities.</b></li>"
        "</ol>"
        "<p><b>Admins</b> - Beave, Yosterizer.<br>"
        "<b>Moderators</b> - Ed, Rich, bh, DetroitBry, BBA<br>"
        "<b>Ceremonial Moderator</b> - wino<br>"
        "<b>Honorary Moderators</b> - BigLake, Blue Man</p>"
        "<p><b>POTY</b> - Craig</p>"
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
            return redirect(url_for("index"))
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

URL_RE = re.compile(r"(https?://[^\s<>\"]+)")


@app.template_filter("boardtime")
def boardtime(iso):
    """ISO timestamp -> 'July 31, 2026 at 07:55:25 PM' (the old board's format)."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    out = dt.strftime("%B %d, %Y at %I:%M:%S %p")
    return re.sub(r" 0(\d,)", r" \1", out)  # strip leading zero on day


@app.template_filter("rendertext")
def rendertext(text):
    """Escape a plain-text post body, linkify URLs, convert newlines to <br>."""
    if not text:
        return ""
    escaped = str(escape(text))
    linked = URL_RE.sub(r'<a href="\1" rel="nofollow">\1</a>', escaped)
    return Markup(linked.replace("\n", "<br>\n"))


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
    for node in nodes.values():
        node["children"].sort(key=lambda n: n["created_at"])
    return roots


# -------------------------------------------------------------------- pages

@app.route("/")
def index():
    page = max(1, request.args.get("page", 1, type=int))
    db = get_db()
    total_roots = db.execute(
        "SELECT COUNT(*) c FROM messages WHERE parent_id IS NULL").fetchone()["c"]
    pages = max(1, -(-total_roots // THREADS_PER_PAGE))
    offset = (page - 1) * THREADS_PER_PAGE
    root_ids = [r["id"] for r in db.execute(
        "SELECT id FROM messages WHERE parent_id IS NULL "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (THREADS_PER_PAGE, offset))]
    threads = []
    if root_ids:
        marks = ",".join("?" * len(root_ids))
        rows = db.execute(
            f"SELECT * FROM messages WHERE thread_id IN ({marks})", root_ids).fetchall()
        by_thread = {}
        for root in build_tree(rows):
            by_thread[root["id"]] = root
        threads = [by_thread[rid] for rid in root_ids if rid in by_thread]
    return render_template("index.html", threads=threads, page=page, pages=pages)


@app.route("/message/<int:message_id>")
def message(message_id):
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg is None:
        abort(404)
    thread_rows = db.execute(
        "SELECT * FROM messages WHERE thread_id = ?", (msg["thread_id"],)).fetchall()
    roots = build_tree(thread_rows)
    parent = None
    if msg["parent_id"]:
        parent = db.execute("SELECT * FROM messages WHERE id = ?",
                            (msg["parent_id"],)).fetchone()
    return render_template("message.html", msg=msg, parent=parent,
                           thread=roots[0] if roots else None)


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
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        image_url = request.form.get("image_url", "").strip()
        if not subject:
            flash("A subject is required.")
        else:
            if image_url and not image_url.lower().startswith(("http://", "https://")):
                image_url = ""
            user = current_user()
            now = datetime.now().isoformat(timespec="seconds")
            cur = db.execute(
                "INSERT INTO messages (thread_id, parent_id, subject, body, is_legacy,"
                " image_url, author_name, user_id, created_at)"
                " VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)",
                (parent["thread_id"] if parent else None,
                 parent["id"] if parent else None,
                 subject, body or None, image_url or None,
                 user["handle"], user["id"], now))
            new_id = cur.lastrowid
            if parent is None:
                db.execute("UPDATE messages SET thread_id = ? WHERE id = ?",
                           (new_id, new_id))
            db.commit()
            return redirect(url_for("message", message_id=new_id))
    subject_prefill = ""
    if parent is not None:
        subject_prefill = parent["subject"]
        if not subject_prefill.lower().startswith("re:"):
            subject_prefill = "Re: " + subject_prefill
    return render_template("post.html", parent=parent, subject_prefill=subject_prefill)


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
                 datetime.now().isoformat(timespec="seconds")))
            db.commit()
            session.clear()
            session["user_id"] = cur.lastrowid
            if first_user:
                flash("Welcome! As the first registered user you are an admin.")
            return redirect(url_for("index"))
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
                target = request.args.get("next") or url_for("index")
                if not target.startswith("/"):
                    target = url_for("index")
                return redirect(target)
        else:
            flash("Wrong handle or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


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
    counts = db.execute(
        "SELECT COUNT(*) total, SUM(is_legacy) legacy FROM messages").fetchone()
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
    db.execute(f"DELETE FROM messages WHERE id IN ({marks})", ids)
    db.commit()
    flash(f"Deleted {len(ids)} message(s).")
    if msg["parent_id"]:
        return redirect(url_for("message", message_id=msg["parent_id"]))
    return redirect(url_for("index"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
