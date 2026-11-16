// Screenshots of the story page's new sections at phone width. Needs
// live_board.py up on :5099.
const { chromium } = require("playwright");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })).newPage();
  await p.goto(BASE + "/story"); await p.waitForLoadState("networkidle");
  // headings are uppercased by CSS, and the source wraps lines, so read the raw text and squash spaces
  const text = (await p.evaluate(() => document.body.textContent)).replace(/\s+/g, " ");
  const problems = [];
  for (const must of ["Week 15", "Live voice, on phones", "A board any assistant can read", "published the receipts", "a public running log", "The voice room that closed on thirty people"]) {
    if (!text.includes(must)) problems.push("missing: " + must);
  }
  if (text.includes("350 people")) problems.push("the hard-coded 350 is still there");
  const shoot = async (heading, file) => {
    const h = p.locator("h2", { hasText: heading }).first();
    await h.scrollIntoViewIfNeeded();
    await p.evaluate(() => window.scrollBy(0, -12));
    await p.screenshot({ path: file });
  };
  await shoot("Six days, then a season", "story-1-timeline.png");
  await p.evaluate(() => window.scrollBy(0, 520)); await p.screenshot({ path: "story-2-timeline-end.png" });
  await shoot("Live voice, on phones", "story-3-voice.png");
  await shoot("A board any assistant can read", "story-4-mcp.png");
  await shoot("The stack", "story-5-stack.png");
  await b.close();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
