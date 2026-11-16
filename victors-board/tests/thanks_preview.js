// The thank-you page: loads logged out, no words beyond the wordmark, a tap
// starts the band and the burst, nothing scrolls. Screenshots at phone and
// laptop width. Needs live_board.py up on :5099.
const { chromium } = require("playwright");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
(async () => {
  const b = await chromium.launch();
  const problems = [];
  const ok = (c, m) => { if (!c) problems.push(m); };
  const p = await (await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })).newPage();
  p.on("pageerror", (e) => problems.push("JS error: " + e.message));
  await p.goto(BASE + "/thanks"); await p.waitForLoadState("networkidle");
  const words = (await p.evaluate(() => document.body.innerText)).trim();
  ok(words === "", "the page has words on it: " + JSON.stringify(words));
  ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight), "the page scrolls");
  ok(await p.evaluate(() => document.getElementById("song").preload === "none"), "the song would download before a tap");
  await p.waitForTimeout(1500);
  await p.screenshot({ path: "thanks-1-phone.png" });
  // a tap: the band starts (play() was called; the test browser has no audio out, so we watch the element)
  await p.evaluate(() => { window.__played = false; const s = document.getElementById("song"); const real = s.play.bind(s); s.play = () => { window.__played = true; return real(); }; });
  await p.mouse.click(195, 420);
  await p.waitForTimeout(400);
  ok(await p.evaluate(() => window.__played), "a tap did not start the song");
  ok(await p.evaluate(() => document.getElementById("flag").classList.contains("on")), "the flag did not come out");
  await p.screenshot({ path: "thanks-2-phone-tapped.png" });
  const lap = await (await b.newContext({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 2 })).newPage();
  await lap.goto(BASE + "/thanks"); await lap.waitForLoadState("networkidle"); await lap.waitForTimeout(1500);
  await lap.screenshot({ path: "thanks-3-laptop.png" });
  await b.close();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
