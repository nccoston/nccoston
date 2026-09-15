# The Victors, as an MCP server

The board speaks [Model Context Protocol](https://modelcontextprotocol.io) at
`/mcp`. Point an AI assistant at it and it can search thirty years of posts,
read a thread, and look up the standings — read-only, over the network, with
no account.

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
| `search_board` | Search subjects and bodies, newest first. Filter by board or author. |
| `get_thread` | A whole conversation — opening post and replies, in order. |
| `recent_threads` | What the board is talking about now, with reply counts. |
| `hall_of_fame` | Posts the members voted in. The best single answer to "what is this community like". |
| `board_stats` | Members, posts, threads, traffic, top posters. |
| `pickem_standings` | The weekly score-prediction game. |
| `arcade_stats` | Totals for Victard Bowl and Stadium Guesser. |

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
allowance once already, so every tool is capped: 25 search results, 50
threads, 200 replies, posts truncated at 1200 characters, and 30 requests a
minute per address. Post bodies are stripped of HTML on the way out, because
the model wants the words and not the tags.

Setting `MCP_TOKEN` in the environment requires `Authorization: Bearer <token>`
on every call. Unset, the endpoint is as public as the board it sits on.

## Testing

Two suites, because they prove different things:

- `mcp_test.py` — protocol conformance, the caps, the rate limit, and the
  privacy invariant above.
- `mcp_client.mjs` — the *reference* client from the official MCP SDK,
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
