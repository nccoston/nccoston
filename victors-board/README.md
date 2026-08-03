# The Victors — Boards2Go migration kit

Everything needed to get the community off Boards2Go for good:

| Piece | What it does |
|---|---|
| `scraper/` | Clones the old board — every thread, reply, author, and date — from the live site **or** from Wayback Machine snapshots while Boards2Go is down |
| `app/` | A self-hosted replacement board that looks and works like the old one |
| `app/import_scrape.py` | Loads the cloned archive into the new board so all the history is there |

The new board keeps the things that made the old one work: nested threaded
replies, handles, subject-only `*` / `nm` posts, the image-embed field, search,
the rules block up top, and the classic look (Verdana, purple links, nested
bullets). It adds what Boards2Go never had: it's yours — your server, your
database, your uptime.

---

## Step 1 — Clone the old board

Run this from any machine with normal internet access (it can't run from a
locked-down environment):

```bash
cd scraper
pip install -r requirements.txt

# While Boards2Go is down, pull everything the Internet Archive has:
python scrape_boards2go.py --user thevictors --wayback

# Once/if the board comes back up, run against the live site (re-runs are safe;
# the importer skips anything already imported):
python scrape_boards2go.py --user thevictors

# If reading the live board requires being logged in, pass your browser cookie:
python scrape_boards2go.py --user thevictors --cookie "b2gsession=PASTE_FROM_BROWSER"
```

Output goes to `scrape_output/`:

- `threads.json` — every message parsed (id, subject, author, date, body, parent)
- `raw/` — the untouched HTML of every page fetched. **Keep this folder.** Even
  if some field fails to parse, nothing is lost — parsing can be re-run against
  it later.

The scraper waits 1 second between requests by default (`--delay` to change) —
be polite to whatever server you're pulling from.

## Step 2 — Import the archive into the new board

```bash
cd app
pip install -r requirements.txt
python import_scrape.py ../scraper/scrape_output/threads.json
```

Re-running is safe: already-imported messages (matched by their old Boards2Go
id) are skipped, so you can scrape again later and import just the new stuff.

## Step 3 — Run the board

```bash
cd app
python app.py          # http://localhost:8080
```

**The first account registered becomes the admin.** Register yours immediately
after launch. From the Admin page you can:

- edit the rules/header block and the links row
- open/close registration
- ban users, promote admins, reset passwords (this replaces the old
  "email your handle and password" flow — members register themselves, or you
  reset a password and hand it to them)
- delete any message and its replies (Delete button on the message page)

Imported posts show their original author handle and date, tagged
`[archived from Boards2Go]`. When members register their old handles, new posts
appear under the same name.

## Step 4 — Put it on the internet

Any of these works; the app is one small Flask process with a SQLite file.

**Render / Railway / Fly.io (easiest, ~$5/mo or free tier):** point the service
at the `app/` folder — the `Dockerfile` is picked up automatically. Attach a
persistent disk/volume mounted at `/data` (that's where `board.db` lives — no
volume means the board wipes on redeploy). Set the env var `SECRET_KEY` to any
long random string. Then upload your imported `board.db` to the volume, or run
the importer once against it.

**A cheap VPS:**

```bash
pip install -r requirements.txt
DATA_DIR=/var/lib/victors gunicorn -b 127.0.0.1:8080 --workers 2 app:app
```

Put nginx/Caddy in front for HTTPS and point your domain at it.

**Backups:** the entire board is one file — `$DATA_DIR/board.db`. Copy it
anywhere on a cron job and you can never lose the board again.

---

## Notes

- Old post bodies are sanitized on import (scripts and event handlers stripped;
  formatting, links, and embedded images kept).
- New posts are plain text with URLs auto-linked, plus the image-URL embed
  field, same as the old board.
- `scrape_output/raw/` is your permanent archive of the original site —
  independent of this app.
