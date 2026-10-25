// Live voice in a real browser, with stand-ins for the two things this
// machine can't do: the relay (live_board.py with VOICE_FAKE=1 answers for
// it) and WebRTC itself (a fake PeerConnection and mic below). What this
// proves is the page's flow: the words beside the count, the taps, who's
// talking, pulling talkers, dropping them, mute, leave, the admin clear.
// Real sound through real phones is the live test.
const { chromium } = require("playwright-core");
const BASE = process.env.BOARD || "http://127.0.0.1:5099";
const FAKE_RTC = `
  window.__rtc = { offers: 0, answers: 0, remote: [], closed: 0, tracks: 0 };
  class FakePC {
    constructor() { this.localDescription = null; this.ontrack = null; this._mid = 0; this._r = 0; }
    addTransceiver(track, opts) { return { mid: String(this._mid++), direction: opts && opts.direction }; }
    createOffer() { window.__rtc.offers++; return Promise.resolve({ type: "offer", sdp: "v=0 fake local offer" }); }
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
  }
  window.RTCPeerConnection = FakePC;
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
  const voiceText = (p) => p.innerText("#voice").then((t) => t.replace(/\s+/g, " ").trim());
  const rtc = (p) => p.evaluate(() => window.__rtc);
  const tick = (p, ms) => p.waitForTimeout(ms || 2600);

  const ken = await page(390, 844), rich = await page(1200, 800), nikos = await page(1200, 800);
  await login(ken, "Ken"); await ken.goto(BASE + "/chat");
  await login(rich, "Rich"); await rich.goto(BASE + "/chat");
  await login(nikos, "Nikos"); await nikos.goto(BASE + "/chat");

  // off: one word
  ok((await voiceText(ken)) === "voice", "off state is not the one word: " + await voiceText(ken));
  await ken.screenshot({ path: "voice-1-off.png", clip: { x: 0, y: 0, width: 390, height: 120 } });

  // Ken listens: a session, no mic asked for, nothing to hear yet
  await ken.click("#voice-join");
  await tick(ken);
  ok(/^🔊 talk · leave$/.test(await voiceText(ken)), "listening state words: " + await voiceText(ken));
  ok((await rtc(ken)).offers === 0, "listening asked for an offer (it should not touch the mic)");
  ok(/voice \(1\)/.test(await voiceText(rich)), "Rich does not see one in voice: " + await voiceText(rich));
  await ken.screenshot({ path: "voice-2-listening.png", clip: { x: 0, y: 0, width: 390, height: 120 } });

  // Rich joins and talks: his offer is answered; Ken pulls him and answers the relay's offer
  await rich.click("#voice-join"); await tick(rich, 800);
  await rich.click("#voice-talk"); await tick(rich);
  ok(/^🎙 mute · leave 🎙 Rich$/.test(await voiceText(rich)), "talking state words: " + await voiceText(rich));
  let r = await rtc(rich);
  ok(r.offers === 1 && r.remote.join() === "answer", "Rich's publish negotiation: " + JSON.stringify(r));
  await tick(ken);
  r = await rtc(ken);
  ok(r.remote.join() === "offer" && r.answers === 1 && r.tracks === 1, "Ken's pull negotiation: " + JSON.stringify(r));
  ok((await ken.locator("#voice-sounds audio").count()) === 1, "Ken has no audio element for Rich");
  ok(/🎙 Rich$/.test(await voiceText(ken)), "Ken does not see Rich talking: " + await voiceText(ken));
  ok(/🎙 Rich$/.test(await voiceText(nikos)), "Nikos (not in voice) does not see who's talking: " + await voiceText(nikos));
  await ken.screenshot({ path: "voice-3-rich-talking.png", clip: { x: 0, y: 0, width: 390, height: 120 } });

  // Ken talks too; Rich pulls him
  await ken.click("#voice-talk"); await tick(ken);
  ok(/^🎙 mute · leave 🎙 Ken, Rich$/.test(await voiceText(ken)), "both talking: " + await voiceText(ken));
  await tick(rich);
  r = await rtc(rich);
  ok(r.remote.join() === "answer,offer" && r.tracks === 1, "Rich did not pull Ken: " + JSON.stringify(r));
  await ken.screenshot({ path: "voice-4-both-talking.png", clip: { x: 0, y: 0, width: 390, height: 120 } });

  // mute: still in, silent, off the talking line
  await ken.click("#voice-mute"); await tick(ken);
  ok(/^🔇 unmute · leave 🎙 Rich$/.test(await voiceText(ken)), "muted state words: " + await voiceText(ken));
  ok(!(await ken.evaluate(() => window.__mic.enabled)), "mute did not disable the mic track");
  await ken.screenshot({ path: "voice-5-muted.png", clip: { x: 0, y: 0, width: 390, height: 120 } });
  await ken.click("#voice-talk"); await tick(ken);
  ok(/^🎙 mute · leave 🎙 Ken, Rich$/.test(await voiceText(ken)), "unmute: " + await voiceText(ken));

  // Rich leaves: Ken's audio element for him goes, his name goes
  await rich.click("#voice-leave"); await tick(ken);
  ok((await voiceText(rich)) === "voice (1) 🎙 Ken", "Rich after leaving: " + await voiceText(rich));
  ok((await rtc(rich)).closed === 1 && (await rich.evaluate(() => window.__mic.stopped)) >= 1, "Rich's connection/mic were not closed");
  ok((await ken.locator("#voice-sounds audio").count()) === 0, "Ken still holds Rich's audio element");
  ok(/^🎙 mute · leave 🎙 Ken$/.test(await voiceText(ken)), "Ken after Rich left: " + await voiceText(ken));

  // the admin clears the room: Ken is dropped out of voice too
  nikos.once("dialog", (d) => d.accept());
  await nikos.click("#chat-clear"); await tick(ken);
  ok((await voiceText(ken)) === "voice", "Ken was not dropped by the clear: " + await voiceText(ken));
  ok((await rtc(ken)).closed === 1, "Ken's connection was not closed by the clear");

  await b.close();
  console.log(problems.length ? "PROBLEMS:\n  " + problems.join("\n  ") : "ALL PASS");
  process.exit(problems.length ? 1 : 0);
})();
