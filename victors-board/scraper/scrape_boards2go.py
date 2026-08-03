#!/usr/bin/env python3
"""Clone a Boards2Go board to disk: every raw page plus a parsed threads.json.

Two sources:
  live     - scrape www.boards2go.com directly (when the board is up)
  wayback  - pull every snapshot of the board from the Internet Archive
             (works even while Boards2Go is down)

Usage:
  python scrape_boards2go.py --user thevictors                 # live site
  python scrape_boards2go.py --user thevictors --wayback       # archive.org
  python scrape_boards2go.py --user thevictors --cookie "b2g=..."  # if reading requires login

Output (default ./scrape_output/):
  raw/          every fetched page, untouched HTML (nothing is ever lost)
  threads.json  parsed messages with id, subject, author, date, body, parent

Everything is parsed defensively: if a field can't be extracted the raw HTML
still has it, so the archive is complete even if parsing needs a second pass.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing dependencies. Run:  pip install -r requirements.txt")

USER_AGENT = "VictorsBoardArchiver/1.0 (community board migration)"
DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M"
)


def log(msg):
    print(msg, flush=True)


def make_session(cookie):
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    if cookie:
        s.headers["Cookie"] = cookie
    return s


def fetch(session, url, delay, retries=4):
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=45)
            if resp.status_code == 200:
                time.sleep(delay)
                return resp.text
            log(f"  HTTP {resp.status_code} for {url} (attempt {attempt + 1})")
        except requests.RequestException as exc:
            log(f"  error {exc} for {url} (attempt {attempt + 1})")
        time.sleep(2 ** attempt)
    return None


def save_raw(out_dir, name, html):
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:150]
    (out_dir / "raw" / f"{safe}.html").write_text(html, errors="replace")


def message_id_from_url(url):
    """Pull the numeric message id out of a message.cgi URL, whatever the param name."""
    qs = parse_qs(urlparse(url).query)
    for key in ("message", "msg", "id", "mid"):
        if key in qs and qs[key] and qs[key][0].isdigit():
            return qs[key][0]
    nums = re.findall(r"\d{3,}", url)
    return nums[-1] if nums else None


def parse_date(text):
    if not text:
        return None
    m = DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), "%B %d, %Y at %I:%M:%S %p").isoformat()
    except ValueError:
        return None


def parse_index_tree(html, base_url):
    """Walk the nested list markup of a board.cgi index page.

    Returns a flat list of dicts: {url, id, subject, author, date, parent_id}.
    Parent/child comes from the <ul>/<li> nesting visible on the board.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    def handle_li(li, parent_id):
        a = li.find("a", href=re.compile(r"message\.cgi"), recursive=False)
        if a is None:
            a = li.find("a", href=re.compile(r"message\.cgi"))
        node_id = None
        if a is not None:
            url = urljoin(base_url, a["href"])
            node_id = message_id_from_url(url)
            author_tag = li.find("b")
            # date is the italic text following the author
            date_text = None
            i_tag = li.find("i")
            if i_tag:
                date_text = i_tag.get_text(" ", strip=True)
            if not date_text:
                date_text = li.get_text(" ", strip=True)
            results.append({
                "url": url,
                "id": node_id,
                "subject": a.get_text(" ", strip=True),
                "author": author_tag.get_text(strip=True) if author_tag else None,
                "date": parse_date(date_text),
                "parent_id": parent_id,
            })
        for child_list in li.find_all(["ul", "ol"], recursive=False):
            for child_li in child_list.find_all("li", recursive=False):
                handle_li(child_li, node_id or parent_id)

    for top_list in soup.find_all(["ul", "ol"]):
        if top_list.find_parent(["ul", "ol"]) is not None:
            continue  # only start from top-level lists
        for li in top_list.find_all("li", recursive=False):
            handle_li(li, None)

    # Fallback: if the nesting walk found nothing, grab every message link flat.
    if not results:
        for a in soup.find_all("a", href=re.compile(r"message\.cgi")):
            url = urljoin(base_url, a["href"])
            results.append({
                "url": url,
                "id": message_id_from_url(url),
                "subject": a.get_text(" ", strip=True),
                "author": None,
                "date": None,
                "parent_id": None,
            })
    return results


def parse_message_page(html, url):
    """Extract what we can from a message.cgi page. Raw HTML is saved regardless."""
    soup = BeautifulSoup(html, "html.parser")
    data = {"url": url, "id": message_id_from_url(url)}

    # Subject: usually the first bold/large text that isn't the board title.
    for tag in soup.find_all(["b", "font", "h1", "h2", "h3"]):
        text = tag.get_text(" ", strip=True)
        if text and len(text) > 1 and "the victors" not in text.lower():
            data["subject"] = text
            break

    page_text = soup.get_text(" ", strip=True)
    data["date"] = parse_date(page_text)

    m = re.search(r"[Bb]y\s+([^\s].{0,40}?)\s+(?:on\s+)?(?:January|February|March|"
                  r"April|May|June|July|August|September|October|November|December)",
                  page_text)
    if m:
        data["author"] = m.group(1).strip(" -–")

    # Parent: "In Response To:" link.
    parent_label = soup.find(string=re.compile(r"In Response To", re.I))
    if parent_label:
        parent_a = parent_label.find_next("a", href=re.compile(r"message\.cgi"))
        if parent_a:
            data["parent_id"] = message_id_from_url(urljoin(url, parent_a["href"]))

    # Body: the block of the page between the header metadata and the reply form.
    # Heuristic: largest table cell / paragraph that contains the date marker's
    # following content. Keep it as HTML to preserve embedded images and links.
    body_html = None
    candidates = soup.find_all(["td", "blockquote", "p", "div"])
    best_len = 0
    for c in candidates:
        if c.find("form") or c.find(["td", "blockquote"]):
            continue
        text = c.get_text(" ", strip=True)
        if DATE_RE.search(text):
            continue
        if len(text) > best_len:
            best_len = len(text)
            body_html = c.decode_contents()
    if body_html:
        data["body_html"] = body_html.strip()

    # Any embedded images
    imgs = [urljoin(url, img["src"]) for img in soup.find_all("img", src=True)]
    if imgs:
        data["images"] = imgs

    # Reply links (children) as a cross-check for the tree.
    reply_ids = []
    for a in soup.find_all("a", href=re.compile(r"message\.cgi")):
        rid = message_id_from_url(urljoin(url, a["href"]))
        if rid and rid != data["id"] and rid != data.get("parent_id"):
            reply_ids.append(rid)
    if reply_ids:
        data["linked_ids"] = sorted(set(reply_ids))
    return data


# ---------------------------------------------------------------- live mode

def scrape_live(args, out_dir):
    session = make_session(args.cookie)
    base = args.base.rstrip("/")
    index_url = f"{base}/boards/board.cgi?user={args.user}"

    index_entries = []
    seen_pages = set()
    page = 1
    empty_streak = 0
    while page <= args.max_pages:
        url = index_url if page == 1 else f"{index_url}&page={page}"
        log(f"Index page {page}: {url}")
        html = fetch(session, url, args.delay)
        if html is None:
            log("  giving up on this page")
            empty_streak += 1
            if empty_streak >= 2:
                break
            page += 1
            continue
        save_raw(out_dir, f"index_page_{page}", html)
        entries = parse_index_tree(html, url)
        new = [e for e in entries if e["id"] and e["id"] not in seen_pages]
        for e in new:
            seen_pages.add(e["id"])
        log(f"  {len(new)} new messages listed")
        if not new:
            empty_streak += 1
            if empty_streak >= 2:
                break
        else:
            empty_streak = 0
        index_entries.extend(new)
        page += 1

    messages = {}
    for i, entry in enumerate(index_entries, 1):
        mid = entry["id"]
        log(f"[{i}/{len(index_entries)}] message {mid}: {entry['subject'][:60]}")
        html = fetch(session, entry["url"], args.delay)
        record = dict(entry)
        if html is not None:
            save_raw(out_dir, f"message_{mid}", html)
            parsed = parse_message_page(html, entry["url"])
            # index data (subject/author/date/parent from the tree) wins where present
            for k, v in parsed.items():
                if record.get(k) in (None, "") and v not in (None, ""):
                    record[k] = v
        else:
            record["fetch_failed"] = True
        messages[mid] = record
    return index_entries, messages


# ------------------------------------------------------------- wayback mode

CDX = "https://web.archive.org/cdx/search/cdx"


def cdx_query(session, url_pattern, board_user):
    params = (f"?url={url_pattern}&matchType=prefix&output=json"
              f"&filter=statuscode:200&collapse=digest&limit=100000")
    text = fetch(session, CDX + params, delay=1.0)
    if not text:
        return []
    try:
        rows = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = rows[1:] if rows and rows[0] and rows[0][0] == "urlkey" else rows
    out = []
    for row in rows:
        # row: urlkey, timestamp, original, mimetype, statuscode, digest, length
        ts, original = row[1], row[2]
        if f"user={board_user}" in original or board_user in original:
            out.append((ts, original))
    return out


def scrape_wayback(args, out_dir):
    session = make_session(None)
    log("Querying the Wayback Machine CDX index...")
    board_snaps = cdx_query(session, "boards2go.com/boards/board.cgi", args.user)
    msg_snaps = cdx_query(session, "boards2go.com/boards/message.cgi", args.user)
    log(f"Found {len(board_snaps)} index snapshots, {len(msg_snaps)} message snapshots")

    # Keep the newest snapshot per message id.
    newest = {}
    for ts, original in msg_snaps:
        mid = message_id_from_url(original)
        if mid and (mid not in newest or ts > newest[mid][0]):
            newest[mid] = (ts, original)

    index_entries = []
    # newest snapshot per distinct index URL (page)
    newest_idx = {}
    for ts, original in board_snaps:
        if original not in newest_idx or ts > newest_idx[original][0]:
            newest_idx[original] = (ts, original)
    for n, (ts, original) in enumerate(newest_idx.values(), 1):
        snap_url = f"https://web.archive.org/web/{ts}id_/{original}"
        log(f"Index snapshot {n}/{len(newest_idx)}: {original} @ {ts}")
        html = fetch(session, snap_url, args.delay)
        if html:
            save_raw(out_dir, f"index_{ts}_{n}", html)
            index_entries.extend(parse_index_tree(html, original))

    messages = {}
    by_id = {}
    for e in index_entries:
        if e["id"] and e["id"] not in by_id:
            by_id[e["id"]] = e

    all_ids = sorted(set(list(newest) + list(by_id)), key=lambda x: int(x) if x.isdigit() else 0)
    log(f"{len(all_ids)} distinct messages to fetch")
    for i, mid in enumerate(all_ids, 1):
        record = dict(by_id.get(mid, {"id": mid, "url": None, "subject": None,
                                      "author": None, "date": None, "parent_id": None}))
        if mid in newest:
            ts, original = newest[mid]
            snap_url = f"https://web.archive.org/web/{ts}id_/{original}"
            log(f"[{i}/{len(all_ids)}] message {mid} @ {ts}")
            html = fetch(session, snap_url, args.delay)
            if html:
                save_raw(out_dir, f"message_{mid}", html)
                parsed = parse_message_page(html, original)
                for k, v in parsed.items():
                    if record.get(k) in (None, "") and v not in (None, ""):
                        record[k] = v
        else:
            log(f"[{i}/{len(all_ids)}] message {mid}: listed in index only (no snapshot)")
            record["index_only"] = True
        messages[mid] = record
    return index_entries, messages


# ----------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", required=True, help="board name, e.g. thevictors")
    ap.add_argument("--base", default="https://www.boards2go.com")
    ap.add_argument("--out", default="scrape_output")
    ap.add_argument("--cookie", default=None,
                    help='login cookie if reading requires it, e.g. "b2g=abc123"')
    ap.add_argument("--delay", type=float, default=1.0,
                    help="seconds between requests (be polite)")
    ap.add_argument("--max-pages", type=int, default=500)
    ap.add_argument("--wayback", action="store_true",
                    help="pull from the Internet Archive instead of the live site")
    args = ap.parse_args()

    out_dir = Path(args.out)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    if args.wayback:
        index_entries, messages = scrape_wayback(args, out_dir)
    else:
        index_entries, messages = scrape_live(args, out_dir)

    result = {
        "board": args.user,
        "source": "wayback" if args.wayback else "live",
        "scraped_at": datetime.now().isoformat(),
        "message_count": len(messages),
        "messages": messages,
    }
    out_file = out_dir / "threads.json"
    out_file.write_text(json.dumps(result, indent=1))
    log(f"\nDone. {len(messages)} messages -> {out_file}")
    log(f"Raw HTML for every page is in {out_dir / 'raw'} — nothing is lost even "
        f"if some fields failed to parse.")


if __name__ == "__main__":
    main()
