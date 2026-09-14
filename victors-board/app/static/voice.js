// Voice memos, for whoever is allowed to post them.
//
// The browser records, and then we encode to MP3 right here before anything
// is uploaded. That is the whole reason this file exists: an iPhone records
// MP4/AAC and an Android records WebM/Opus, and an iPhone will not play back
// WebM/Opus. Left alone, half the board would post memos the other half
// hears as silence. Encoding on the way out settles it once.
//
// 32kbps mono is telephone quality, which is what a voice memo is. A minute
// weighs about 230KB.
(function () {
  var mount = document.getElementById("voice-memo");
  if (!mount) return;
  var input = document.querySelector('input[name="image_file"]');
  if (!input || !navigator.mediaDevices || !window.MediaRecorder) {
    mount.innerHTML = '<p class="hint">This browser can\'t record audio.</p>';
    return;
  }

  var MAX_SECONDS = parseInt(mount.getAttribute("data-max") || "120", 10);
  var RATE = 22050, KBPS = 32;
  var lameUrl = mount.getAttribute("data-lame");

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "rec-btn";
  btn.textContent = "🎤 Record a memo";
  var time = document.createElement("span");
  time.className = "rec-time";
  var note = document.createElement("span");
  note.className = "hint";
  var row = document.createElement("p");
  row.className = "rec-row";
  row.appendChild(btn);
  row.appendChild(time);
  row.appendChild(note);
  mount.appendChild(row);

  var stream = null, rec = null, chunks = [], started = 0, ticker = null;
  var lameReady = false, preview = null;

  function say(msg) { note.textContent = msg || ""; }
  function clock(secs) {
    var m = Math.floor(secs / 60), s = Math.floor(secs % 60);
    time.textContent = m + ":" + (s < 10 ? "0" : "") + s;
  }

  // the encoder is 150KB — nobody downloads it for reading a thread
  function loadLame() {
    if (lameReady) return Promise.resolve();
    return new Promise(function (ok, no) {
      var el = document.createElement("script");
      el.src = lameUrl;
      el.onload = function () { lameReady = true; ok(); };
      el.onerror = function () { no(new Error("encoder failed to load")); };
      document.head.appendChild(el);
    });
  }

  function stop() {
    if (rec && rec.state !== "inactive") rec.stop();
    if (ticker) { clearInterval(ticker); ticker = null; }
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    btn.classList.remove("recording");
    btn.textContent = "🎤 Record a memo";
  }

  btn.addEventListener("click", function () {
    if (rec && rec.state === "recording") { stop(); return; }
    say("");
    loadLame().then(function () {
      return navigator.mediaDevices.getUserMedia({ audio: true });
    }).then(function (s) {
      stream = s;
      chunks = [];
      rec = new MediaRecorder(s);
      rec.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
      rec.onstop = function () { encode(new Blob(chunks)); };
      rec.start();
      started = Date.now();
      btn.classList.add("recording");
      btn.textContent = "⏹ Stop";
      clock(0);
      ticker = setInterval(function () {
        var secs = (Date.now() - started) / 1000;
        clock(secs);
        if (secs >= MAX_SECONDS) { say("Two minutes is the limit."); stop(); }
      }, 200);
    }).catch(function (err) {
      stop();
      say(String(err && err.name) === "NotAllowedError"
        ? "The microphone is blocked for this site — allow it and try again."
        : "Couldn't start recording: " + (err && err.message ? err.message : err));
    });
  });

  // raw recording -> mono 22.05k -> MP3, all in the page
  function encode(blob) {
    time.textContent = "";
    say("Encoding…");
    var reader = new FileReader();
    reader.onload = function () {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      var ctx = new Ctx();
      ctx.decodeAudioData(reader.result, function (buf) {
        var mono = downmix(buf);
        var pcm = resample(mono, buf.sampleRate, RATE);
        var mp3 = toMp3(pcm);
        ctx.close();
        attach(mp3, pcm.length / RATE);
      }, function () {
        ctx.close();
        say("That recording couldn't be read back.");
      });
    };
    reader.readAsArrayBuffer(blob);
  }

  function downmix(buf) {
    var n = buf.length, out = new Float32Array(n);
    for (var c = 0; c < buf.numberOfChannels; c++) {
      var d = buf.getChannelData(c);
      for (var i = 0; i < n; i++) out[i] += d[i] / buf.numberOfChannels;
    }
    return out;
  }

  function resample(data, from, to) {
    if (from === to) return data;
    var ratio = from / to, n = Math.floor(data.length / ratio);
    var out = new Float32Array(n);
    for (var i = 0; i < n; i++) {
      var x = i * ratio, j = Math.floor(x), f = x - j;
      out[i] = data[j] * (1 - f) + (data[j + 1] || data[j]) * f;
    }
    return out;
  }

  function toMp3(pcm) {
    var enc = new lamejs.Mp3Encoder(1, RATE, KBPS);
    var samples = new Int16Array(pcm.length);
    for (var i = 0; i < pcm.length; i++) {
      var v = Math.max(-1, Math.min(1, pcm[i]));
      samples[i] = v < 0 ? v * 0x8000 : v * 0x7FFF;
    }
    var parts = [], BLOCK = 1152;
    for (var k = 0; k < samples.length; k += BLOCK) {
      var buf = enc.encodeBuffer(samples.subarray(k, k + BLOCK));
      if (buf.length) parts.push(new Int8Array(buf));
    }
    var last = enc.flush();
    if (last.length) parts.push(new Int8Array(last));
    return new Blob(parts, { type: "audio/mpeg" });
  }

  // hand it to the form's own file input, so it rides along on submit
  // exactly like a photo does
  function attach(blob, secs) {
    var name = "memo-" + Date.now() + ".mp3";
    var file = new File([blob], name, { type: "audio/mpeg" });
    var ok = false;
    try {
      var dt = new DataTransfer();
      for (var i = 0; i < input.files.length; i++) {
        if (!/\.mp3$/i.test(input.files[i].name)) dt.items.add(input.files[i]);
      }
      dt.items.add(file);
      input.files = dt.files;
      ok = input.files.length === dt.items.length;
    } catch (e) { ok = false; }
    if (!ok) {
      // iOS won't let a page fill a file input; the form's own paste
      // handler knows how to carry extras, so mirror that here
      window.__voiceFile = file;
      var form = input.form;
      if (form && !form.__voiceHooked) {
        form.__voiceHooked = true;
        form.addEventListener("submit", function (e) {
          if (!window.__voiceFile) return;
          e.preventDefault();
          var fd = new FormData(form);
          fd.append("image_file", window.__voiceFile, window.__voiceFile.name);
          fetch(form.action || location.href, { method: "POST", body: fd })
            .then(function (r) { location.href = r.url || "/"; })
            .catch(function () { say("Upload failed — try again."); });
        });
      }
    }
    if (preview) preview.remove();
    preview = document.createElement("audio");
    preview.controls = true;
    preview.src = URL.createObjectURL(blob);
    row.appendChild(preview);
    var kb = Math.round(blob.size / 1024);
    say("✓ " + Math.round(secs) + "s, " + kb + "KB — posts with your message.");
    var drop = document.createElement("button");
    drop.type = "button";
    drop.className = "rec-drop";
    drop.textContent = "Discard";
    drop.addEventListener("click", function () {
      window.__voiceFile = null;
      try {
        var dt2 = new DataTransfer();
        for (var j = 0; j < input.files.length; j++) {
          if (!/\.mp3$/i.test(input.files[j].name)) dt2.items.add(input.files[j]);
        }
        input.files = dt2.files;
      } catch (e) {}
      if (preview) { preview.remove(); preview = null; }
      drop.remove();
      say("Memo discarded.");
    });
    row.appendChild(drop);
  }
})();
