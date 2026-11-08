// Live voice in a real browser, with stand-ins for the two things this
// machine can't do: the relay (live_board.py with VOICE_FAKE=1 answers for
// it) and WebRTC itself (a fake PeerConnection and mic below). What this
// proves is the page's flow: the word only once an admin is in; talkers
// reaching a touched page on their own; an untouched page offered the tap;
// leave keeping you out; talk, a failed talk, mute, who's talking; the
// admin leaving closing voice; the admin clear. Real sound is the live test.
const { chromium } = require("playwright-core");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
const FAKE_RTC = `
  window.__rtc = { offers: 0, answers: 0, remote: [], closed: 0, tracks: 0 };
  class FakePC {
    constructor() { this.localDescription = null; this.ontrack = null; this._mid = 0; this._r = 0; }
    addTransceiver(track, opts) { return { mid: String(this._mid++), direction: opts && opts.direction, stop() {} }; }
    createOffer() { window.__rtc.offers++;
      if (window.__failOffer) { window.__failOffer = false; return Promise.reject(new Error("fake offer failure")); }
      return Promise.resolve({ type: "offer", sdp: "v=0 fake local offer" }); }
    createAnswer() { window.__rtc.answers++; return Promise.resolve({ type: "answer", sdp: "v=0 fake local answer" }); }
    setLocalDescription(d) { this.localDescription = d; return Promise.resolve(); }
    setRemoteDescription(d) {
      window.__rtc.remote.push(d.type);
      const m = /tracks=(\\d+)/.exec(d.sdp || "");
      const k = m ? parseInt(m[1], 10) : 0;
      for (let i = 0; i < k; i++) {
        this._r++; window.__rtc.tracks++;
        if (this.ontrack) this.ontrack({ transceiver: { mid: "r" + this._r }, streams: [new MediaStream()], track: {} });
      }
      return Promise.resolve();
    }
    close() { window.__rtc.closed++; }
    getStats() {
      const st = window.__stats || { packets: 0, level: 0 };
      const rows = [{ type: "outbound-rtp", kind: "audio", packetsSent: st.packets },
                    { type: "media-source", kind: "audio", audioLevel: st.level }];
      return Promise.resolve({ forEach: (f) => rows.forEach(f) });
    }
  }
  window.__wake = { requests: 0, releases: 0 };
  Object.defineProperty(navigator, "wakeLock", { configurable: true, value: { request: () => { window.__wake.requests++;
    const l = { release() { window.__wake.releases++; return Promise.resolve(); }, addEventListener() {} };
    return Promise.resolve(l); } } });
  window.RTCPeerConnection = FakePC;
  // like a phone: no sound until the page has been touched
  window.__touched = false;
  document.addEventListener("pointerdown", () => { window.__touched = true; }, true);
  document.addEventListener("keydown", () => { window.__touched = true; }, true);
  HTMLMediaElement.prototype.play = function () {
    return window.__touched ? Promise.resolve() : Promise.reject(new Error("NotAllowedError")); };
  const mic = { enabled: true, stopped: 0, stop() { this.stopped++; } };
  window.__mic = mic;
  navigator.mediaDevices.getUserMedia = () => Promise.resolve({ getAudioTracks: () => [mic], getTracks: () => [mic] });
`;
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const problems = [];
  const ok = (c, m) => { if (!c) problems.push(m); };
  const page = async (w, h) => {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: w < 500 ? 2 : 1 });
    await ctx.addInitScript(FAKE_RTC);
    return ctx.newPage();
  };
  const login = async (p, h) => {
    await p.goto(BASE + "/login");
    await p.fill('input[name="handle"]', h); await p.fill('input[name="password"]', "pw");
    await p.click('button[type="submit"]'); await p.waitForLoadState("networkidle");
  };
  const words = async (p) => (await p.isVisible("#voice")) ? (await p.innerText("#voice")).replace(/\s+/g, " ").trim() : "(hidden)";
  const is = async (p, want, why) => { const got = await words(p); ok(got === want, why + ": " + JSON.stringify(got)); };
  const rtc = (p) => p.evaluate(() => window.__rtc);
  const sounds = (p) => p.locator("#voice-sounds audio").count();
  const tick = (p, ms) => p.waitForTimeout(ms || 2600);
  const shot = (p, name) => p.screenshot({ path: name, clip: { x: 0, y: 0, width: 390, height: 120 } });

  const ken = await page(390, 844), rich = await page(1200, 800), nikos = await page(1200, 800);
  await login(ken, "Ken"); await ken.goto(BASE + "/chat");
  await login(rich, "Rich"); await rich.goto(BASE + "/chat");
  await login(nikos, "Nikos"); await nikos.goto(BASE + "/chat");
  await tick(ken);

  // closed: members see nothing; the admin sees the word
  await is(ken, "(hidden)", "Ken sees voice while it's closed");
  await is(rich, "(hidden)", "Rich sees voice while it's closed");
  await is(nikos, "· voice", "Nikos (admin) lacks the word");
  await shot(ken, "voice-1-closed.png");

  // the admin opens it by coming in; now the word is there for everyone
  await nikos.click("#voice-join"); await tick(nikos);
  await is(nikos, "· 🔊 talk · leave", "Nikos listening");
  await is(ken, "· voice (1)", "Ken does not see voice open");
  await shot(ken, "voice-2-open.png");

  // Rich talks. Ken is brought in on his own; his phone won't play until he touches the page, and says so
  await rich.click("#voice-join"); await tick(rich, 800);
  await rich.click("#voice-talk"); await tick(rich);
  await is(rich, "· 🎙 mute · leave 🎙 Rich", "Rich talking");
  await tick(ken, 3000);
  await is(ken, "· 🔊 talk · leave 🎙 Rich tap anywhere to hear", "untouched Ken: not in, or not told to tap");
  let r = await rtc(ken);
  ok(r.remote.join() === "offer" && r.answers === 1 && r.tracks === 1 && (await sounds(ken)) === 1, "Ken's pull: " + JSON.stringify(r));
  ok((await ken.locator("#voice-sounds audio[data-blocked]").count()) === 1, "Ken's sound is not marked blocked");
  ok((await sounds(nikos)) === 1, "Nikos does not hear Rich");
  await is(nikos, "· 🔊 talk · leave 🎙 Rich", "Nikos does not see Rich talking");
  await shot(ken, "voice-3-tap-to-hear.png");

  // Ken taps anywhere: the sound starts, the note goes
  await ken.click("#chat-messages"); await tick(ken, 300);
  await is(ken, "· 🔊 talk · leave 🎙 Rich", "the tap did not clear the note");
  ok((await ken.locator("#voice-sounds audio[data-blocked]").count()) === 0, "Ken's sound is still marked blocked");
  await shot(ken, "voice-4-auto-listening.png");

  // the talking stops: a listener who came in on his own goes out on his own (window shortened for the test)
  await ken.evaluate(() => document.getElementById("voice").setAttribute("data-quiet", "1500"));
  await rich.click("#voice-mute"); await tick(ken, 7500);
  await is(ken, "· voice (2)", "Ken did not go out when the talking stopped");
  const closedBefore = (await rtc(ken)).closed;
  await rich.click("#voice-talk"); await tick(ken, 3500);   // unmute
  await is(ken, "· 🔊 talk · leave 🎙 Rich", "Ken did not come back when the talking resumed");

  // leave means leave: Rich keeps talking, Ken stays out
  await ken.click("#voice-leave"); await tick(ken, 5500);
  await is(ken, "· voice (2) 🎙 Rich", "Ken was pulled back in after leaving");
  ok((await rtc(ken)).closed === closedBefore + 1, "Ken's connection was not closed on leave");

  // and the tap brings him back
  await ken.click("#voice-join"); await tick(ken);
  await is(ken, "· 🔊 talk · leave 🎙 Rich", "Ken's tap did not bring him back");

  // Ken's first try to talk fails in the browser: he's told, the mic is let go, he's still listening
  await ken.evaluate(() => { window.__failOffer = true; });
  await ken.click("#voice-talk"); await tick(ken, 2500);   // a poll passes: the note must survive it
  await is(ken, "· 🔊 talk · leave 🎙 Rich couldn't go live: fake offer failure", "a failed talk was silent");
  ok((await ken.evaluate(() => window.__mic.stopped)) >= 1, "the mic was kept open after a failed talk");
  await tick(ken, 4200);
  await is(ken, "· 🔊 talk · leave 🎙 Rich", "the failure note did not clear");

  // Ken talks; Rich and Nikos pull him
  await ken.evaluate(() => { document.getElementById("voice").setAttribute("data-silent", "2500");
    window.__stats = { packets: 10, level: 0.4 }; });
  await ken.click("#voice-talk"); await tick(ken);
  await is(ken, "· 🎙 mute · leave 🎙 Ken, Rich", "both talking");
  ok((await ken.evaluate(() => window.__wake.requests)) >= 1, "the screen was not kept awake in voice");

  // knowing your mic works: it lights while you talk; a silent mic, or a dead connection, is called out
  const packetsUp = setInterval(() => ken.evaluate(() => { if (window.__stats) window.__stats.packets++; }).catch(() => {}), 400);
  await tick(ken, 1600);
  ok(await ken.evaluate(() => document.getElementById("voice-icon").classList.contains("speaking")), "the mic does not light while talking");
  await ken.evaluate(() => { window.__stats.level = 0; });
  await tick(ken, 4500);
  ok(!(await ken.evaluate(() => document.getElementById("voice-icon").classList.contains("speaking"))), "the mic stays lit in silence");
  await is(ken, "· 🎙 mute · leave 🎙 Ken, Rich ⚠ your mic is silent", "a silent mic was not called out");
  await ken.evaluate(() => { window.__stats.level = 0.5; });
  await tick(ken, 1600);
  await is(ken, "· 🎙 mute · leave 🎙 Ken, Rich", "the silence warning did not clear");
  clearInterval(packetsUp);
  await tick(ken, 8000);
  await is(ken, "· 🎙 mute · leave 🎙 Ken, Rich ⚠ not getting through", "a dead connection was not called out");
  const packetsUp2 = setInterval(() => ken.evaluate(() => { if (window.__stats) window.__stats.packets++; }).catch(() => {}), 400);
  await tick(ken, 1600);
  await is(ken, "· 🎙 mute · leave 🎙 Ken, Rich", "the connection warning did not clear");
  await tick(rich);
  ok((await sounds(rich)) === 1 && (await sounds(nikos)) === 2, "Ken was not pulled by the others");
  await shot(ken, "voice-5-talking.png");

  // mute: still in, silent, off the talking line
  await ken.click("#voice-mute"); await tick(ken);
  await is(ken, "· 🔇 unmute · leave 🎙 Rich", "muted state");
  ok(!(await ken.evaluate(() => window.__mic.enabled)), "mute did not disable the mic track");
  await ken.click("#voice-talk"); await tick(ken);
  await is(ken, "· 🎙 mute · leave 🎙 Ken, Rich", "unmute");

  // the page reports what it sees, for the admin's voice check
  await tick(ken, 5500);
  const check = await nikos.evaluate(() => fetch("/admin/voice-check").then((r) => r.json()));
  const kenRow = check.peers.find((p) => p.handle === "Ken");
  ok(kenRow && kenRow.page && kenRow.page.state === "talking" && kenRow.page.pulled === 1 && kenRow.page.sounds === 1,
     "the voice check does not show Ken's page: " + JSON.stringify(kenRow));
  ok(check.open === true && check.peers.length === 3, "the voice check's room picture is off: " + JSON.stringify(check));

  // leave and come straight back while someone talks: you hear them again (suede's "when I left it died")
  await ken.click("#voice-leave"); await ken.click("#voice-join"); await tick(ken, 3500);
  await is(ken, "· 🔊 talk · leave 🎙 Rich", "Ken after leaving and rejoining at once");
  ok((await sounds(ken)) === 1, "Ken does not hear Rich after rejoining");
  ok((await ken.evaluate(() => window.__rtc.remote.filter((t) => t === "offer").length)) >= 2, "Ken's rejoin did not negotiate a fresh pull");
  await ken.evaluate(() => { window.__stats = { packets: 100, level: 0.4 }; });
  await ken.click("#voice-talk"); await tick(ken);
  await is(ken, "· 🎙 mute · leave 🎙 Ken, Rich", "Ken could not talk after rejoining");
  const packetsUp3 = setInterval(() => ken.evaluate(() => { if (window.__stats) window.__stats.packets++; }).catch(() => {}), 400);

  // the phone takes the mic away: Ken drops to listening and the room stops seeing him talk
  await ken.evaluate(() => { window.__mic.onended && window.__mic.onended(); });
  await tick(ken, 300);
  ok(/^· 🔊 talk · leave 🎙 (Ken, )?Rich mic stopped — tap talk$/.test(await words(ken)), "a lost mic was not reported: " + await words(ken));
  await tick(ken, 4500);
  await is(ken, "· 🔊 talk · leave 🎙 Rich", "the room still lists Ken as talking after his mic went");
  await ken.evaluate(() => { window.__stats = { packets: 100, level: 0.4 }; });
  await ken.click("#voice-talk"); await tick(ken);
  await is(ken, "· 🎙 mute · leave 🎙 Ken, Rich", "Ken could not talk again after the mic came back");

  // Rich leaves: his sound element goes from the others, his name goes
  await rich.click("#voice-leave"); await tick(ken);
  await is(rich, "· voice (2) 🎙 Ken", "Rich after leaving");
  ok((await sounds(ken)) === 0 && (await sounds(nikos)) === 1, "Rich's sound element lingered");

  // the admin leaves: voice stays open. Rich, out, still sees the word; Nikos sees the way to close it
  await nikos.click("#voice-leave"); await tick(rich);
  await is(rich, "· voice (1) 🎙 Ken", "Rich lost the word when the admin left");
  await is(ken, "· 🎙 mute · leave 🎙 Ken", "Ken, still in, lost his words");
  await is(nikos, "· voice (1) · close voice 🎙 Ken", "Nikos after leaving");

  // the admin closes voice: everyone is out, members lose the word
  nikos.once("dialog", (d) => d.accept());
  await nikos.click("#voice-close"); await tick(ken);
  await is(ken, "(hidden)", "Ken was not dropped by the close");
  await is(rich, "(hidden)", "Rich still sees voice after the close");
  await is(nikos, "· voice", "Nikos after the close");

  // and the clear does the same
  await nikos.click("#voice-join"); await tick(nikos);
  await is(ken, "· voice (1)", "voice did not reopen");
  nikos.once("dialog", (d) => d.accept());
  await nikos.click("#chat-clear"); await tick(ken);
  await is(ken, "(hidden)", "Ken still sees voice after the clear");
  await is(nikos, "· voice", "Nikos after the clear");
  ok((await rtc(ken)).closed >= closedBefore + 2, "Ken's connections were not closed by the clear");
  ok((await ken.evaluate(() => window.__wake.releases)) >= 1, "the screen lock was not let go on the way out");
  clearInterval(packetsUp2); clearInterval(packetsUp3);

  // one-touch launch: the admin opens /chat?voice=talk and is talking with no tap; a member's ?voice=listen joins
  const nikos2 = await page(390, 844);
  await login(nikos2, "Nikos");
  await nikos2.evaluate(() => { window.__stats = { packets: 100, level: 0.4 }; });
  await nikos2.goto(BASE + "/chat?voice=talk"); await tick(nikos2, 4000);
  await is(nikos2, "· 🎙 mute · leave 🎙 Nikos", "the admin's one-touch launch did not land talking");
  ok((await nikos2.evaluate(() => window.__wake.requests)) >= 1, "the launch did not keep the screen on");
  const ken2 = await page(390, 844);
  await login(ken2, "Ken");
  await ken2.goto(BASE + "/chat?voice=listen"); await tick(ken2, 4000);
  ok(/^· 🔊 talk · leave 🎙 Nikos/.test(await words(ken2)), "a member's listen launch did not join: " + await words(ken2));
  ok((await sounds(ken2)) === 1, "the listen launch does not hear the talker");
  await nikos2.click("#voice-leave"); await nikos2.evaluate(() => fetch("/chat/voice/close", { method: "POST" })); await tick(ken2);

  await b.close();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
