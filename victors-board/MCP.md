# The Victors, as an MCP server

The board speaks [Model Context Protocol](https://modelcontextprotocol.io) at
`/mcp`. Point an AI assistant at it and it can search the board's posts,
read a thread, read the archive in order, and look up the standings — read-only,
over the network, with no account. The community dates to 1995; the archive
here begins 3 August 2026, the day the board moved to its own address.

```
https://the-victors-board.onrender.com/mcp
```

## Connecting

**Claude Code**

```
claude mcp add --transport http victors https://the-victors-board.onrender.com/mcp
```

**Claude Desktop** — in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "victors": {
      "type": "http",
      "url": "https://the-victors-board.onrender.com/mcp"
    }
  }
}
```

**Anything else** — it's Streamable HTTP, so any MCP client works. By hand:

```bash
curl -X POST https://the-victors-board.onrender.com/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## What it exposes

| Tool | What it does |
| --- | --- |
| `search_board` | Search subjects and bodies, newest first. Filter by board, author, or one day; page with `offset`. |
| `get_posts` | Every post after an id, oldest first, full text. Read the archive or keep a copy current: pass `next_since_id` back until `has_more` is false. |
| `get_post` | One post by id, full text. A deleted post comes back as `{deleted: true}`, not an error. |
| `get_thread` | A whole conversation — opening post and replies, in order, full text. |
| `recent_threads` | What the board is talking about now, with reply counts. |
| `hall_of_fame` | Posts the members voted in. The best single answer to "what is this community like". |
| `board_stats` | Members, posts, threads, traffic, top posters. |
| `pickem_standings` | The weekly score-prediction game. |
| `arcade_stats` | Totals for Victard Bowl and Stadium Guesser. |

Every post carries `subject_only` — true when the subject is the whole post,
which is about three posts in four here — and `author` is always the member.
An aliased post also carries `alias`, the name the board shows for it. `url`
is the post itself; `thread_url` is the top of its thread. Search's `matches`
is the total; `returned` is this page.

Two resources come with it. `victors://about` is the one that matters: it tells
the model the conventions it would otherwise misread — that a subject ending in
an asterisk *is* the whole post, that Skeeps is a reserved account and not a
person, and that the pick 'em is scored by closest to the final score rather
than by picking the winner. Without that, a model reads the board wrong in
exactly the ways a new member does.

## The three decisions

**Read-only, structurally.** This is not "I was careful not to write any
INSERTs." `mcp_server.py` opens its own SQLite handle with `mode=ro`, so the
driver refuses a write. Nothing reachable from `/mcp` can post, edit, or
delete, and a future careless edit to that file still can't. The test suite
asserts it by trying.

**Nothing private, by a rule that can be tested.** The board is already
readable logged out — threads, search, the Hall of Fame, the pick 'em
standings and `/stats` are public URLs with an RSS feed alongside them. So the
rule is: *this server may return exactly what a logged-out browser can already
see, and nothing else.* Both arcade leaderboards sit behind a login, so those
come back as totals with no handles attached. The tests seed a database where
every post carries the same IP and every account the same password hash, then
try to reach them through every tool and every argument; if search could touch
those columns, the probes would match everything.

**No new service, no new dependency.** It's a Flask blueprint on the existing
app, so it deploys with the board and costs nothing extra. MCP's Streamable
HTTP transport is JSON-RPC 2.0 over a single POST endpoint — about two hundred
lines — which is cheaper than bolting an ASGI server onto a synchronous WSGI
app running one worker in 512MB. The tradeoff: no server-initiated SSE stream,
so `GET /mcp` returns 405 and says why. Nothing here needs to push.

## Limits

The board pays for its own bandwidth and has blown through a month's
allowance once already, so every tool is capped — but sized so that reading
the whole archive is a few hundred calls, not fifty thousand page loads:

- `search_board`: 25 hits per call, page with `offset`.
- `get_posts`: 200 posts per call, full text.
- `get_thread`: 200 replies, full text.
- Full text means up to 20,000 characters a post; lists and search results
  trim at 1,200. HTML is stripped on the way out, because the model wants
  the words and not the tags.
- 60 requests a minute per address. Past that, a 429 with `Retry-After: 60`.

If you want a copy of the board, use `get_posts` from `since_id: 0` and
follow `next_since_id`; keep it current by calling again from the last id
you have. That is the cheapest way through for the board and the fastest
for you.

Setting `MCP_TOKEN` in the environment requires `Authorization: Bearer <token>`
on every call. Unset, the endpoint is as public as the board it sits on.

## Testing

Two suites, because they prove different things:

- `tests/mcp_test.py` — protocol conformance, the caps, the rate limit, and the
  privacy invariant above.
- `tests/mcp_client.mjs` — the *reference* client from the official MCP SDK,
  connecting over a real socket. The first suite proves the code agrees with
  itself; this one proves it agrees with the people who wrote the spec.

## Why bother

A message board is a strange thing to make agent-readable, which is roughly
the point. The community's history is thirty years of context that lived in a
format nothing could reach: no API, no export, and for most of its life no
guarantee it would exist next week. It is now a few hundred lines from being
something an assistant can actually answer questions from.

That generalizes further than the board does. The interesting question about
distribution right now is not which integrations a platform has — it is what
an AI can reach on its own, and a protocol endpoint is how something small
gets reached at all.
