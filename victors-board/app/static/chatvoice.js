// Live voice on top of the chat room.
//
// Voice is open while an admin is in it. Then whoever is talking reaches
// everyone in chat on their own. A phone may refuse to play sound on a page
// nobody has tapped yet; then the page says "tap anywhere to hear" and the
// next tap, anywhere, starts it. Talking is opt-in:
// "talk" asks for the mic; "mute" keeps you in but silent; "leave" drops
// you out and keeps you out until you tap back in. When no admin is in
// voice, members don't see the word at all.
//
// Audio goes through Cloudflare's relay; this page only ever talks to the
// board, which brokers the relay sessions. Nothing is recorded anywhere.
// One relay session, one PeerConnection, one negotiation at a time.
(function () {
  var el = document.getElementById("voice");
  if (!el || !window.RTCPeerConnection) return;
  var ICE = el.getAttribute("data-ice");
  var ADMIN = el.getAttribute("data-admin") === "1";
  var pc = null, mic = null, micTrack = null;
  var state = "off";          // off | in | talking | muted
  var joining = false;        // between the tap and the board's answer
  var auto = false;           // we joined on our own, to listen
  var optedOut = false;       // they tapped leave: stay out until they tap in
  var note = null, noteUntil = 0;   // a few words beside the count, for a while
  var quietSince = null;      // when the talking stopped, for auto-listeners
  var seen = {};              // "sid|track" -> true, tracks we've pulled
  var byMid = {};             // relay mid -> "sid|track"
  var audio = {};             // "sid|track" -> <audio>
  var lastEpoch = null, lastVoice = null;
  var chain = Promise.resolve();
  var sounds = document.createElement("div");
  sounds.id = "voice-sounds";
  document.body.appendChild(sounds);

  document.addEventListener("pointerdown", replay, true);
  document.addEventListener("keydown", replay, true);

  function post(path, fields) {
    var body = new FormData();
    Object.keys(fields || {}).forEach(function (k) { body.append(k, fields[k]); });
    return fetch(path, { method: "POST", body: body }).then(function (r) { return r.json(); });
  }
  function queue(fn) {
    chain = chain.then(fn, fn).catch(function () {});
    return chain;
  }

  // --- the words beside the count
  function link(id, text, fn) {
    var a = document.createElement("a");
    a.href = "#"; a.id = id; a.textContent = text;
    a.addEventListener("click", function (e) { e.preventDefault(); fn(); });
    return a;
  }
  function say(text, forHowLong) {
    note = text; noteUntil = Date.now() + (forHowLong || 4000);
    draw();
    if (forHowLong !== Infinity) setTimeout(draw, (forHowLong || 4000) + 50);
  }
  function draw() {
    el.textContent = "";
    var v = lastVoice || {};
    var who = v.talking || [];
    var show = state !== "off" || ADMIN || v.open;
    if (!show) { el.hidden = true; return; }
    el.hidden = false;
    el.appendChild(document.createTextNode(" · "));
    if (state === "off") {
      el.appendChild(link("voice-join", v.count ? "voice (" + v.count + ")" : "voice", join));
    } else {
      el.appendChild(document.createTextNode(
        state === "talking" ? "🎙 " : state === "muted" ? "🔇 " : "🔊 "));
      if (state === "in") el.appendChild(link("voice-talk", "talk", talk));
      if (state === "talking") el.appendChild(link("voice-mute", "mute", mute));
      if (state === "muted") el.appendChild(link("voice-talk", "unmute", unmute));
      el.appendChild(document.createTextNode(" · "));
      el.appendChild(link("voice-leave", "leave", leave));
    }
    if (who.length) {
      var w = document.createElement("span");
      w.id = "voice-who";
      w.textContent = " 🎙 " + who.join(", ");
      el.appendChild(w);
    }
    if (note && Date.now() < noteUntil) {
      var n = document.createElement("span");
      n.className = "hint"; n.textContent = " " + note;
      el.appendChild(n);
    }
  }

  function connection() {
    if (pc) return pc;
    pc = new RTCPeerConnection({ iceServers: ICE ? [{ urls: ICE }] : [] });
    pc.ontrack = function (e) {
      var key = byMid[e.transceiver && e.transceiver.mid];
      var a = document.createElement("audio");
      a.autoplay = true;
      a.setAttribute("playsinline", "");
      a.srcObject = (e.streams && e.streams[0]) || new MediaStream([e.track]);
      sounds.appendChild(a);
      if (key) audio[key] = a;
      play(a);
    };
    return pc;
  }
  // a phone may refuse to play until the page is touched; the next touch retries
  function play(a) {
    var p = a.play();
    if (p && p.catch) p.catch(function () { a.setAttribute("data-blocked", "1"); say("tap anywhere to hear", Infinity); });
  }
  function replay() {
    var blocked = sounds.querySelectorAll("audio[data-blocked]");
    if (!blocked.length) return;
    for (var i = 0; i < blocked.length; i++) { blocked[i].removeAttribute("data-blocked"); play(blocked[i]); }
    if (noteUntil === Infinity) { note = null; noteUntil = 0; draw(); }
  }

  // --- listening: pull whoever is talking into our session
  function pull(tracks) {
    return queue(function () {
      var want = tracks.filter(function (t) { return !seen[t.sid + "|" + t.track]; });
      if (!want.length || state === "off") return;
      want.forEach(function (t) { seen[t.sid + "|" + t.track] = true; });
      return post("/chat/voice/pull", { tracks: JSON.stringify(want) }).then(function (d) {
        if (!d.ok) { want.forEach(function (t) { delete seen[t.sid + "|" + t.track]; }); return; }
        (d.tracks || []).forEach(function (t) { if (t.mid != null) byMid[t.mid] = t.sid + "|" + t.track; });
        if (!d.sdp || d.type !== "offer") return;
        var c = connection();
        return c.setRemoteDescription({ type: "offer", sdp: d.sdp })
          .then(function () { return c.createAnswer(); })
          .then(function (a) { return c.setLocalDescription(a); })
          .then(function () { return post("/chat/voice/answer", { sdp: c.localDescription.sdp }); });
      });
    });
  }
  function drop(key) {
    delete seen[key];
    if (audio[key]) { sounds.removeChild(audio[key]); delete audio[key]; }
  }

  // --- the taps
  function join(byItself) {
    if (state !== "off") return;
    state = "in"; joining = true; auto = !!byItself; optedOut = false; draw();
    connection();
    queue(function () {
      return post("/chat/voice/join").then(function (d) {
        joining = false;
        if (!d.ok) { hangup(); say(d.error || "voice is not available"); return; }
        if (lastVoice) pull(lastVoice.tracks || []);
      }, function () { joining = false; hangup(); say("voice is not available"); });
    });
  }
  function talk() {
    if (state !== "in") return;
    var md = navigator.mediaDevices;
    if (!md || !md.getUserMedia) { say("no mic"); return; }
    md.getUserMedia({ audio: true }).then(function (stream) {
      mic = stream; micTrack = stream.getAudioTracks()[0];
      var c = connection();
      var tx = c.addTransceiver(micTrack, { direction: "sendonly" });
      // run the whole exchange in the queue, and find out if it failed:
      // the queue swallows errors so the room keeps working
      var failed = null;
      return queue(function () {
        return c.createOffer()
          .then(function (o) { return c.setLocalDescription(o); })
          .then(function () { return post("/chat/voice/publish", { sdp: c.localDescription.sdp, mid: tx.mid }); })
          .then(function (d) {
            if (!d.ok) { throw new Error(d.error || "the relay did not take the mic"); }
            return c.setRemoteDescription({ type: "answer", sdp: d.sdp });
          })
          .then(function () { state = "talking"; auto = false; draw(); })
          .catch(function (e) { failed = e; });
      }).then(function () {
        if (!failed) return;
        try { tx.stop(); } catch (e) {}
        if (mic) { mic.getTracks().forEach(function (t) { t.stop(); }); mic = null; micTrack = null; }
        state = "in";
        say("couldn't go live: " + (failed.message || failed));
      });
    }).catch(function () {
      if (mic) { mic.getTracks().forEach(function (t) { t.stop(); }); mic = null; micTrack = null; }
      say("mic blocked");
    });
  }
  function mute() {
    if (state !== "talking" || !micTrack) return;
    micTrack.enabled = false; state = "muted"; draw();
    post("/chat/voice/talking", { on: "0" });
  }
  function unmute() {
    if (state !== "muted" || !micTrack) return;
    micTrack.enabled = true; state = "talking"; draw();
    post("/chat/voice/talking", { on: "1" });
  }
  function hangup() {
    if (mic) { mic.getTracks().forEach(function (t) { t.stop(); }); }
    mic = null; micTrack = null;
    if (pc) { try { pc.close(); } catch (e) {} }
    pc = null; seen = {}; byMid = {}; audio = {};
    sounds.textContent = "";
    state = "off"; auto = false; quietSince = null;
    if (noteUntil === Infinity) { note = null; noteUntil = 0; }
  }
  function leave(byItself) {
    if (state === "off") return;
    hangup();
    if (!byItself) optedOut = true;
    draw();
    post("/chat/voice/leave");
  }
  window.addEventListener("pagehide", function () {
    if (state !== "off" && navigator.sendBeacon) navigator.sendBeacon("/chat/voice/leave");
  });

  // --- every chat poll brings the room's voice picture
  window.chatVoice = function (v) {
    if (!v) return;
    lastVoice = v;
    if (lastEpoch !== null && v.epoch !== lastEpoch && state !== "off") hangup();   // admin cleared the room
    lastEpoch = v.epoch;
    if (state !== "off" && !v.me && !joining) hangup();   // the board no longer has us (timed out)
    var talking = (v.talking || []).length > 0;
    if (state !== "off") {
      var live = {};
      (v.tracks || []).forEach(function (t) { live[t.sid + "|" + t.track] = true; });
      Object.keys(seen).forEach(function (k) { if (!live[k]) drop(k); });
      pull(v.tracks || []);
      // a listener who came in on their own goes out the same way, a minute after the talking stops
      if (auto && state === "in") {
        if (talking) quietSince = null;
        else if (quietSince === null) quietSince = Date.now();
        else if (Date.now() - quietSince > (parseInt(el.getAttribute("data-quiet"), 10) || 60000)) { leave(true); return; }
      }
    } else if (v.open && talking && !optedOut) {
      join(true);   // someone is talking: listen, nothing to find or tap
      return;
    }
    draw();
  };
  draw();
})();
