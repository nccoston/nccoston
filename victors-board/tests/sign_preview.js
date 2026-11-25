// Screenshot the sign under the header on the test board (live_board.py on :5099).
//   NO_PROXY='*' no_proxy='*' node victors-board/tests/sign_preview.js
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:5099";
const OUT = process.env.OUT || "/tmp/claude-0/-home-user-nccoston/dc8cde6b-bf19-5f0f-b0b8-05892da08672/scratchpad";

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 700 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(BASE + "/login");
  await page.fill('input[name="handle"]', "Nikos");
  await page.fill('input[name="password"]', "pw");
  await page.click('button[type="submit"]');
  await page.goto(BASE + "/admin/settings");
  const since = new Date(); since.setDate(since.getDate() - 11);
  await page.fill('input[name="humiliation_at"]', since.toISOString().slice(0, 10));
  await page.fill('input[name="humiliation_what"]', "Oregon 31–7");
  await page.click('button[type="submit"]');
  await page.goto(BASE + "/");
  await page.screenshot({ path: OUT + "/sign-desktop.png", clip: { x: 0, y: 0, width: 1100, height: 420 } });
  const phone = await browser.newContext({ viewport: { width: 390, height: 700 }, deviceScaleFactor: 2 });
  const p2 = await phone.newPage();
  await p2.goto(BASE + "/");
  await p2.screenshot({ path: OUT + "/sign-phone.png", clip: { x: 0, y: 0, width: 390, height: 420 } });
  console.log(await page.locator(".sign").innerText());
  await browser.close();
})();
