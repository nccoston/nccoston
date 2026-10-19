// Previews of thread polls at phone width: single and multiple choice, voted
// by button and by hand, as a member and as a reader.
const { chromium } = require("playwright-core");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const ctx = await b.newContext({ viewport: { width: 420, height: 1000 }, deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  const login = async (h) => {
    await p.goto(BASE + "/logout"); await p.goto(BASE + "/login");
    await p.fill('input[name="handle"]', h); await p.fill('input[name="password"]', "pw");
    await p.click('button[type="submit"]'); await p.waitForLoadState("networkidle");
  };

  // Nikos asks the question
  await login("Nikos");
  await p.goto(BASE + "/post");
  await p.fill('input[name="subject"]', "Should the band play Temptation at every game?");
  await p.fill('textarea[name="poll_options"]', "Yes\nNo\nOnly after wins");
  await p.locator("form.board-form").screenshot({ path: "poll-1-form.png" });
  await p.click('button[type="submit"]'); await p.waitForLoadState("networkidle");
  const thread = p.url();

  // Ken votes with the button
  await login("Ken"); await p.goto(thread);
  await p.locator(".bigpoll").screenshot({ path: "poll-2-fresh.png" });
  await p.click('.bigpoll-vote button:has-text("Yes")'); await p.waitForLoadState("networkidle");
  // Rich votes the old way: a reply with the answer as its subject
  await login("Rich"); await p.goto(thread);
  await p.fill('form.board-form input[name="subject"]', "No*");
  await p.click('form.board-form button[type="submit"]'); await p.waitForLoadState("networkidle");
  // danny, jjwalker, chief
  for (const [h, opt] of [["danny", "Only after wins"], ["jjwalker", "Yes"], ["chief", "Yes"]]) {
    await login(h); await p.goto(thread);
    await p.click(`.bigpoll-vote button:has-text("${opt}")`); await p.waitForLoadState("networkidle");
  }
  await login("Ken"); await p.goto(thread);
  await p.locator(".message-box").first().screenshot({ path: "poll-3-voted.png" });

  // a reader with no account sees the names, not the buttons
  const anon = await (await b.newContext({ viewport: { width: 420, height: 1000 }, deviceScaleFactor: 2 })).newPage();
  await anon.goto(thread);
  await anon.locator(".bigpoll").screenshot({ path: "poll-4-reader.png" });

  // pick all that apply
  await login("Nikos"); await p.goto(BASE + "/post");
  await p.fill('input[name="subject"]', "Best uniform combo");
  await p.fill('textarea[name="poll_options"]', "Maize\nBlue\nWhite");
  await p.check('input[name="poll_multi"]');
  await p.click('button[type="submit"]'); await p.waitForLoadState("networkidle");
  const multi = p.url();
  await login("Ken"); await p.goto(multi);
  await p.check('.bigpoll-vote input[value]:nth-of-type(1)').catch(() => {});
  const boxes = await p.$$('.bigpoll-vote input[type="checkbox"]');
  await boxes[0].check(); await boxes[1].check();
  await p.locator(".bigpoll").screenshot({ path: "poll-5-multi-form.png" });
  await p.click('.bigpoll-vote button[type="submit"]'); await p.waitForLoadState("networkidle");
  await login("Rich"); await p.goto(multi);
  await p.fill('form.board-form input[name="subject"]', "maize and blue*");
  await p.click('form.board-form button[type="submit"]'); await p.waitForLoadState("networkidle");
  await p.goto(multi);          // back to the question; replying lands on the reply
  await p.locator(".message-box").first().screenshot({ path: "poll-6-multi.png" });

  // the front page: the poll and its votes are just posts
  await p.goto(BASE + "/");
  await p.locator("ul.thread-list").first().screenshot({ path: "poll-7-front.png" });

  await b.close();
  console.log("previews written");
})();
