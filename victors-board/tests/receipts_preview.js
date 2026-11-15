// Screenshots of The Receipts on a phone and a laptop, light and dark, plus
// a check that the season strip lights the chip for the game on screen.
// Needs live_board.py up on :5099.
const { chromium } = require("playwright");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
(async () => {
  const b = await chromium.launch();
  const problems = [];
  const ok = (c, m) => { if (!c) problems.push(m); };

  // a couple of the words on the board, so the live number isn't zero
  const seed = await (await b.newContext()).newPage();
  await seed.goto(BASE + "/login");
  await seed.fill('input[name="handle"]', "Nikos"); await seed.fill('input[name="password"]', "pw");
  await seed.click('button[type="submit"]'); await seed.waitForLoadState("networkidle");
  for (const s of ["Fire Kyle Whittingham. (nm)", "Fire Kyle Whittingham. (nm)", "I would fire Kyle Whittingham. (nm)"]) {
    await seed.goto(BASE + "/post");
    await seed.fill('input[name="subject"]', s);
    await seed.click('button[type="submit"]'); await seed.waitForLoadState("networkidle");
  }

  const phone = await (await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })).newPage();
  await phone.goto(BASE + "/receipts"); await phone.waitForLoadState("networkidle");
  ok((await phone.innerText("#fired")) !== "0", "the live count is zero");
  await phone.screenshot({ path: "receipts-1-phone-top.png" });
  // the strip follows the reader
  await phone.locator("#iu").scrollIntoViewIfNeeded();
  await phone.waitForTimeout(900);
  const lit = await phone.locator(".chip.on").getAttribute("data-for");
  ok(lit === "iu", "chip lit after scrolling to Indiana: " + lit);
  await phone.screenshot({ path: "receipts-2-phone-indiana.png" });
  // tapping a chip jumps
  await phone.click('.chip[data-for="minn"]');
  await phone.waitForTimeout(2500);   // a long smooth scroll from the bottom third
  const y = await phone.evaluate(() => document.getElementById("minn").getBoundingClientRect().top);
  ok(y > 40 && y < 120, "Minnesota did not land under the strip: " + y);
  // no sideways scroll on a phone
  ok(await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "the page scrolls sideways");
  // every receipt points at a post
  const hrefs = await phone.$$eval(".receipt", (as) => as.map((a) => a.getAttribute("href")));
  ok(hrefs.length > 40 && hrefs.every((h) => /^\/message\/\d+$/.test(h)), "receipt links: " + hrefs.length);
  await phone.screenshot({ path: "receipts-3-phone-full.png", fullPage: true });

  const dark = await (await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, colorScheme: "dark" })).newPage();
  await dark.goto(BASE + "/receipts"); await dark.waitForLoadState("networkidle");
  await dark.screenshot({ path: "receipts-4-phone-dark.png" });

  const lap = await (await b.newContext({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 2 })).newPage();
  await lap.goto(BASE + "/receipts"); await lap.waitForLoadState("networkidle");
  await lap.screenshot({ path: "receipts-5-laptop.png" });
  await lap.locator("#msu").scrollIntoViewIfNeeded(); await lap.waitForTimeout(700);
  await lap.screenshot({ path: "receipts-6-laptop-msu.png" });

  await b.close();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
