// The post form, driven in a real browser: the pre-post warnings, the Cards
// question, and the one-in-a-hundred send-off. Needs a seeded board:
//
//   python3 victors-board/tests/live_board.py &
//   npm install playwright-core            (next to this file, or on NODE_PATH)
//   node victors-board/tests/post_form_browser.js
const { chromium } = require("playwright-core");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
(async () => {
  const b = await chromium.launch({
    executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium",
    args: ["--autoplay-policy=no-user-gesture-required"],
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

  // ---- 1. an ordinary post sails through (the dice say no)
  let p = await page(0.5);
  await p.goto(BASE + "/post");
  await p.fill('input[name="subject"]', "Jim update");
  await p.fill('textarea[name="body"]', "he's fine");
  await p.click('button[type="submit"]');
  await p.waitForLoadState("networkidle");
  ok(!onForm(p), "an ordinary post was held up");
  ok(!(await p.evaluate(() => document.querySelector("form.board-form")?.dataset.farted)),
     "the dice said no but the form was marked");
  console.log("1. ordinary post: posted, no sound");

  // ---- 2. the one in a hundred: a sound, a short wait, then the post
  p = await page(0.001);
  await p.goto(BASE + "/post");
  await p.evaluate(() => { const o = window.fart; window.fart = () => (window.__sfx = o()); });
  await p.fill('input[name="subject"]', "the dice have spoken*");
  const t0 = Date.now();
  await p.click('button[type="submit"]');
  await p.waitForTimeout(400);
  const marked = await p.evaluate(() => document.querySelector("form.board-form")?.dataset.farted === "1");
  ok(marked, "the dice said yes but nothing happened");
  const played = await p.evaluate(() => !!window.__sfx && (window.__sfx.currentTime > 0 || !window.__sfx.paused || window.__sfx.readyState > 0));
  ok(played, "the sound did not start");
  await p.waitForURL(u => !/\/post/.test(u.pathname), { timeout: 6000 });
  const held = Date.now() - t0;
  ok(held >= 300 && held < 4500, "the post was held for " + held + "ms");
  const home = await (await p.goto(BASE + "/")).text();
  ok(/the dice have spoken/.test(home), "the post did not land after the sound");
  console.log("2. one in a hundred: sound, held " + held + "ms, then posted");

  // ---- 3. Post anyway also rolls the dice (and only once)
  p = await page(0.001);
  await p.goto(BASE + "/post");
  await p.fill('input[name="subject"]', "no asterisk, and lucky");
  await p.click('button[type="submit"]');
  await p.waitForTimeout(200);
  ok(!!(await panel(p)), "no warning for a body-less post without *");
  await p.click(".postcheck-anyway");
  await p.waitForURL(u => !/\/post/.test(u.pathname), { timeout: 6000 });
  ok(!onForm(p), "Post anyway + dice did not post");
  console.log("3. Post anyway with the dice: posted once");

  // ---- 4. the Cards question still asks, with two buttons
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
  console.log("4. Cards -> main: posted on main");

  await b.close();
  console.log();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
