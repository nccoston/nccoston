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

## Backups and restore

Three layers:

1. **Nightly snapshots (automatic):** the app writes a gzipped copy of the
   database to `$DATA_DIR/backups/` on the first request of each day and keeps
   the last 7. These protect against corruption or a bad change — not against
   losing the disk.
2. **Render disk snapshots (automatic):** Render keeps its own snapshots of
   the persistent disk (service → Disk → Snapshots) and can restore one from
   the dashboard.
3. **Full offsite backup (manual, the one that matters):** Admin → Backups →
   "Download full backup" produces `victors-backup-YYYY-MM-DD.tar.gz`
   containing `board.db` (a consistent live snapshot) and the whole `uploads/`
   folder. Download one after any big week and keep it off the server.

**Restoring from a full backup** (new server, disaster, or migration):

```bash
# on the new/repaired server, with the app stopped or before first deploy:
tar -xzf victors-backup-YYYY-MM-DD.tar.gz -C $DATA_DIR
# $DATA_DIR now contains board.db and uploads/ — start the app.
```

On Render: create the service from this repo as usual (blueprint), then use
"SSH" on the service to get a shell, upload the tarball (`scp` works with the
same SSH target), extract it into `/data` as above, and restart the service.
A nightly `.db.gz` restores the same way: `gunzip` it, replace
`$DATA_DIR/board.db`, restart (photos aren't in nightly snapshots).

**A restore is only real if it's been tested** — the restore path above is
exercised by the backup test before each release of this feature.

## Notes

- Posts are plain text; URLs are auto-linked, newlines preserved, and the
  image-URL field embeds a picture — same posting flow as the old board.
- Board title, rules text, and the links row are editable live from the Admin
  page; the defaults match the old board's header.
