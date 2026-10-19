// The post form, driven in a real browser: the pre-post warnings and the
// Cards question. Needs a seeded board:
//
//   python3 victors-board/tests/live_board.py &
//   npm install playwright-core            (next to this file, or on NODE_PATH)
//   node victors-board/tests/post_form_browser.js
const { chromium } = require("playwright-core");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
(async () => {
  const b = await chromium.launch({
    executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium",
  });
  const problems = [];
  const ok = (c, m) => { if (!c) problems.push(m); };

  // a fresh page per scenario, with Math.random pinned where it matters
  async function page(random) {
    const ctx = await b.newContext({ viewport: { width: 420, height: 900 } });
    const p = await ctx.newPage();
    if (random !== undefined) {
      await p.addInitScript(r => { Math.random = () => r; }, random);
    }
    p.on("pageerror", e => problems.push("JS error: " + e.message));
    await p.goto(BASE + "/login");
    await p.fill('input[name="handle"]', "chief");
    await p.fill('input[name="password"]', "pw");
    await p.click('button[type="submit"]');
    await p.waitForLoadState("networkidle");
    return p;
  }
  const panel = async (p) => { const el = await p.$(".postcheck"); return el ? el.innerText() : null; };
  const onForm = (p) => /\/post(\/\d+)?$/.test(new URL(p.url()).pathname);

  // ---- 1. an ordinary post sails through
  let p = await page(0.5);
  await p.goto(BASE + "/post");
  await p.fill('input[name="subject"]', "Jim update");
  await p.fill('textarea[name="body"]', "he's fine");
  await p.click('button[type="submit"]');
  await p.waitForLoadState("networkidle");
  ok(!onForm(p), "an ordinary post was held up");
  console.log("1. ordinary post: posted");

  // ---- 2. the Cards question asks, with two buttons
  p = await page(0.5);
  await p.goto(BASE + "/post?board=cards");
  await p.fill('input[name="subject"]', "not about cards");
  await p.fill('textarea[name="body"]', "oops");
  await p.click('button[type="submit"]');
  await p.waitForTimeout(200);
  const t = await panel(p);
  ok(t && /Cards board/.test(t), "Cards question missing");
  ok((await p.$$(".postcheck button")).length === 2, "Cards question should have two buttons");
  await p.click('.postcheck button:has-text("main board instead")');
  await p.waitForURL(u => !/\/post/.test(u.pathname), { timeout: 6000 });
  const main = await (await p.goto(BASE + "/")).text();
  ok(/not about cards/.test(main), "redirected post did not land on main");
  console.log("2. Cards -> main: posted on main");

  await b.close();
  console.log();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
