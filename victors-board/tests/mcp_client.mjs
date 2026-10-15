// The reference MCP client, over a real socket, against the board.
// My own tests prove my code agrees with itself; this proves it agrees with
// the people who wrote the protocol.
//
//   python3 victors-board/tests/live_board.py &     (a seeded board on :5099)
//   npm install @modelcontextprotocol/sdk            (anywhere on NODE_PATH)
//   node victors-board/tests/mcp_client.mjs
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport }
  from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const problems = [];
const ok = (cond, msg) => { if (!cond) problems.push(msg); };
const asJson = (r) => JSON.parse(r.content[0].text);

const transport = new StreamableHTTPClientTransport(
  new URL(process.env.BOARD || "http://127.0.0.1:5099/mcp"));
const client = new Client({ name: "victors-probe", version: "1.1.0" },
                          { capabilities: {} });
await client.connect(transport);
console.log("connected — handshake completed against the real transport");
ok(client.getServerVersion()?.name === "the-victors-board", "serverInfo.name wrong");
ok(/calls a minute/.test(client.getInstructions() || ""), "instructions lack the rate limit");

const { tools } = await client.listTools();
console.log("tools:", tools.map(t => t.name).join(", "));
ok(tools.length === 9, `expected 9 tools, got ${tools.length}`);

// read the whole seeded archive the cheap way
let since = 0, total = 0, calls = 0;
for (;;) {
  const pg = asJson(await client.callTool({ name: "get_posts", arguments: { since_id: since, limit: 5 } }));
  calls++; total += pg.returned;
  if (!pg.has_more) break;
  since = pg.next_since_id;
}
const stats = asJson(await client.callTool({ name: "board_stats", arguments: {} }));
console.log(`get_posts walked ${total} posts in ${calls} calls; board_stats says ${stats.messages}`);
ok(total === stats.messages, "get_posts did not return every post");

const found = asJson(await client.callTool({ name: "search_board", arguments: { query: "1969", limit: 2 } }));
ok(found.matches >= 1, "search found nothing");
ok("subject_only" in found.results[0], "subject_only missing from search results");
const thread = asJson(await client.callTool({ name: "get_thread", arguments: { thread_id: found.results[0].id } }));
ok(thread.reply_count >= 1, "thread came back without replies");
const one = asJson(await client.callTool({ name: "get_post", arguments: { post_id: thread.thread.id } }));
ok(one.id === thread.thread.id && typeof one.body === "string", "get_post shape wrong");

const bad = await client.callTool({ name: "recent_threads", arguments: { board: "nope" } });
ok(bad.isError === true, "a bad board name was not flagged isError");
let threw = false;
try { await client.callTool({ name: "delete_everything", arguments: {} }); } catch (e) { threw = true; }
ok(threw, "an unknown tool did not raise");

await client.close();
console.log();
console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
process.exit(problems.length ? 1 : 0);
