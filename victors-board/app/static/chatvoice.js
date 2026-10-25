// Live voice on top of the chat room, opt-in both ways.
//
// Tap "voice" and you hear whoever is talking (browsers won't play sound
// without a tap, so listening is the first tap). Tap "talk" and your mic is
// live; "mute" keeps you in the room but silent; "leave" drops you out.
// Audio goes through Cloudflare's relay; this page only ever talks to the
// board, which brokers the relay sessions. Nothing is recorded anywhere.
//
// One relay session, one PeerConnection. Every negotiation runs through a
// single queue because the relay insists on one exchange at a time.
(function () {
  var el = document.getElementById("voice");
  if (!el || !window.RTCPeerConnection) return;
  var ICE = el.getAttribute("data-ice");
  var pc = null, mic = null, micTrack = null;
  var state = "off";          // off | in | talking | muted
  var joining = false;        // between the tap and the board's answer
  var seen = {};              // "sid|track" -> true, tracks we've pulled
  var byMid = {};             // relay mid -> "sid|track"
  var audio = {};             // "sid|track" -> <audio>
  var lastEpoch = null, lastVoice = null;
  var chain = Promise.resolve();
  var sounds = document.createElement("div");
  sounds.id = "voice-sounds";
  document.body.appendChild(sounds);

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
  function draw(note) {
    el.textContent = "";
    var count = lastVoice ? lastVoice.count : 0;
    if (state === "off") {
      el.appendChild(link("voice-join", count ? "voice (" + count + ")" : "voice", join));
    } else {
      el.appendChild(document.createTextNode(
        state === "talking" ? "🎙 " : state === "muted" ? "🔇 " : "🔊 "));
      if (state === "in") el.appendChild(link("voice-talk", "talk", talk));
      if (state === "talking") el.appendChild(link("voice-mute", "mute", mute));
      if (state === "muted") el.appendChild(link("voice-talk", "unmute", unmute));
      el.appendChild(document.createTextNode(" · "));
      el.appendChild(link("voice-leave", "leave", leave));
    }
    var who = lastVoice ? lastVoice.talking : [];
    if (who.length) {
      var w = document.createElement("span");
      w.id = "voice-who";
      w.textContent = " 🎙 " + who.join(", ");
      el.appendChild(w);
    }
    if (note) {
      var n = document.createElement("span");
      n.className = "hint"; n.textContent = " " + note;
      el.appendChild(n);
      setTimeout(function () { if (n.parentNode) n.parentNode.removeChild(n); }, 4000);
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
      var p = a.play(); if (p && p.catch) p.catch(function () {});
    };
    return pc;
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
  function join() {
    if (state !== "off") return;
    state = "in"; joining = true; draw();
    connection();
    queue(function () {
      return post("/chat/voice/join").then(function (d) {
        joining = false;
        if (!d.ok) { hangup(); draw(d.error || "voice is not available"); return; }
        if (lastVoice) pull(lastVoice.tracks || []);
      }, function () { joining = false; hangup(); draw("voice is not available"); });
    });
  }
  function talk() {
    if (state !== "in") return;
    var md = navigator.mediaDevices;
    if (!md || !md.getUserMedia) { draw("no mic"); return; }
    md.getUserMedia({ audio: true }).then(function (stream) {
      mic = stream; micTrack = stream.getAudioTracks()[0];
      var c = connection();
      var tx = c.addTransceiver(micTrack, { direction: "sendonly" });
      return queue(function () {
        return c.createOffer()
          .then(function (o) { return c.setLocalDescription(o); })
          .then(function () { return post("/chat/voice/publish", { sdp: c.localDescription.sdp, mid: tx.mid }); })
          .then(function (d) {
            if (!d.ok) { throw new Error(d.error || "no answer"); }
            return c.setRemoteDescription({ type: "answer", sdp: d.sdp });
          })
          .then(function () { state = "talking"; draw(); });
      });
    }).catch(function () {
      if (mic) { mic.getTracks().forEach(function (t) { t.stop(); }); mic = null; micTrack = null; }
      draw("mic blocked");
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
    state = "off";
  }
  function leave() {
    if (state === "off") return;
    hangup(); draw();
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
    if (state !== "off") {
      var live = {};
      (v.tracks || []).forEach(function (t) { live[t.sid + "|" + t.track] = true; });
      Object.keys(seen).forEach(function (k) { if (!live[k]) drop(k); });
      pull(v.tracks || []);
    }
    draw();
  };
  draw();
})();
