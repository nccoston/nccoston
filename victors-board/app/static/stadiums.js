// Stadium Guesser. A photo, a map of the lower 48, and a pin.
//
// The map is drawn from state outlines projected at build time with an
// Albers conic; the same projection constants ride along in the file so
// this can run it backwards and turn a click into a latitude and longitude.
// Nothing is fetched from anywhere but this board.
(function () {
  var root = document.getElementById("sg");
  if (!root) return;
  var RAD = Math.PI / 180;
  var MAP = null, P = null;
  var token = null, pending = null, guess = null, answer = null;
  var els = {};

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function status(msg) { root.innerHTML = ""; root.appendChild(el("p", "sg-status", msg)); }

  // ---- projection: lat/lon <-> the map's own coordinate space ----
  function project(lat, lon) {
    var rho = Math.sqrt(P.C - 2 * P.n * Math.sin(lat * RAD)) / P.n;
    var th = P.n * (lon - P.l0) * RAD;
    return { x: rho * Math.sin(th) * P.scale + P.ox,
             y: (rho * Math.cos(th) - P.r0) * P.scale + P.oy };
  }
  function unproject(x, y) {
    var px = (x - P.ox) / P.scale, py = (y - P.oy) / P.scale;
    var ry = py + P.r0;
    var rho = Math.sqrt(px * px + ry * ry);
    var s = (P.C - rho * rho * P.n * P.n) / (2 * P.n);
    s = Math.max(-1, Math.min(1, s));
    return { lat: Math.asin(s) / RAD, lon: P.l0 + Math.atan2(px, ry) / P.n / RAD };
  }
  function miles(a, b) {
    var h = Math.pow(Math.sin((b.lat - a.lat) * RAD / 2), 2)
          + Math.cos(a.lat * RAD) * Math.cos(b.lat * RAD)
          * Math.pow(Math.sin((b.lon - a.lon) * RAD / 2), 2);
    return 7917.5 * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  // ---- the page ----
  function build() {
    root.innerHTML = "";

    var head = el("div", "sg-head");
    els.round = el("span", "sg-round", "");
    els.total = el("span", "sg-total", "");
    head.appendChild(els.round); head.appendChild(els.total);
    root.appendChild(head);

    els.shot = el("div", "sg-shot");
    els.img = document.createElement("img");
    els.img.alt = "Somewhere in college football";
    els.shot.appendChild(els.img);
    els.credit = el("p", "sg-credit", "");
    els.shot.appendChild(els.credit);
    root.appendChild(els.shot);

    var wrap = el("div", "sg-map");
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + MAP.w + " " + MAP.h);
    svg.setAttribute("class", "sg-svg");
    MAP.states.forEach(function (s) {
      var p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", s.d);
      p.setAttribute("class", "sg-state");
      svg.appendChild(p);
    });
    els.marks = document.createElementNS("http://www.w3.org/2000/svg", "g");
    svg.appendChild(els.marks);
    svg.addEventListener("click", onMap);
    wrap.appendChild(svg);
    els.svg = svg;
    root.appendChild(wrap);

    els.result = el("p", "sg-result", "");
    root.appendChild(els.result);

    els.btn = el("button", "sg-btn", "Guess");
    els.btn.type = "button";
    els.btn.disabled = true;
    els.btn.addEventListener("click", onButton);
    var bar = el("p", "sg-bar");
    bar.appendChild(els.btn);
    root.appendChild(bar);
  }

  function svgPoint(evt) {
    var r = els.svg.getBoundingClientRect();
    return { x: (evt.clientX - r.left) * MAP.w / r.width,
             y: (evt.clientY - r.top) * MAP.h / r.height };
  }

  function onMap(evt) {
    if (answer) return;               // the round is over; look, don't touch
    var pt = svgPoint(evt);
    guess = unproject(pt.x, pt.y);
    drawMarks();
    els.btn.disabled = false;
  }

  function mark(pt, cls, label) {
    var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", pt.x); c.setAttribute("cy", pt.y);
    c.setAttribute("r", 7); c.setAttribute("class", cls);
    g.appendChild(c);
    if (label) {
      var t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("x", pt.x + 11); t.setAttribute("y", pt.y + 6);
      t.setAttribute("class", "sg-label");
      t.textContent = label;
      g.appendChild(t);
    }
    els.marks.appendChild(g);
  }

  function drawMarks() {
    els.marks.innerHTML = "";
    var gp = guess ? project(guess.lat, guess.lon) : null;
    if (answer) {
      var ap = project(answer.lat, answer.lon);
      if (gp) {
        var line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", gp.x); line.setAttribute("y1", gp.y);
        line.setAttribute("x2", ap.x); line.setAttribute("y2", ap.y);
        line.setAttribute("class", "sg-line");
        els.marks.appendChild(line);
      }
      mark(ap, "sg-answer", answer.stadium);
    }
    if (gp) mark(gp, "sg-guess", answer ? "you" : null);
  }

  // ---- rounds ----
  function showPhoto(p) {
    els.img.src = p.url;
    var bits = [];
    if (p.credit) bits.push(p.credit);
    if (p.license) bits.push(p.license);
    els.credit.textContent = bits.length ? "Photo: " + bits.join(" · ") : "";
    if (p.source) {
      els.credit.appendChild(document.createTextNode(" "));
      var a = document.createElement("a");
      a.href = p.source; a.target = "_blank"; a.rel = "noopener";
      a.textContent = "source";
      els.credit.appendChild(a);
    }
  }

  function setHead(round, of, total) {
    els.round.textContent = "Round " + round + " of " + of;
    els.total.textContent = total ? total.toLocaleString() + " pts" : "";
  }

  function post(url, body) {
    return fetch(url, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}) }).then(function (r) {
        return r.json().then(function (j) {
          if (!r.ok) throw new Error(j.error || "http " + r.status);
          return j;
        });
      });
  }

  var running = 0;
  function onButton() {
    if (running) return;
    if (answer) { nextRound(); return; }
    if (!guess) return;
    running = 1;
    els.btn.disabled = true;
    els.btn.textContent = "Scoring…";
    post("/games/stadiums/guess", { token: token, lat: guess.lat, lon: guess.lon })
      .then(function (j) {
        running = 0;
        answer = j.answer;
        pending = j.next || null;
        drawMarks();
        var m = j.miles < 10 ? j.miles.toFixed(1) : Math.round(j.miles).toLocaleString();
        els.result.innerHTML = "";
        els.result.appendChild(el("b", "", answer.stadium));
        els.result.appendChild(document.createTextNode(
          " — " + answer.team + ", " + answer.city + ", " + answer.state));
        els.result.appendChild(document.createElement("br"));
        els.result.appendChild(document.createTextNode(
          "You were " + m + " mile" + (j.miles === 1 ? "" : "s") + " off. "));
        els.result.appendChild(el("b", "", j.points.toLocaleString() + " points"));
        setHead(j.round, j.of, j.total);
        if (j.done) {
          finish(j);
        } else {
          els.btn.disabled = false;
          els.btn.textContent = "Next stadium";
        }
      }).catch(function (e) {
        running = 0;
        if (String(e.message) === "expired") {
          els.result.textContent = "That game timed out — start another one.";
          els.btn.textContent = "New game";
          els.btn.disabled = false;
          answer = null; token = null;
          els.btn.onclick = null;
          els.btn.addEventListener("click", start, { once: true });
        } else {
          els.result.textContent = "Something went wrong scoring that: " + e.message;
          els.btn.disabled = false;
          els.btn.textContent = "Guess";
        }
      });
  }

  function nextRound() {
    answer = null; guess = null;
    els.result.textContent = "";
    els.btn.textContent = "Guess";
    els.btn.disabled = true;
    drawMarks();
    if (pending) showPhoto(pending);
    pending = null;
  }

  function finish(j) {
    els.shot.classList.add("sg-over");
    var box = el("div", "sg-final");
    box.appendChild(el("h3", "", j.total.toLocaleString() + " out of "
                       + (j.of * 5000).toLocaleString()));
    var best = el("p", "hint", j.total >= j.best
      ? "That's your best yet." : "Your best is " + j.best.toLocaleString() + ".");
    box.appendChild(best);
    var again = el("button", "sg-btn", "Play again");
    again.type = "button";
    again.addEventListener("click", function () { start(); });
    box.appendChild(again);
    var lb = document.createElement("a");
    lb.href = "/games/stadiums/leaderboard";
    lb.className = "sg-link";
    lb.textContent = "Leaderboard";
    box.appendChild(lb);
    els.result.appendChild(box);
    els.btn.style.display = "none";
  }

  function start() {
    status("Dealing five stadiums…");
    post("/games/stadiums/start").then(function (j) {
      token = j.token;
      guess = null; answer = null; pending = null;
      build();
      setHead(j.round, j.of, 0);
      showPhoto(j.photo);
    }).catch(function (e) {
      status("Could not start a game: " + e.message);
    });
  }

  fetch(root.getAttribute("data-map")).then(function (r) { return r.json(); })
    .then(function (m) { MAP = m; P = m.proj; start(); })
    .catch(function () { status("The map didn't load. Try a refresh."); });
})();
