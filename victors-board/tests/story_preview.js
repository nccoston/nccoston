// The story page in a real browser: the chapter strip follows the scroll,
// the charts draw, nothing scrolls sideways on a phone. Screenshots at phone
// and laptop width. Needs live_board.py up on :5099.
const { chromium } = require("playwright");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
(async () => {
  const b = await chromium.launch();
  const problems = [];
  const ok = (c, m) => { if (!c) problems.push(m); };

  const p = await (await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })).newPage();
  p.on("pageerror", (e) => problems.push("JS error: " + e.message));
  await p.goto(BASE + "/story"); await p.waitForLoadState("networkidle");
  // headings are uppercased by CSS and the source wraps lines, so read the raw text and squash spaces
  const text = (await p.evaluate(() => document.body.textContent)).replace(/\s+/g, " ");
  for (const must of ["Week 15", "Live voice, on phones", "A board any assistant can read", "published the receipts", "a public running log", "The voice room that closed on thirty people", "Five homes"]) {
    if (!text.includes(must)) problems.push("missing: " + must);
  }
  ok(!text.includes("350 people"), "the hard-coded 350 is still there");
  ok((await p.$$(".chip")).length === 13, "thirteen chapter chips");
  ok((await p.$$(".chart svg")).length >= 3, "three charts");
  ok(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "the page scrolls sideways");
  await p.screenshot({ path: "story-1-phone-top.png" });
  await p.locator("#incidents").scrollIntoViewIfNeeded(); await p.waitForTimeout(900);
  ok((await p.locator(".chip.on").getAttribute("data-for")) === "incidents", "chip lit after scrolling to incidents");
  await p.screenshot({ path: "story-2-phone-incidents.png" });
  await p.click('.chip[data-for="season"]'); await p.waitForTimeout(2500);
  const y = await p.evaluate(() => document.getElementById("season").getBoundingClientRect().top);
  ok(y > 30 && y < 120, "the season chapter did not land under the strip: " + y);
  await p.screenshot({ path: "story-3-phone-season.png" });

  const lap = await (await b.newContext({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 2 })).newPage();
  await lap.goto(BASE + "/story"); await lap.waitForLoadState("networkidle");
  await lap.screenshot({ path: "story-4-laptop.png" });
  await lap.locator("#voice").scrollIntoViewIfNeeded(); await lap.waitForTimeout(700);
  await lap.screenshot({ path: "story-5-laptop-voice.png" });
  await lap.locator("#incidents").scrollIntoViewIfNeeded(); await lap.waitForTimeout(700);
  await lap.screenshot({ path: "story-6-laptop-incidents.png" });

  await b.close();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
