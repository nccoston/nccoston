# The Victors

A Michigan fan message board, self-hosted, for a community that has been
posting together since 1995. The board lived on Boards2Go until that host
died in the summer of 2026; this is the rebuild, at its own address since
3 August 2026.

- **Live:** https://the-victors-board.onrender.com
- **Members:** about 350, most of them on phones
- **Built and run by:** Nick Coston ("Nikos" on the board), a member, not a
  programmer, working with Claude; Andy Jordan ("suede") as the second pair
  of eyes on anything technical
- **Code:** one Flask app, one SQLite file, in this repository under
  `victors-board/app`

This file is the overview. `README.md` covers running, deploying, backups
and restore. `MCP.md` covers the board's read-only API for AI assistants.
The board's own running log of every change, with dates, is public at
`/stats/log`.

## What it is

The old board, kept: nested threaded replies, handles, the `*` / `nm`
subject-only post, the rules block at the top of every page, the admins and
moderators roster, purple links on white, Verdana. Members voted to keep the
rules at the top rather than fold them away. "The board is the board."

What the move made possible, in the order the community asked for it:

**Posting**
- Pictures: upload, paste from the clipboard, several per post, sized
  small to full; portrait photos stay upright; short video clips go to
  Streamable
- Any link that stands for a picture shows it: direct image links, Tenor and
  Giphy pages, Google image shares; YouTube, Streamable, Reddit, TikTok and
  X embed; Reddit's mobile share links are resolved at post time
- A safe subset of old-school HTML in post bodies
- Pre-post warnings, in maize and blue: an empty post, an untouched "Re:"
  reply, a missing `*`, a picture link that won't load, a cut-off link,
  a new thread about to land on the Cards board
- Edit your post; delete your own post while nobody has replied
- Alias posts: post under a name that isn't yours, with the real handle one
  tap away (a member's handle, or anything that looks like one, is refused)
- Voice memos on the post form, admin only; the browser encodes to MP3 so
  every phone can play every memo

**Reading**
- Read posts follow you across devices
- Replying returns you to where you were, not the top
- Search; a public stats page; RSS
- Per-device settings: light, dark, and a hidden maize-and-blue theme;
  normal, large and huge text

**Three boards:** the main board, Scores, and Cards (Lodz's card site)

**Polls:** a thread with the question as its subject; members vote with a
tap or, the old way, with a reply whose subject is their answer; names in
the box; secret ballot on request; results after you've voted; single or
pick-all-that-apply

**Hall of Fame:** nominate a post; five nominations enshrine it; admins can
enshrine on the spot; filed by year

**Pins:** any post, a reply too, pinned to the header on every page

**Game day**
- A GAME DAY banner whenever Michigan plays, with the live score, the
  waving M, and the band's pregame one tap away
- Pick 'em: Skeeps, the board's own scorekeeping account, posts the week's
  pick 'em thread on Monday, reads picks made by form or by the thirty-year
  habit of a bare "M 48 WMU 10*" thread, locks them at kickoff, enters the
  real final from ESPN, and crowns the winner on the banner
- The week line under the nav, "Michigan at Rutgers Sat 12:00 PM EDT on
  BTN · Pick 'em is open — 66 picks in", from ESPN
- A live scoreboard of the day's FBS games on Scores; the Slippery Rock
  line any day they play
- Wednesday: the newest Blue By Ninety episode in a box on the homepage

**Chat:** a members-only room, memory-only, the last 200 messages, nothing
written to disk. It fills a phone screen with the input in view, tells you
when messages land while you're reading back, lets you tap a name to answer
them, and folds who's-in-the-room into the count on a phone. The homepage
says "Chat is ROCKING" when it is.
- Live polls in the room: `/poll Do we beat Iowa? Yes, No, Nobody wins`
- Live voice: an admin opens it by tapping **voice**; from then on whoever
  talks reaches everyone in the room, nothing to find. Talking is opt-in
  (talk, mute, leave). Audio goes through Cloudflare's relay; the board
  only brokers sessions; nothing is recorded. A hit on its first night.

**Games:** the Victard Bowl, an original pixel football game with a season
mode and a board leaderboard that Skeeps posts monthly; the Stadium
Guesser, name the FBS stadium from the photo

**For AI assistants:** the board is a read-only MCP server at `/mcp`. Search,
threads, the archive in order, standings, Hall of Fame. Only what a
logged-out reader can see. See `MCP.md`.

**For admins:** header and links editing, registration on and off, bans,
renames, password resets, delete, pin, enshrine, clear the chat room, nightly
and on-demand backups with a tested restore, and diagnostic pages that answer
"why is there no pick 'em thread", "why is the pod box showing", and "is
the site slow" with numbers rather than guesses.

**Unlisted:** `/story`, the rescue told with live numbers.

## How it's built

- **Python 3, Flask 3, SQLite** in WAL mode. One process, sixteen threads,
  under gunicorn. The whole board, chat and voice included, is one file of
  Python plus a markup renderer and the MCP server.
- **Render**, Docker, starter plan, a 1 GB persistent disk at `/data` for the
  database and uploads. Render's edge runs on Cloudflare, which caches
  static files and uploads for 30 days; every static URL carries the boot
  time, so each deploy busts the cache by itself.
- **ESPN's public scoreboard feed** for games, kickoffs and networks, read
  in the background on a stale-while-revalidate cache so a slow ESPN never
  slows a page.
- **Cloudflare Realtime (SFU)** for voice. Browsers send audio to the relay
  and get the talkers back from it. The board creates relay sessions and
  passes offers and answers; the app secret never leaves the server. The
  free allowance is 1,000 GB a month of outbound audio; a season of game
  days is a few gigabytes.
- **No JavaScript framework.** The pages are server-rendered HTML with the
  small scripts chat, voice, the post warnings and the games need.
- **No analytics, no trackers, no third-party scripts** beyond the embeds
  members paste. Traffic is counted on the server, members apart from
  readers apart from robots.

Push to the branch, Render builds and deploys in under a minute. Every
commit carries a message written for the board's running log, which is
generated from git and published at `/stats/log`.

## How it's tested

Each feature ships with its test, in `victors-board/tests`, run from a clean
temporary database:

| Suite | Covers |
|---|---|
| `markup_test.py` | post metadata as data (time, author), the markup renderer |
| `gif_test.py` | GIF page links: Giphy, Tenor, Google image shares, failures |
| `poll_test.py` | thread polls: taps, replies, secret ballot, results after voting |
| `pin_test.py` | pinning any post, the header line |
| `kickoff_test.py` | kickoff and network from ESPN, TBA handling, the week line |
| `chat_test.py` | the room: send, read, presence, rate limit, live polls |
| `voice_test.py` | the voice broker against a stand-in relay; the admin gate |
| `caches_test.py`, `latency_test.py` | the background refresh, the latency page |
| `mcp_test.py` | every MCP tool, privacy (nothing a reader can't see) |
| `chat_browser.js`, `voice_browser.js`, `traditions_browser.js`, `post_form_browser.js` | the real pages in a real Chromium at phone and desktop widths, with stand-ins for the relay and the microphone |

`live_board.py` seeds a board on port 5099 for the browser suites and for
previews. Real phones and real sound are tested on the live site by the
members, who are not shy about it.

## How decisions get made

- A member asks on the board, or in chat, or by text. Nick pastes it here.
- Anything visible gets a preview before it goes out. Nick decides.
- No explanatory copy on the page. The controls say what they do or they
  don't ship.
- The community votes on anything that touches the culture. Folding the
  rules lost four to one in twenty minutes. Per-poster muting and private
  messages were declined without a vote: the board is one room.
- Nothing is charged for, ever.
- Chat is never written to disk. Voice is never recorded. The board keeps
  posts and nothing else.

## Timeline

| | |
|---|---|
| 1995 | The community forms |
| Summer 2026 | Boards2Go goes dark |
| 3 Aug 2026 | The Victors at its own address; threads, handles, the look |
| Aug 2026 | Chat, Pick 'em, Hall of Fame, Cards, live scoreboard, backups |
| Sep 2026 | Game-day engine, Victard Bowl, Stadium Guesser, settings, the MCP server, post warnings, alias posts, the running log |
| Oct 2026 | Polls as threads, chat for phones, live polls, live voice, GIF links, kickoff times |

Two hundred and twenty-five entries on the running log so far.
