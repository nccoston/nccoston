# The Victors — self-hosted board

A clean replacement for the old Boards2Go board. Same feel, none of the
dependency: nested threaded replies, handles, subject-only `*` / `nm` posts,
the image-embed field, search, the rules block up top, and the classic look
(Verdana, purple links, nested bullets). One small Flask app, one SQLite file.

## Run it

```bash
cd app
pip install -r requirements.txt
python app.py          # http://localhost:8080
```

**The first account registered becomes the admin** — register yours immediately
after launch. From the Admin page you can:

- edit the rules/header block and the links row (raw HTML)
- open/close registration
- ban users, promote admins, reset passwords (replaces the old
  "email your handle and password" flow — members register themselves, or you
  reset a password and hand it to them privately)
- delete any message and all its replies (Delete button on the message page)

## Put it on the internet

**Render / Railway / Fly.io (easiest, free tier or ~$5/mo):** point the service
at the `app/` folder — the `Dockerfile` is picked up automatically. Attach a
persistent disk/volume mounted at `/data` (that's where `board.db` lives — no
volume means the board wipes on redeploy). Set the env var `SECRET_KEY` to any
long random string.

**A cheap VPS:**

```bash
pip install -r requirements.txt
DATA_DIR=/var/lib/victors gunicorn -b 127.0.0.1:8080 --workers 2 app:app
```

Put nginx or Caddy in front for HTTPS and point your domain at it.

**Backups:** the entire board is one file — `$DATA_DIR/board.db`. Copy it
somewhere on a cron job and the community can never lose the board again.

## Notes

- Posts are plain text; URLs are auto-linked, newlines preserved, and the
  image-URL field embeds a picture — same posting flow as the old board.
- Board title, rules text, and the links row are editable live from the Admin
  page; the defaults match the old board's header.
