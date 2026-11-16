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

  // ---- 3. "nm" typed into the message box is caught, and the fix moves it
  p = await page(0.5);
  await p.goto(BASE + "/post");
  await p.fill('input[name="subject"]', "Can anyone steelman the case?");
  await p.fill('textarea[name="body"]', "nm");
  await p.click('button[type="submit"]');
  await p.waitForTimeout(200);
  const t3 = await panel(p);
  ok(t3 && /goes at the end of the subject/.test(t3), "nm-in-the-box warning missing: " + t3);
  await p.click('.postcheck button:has-text("Put it on the subject")');
  await p.waitForURL(u => !/\/post/.test(u.pathname), { timeout: 6000 });
  const posted = await p.content();
  ok(/Can anyone steelman the case\?\*/.test(posted), "the subject did not get its *");
  ok(!/class="message-body"[^>]*>\s*(<p>)?\s*nm\b/.test(posted), "nm landed in the body");
  console.log("3. nm in the box: moved to the subject");

  await b.close();
  console.log();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
