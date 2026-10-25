// Chat in a real browser: the room fills a phone screen with the input in
// view, who's-in-the-room folds into the count, a pill appears when messages
// land while you're reading back, a tap on a name addresses them, and the box
// shrinks with the keyboard. Also the desktop layout. Needs live_board.py up.
const { chromium } = require("playwright-core");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const problems = [];
  const ok = (c, m) => { if (!c) problems.push(m); };
  const login = async (p, h) => {
    await p.goto(BASE + "/login");
    await p.fill('input[name="handle"]', h); await p.fill('input[name="password"]', "pw");
    await p.click('button[type="submit"]'); await p.waitForLoadState("networkidle");
  };
  const say = async (p, t) => { await p.fill("#chat-text", t); await p.press("#chat-text", "Enter"); await p.waitForTimeout(1050); };
  const rect = (p, sel) => p.evaluate((s) => { const r = document.querySelector(s).getBoundingClientRect();
    return { top: r.top, bottom: r.bottom, height: r.height }; }, sel);
  const atBottom = (p) => p.evaluate(() => { const b = document.getElementById("chat-messages");
    return b.scrollTop + b.clientHeight >= b.scrollHeight - 2; });

  const phone = await (await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })).newPage();
  const desk = await (await b.newContext({ viewport: { width: 1200, height: 800 } })).newPage();
  await login(desk, "Rich"); await desk.goto(BASE + "/chat");
  await login(phone, "Ken"); await phone.goto(BASE + "/chat");

  // a conversation
  const lines = [[phone, "anyone watching the Iowa pressers"], [desk, "yes. Moore looked tired"],
    [phone, "they all look tired in October"], [desk, "Ken do you have the link from Friday"],
    [phone, "https://www.youtube.com/watch?v=FVrlVgTlH_w"], [desk, "that's the one"]];
  for (const [p, t] of lines) await say(p, t);
  await phone.waitForTimeout(2500);

  // --- phone: the room fills the screen, input in view, header one swipe up
  let f = await rect(phone, "#chat-form"), w = await rect(phone, "#chat-wrap");
  ok(f.bottom <= 844 && f.bottom > 700, "phone: the input is not at the bottom of the screen (" + f.bottom + ")");
  ok(w.top >= -8 && w.top <= 20, "phone: the page did not open on the chat (wrap top " + w.top + ")");
  ok(await phone.evaluate(() => window.pageYOffset > 200), "phone: the header was not scrolled away");
  ok(!(await phone.isVisible("#chat-roster")), "phone: the roster is showing by default");
  ok(await phone.isVisible(".chat-mention"), "phone: Ken's mention was not highlighted");
  await phone.screenshot({ path: "chat-1-phone.png" });

  // --- the count folds the roster open and closed
  await phone.click("#chat-online");
  ok(await phone.isVisible("#chat-roster"), "phone: tapping the count did not show the roster");
  // one line: every name's box starts at the same height (the commas are CSS)
  const tops = await phone.evaluate(() => Array.from(document.querySelectorAll("#chat-roster-names div"),
    (d) => Math.round(d.getBoundingClientRect().top)));
  ok(tops.length === 2 && tops[0] === tops[1], "phone: the names are not one line: " + tops);
  f = await rect(phone, "#chat-form");
  ok(f.bottom <= 844, "phone: the input left the screen when the roster opened");
  await phone.screenshot({ path: "chat-2-phone-roster.png" });
  await phone.click("#chat-online");
  ok(!(await phone.isVisible("#chat-roster")), "phone: the second tap did not hide the roster");

  // --- enough traffic to overflow the box; Ken stays pinned to the newest
  for (let i = 1; i <= 24; i++) await say(desk, "line " + i + " of the pregame argument");
  await phone.waitForTimeout(2500);
  ok(await atBottom(phone), "phone: not pinned to the newest message after traffic");
  ok(await phone.isHidden("#chat-new"), "the pill showed while already at the bottom");

  // --- reading back: new messages do not yank the scroll, the pill offers them
  await phone.evaluate(() => { document.getElementById("chat-messages").scrollTop = 0; });
  await say(desk, "Ken are you still there");
  await phone.waitForTimeout(3500);   // at least one poll tick after the send, with margin
  ok(await phone.evaluate(() => document.getElementById("chat-messages").scrollTop < 40), "the scroll was yanked while reading back");
  ok(await phone.isVisible("#chat-new"), "no pill for messages that arrived while reading back: " + JSON.stringify(await phone.evaluate(() => {
    const b = document.getElementById("chat-messages"); const last = b.lastChild && b.lastChild.textContent;
    return { top: b.scrollTop, h: b.scrollHeight, ch: b.clientHeight, kids: b.children.length, last: last, hidden: document.hidden }; })));
  await phone.screenshot({ path: "chat-3-phone-pill.png" });
  if (await phone.isVisible("#chat-new")) await phone.click("#chat-new");
  ok(await atBottom(phone), "the pill did not jump to the bottom");
  ok(await phone.isHidden("#chat-new"), "the pill stayed after the jump");

  // --- tap a name to answer them
  await phone.fill("#chat-text", "yes");
  await phone.click('#chat-messages .chat-handle[data-handle="Rich"] >> nth=-1');
  ok((await phone.inputValue("#chat-text")) === "@Rich yes", "tapping a name did not address them: " + await phone.inputValue("#chat-text"));
  await phone.click('#chat-messages .chat-handle[data-handle="Rich"] >> nth=-1');
  ok((await phone.inputValue("#chat-text")) === "@Rich yes", "a second tap doubled the name");
  ok(await phone.evaluate(() => document.activeElement.id === "chat-text"), "the input did not take focus");
  // the names in the room work the same way
  await phone.fill("#chat-text", "yes");
  await phone.click("#chat-online");
  await phone.click('#chat-roster-names .chat-handle[data-handle="Rich"]');
  ok((await phone.inputValue("#chat-text")) === "@Rich yes", "tapping a name in the room did not address them: " + await phone.inputValue("#chat-text"));
  await phone.click("#chat-online");
  await phone.press("#chat-text", "Enter"); await phone.waitForTimeout(2500);
  ok(await desk.isVisible(".chat-mention"), "desktop: Rich's mention was not highlighted");
  ok((await phone.inputValue("#chat-text")) === "", "the input did not clear after sending");

  // --- the keyboard comes up: the box shrinks, the input stays on screen
  await phone.setViewportSize({ width: 390, height: 460 });
  await phone.waitForTimeout(400);
  f = await rect(phone, "#chat-form");
  ok(f.bottom <= 460 && f.bottom > 300, "phone: the input is off screen with the keyboard up (" + f.bottom + ")");
  ok(await atBottom(phone), "phone: lost the newest message when the keyboard came up");
  await phone.screenshot({ path: "chat-4-phone-keyboard.png" });

  // --- a live poll in the room (the newest one: the room may hold old ones)
  await phone.setViewportSize({ width: 390, height: 844 });
  await say(phone, "/poll Do we beat Iowa? Yes, No, Nobody beats anybody in this game");
  await desk.waitForTimeout(2500);
  const dPoll = desk.locator(".chat-poll").last(), pPoll = phone.locator(".chat-poll").last();
  ok((await desk.locator(".chat-poll").count()) >= 1, "desktop: the poll did not arrive");
  ok((await dPoll.locator(".chat-poll-opt").count()) === 3, "desktop: wrong number of options");
  ok(/Ken asks: Do we beat Iowa\?/.test(await dPoll.innerText()), "desktop: the poll head is off");
  await dPoll.locator('.chat-poll-opt:has-text("Yes")').click();
  await pPoll.locator('.chat-poll-opt:has-text("Nobody")').click();
  await phone.waitForTimeout(3500);
  let rows = await pPoll.locator(".chat-poll-row").allInnerTexts();
  ok(/Yes\s+1\s+— Rich/.test(rows[0]) && /Nobody.*1\s+— Ken/.test(rows[2]) && !/\d/.test(rows[1]),
     "phone: the tally is off: " + JSON.stringify(rows));
  ok(await pPoll.locator(".chat-poll-opt").nth(2).evaluate((b) => b.classList.contains("chosen")), "phone: Ken's choice is not marked");
  await phone.screenshot({ path: "chat-6-phone-poll.png" });
  await dPoll.locator('.chat-poll-opt').nth(1).click();   // Rich changes his mind: No
  await phone.waitForTimeout(3500);
  rows = await pPoll.locator(".chat-poll-row").allInnerTexts();
  ok(!/\d/.test(rows[0]) && /No\s+1\s+— Rich/.test(rows[1]), "phone: Rich's change did not show: " + JSON.stringify(rows));
  ok(await dPoll.locator(".chat-poll-opt").nth(1).evaluate((b) => b.classList.contains("chosen")), "desktop: Rich's new choice is not marked");

  // --- desktop: roster column beside the box, both fitted to the window
  f = await rect(desk, "#chat-form");
  ok(f.bottom <= 800 && f.bottom > 650, "desktop: the input is not at the bottom (" + f.bottom + ")");
  ok(await desk.isVisible("#chat-roster"), "desktop: the roster column is missing");
  const rb = await rect(desk, "#chat-roster"), mb = await rect(desk, "#chat-messages");
  ok(Math.abs(rb.height - mb.height) < 2 && rb.top === mb.top, "desktop: the roster and the box are not side by side");
  await desk.screenshot({ path: "chat-5-desktop.png" });

  await b.close();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
