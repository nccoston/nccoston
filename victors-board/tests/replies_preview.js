// Previews of "replies to you" at phone width: the count beside the handle,
// the page, and the Settings switch. Needs live_board.py up.
const { chromium } = require("playwright-core");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  const login = async (h) => {
    await p.goto(BASE + "/logout"); await p.goto(BASE + "/login");
    await p.fill('input[name="handle"]', h); await p.fill('input[name="password"]', "pw");
    await p.click('button[type="submit"]'); await p.waitForLoadState("networkidle");
  };
  await login("Ken");
  await p.goto(BASE + "/post");
  await p.fill('input[name="subject"]', "Who should the next coach be?*");
  await p.click('button[type="submit"]'); await p.waitForLoadState("networkidle");
  const thread = p.url();
  for (const [h, s] of [["Rich", "Chesney*"], ["danny", "Dickert*"], ["jjwalker", "anyone with a pulse*"]]) {
    await login(h); await p.goto(thread);
    await p.fill('form.board-form input[name="subject"]', s);
    await p.click('form.board-form button[type="submit"]'); await p.waitForLoadState("networkidle");
  }
  await login("Ken"); await p.goto(BASE + "/");
  await p.locator(".nav-row").nth(1).screenshot({ path: "replies-1-nav.png" });
  await p.goto(BASE + "/replies");
  await p.locator(".message-box").screenshot({ path: "replies-2-page.png" });
  await p.goto(BASE + "/settings");
  await p.locator("#set-replies").locator("..").screenshot({ path: "replies-3-settings.png" });
  await b.close();
  console.log("done");
})();
