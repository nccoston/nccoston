// Victard Bowl — a pixel football game for The Victors board.
// Original art and code. You run Michigan's offense; the defense and the
// other team's drives play themselves. Flick to throw, drag to steer.
(function () {
  "use strict";

  // ------------------------------------------------------------ constants
  var W = 320, H = 180;                 // logical pixels (scaled by CSS)
  var PX = 4;                           // pixels per yard along the field
  var FIELD_TOP = 22, FIELD_BOT = 166;  // sideline to sideline, in px
  var MAIZE = "#FFCB05", BLUE = "#00274C";
  var GRASS_A = "#3f8f3a", GRASS_B = "#3a8535", LINE = "#dfeedb";
  var QUARTER_SECS = 300;               // game clock per quarter
  var CATCH_R = 16, TACKLE_R = 5, ASSIST_R = 26;

  var canvas = document.getElementById("bowl");
  var ctx = canvas.getContext("2d");
  var RES = 2;                          // backing pixels per logical pixel
  canvas.width = W * RES; canvas.height = H * RES;
  ctx.scale(RES, RES);
  ctx.imageSmoothingEnabled = false;

  var CFG = window.BOWL || {};
  var schedule = CFG.schedule || [];
  if (!schedule.length) schedule = [{ name: "Opponent", abbr: "OPP", home: true }];

  // ------------------------------------------------------------- season
  // One row per week, kept on this device. The season runs the real
  // schedule start to finish, then hands back a recap.
  function loadSeason() {
    var sn = null;
    try { sn = JSON.parse(load("bowlSeason") || "null"); } catch (e) {}
    if (!sn || typeof sn.week !== "number" || !(sn.results instanceof Array)) {
      sn = { year: 1, week: 0, results: [] };
      var old = parseInt(load("bowlWeek") || "0", 10);   // carry an older save forward
      if (old > 0 && old < schedule.length) sn.week = old;
    }
    sn.week = clamp(sn.week, 0, schedule.length);
    return sn;
  }
  function saveSeason() { store("bowlSeason", JSON.stringify(season)); }
  function seasonRecord() {
    var w = 0, l = 0, t = 0;
    season.results.forEach(function (r) {
      if (!r) return;
      if (r.us > r.them) w++; else if (r.us < r.them) l++; else t++;
    });
    return { w: w, l: l, t: t, text: w + "-" + l + (t ? "-" + t : "") };
  }
  // the last game on the schedule is the one that matters; so is Ohio State
  function isRivalry(i) {
    var g = schedule[i];
    return i === schedule.length - 1 || (g && teamKey(g.name, g.abbr) === "ohio state");
  }

  var season = loadSeason();
  var seasonOver = season.week >= schedule.length;
  var week = clamp(season.week, 0, schedule.length - 1);

  // opponent strength, by reputation (0.2 cupcake .. 0.9 nightmare)
  var RATINGS = {
    "ohio state": 0.9, "oregon": 0.85, "penn state": 0.8, "oklahoma": 0.8,
    "usc": 0.75, "texas": 0.8, "alabama": 0.85, "georgia": 0.85,
    "washington": 0.65, "wisconsin": 0.55, "nebraska": 0.55, "iowa": 0.55,
    "michigan state": 0.5, "illinois": 0.5, "minnesota": 0.45, "maryland": 0.45,
    "indiana": 0.5, "rutgers": 0.4, "northwestern": 0.35, "purdue": 0.3,
    "ucla": 0.5, "western michigan": 0.25, "central michigan": 0.2,
    "eastern michigan": 0.2, "new mexico": 0.2, "toledo": 0.3
  };
  // ESPN's feed says "W Michigan", "Michigan St", "Ohio St": match on the
  // abbreviation first, then on any long-name substring
  var ABBR_KEY = {
    WMU: "western michigan", CMU: "central michigan", EMU: "eastern michigan",
    MSU: "michigan state", OSU: "ohio state", PSU: "penn state", NEB: "nebraska",
    WIS: "wisconsin", USC: "usc", WASH: "washington", MD: "maryland", PUR: "purdue",
    NW: "northwestern", NU: "northwestern", ORE: "oregon", MINN: "minnesota",
    IOWA: "iowa", ILL: "illinois", IND: "indiana", RUTG: "rutgers", UCLA: "ucla",
    TEX: "texas", ALA: "alabama", UGA: "georgia", UNM: "new mexico", TOL: "toledo",
    ND: "notre dame", OU: "oklahoma", OKLA: "oklahoma", FLA: "florida"
  };
  function teamKey(name, abbr) {
    var a = (abbr || "").toUpperCase();
    if (ABBR_KEY[a]) return ABBR_KEY[a];
    var n = (name || "").toLowerCase();
    for (var k in RATINGS) if (n.indexOf(k) !== -1) return k;
    for (var k2 in TEAM_COLORS) if (n.indexOf(k2) !== -1) return k2;
    return n;
  }
  function ratingFor(name, abbr) {
    var k = teamKey(name, abbr);
    return RATINGS[k] !== undefined ? RATINGS[k] : 0.5;
  }
  // opponent color: the school's real color where we know it, otherwise a
  // stable pick from a palette with no blues — nobody gets to look like us
  var TEAM_COLORS = {
    "ohio state": "#bb0000", "michigan state": "#18453b", "western michigan": "#6c4023",
    "central michigan": "#6a0032", "eastern michigan": "#046a38", "oklahoma": "#841617",
    "usc": "#990000", "washington": "#4b2e83", "wisconsin": "#c5050c", "nebraska": "#d00000",
    "penn state": "#1e407c", "maryland": "#e03a3e", "purdue": "#cfb991", "northwestern": "#4e2a84",
    "oregon": "#154733", "minnesota": "#7a0019", "iowa": "#000000", "illinois": "#e84a27",
    "indiana": "#990000", "rutgers": "#cc0033", "ucla": "#2d68c4", "texas": "#bf5700",
    "alabama": "#9e1b32", "georgia": "#ba0c2f", "new mexico": "#ba0c2f", "toledo": "#ffb20f",
    "notre dame": "#0c2340", "florida": "#fa4616", "arkansas state": "#cc092f"
  };
  function colorFor(name, abbr) {
    var k = teamKey(name, abbr);
    if (TEAM_COLORS[k]) return TEAM_COLORS[k];
    var h = 0;
    for (var i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff;
    var palette = ["#b3272d", "#8c1d40", "#cc0000", "#2d5f2e", "#4a1a70", "#c8102e",
                   "#e07000", "#5b2c6f", "#7a0019", "#154733"];
    return palette[h % palette.length];
  }

  // ------------------------------------------------------------ helpers
  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function dist(a, b) { var dx = a.x - b.x, dy = a.y - b.y; return Math.sqrt(dx * dx + dy * dy); }
  function yardToPx(yd) { return (yd + 10) * PX; }
  function pxToYard(px) { return px / PX - 10; }
  function fmtClock(s) {
    s = Math.max(0, Math.ceil(s));
    var m = Math.floor(s / 60), r = s % 60;
    return m + ":" + (r < 10 ? "0" : "") + r;
  }
  function ordinal(n) { return n + (["th", "st", "nd", "rd"][n] || "th"); }

  // ------------------------------------------------------------ game state
  var opp = schedule[week];
  var oppRating = ratingFor(opp.name, opp.abbr);
  var oppColor = colorFor(opp.name, opp.abbr);
  var G = {
    mode: "presnap",       // presnap | play | dead | oppdrive | gameover
    score: [0, 0],         // [Michigan, opponent]
    quarter: 1, clock: QUARTER_SECS,
    spot: 25, down: 1, toGo: 10,   // spot = yards from own goal (0..100)
    play: null,            // "pass" | "run"
    banner: null, bannerT: 0,
    card: null, cardT: 0,  // opponent-drive card
    poss: 0,               // 0 = we have it, 1 = they do
    call: null,            // our defensive call, when we're on defense
    qbClock: 99,           // when the AI quarterback lets it go
    stats: { yards: 0, tds: 0, longest: 0, ints: 0, sacks: 0, comp: 0, att: 0 },
    result: null
  };

  // Who has the ball, and whether the player takes the field when they
  // don't. You play defense unless this device has asked for "sim", which
  // resolves their drive as a card instead.
  var defenseMode = (load("bowlDefense") === "sim") ? "sim" : "play";
  function weHaveBall() { return G.poss === 0; }
  function offUniform() { return G.poss === 0 ? "M" : "O"; }
  function defUniform() { return G.poss === 0 ? "O" : "M"; }

  var DEFENSE_CALLS = [
    { name: "COVER",  blitz: 0, spy: false },
    { name: "BLITZ",  blitz: 2, spy: false },
    { name: "SPY QB", blitz: 0, spy: true }
  ];

  var players = [], ball = null, carrier = null, qb = null, camX = 0;
  var myDef = null;          // the defender you steer, when you're on defense
  var lastCarrier = null, reactT = 0, carrierAt = 0;
  var aim = null;            // {x0,y0,x,y} while aiming a pass
  var steer = null;          // {x0,y0,x,y} while steering a runner
  var playT = 0;

  // ------------------------------------------------------------ playbook
  // Each play: a formation (receiver spots, as fractions of field width,
  // with a small x offset), a route per receiver, and what the back does.
  // Runs carry an opening direction the back takes before you steer.
  var FORMATIONS = {
    spread: [[0.12, -2], [0.88, -2], [0.30, -8]],
    trips:  [[0.10, -2], [0.22, -8], [0.34, -2]],
    twins:  [[0.12, -2], [0.24, -8], [0.88, -2]],
    iform:  [[0.14, -2], [0.86, -2], [0.36, -3]]
  };
  var PLAYBOOK = [
    { name: "VERTICALS", type: "pass", f: "spread", routes: ["go", "go", "post"], rb: "flat" },
    { name: "SLANTS",    type: "pass", f: "spread", routes: ["slant", "slant", "out"], rb: "flat" },
    { name: "FLOOD",     type: "pass", f: "trips",  routes: ["corner", "out", "drag"], rb: "flat" },
    { name: "MESH",      type: "pass", f: "spread", routes: ["drag", "drag", "go"], rb: "wheel" },
    { name: "CURL FLAT", type: "pass", f: "twins",  routes: ["curl", "out", "curl"], rb: "flat" },
    { name: "SCREEN",    type: "pass", f: "iform",  routes: ["go", "go", "go"], rb: "screen" },
    { name: "DIVE",      type: "run",  f: "iform",  routes: ["go", "go", "block"], rb: null, dir: [1, 0] },
    { name: "SWEEP R",   type: "run",  f: "twins",  routes: ["go", "block", "go"], rb: null, dir: [0.6, 0.8] },
    { name: "SWEEP L",   type: "run",  f: "trips",  routes: ["block", "go", "go"], rb: null, dir: [0.6, -0.8] },
    { name: "COUNTER",   type: "run",  f: "spread", routes: ["go", "go", "block"], rb: null, dir: [0.3, -0.9], cut: [0.8, 0.6] }
  ];
  var offered = [], chosen = 0;
  function isRun() { return G.play && G.play.type === "run"; }
  function isPass() { return G.play && G.play.type === "pass"; }

  function enterPresnap() {
    G.mode = "presnap";
    G.call = null;
    if (!weHaveBall()) {
      if (G.down === 4 && aiFourthDown()) return;
      // they call it; we answer with a front
      var pool = PLAYBOOK.filter(function (x) {
        return G.toGo >= 7 ? true : (x.type === "run" || Math.random() < 0.5);
      });
      G.play = pool[Math.floor(Math.random() * pool.length)] || PLAYBOOK[0];
      offered = DEFENSE_CALLS.slice();
      chosen = 0; G.call = offered[0];
      buildFormation();
      return;
    }
    // four fresh plays each down: mostly passes, at least one run
    var passes = PLAYBOOK.filter(function (x) { return x.type === "pass"; }).sort(function () { return Math.random() - 0.5; });
    var runs = PLAYBOOK.filter(function (x) { return x.type === "run"; }).sort(function () { return Math.random() - 0.5; });
    var nPass = G.down === 4 ? 1 : 2 + (Math.random() < 0.5 ? 1 : 0);
    var nRun = (G.down === 4 ? 2 : 4) - nPass;
    offered = passes.slice(0, nPass).concat(runs.slice(0, nRun)).sort(function () { return Math.random() - 0.5; });
    chosen = 0; G.play = offered[0];
    buildFormation();
  }

  // ------------------------------------------------------------ setup a play
  function fieldY(frac) { return FIELD_TOP + (FIELD_BOT - FIELD_TOP) * frac; }

  function buildFormation() {
    players = []; ball = null; carrier = null; aim = null; steer = null; playT = 0;
    lastCarrier = null; reactT = 0; carrierAt = 0;
    var los = yardToPx(G.spot);
    var play = G.play;
    function P(side, role, x, y, spd) {
      var team = side === "off" ? offUniform() : defUniform();
      var p = { team: team, side: side, role: role, x: x, y: y, vx: 0, vy: 0, spd: spd,
                anim: Math.random() * 10, engaged: 0, stun: 0, route: null, t: 0,
                mark: null, zone: null, home: null, block: null, blockT: 0, held: 0, holdMax: 0 };
      players.push(p); return p;
    }
    // offense (Michigan, drives left -> right)
    qb = P("off", "QB", los - 20, fieldY(0.5), 46);
    var rbY = play.f === "iform" ? 0.5 : (play.dir && play.dir[1] > 0 ? 0.42 : 0.58);
    var rb = P("off", "RB", los - (play.f === "iform" ? 34 : 28), fieldY(rbY), 60);
    var wrs = FORMATIONS[play.f].map(function (spot) { return P("off", "WR", los + spot[1], fieldY(spot[0]), 60); });
    var ols = [];
    for (var i = 0; i < 5; i++) {
      ols.push(P("off", "OL", los - 4 - (i === 2 ? 1 : 0) - (i % 2) * 1.5,
                 fieldY(0.315 + i * 0.0925), 44));
    }
    wrs.forEach(function (w, k) { w.route = play.routes[k]; w.home = { x: w.x, y: w.y }; });
    rb.route = play.rb; rb.home = { x: rb.x, y: rb.y };
    // defense
    var dls = [];
    for (var j = 0; j < 4; j++) dls.push(P("def", "DL", los + 5 + (j % 2) * 1.5, fieldY(0.355 + j * 0.1), 38));
    var lbs = [P("def", "LB", los + 28, fieldY(0.38), 46), P("def", "LB", los + 28, fieldY(0.62), 46)];
    // blocking assignments: four linemen on the four down linemen; the
    // fifth pulls to a linebacker on runs (the lane) or doubles on passes
    for (var b = 0; b < 4; b++) { ols[b].block = dls[b]; }
    ols[4].block = play.type === "run"
      ? (play.dir && play.dir[1] < 0 ? lbs[0] : lbs[1])
      : dls[1];
    ols.forEach(function (o) {
      o.holdMax = rnd(1.8, 3.4) * (1.2 - oppRating * 0.5);   // how long the block holds
      o.held = 0;
    });
    lbs[0].zone = { x: los + 30, y: fieldY(0.35) }; lbs[1].zone = { x: los + 30, y: fieldY(0.65) };
    wrs.forEach(function (w, k) {
      var cb = P("def", "CB", los + 32, w.y + (w.y < H / 2 ? 3 : -3), 57 + oppRating * 6);
      cb.mark = w;
    });
    var s = P("def", "S", los + 64, fieldY(0.5), 62 + oppRating * 3); s.role = "S";
    ball = { x: qb.x, y: qb.y, z: 0, flying: false, tx: 0, ty: 0, t: 0, dur: 0, holder: qb };
    carrier = qb;
    // how long their quarterback holds it — better teams wait for a read
    G.qbClock = rnd(1.3, 2.4) + oppRating * 0.5;
    myDef = weHaveBall() ? null
          : lbs.reduce(function (a, b) {          // you start on a linebacker
              return Math.abs(a.y - H / 2) < Math.abs(b.y - H / 2) ? a : b; });
  }
  function snapBall() {
    if (G.mode !== "presnap") return;
    G.mode = "play"; playT = 0;
    G.banner = G.play.name; G.bannerT = 0.7;
  }

  // route running: returns velocity for a receiver at time t
  function routeVel(p, t) {
    var s = p.spd;
    var side = (p.home ? p.home.y : p.y) < H / 2 ? -1 : 1;   // -1: top sideline is nearer
    switch (p.route) {
      case "go":     return { vx: s, vy: 0 };
      case "slant":  return t < 0.35 ? { vx: s, vy: 0 } : { vx: s * 0.7, vy: -side * s * 0.7 };
      case "out":    return t < 0.7 ? { vx: s, vy: 0 } : { vx: s * 0.35, vy: side * s * 0.9 };
      case "in":     return t < 0.8 ? { vx: s, vy: 0 } : { vx: s * 0.5, vy: -side * s * 0.85 };
      case "drag":   return t < 0.25 ? { vx: s * 0.8, vy: 0 } : { vx: s * 0.35, vy: -side * s * 0.9 };
      case "post":   return t < 1.0 ? { vx: s, vy: 0 } : { vx: s * 0.8, vy: -side * s * 0.5 };
      case "corner": return t < 1.0 ? { vx: s, vy: 0 } : { vx: s * 0.75, vy: side * s * 0.6 };
      case "curl":   return t < 1.1 ? { vx: s, vy: 0 } : t < 1.45 ? { vx: -s * 0.45, vy: 0 } : { vx: 0, vy: 0 };
      case "flat":   return t < 0.5 ? { vx: s * 0.3, vy: side * s * 0.6 } : { vx: s * 0.7, vy: 0 };
      case "wheel":  return t < 0.5 ? { vx: s * 0.3, vy: side * s * 0.7 } : { vx: s, vy: 0 };
      case "screen": return t < 0.6 ? { vx: -s * 0.4, vy: side * s * 0.5 } : { vx: 0, vy: 0 };
      case "block":  return t < 0.4 ? { vx: s * 0.5, vy: 0 } : { vx: 0, vy: 0 };
    }
    return { vx: 0, vy: 0 };
  }

  function projectReceiver(p, T) {
    var sim = { x: p.x, y: p.y, spd: p.spd, route: p.route, home: p.home };
    for (var t = playT; t < playT + T; t += 0.05) {
      var v = routeVel(sim, t); sim.x += v.vx * 0.05; sim.y += v.vy * 0.05;
    }
    return sim;
  }
  function receivers() {
    return players.filter(function (q) { return q.team === "M" && (q.role === "WR" || q.role === "RB") && q.route && q.route !== "block"; });
  }

  // ------------------------------------------------------------ simulation
  // pace: the whole game runs at 3/4 speed, and while you're pulling back
  // to throw it drops to 40% — bullet-time for reading the field
  var BASE_PACE = 0.6, AIM_PACE = 0.33;
  function update(dt) {
    if (G.bannerT > 0) { G.bannerT -= dt; if (G.bannerT <= 0) G.banner = null; }
    if (G.mode === "oppdrive") { G.cardT -= dt; if (G.cardT <= 0) endOppDrive(); return; }
    if (G.mode !== "play") return;
    dt *= (aim && carrier === qb) ? AIM_PACE : BASE_PACE;
    playT += dt;
    var los = yardToPx(G.spot);

    // --- offense ---
    players.forEach(function (p) {
      if (p.side !== "off") return;
      if (p.role === "QB") {
        if (carrier === p) {
          // drop back, then stand in the pocket
          if (playT < 0.5) { p.x -= 30 * dt; }
          if (!weHaveBall() && isPass() && !ball.flying && playT > G.qbClock) aiThrow();
          if (isRun() && playT > 0.3) {
            // handoff
            var rb = players.filter(function (q) { return q.role === "RB"; })[0];
            carrier = rb; ball.holder = rb;
          }
        }
      } else if (p.role === "RB") {
        if (carrier === p) moveCarrier(p, dt);
        else if (isRun()) { // come get the ball
          if (dist(p, qb) > 3) stepToward(p, qb, p.spd * 0.9, dt);
        } else if (ball.flying && ball.target === p) { stepToward(p, { x: ball.tx, y: ball.ty }, p.spd, dt); }
        else if (p.route) { var v = routeVel(p, playT); p.x += v.vx * dt; p.y += v.vy * dt; p.anim += dt * 8; }
      } else if (p.role === "WR") {
        if (carrier === p) moveCarrier(p, dt);
        else if (ball.flying && ball.target === p) { stepToward(p, { x: ball.tx, y: ball.ty }, p.spd, dt); }
        else { var v2 = routeVel(p, playT); p.x += v2.vx * dt; p.y += v2.vy * dt; p.anim += dt * 8; }
      } else if (p.role === "OL") {
        var t = p.block;
        if (t && p.held < p.holdMax) {
          if (dist(p, t) > 6) stepToward(p, t, p.spd, dt);
          else { t.blockT = 0.2; p.held += dt; p.x = t.x - 5; p.y += (t.y - p.y) * 0.5; }
        }
      }
      p.y = clamp(p.y, FIELD_TOP + 2, FIELD_BOT - 2);
    });

    // --- ball in flight ---
    if (ball.flying) {
      ball.t += dt;
      var f = clamp(ball.t / ball.dur, 0, 1);
      ball.x = ball.sx + (ball.tx - ball.sx) * f;
      ball.y = ball.sy + (ball.ty - ball.sy) * f;
      ball.z = Math.sin(f * Math.PI) * Math.min(28, ball.dur * 22);
      if (f >= 1) arrive();
    } else if (ball.holder) { ball.x = ball.holder.x; ball.y = ball.holder.y - 2; }

    // --- defense ---
    if (carrier !== lastCarrier) { lastCarrier = carrier; reactT = 0.5; carrierAt = playT; }  // "who has it?"
    if (ball.flying && !ball.reacted) { ball.reacted = true; reactT = 0.4; }  // "ball's up"
    if (reactT > 0) reactT -= dt;
    var chasers = [];
    if (carrier && carrier !== qb) {
      chasers = players.filter(function (q) { return q.side === "def" && !(q.blockT > 0); })
        .sort(function (a, b) { return dist(a, carrier) - dist(b, carrier); }).slice(0, 4);
    }
    players.forEach(function (d) {
      if (d.side !== "def") return;
      if (d.stun > 0) { d.stun -= dt; return; }
      if (d === myDef) {                      // this one is yours
        moveDefender(d, dt);
        d.y = clamp(d.y, FIELD_TOP + 2, FIELD_BOT - 2);
        if (carrier && !ball.flying && dist(d, carrier) < TACKLE_R && carrier !== qb) endPlay("tackle");
        else if (carrier === qb && !ball.flying && dist(d, carrier) < TACKLE_R) endPlay("sack");
        return;
      }
      if (d.blockT > 0) { d.blockT -= dt; d.anim += dt * 4; return; }   // held up by a lineman
      var target = null;
      var pace = 1;
      if (carrier && carrier !== qb) {
        if (reactT > 0) pace = 0.25;                       // still reading it
        else if (chasers.indexOf(d) === -1) pace = 0.55;   // not your play
        else pace = 1.15;                                  // pursuit angle: a step closes
      } else if (ball.flying && reactT > 0) pace = 0.3;    // watching the ball
      if (d.role === "DL") {
        target = carrier || qb;
      } else if (d.role === "CB") {
        // stay on your man (a step behind him, a step inside) until someone
        // has the ball — corners don't race the throw to the landing spot
        // ...but never INTO the backfield: at the snap the receiver is on
        // the line, and "behind him" would put the corner on the runner
        // corners play five yards off until their man passes them, and
        // keep covering through the reaction window before they commit
        // a corner stays on his man — who is running downfield, taking the
        // corner with him — until the runner is near him or clearly loose
        // on a pass, once it's caught the receiver IS the play — everyone goes
        var chasing = carrier && carrier !== qb && reactT <= 0 &&
                      (!isRun() || dist(d, carrier) < 30 || playT - carrierAt > 1.8);
        target = chasing ? carrier
               : { x: Math.max(d.mark.x - 8, los + 28), y: d.mark.y + (d.mark.y < H / 2 ? 3 : -3) };
      } else if (d.role === "LB") {
        var call = (!weHaveBall() && G.call) ? G.call : null;
        if (carrier && carrier !== qb) target = carrier;
        else if (ball.flying) target = { x: ball.tx, y: ball.ty };
        else if (call && call.spy) target = { x: qb.x + 16, y: qb.y };   // shadow him
        else if (call && call.blitz) target = qb;                        // come now
        else if (!call && playT > 2.2 + (1 - oppRating)) target = qb;    // blitz late
        else target = d.zone;
      } else if (d.role === "S") {
        if (carrier && carrier !== qb) target = carrier;
        else if (ball.flying) target = { x: ball.tx, y: ball.ty };
        else { // shade the deepest receiver
          var deep = null;
          players.forEach(function (q) { if (q.side === "off" && q.role === "WR" && (!deep || q.x > deep.x)) deep = q; });
          target = deep ? { x: deep.x + 24, y: (deep.y + H / 2) / 2 } : d;
        }
      }
      if (target) stepToward(d, target, d.spd * pace, dt);
      d.y = clamp(d.y, FIELD_TOP + 2, FIELD_BOT - 2);
      // tackles and sacks
      if (carrier && !ball.flying && dist(d, carrier) < TACKLE_R) {
        if (carrier === qb) { endPlay("sack"); }
        else if (Math.random() < 0.18 * (1 - oppRating * 0.4)) { d.stun = 0.7; } // broke it
        else {
          G.lastEnd = { by: d.role, dx: Math.round(d.x - yardToPx(G.spot)), dy: Math.round(d.y),
                        cx: Math.round(carrier.x - yardToPx(G.spot)), cy: Math.round(carrier.y),
                        who: carrier.role, t: Math.round(playT * 100) / 100, pace: pace };
          endPlay("tackle");
        }
      }
    });

    // pocket collapses eventually even if the line holds
    if (carrier === qb && isPass() && playT > 7) endPlay("sack");

    // scoring / boundaries for a live carrier
    if (carrier && !ball.flying && G.mode === "play") {
      if (carrier.x >= yardToPx(100)) endPlay("td");
      else if (carrier !== qb && (carrier.y <= FIELD_TOP + 2 || carrier.y >= FIELD_BOT - 2)) endPlay("oob");
    }
    camX = clamp((ball.x) - 130, 0, yardToPx(110) - W);
  }
  function presnapCamera() { if (G.mode === "presnap") camX = clamp(yardToPx(G.spot) - 130, 0, yardToPx(110) - W); }

  function stepToward(p, t, spd, dt) {
    var dx = t.x - p.x, dy = t.y - p.y, d = Math.sqrt(dx * dx + dy * dy);
    if (d < 0.5) return;
    p.x += dx / d * spd * dt; p.y += dy / d * spd * dt; p.anim += dt * 8;
  }
  // their quarterback picks the most open man and lets it go
  function aiThrow() {
    var best = null, bestSep = -1;
    receivers().forEach(function (r) {
      var T = Math.max(0.35, dist(qb, r) / 150);
      var pr = projectReceiver(r, T);
      var sep = 1e9;
      players.forEach(function (d) {
        if (d.side === "def") sep = Math.min(sep, dist(d, pr));
      });
      if (sep > bestSep) { bestSep = sep; best = { p: r, x: pr.x, y: pr.y }; }
    });
    if (best && bestSep > 9) throwBall(best.x, best.y, best.p);
    else G.qbClock = playT + 0.4;          // nobody open; hold it a beat
  }

  // an AI ball carrier runs at the widest gap in front of him
  function aiRunDir(p) {
    var ahead = [];
    players.forEach(function (q) {
      if (q.side === "def" && !(q.blockT > 0) && q.x > p.x - 4 && q.x < p.x + 70) ahead.push(q.y);
    });
    ahead.sort(function (a, b) { return a - b; });
    var edges = [FIELD_TOP + 4].concat(ahead, [FIELD_BOT - 4]);
    var best = -1, midY = p.y;
    for (var i = 1; i < edges.length; i++) {
      var gap = edges[i] - edges[i - 1];
      if (gap > best) { best = gap; midY = (edges[i] + edges[i - 1]) / 2; }
    }
    var dy = clamp((midY - p.y) * 0.05, -0.85, 0.85);
    return { x: Math.sqrt(Math.max(0.05, 1 - dy * dy)), y: dy };
  }

  // your defender: steered by drag, and he keeps moving when you let go
  function moveDefender(p, dt) {
    var vx = 0, vy = 0;
    if (steer) {
      var dx = steer.x - steer.x0, dy2 = steer.y - steer.y0;
      var d = Math.sqrt(dx * dx + dy2 * dy2);
      if (d > 4) { vx = dx / d * p.spd; vy = dy2 / d * p.spd; }
    } else if (carrier && carrier !== qb) {
      var t = carrier, ddx = t.x - p.x, ddy = t.y - p.y;
      var dd = Math.sqrt(ddx * ddx + ddy * ddy) || 1;
      vx = ddx / dd * p.spd * 0.55; vy = ddy / dd * p.spd * 0.55;   // drift at the play
    }
    p.x += vx * dt; p.y += vy * dt;
    if (vx || vy) p.anim += dt * 10;
  }

  function moveCarrier(p, dt) {
    var vx = p.spd, vy = 0;
    if (!weHaveBall()) {                    // their back, running himself
      var d2 = aiRunDir(p);
      p.x += d2.x * p.spd * dt; p.y += d2.y * p.spd * dt; p.anim += dt * 10;
      return;
    }
    if (!steer && p.role === "RB" && isRun() && G.play.dir && playT < 1.3) {
      var d = (G.play.cut && playT > 0.75) ? G.play.cut : G.play.dir;
      vx = d[0] * p.spd; vy = d[1] * p.spd;
    }
    if (steer) {
      var dx = steer.x - steer.x0, dy = steer.y - steer.y0, d = Math.sqrt(dx * dx + dy * dy);
      if (d > 4) { vx = dx / d * p.spd; vy = dy / d * p.spd; }
    }
    p.x += vx * dt; p.y += vy * dt; p.anim += dt * 8;
  }

  function throwBall(tx, ty, target) {
    if (!qb || carrier !== qb || ball.flying) return;
    ball.target = target || null; ball.reacted = false; G.stats.att++;
    tx = clamp(tx, qb.x - 10, yardToPx(112)); ty = clamp(ty, FIELD_TOP + 1, FIELD_BOT - 1);
    var d = dist(qb, { x: tx, y: ty });
    ball.flying = true; ball.holder = null; carrier = null;
    ball.sx = qb.x; ball.sy = qb.y; ball.tx = tx; ball.ty = ty;
    ball.t = 0; ball.dur = Math.max(0.35, d / 150);
  }
  function arrive() {
    ball.flying = false;
    var land = { x: ball.tx, y: ball.ty };
    var rcv = null, rd = 1e9, def = null, dd = 1e9;
    players.forEach(function (p) {
      if (p.team === "M" && (p.role === "WR" || p.role === "RB")) { var q = dist(p, land); if (q < rd) { rd = q; rcv = p; } }
      if (p.team === "O") { var q2 = dist(p, land); if (q2 < dd) { dd = q2; def = p; } }
    });
    if (rcv && rd < CATCH_R) {
      var r = Math.random();
      var pInt = dd < 4 ? 0.30 : dd < 9 ? 0.08 : 0.01;
      var pInc = dd < 4 ? 0.40 : dd < 9 ? 0.22 : 0.04;
      if (r < pInt) { endPlay("int", land); return; }
      if (r < pInt + pInc) { endPlay("incomplete"); return; }
      carrier = rcv; ball.holder = rcv; rcv.route = null;
      G.stats.comp++; G.banner = "CAUGHT"; G.bannerT = 0.5;
    } else if (def && dd < 4 && Math.random() < 0.2) {
      endPlay("int", land);
    } else endPlay("incomplete");
  }

  // ------------------------------------------------------------ play results
  function endPlay(kind, at) {
    if (G.mode !== "play") return;
    G.mode = "dead";
    var spotBefore = G.spot;
    var endYd = carrier ? pxToYard(carrier.x) : G.spot;
    var gain = 0, text = "";
    var secs = 32;
    switch (kind) {
      case "td":
        gain = 100 - spotBefore;
        text = weHaveBall() ? "TOUCHDOWN!" : (opp.abbr || "OPP") + " TOUCHDOWN";
        G.score[G.poss] += 7;
        if (weHaveBall()) {
          G.stats.tds++;
          G.stats.longest = Math.max(G.stats.longest, gain);
          G.stats.yards += gain;
        }
        after(1.6, function () { giveBall(1 - G.poss, 25); });
        break;
      case "sack":
        gain = -Math.round(rnd(4, 9)); text = "SACK " + gain;
        if (weHaveBall()) G.stats.sacks++;
        nextDown(gain); break;
      case "int":
        text = "INTERCEPTED"; if (weHaveBall()) G.stats.ints++;
        var iy = Math.round(clamp(pxToYard(at.x), 1, 99));
        secs = 12;
        after(1.6, function () { giveBall(1 - G.poss, 100 - iy); });
        break;
      case "incomplete":
        text = "INCOMPLETE"; secs = 8; nextDown(0); break;
      case "oob":
        secs = 10; /* fallthrough */
      case "tackle":
      default:
        gain = Math.round(endYd - spotBefore);
        if (gain > 0 && weHaveBall()) {
          G.stats.yards += gain; G.stats.longest = Math.max(G.stats.longest, gain);
        }
        text = (gain >= 0 ? "+" : "") + gain + " YDS";
        nextDown(gain);
    }
    G.clock -= secs;
    if (text) { G.banner = text; G.bannerT = 1.3; }
    if (G.clock <= 0) { G.clock = 0; tickQuarter(); }
  }

  // Hand the ball over. In sim mode their possession resolves as a card;
  // in play mode you take the field for it.
  function giveBall(newPoss, spot) {
    G.poss = newPoss;
    G.spot = clamp(spot, 1, 99);
    G.down = 1; G.toGo = Math.min(10, 100 - G.spot);
    G.call = null;
    if (G.poss === 1 && defenseMode === "sim") { startOppDrive(G.spot); return; }
    enterPresnap();
  }

  // their fourth down, when you're out there for it
  function aiFourthDown() {
    var fgYds = 100 - G.spot + 17;
    if (G.toGo <= 2 && G.spot > 55 && Math.random() < 0.35) return false;  // they go for it
    G.mode = "dead";
    var name = opp.abbr || "OPP";
    if (fgYds <= 50) {
      var good = Math.random() < (fgYds <= 35 ? 0.88 : 0.62);
      if (good) G.score[1] += 3;
      G.banner = name + " " + fgYds + " YD FG — " + (good ? "GOOD" : "NO GOOD");
      G.bannerT = 1.6; G.clock -= 6;
      var missSpot = clamp(100 - G.spot + 7, 20, 80);
      after(1.7, function () { giveBall(0, good ? 25 : missSpot); });
    } else {
      var net = Math.round(rnd(34, 48));
      G.banner = name + " PUNTS " + net + " YDS"; G.bannerT = 1.4; G.clock -= 8;
      var ours = clamp(100 - G.spot - net, 5, 80);
      after(1.5, function () { giveBall(0, ours); });
    }
    return true;
  }

  function nextDown(gain) {
    G.spot = clamp(G.spot + gain, 0, 99.5);
    if (G.spot <= 0.5 && gain < 0) { // safety
      G.score[1 - G.poss] += 2; G.banner = "SAFETY"; G.bannerT = 1.5;
      after(1.6, function () { giveBall(1 - G.poss, 35); }); return;
    }
    if (gain >= G.toGo) { G.down = 1; G.toGo = Math.min(10, 100 - G.spot); G.banner = "FIRST DOWN"; }
    else { G.down++; G.toGo -= Math.max(0, gain); if (gain < 0) G.toGo -= gain; }
    if (G.down > 4) { G.banner = "TURNOVER ON DOWNS"; G.bannerT = 1.6;
      after(1.6, function () { giveBall(1 - G.poss, 100 - G.spot); }); return; }
    after(1.2, enterPresnap);
  }

  function tickQuarter() {
    if (G.quarter >= 4) { finishGame(); return; }
    G.quarter++; G.clock = QUARTER_SECS;
    G.banner = "END OF " + ordinal(G.quarter - 1) + " QUARTER"; G.bannerT = 1.6;
  }

  var timers = [];
  function after(s, fn) { timers.push({ t: s, fn: fn }); }
  function runTimers(dt) {
    for (var i = timers.length - 1; i >= 0; i--) {
      timers[i].t -= dt;
      if (timers[i].t <= 0) {
        var fn = timers[i].fn; timers.splice(i, 1);
        if (G.mode !== "gameover") fn();   // the final gun is final
      }
    }
  }

  // 4th-down choices
  function punt() {
    var net = Math.round(rnd(34, 48));
    var oppSpot = clamp(100 - G.spot - net, 20, 80);   // from the opponent's own goal
    G.clock -= 8; G.banner = "PUNT " + net + " YDS"; G.bannerT = 1.4;
    after(1.5, function () { giveBall(1, oppSpot); });
  }
  function fieldGoal() {
    var yds = 100 - G.spot + 17;
    var p = yds <= 30 ? 0.97 : yds <= 40 ? 0.86 : yds <= 50 ? 0.7 : 0.5;
    G.clock -= 6;
    var good = Math.random() < p;            // remember it; the banner is gone by then
    if (good) G.score[0] += 3;
    G.banner = yds + " YD FIELD GOAL — " + (good ? "GOOD" : "NO GOOD");
    G.bannerT = 1.6; G.mode = "dead";
    var missSpot = clamp(100 - G.spot + 7, 20, 80);
    after(1.7, function () { giveBall(1, good ? 25 : missSpot); });
  }

  // ------------------------------------------------------------ opponent drives (simmed)
  function startOppDrive(fromTheirOwn) {
    G.mode = "oppdrive";
    var start = fromTheirOwn;               // yards from their own goal
    var need = 100 - start;
    var r = oppRating;
    var roll = Math.random();
    var pTD = 0.12 + 0.38 * r, pFG = 0.16 + 0.1 * r, pTO = 0.14 - 0.08 * r;
    var yards, text, secs;
    if (roll < pTD) {
      yards = need; G.score[1] += 7; text = "drives " + yards + " yards — TOUCHDOWN.";
      secs = rnd(110, 200);
    } else if (roll < pTD + pFG) {
      yards = Math.round(need - rnd(8, 25)); G.score[1] += 3; text = "drives " + yards + " yards — FIELD GOAL.";
      secs = rnd(100, 170);
    } else if (roll < pTD + pFG + pTO) {
      yards = Math.round(rnd(0, need * 0.5)); text = "turns it over after " + yards + " yards!";
      secs = rnd(40, 100);
      G.nextSpot = clamp(100 - (start + yards), 5, 95);
    } else {
      yards = Math.round(rnd(-5, need * 0.55)); text = "goes " + yards + " yards, then punts.";
      secs = rnd(60, 130);
      G.nextSpot = clamp(100 - (start + yards) - Math.round(rnd(35, 45)), 5, 40);
      if (G.nextSpot < 5) G.nextSpot = 20;
    }
    if (roll < pTD + pFG) G.nextSpot = 25;
    var from = start >= 50 ? "the MICH " + (100 - start) : "their own " + start;
    G.card = opp.name + " takes over at " + from + " and " + text;
    G.cardT = 2.4;
    G.clock -= secs;
    if (G.clock <= 0) {
      G.clock = 0;
      if (G.quarter >= 4) { G.cardT = 2.4; G.pendingEnd = true; }
      else { G.quarter++; G.clock = QUARTER_SECS; }
    }
  }
  function endOppDrive() {
    G.card = null;
    if (G.pendingEnd) { finishGame(); return; }
    G.poss = 0;
    G.spot = G.nextSpot || 25; G.down = 1; G.toGo = 10; enterPresnap();
  }

  function postScore() {
    // hand the result to the board for the leaderboard; failures are silent
    try {
      var rec = seasonRecord();
      fetch("/bowl/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          us: G.score[0], them: G.score[1],
          longest: G.stats.longest,
          season_done: season.week >= schedule.length,
          season_w: rec.w, season_l: rec.l
        })
      }).catch(function () {});
    } catch (e) {}
  }

  function finishGame() {
    G.mode = "gameover";
    G.result = G.score[0] > G.score[1] ? "W"
             : (G.score[0] === G.score[1] ? "T" : "L");
    if (!G.recorded) {                       // write the week down exactly once
      G.recorded = true;
      season.results[week] = { n: opp.name, a: opp.abbr || "OPP",
                               us: G.score[0], them: G.score[1], home: !!opp.home };
      season.week = week + 1;
      saveSeason();
      var best = parseInt(load("bowlLongest") || "0", 10);
      if (G.stats.longest > best) store("bowlLongest", String(G.stats.longest));
      postScore();
    }
    G.record = seasonRecord();
    G.lastOfSeason = (week + 1 >= schedule.length);
  }

  // ------------------------------------------------------------ drawing
  // ------------------------------------------------------------ the field
  // The field never changes, so it's painted ONCE into an offscreen canvas
  // (turf texture, numbers, logo, goal posts) and the visible slice is
  // blitted each frame. Detail is free when you only pay for it at load.
  var FIELD_W = yardToPx(110);          // -10 .. 110 yards
  // The offense always drives left to right, so the end zones swap
  // depending on who has it. Baked once each, then reused.
  var fieldCanvases = {};

  function endzone(g, x, w, color, label, flip) {
    g.fillStyle = color; g.fillRect(x, FIELD_TOP, w, FIELD_BOT - FIELD_TOP);
    // diagonal weave, barely there — paint on grass, not a flat block
    g.save();
    g.beginPath(); g.rect(x, FIELD_TOP, w, FIELD_BOT - FIELD_TOP); g.clip();
    g.strokeStyle = "rgba(255,255,255,0.055)"; g.lineWidth = 1;
    for (var d = -160; d < w + 160; d += 7) {
      g.beginPath(); g.moveTo(x + d, FIELD_TOP); g.lineTo(x + d + 160, FIELD_BOT); g.stroke();
    }
    g.restore();
    // lettering, reading from the near sideline
    g.save();
    g.translate(x + w / 2, (FIELD_TOP + FIELD_BOT) / 2);
    g.rotate(flip ? Math.PI / 2 : -Math.PI / 2);
    g.textAlign = "center"; g.textBaseline = "middle";
    g.font = "bold 13px Verdana, sans-serif";
    g.lineWidth = 3; g.lineJoin = "round";
    g.strokeStyle = "rgba(0,0,0,0.35)"; g.strokeText(label, 0, 0);
    g.fillStyle = "#ffffff"; g.fillText(label, 0, 0);
    g.restore();
  }

  function goalPost(g, x, dir) {
    // seen from above: the base, the crossbar, and two uprights
    var midY = (FIELD_TOP + FIELD_BOT) / 2, spread = 13;
    g.strokeStyle = "#f2c200"; g.lineWidth = 1.6; g.lineCap = "round";
    g.beginPath(); g.moveTo(x, midY - spread); g.lineTo(x, midY + spread); g.stroke();
    g.beginPath();
    g.moveTo(x, midY - spread); g.lineTo(x + dir * 5, midY - spread);
    g.moveTo(x, midY + spread); g.lineTo(x + dir * 5, midY + spread);
    g.stroke();
    g.fillStyle = "rgba(0,0,0,0.3)";
    g.fillRect(x - 1, midY - spread + 1, 2, spread * 2 - 2);
    g.fillStyle = "#ffd633"; g.fillRect(x - 1.2, midY - 2, 2.4, 4);
  }

  function fieldNumbers(g) {
    g.textAlign = "center"; g.textBaseline = "middle";
    for (var yd = 10; yd <= 90; yd += 10) {
      var lx = yardToPx(yd);
      var n = yd > 50 ? 100 - yd : yd;
      var label = n === 50 ? "50" : String(n);
      [[FIELD_TOP + 17, -1], [FIELD_BOT - 17, 1]].forEach(function (pos) {
        var ty = pos[0], side = pos[1];
        g.save();
        g.translate(lx, ty);
        g.rotate(side < 0 ? -Math.PI / 2 : Math.PI / 2);
        g.font = "bold 11px Verdana, sans-serif";
        g.fillStyle = "rgba(0,0,0,0.28)"; g.fillText(label, 0.8, 1.2);
        g.fillStyle = "rgba(255,255,255,0.92)"; g.fillText(label, 0, 0);
        // the arrow that points at the nearer goal line
        if (n !== 50) {
          var toRight = yd < 50;
          var ax = (toRight ? 1 : -1) * 10;
          g.fillStyle = "rgba(255,255,255,0.85)";
          g.beginPath();
          g.moveTo(ax + (toRight ? 3 : -3), 0);
          g.lineTo(ax, -2.4); g.lineTo(ax, 2.4);
          g.closePath(); g.fill();
        }
        g.restore();
      });
    }
  }

  function bakeField(poss) {
    var c = document.createElement("canvas");
    c.width = FIELD_W * RES; c.height = H * RES;
    var g = c.getContext("2d");
    g.scale(RES, RES);

    // beyond the sidelines: shadowed apron, so the field sits in something
    var sur = g.createLinearGradient(0, 0, 0, H);
    sur.addColorStop(0, "#0e1a12"); sur.addColorStop(0.5, "#16261a"); sur.addColorStop(1, "#0e1a12");
    g.fillStyle = sur; g.fillRect(0, 0, FIELD_W, H);

    // turf: mown stripes every five yards
    for (var yd = -10; yd < 110; yd += 5) {
      g.fillStyle = ((yd / 5) % 2 === 0) ? GRASS_A : GRASS_B;
      g.fillRect(yardToPx(yd), FIELD_TOP, 5 * PX, FIELD_BOT - FIELD_TOP);
    }
    // light across the grass: brighter down the middle, shaded at the rails
    var lit = g.createLinearGradient(0, FIELD_TOP, 0, FIELD_BOT);
    lit.addColorStop(0, "rgba(0,0,0,0.30)");
    lit.addColorStop(0.42, "rgba(255,255,255,0.07)");
    lit.addColorStop(1, "rgba(0,0,0,0.34)");
    g.fillStyle = lit; g.fillRect(0, FIELD_TOP, FIELD_W, FIELD_BOT - FIELD_TOP);

    var theirs = (opp.name || "OPP").toUpperCase().slice(0, 11);
    if (poss === 0) {          // we're driving: our end behind us, theirs ahead
      endzone(g, yardToPx(-10), 10 * PX, BLUE, "MICHIGAN", false);
      endzone(g, yardToPx(100), 10 * PX, oppColor, theirs, true);
    } else {
      endzone(g, yardToPx(-10), 10 * PX, oppColor, theirs, false);
      endzone(g, yardToPx(100), 10 * PX, BLUE, "MICHIGAN", true);
    }

    // yard lines
    for (var y2 = 0; y2 <= 100; y2 += 5) {
      var lx = yardToPx(y2);
      var goal = (y2 === 0 || y2 === 100);
      g.fillStyle = goal ? "#ffffff" : "rgba(255,255,255,0.78)";
      g.fillRect(lx - (goal ? 1 : 0.5), FIELD_TOP, goal ? 2 : 1, FIELD_BOT - FIELD_TOP);
    }
    // hash marks, and the little ticks along each sideline
    g.fillStyle = "rgba(255,255,255,0.62)";
    var h1 = FIELD_TOP + 46, h2 = FIELD_BOT - 46;
    for (var y3 = 0; y3 <= 100; y3++) {
      if (y3 % 5 === 0) continue;
      var hx = yardToPx(y3);
      g.fillRect(hx, h1, 1, 3); g.fillRect(hx, h2, 1, 3);
      g.fillRect(hx, FIELD_TOP + 1, 1, 3); g.fillRect(hx, FIELD_BOT - 4, 1, 3);
    }
    fieldNumbers(g);

    // sidelines and the bright rail that frames the whole thing
    g.fillStyle = "#f2f2f2";
    g.fillRect(0, FIELD_TOP - 2, FIELD_W, 2); g.fillRect(0, FIELD_BOT, FIELD_W, 2);
    g.fillStyle = "rgba(255,203,5,0.5)";
    g.fillRect(0, FIELD_TOP - 3, FIELD_W, 1); g.fillRect(0, FIELD_BOT + 2, FIELD_W, 1);

    goalPost(g, yardToPx(-9), -1);
    goalPost(g, yardToPx(109), 1);

    // turf grain: a fine speckle over everything, so it reads as grass
    var img = g.getImageData(0, FIELD_TOP * RES, FIELD_W * RES, (FIELD_BOT - FIELD_TOP) * RES);
    var d = img.data;
    for (var i = 0; i < d.length; i += 4) {
      var n = ((i * 2654435761) % 23) - 11;      // cheap deterministic dither
      d[i] = clamp(d[i] + n, 0, 255);
      d[i + 1] = clamp(d[i + 1] + n, 0, 255);
      d[i + 2] = clamp(d[i + 2] + n, 0, 255);
    }
    g.putImageData(img, 0, FIELD_TOP * RES);
    return c;
  }

  function drawField() {
    var poss = G.poss || 0;
    if (!fieldCanvases[poss]) fieldCanvases[poss] = bakeField(poss);
    ctx.fillStyle = "#0b1410"; ctx.fillRect(0, 0, W, H);
    ctx.drawImage(fieldCanvases[poss], camX * RES, 0, W * RES, H * RES, 0, 0, W, H);

    // the two lines that move: scrimmage and the sticks
    if (G.mode === "presnap" || G.mode === "play" || G.mode === "dead") {
      var sx = Math.round(yardToPx(G.spot) - camX);
      ctx.fillStyle = "rgba(90,150,255,0.30)"; ctx.fillRect(sx - 1, FIELD_TOP, 3, FIELD_BOT - FIELD_TOP);
      ctx.fillStyle = "rgba(150,200,255,0.95)"; ctx.fillRect(sx, FIELD_TOP, 1, FIELD_BOT - FIELD_TOP);
      var fx = Math.round(yardToPx(Math.min(100, G.spot + G.toGo)) - camX);
      ctx.fillStyle = "rgba(255,203,5,0.28)"; ctx.fillRect(fx - 1, FIELD_TOP, 3, FIELD_BOT - FIELD_TOP);
      ctx.fillStyle = "rgba(255,220,60,0.95)"; ctx.fillRect(fx, FIELD_TOP, 1, FIELD_BOT - FIELD_TOP);
    }
  }

  // ------------------------------------------------------------ sprites
  // 8x13 pixel players, baked once per (team, skin, frame, facing) to tiny
  // offscreen canvases. Michigan: winged helmet, navy jersey, maize pants.
  // Opponent: their color with a white helmet stripe and white pants.
  var SPRITE_ROWS = [
    "......HHHH......",
    "....HHHHHHHH....",
    "...HHWWWWWWHH...",
    "...HWWWWWWWWH...",
    "...HHHWWWHHHHF..",
    "...HHHHHHHHHHF..",
    "...HHHHHHHHHFF..",
    "....HHHHHHHF....",
    "......SSSS......",
    "..JJJJJJJJJJJJ..",
    ".JJJJJJJJJJJJJJ.",
    ".JJJJNNNNNNJJJJ.",
    ".JJJJNNNNNNJJJJ.",
    "..JJJJJJJJJJJJ..",
    "..SJJJJJJJJJJS..",
    "...JJJJJJJJJJ...",
    "....PPPPPPPP....",
    "....PPPPPPPP....",
    "....PPPPPPPP....",
    "....PPP..PPP...."
  ];
  // a running gait, not a scissor: contact, passing, contact with the
  // trail leg kicked up, passing — each step asymmetric like a real stride
  var LEG_FRAMES = [
    ["....PPP..PPP....", "...PPP....PPP...", "..OOO......OOO..", "..OOO.......OOO.", ".KKKK.......KKKK", "................"],
    [".....PPPPPP.....", ".....PPPPP......", ".....OOOOO......", "......OOOO......", ".....KKKKK......", "................"],
    [".....PPP.PP.....", "....PPP...PP....", "...OOO....OO....", "..OOO......OO...", ".KKKK......KKK..", "................"]
  ];
  var SW = 16, SH = 26;          // sprite pixels; drawn into an 8x13 logical box
  var PAD = 1;                   // room for the outline
  var SKINS = ["#f1c9a5", "#c68642", "#6b3e22"];
  var spriteCache = {};
  function shade(hex, amt) {
    var n = parseInt(hex.slice(1), 16);
    var r = clamp(((n >> 16) & 255) + amt, 0, 255);
    var g2 = clamp(((n >> 8) & 255) + amt, 0, 255);
    var b = clamp((n & 255) + amt, 0, 255);
    return "rgb(" + r + "," + g2 + "," + b + ")";
  }
  function bakeSprite(team, skin, frame, faceRight) {
    var key = team + skin + frame + (faceRight ? "R" : "L");
    if (spriteCache[key]) return spriteCache[key];
    var c = document.createElement("canvas");
    c.width = SW + PAD * 2; c.height = SH + PAD * 2;
    var g = c.getContext("2d");
    var jersey = team === "M" ? BLUE : oppColor;
    var helm = team === "M" ? "#00274C" : oppColor;
    var colors = team === "M"
      ? { H: helm, W: MAIZE, F: "#2b2b2b", S: SKINS[skin], J: jersey, N: MAIZE, P: MAIZE, O: jersey, K: "#1a1a1a" }
      : { H: helm, W: "#f4f4f4", F: "#2b2b2b", S: SKINS[skin], J: jersey, N: "#f4f4f4", P: "#ececec", O: jersey, K: "#1a1a1a" };
    var rows = SPRITE_ROWS.concat(LEG_FRAMES[frame]);
    function at(r, col) {
      if (r < 0 || r >= rows.length || col < 0 || col >= SW) return ".";
      return rows[r][col];
    }
    // 1. outline: any empty pixel touching the figure goes near-black
    g.fillStyle = "rgba(8,10,16,0.85)";
    for (var r0 = -1; r0 <= rows.length; r0++) {
      for (var c0 = -1; c0 <= SW; c0++) {
        if (at(r0, c0) !== ".") continue;
        if (at(r0 - 1, c0) === "." && at(r0 + 1, c0) === "." &&
            at(r0, c0 - 1) === "." && at(r0, c0 + 1) === ".") continue;
        var ox = faceRight ? c0 : SW - 1 - c0;
        g.fillRect(ox + PAD, r0 + PAD, 1, 1);
      }
    }
    // 2. the figure
    for (var r = 0; r < rows.length; r++) {
      for (var col = 0; col < SW; col++) {
        var ch = rows[r][col];
        if (ch === ".") continue;
        var base = colors[ch];
        // light from above-left: brighten the top row of each part, darken the last
        if (ch === "J" || ch === "P" || ch === "H" || ch === "O") {
          if (at(r - 1, col) === ".") base = shade(base === MAIZE ? "#FFCB05" : base, 26);
          else if (at(r + 1, col) === ".") base = shade(base === MAIZE ? "#FFCB05" : base, -26);
        }
        g.fillStyle = base;
        g.fillRect((faceRight ? col : SW - 1 - col) + PAD, r + PAD, 1, 1);
      }
    }
    // 3. a glint on the helmet
    g.fillStyle = "rgba(255,255,255,0.30)";
    g.fillRect((faceRight ? 4 : SW - 8) + PAD, 1 + PAD, 3, 1);
    spriteCache[key] = c;
    return c;
  }
  var RUN_CYCLE = [0, 1, 2, 1];

  function drawPlayer(p) {
    var x = p.x - camX, y = p.y;
    if (p.skin === undefined) p.skin = Math.floor(Math.random() * SKINS.length);
    // facing: carriers by motion, otherwise offense right / defense left
    var faceRight = p.team === "M";
    if (p === carrier && steer) {
      var sdx = steer.x - steer.x0;
      if (Math.abs(sdx) > 4) faceRight = sdx > 0;
    }
    var moving = (p === carrier) || p.team === "O" || (p.route && G.mode === "play");
    var frame = moving ? RUN_CYCLE[Math.floor(p.anim) % 4] : 0;
    // shadow, cast to the low right
    ctx.save();
    ctx.fillStyle = "rgba(0,0,0,0.30)";
    ctx.beginPath(); ctx.ellipse(x + 1, y + 3, 4.2, 1.6, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    ctx.drawImage(bakeSprite(p.team, p.skin, frame, faceRight),
                  Math.round(x) - 4.5, Math.round(y) - 10.5, 9, 14);
    if (p === myDef && G.mode !== "recap") {   // the one you're steering
      ctx.save();
      ctx.strokeStyle = "rgba(255,203,5,0.95)"; ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.ellipse(Math.round(x), Math.round(y) + 3, 5.5, 2.2, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
    if (p === carrier && !ball.flying) {   // a chevron over whoever has it
      var by = Math.round(y) - 14 + Math.sin(playT * 7) * 0.6;
      ctx.fillStyle = "rgba(0,0,0,0.5)";
      ctx.beginPath();
      ctx.moveTo(Math.round(x), by + 3.6); ctx.lineTo(Math.round(x) - 2.6, by - 0.4);
      ctx.lineTo(Math.round(x) + 2.6, by - 0.4); ctx.closePath(); ctx.fill();
      ctx.fillStyle = MAIZE;
      ctx.beginPath();
      ctx.moveTo(Math.round(x), by + 2.8); ctx.lineTo(Math.round(x) - 2, by - 0.6);
      ctx.lineTo(Math.round(x) + 2, by - 0.6); ctx.closePath(); ctx.fill();
    }
  }

  function drawBall() {
    if (!ball) return;
    if (ball.holder && !ball.flying) return;    // it's tucked under an arm
    var x = ball.x - camX, y = ball.y - (ball.z || 0);
    if (ball.flying) {
      ctx.save();
      ctx.fillStyle = "rgba(0,0,0,0.28)";
      ctx.beginPath(); ctx.ellipse(ball.x - camX, ball.y + 3, 3, 1.1, 0, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    }
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(ball.flying ? (ball.tx > ball.sx ? 0.35 : -0.35) + ball.t * 7 : 0.3);
    ctx.fillStyle = "rgba(8,10,16,0.8)";
    ctx.beginPath(); ctx.ellipse(0, 0, 3.4, 2.1, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#8a4a20";
    ctx.beginPath(); ctx.ellipse(0, 0, 2.9, 1.7, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#a95f2c";
    ctx.beginPath(); ctx.ellipse(-0.4, -0.4, 2.1, 0.9, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#f6f0e6";
    ctx.fillRect(-1.1, -0.45, 2.2, 0.9);
    ctx.fillRect(2.0, -0.5, 0.7, 1.0); ctx.fillRect(-2.7, -0.5, 0.7, 1.0);
    ctx.restore();
  }

  function scoreChip(x, y, w, color, textColor, name, score, hasBall) {
    ctx.fillStyle = "rgba(0,0,0,0.45)"; ctx.fillRect(x + 1, y + 1, w, 8);
    ctx.fillStyle = color; ctx.fillRect(x, y, w, 8);
    ctx.fillStyle = "rgba(255,255,255,0.16)"; ctx.fillRect(x, y, w, 1);
    ctx.font = "bold 7px Verdana, sans-serif";
    ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillStyle = textColor; ctx.fillText(name, x + 3, y + 4.5);
    if (hasBall) {              // a ball beside whoever has it
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(x + w - 15, y + 4.5, 2.6, 1.6, 0, 0, Math.PI * 2);
      ctx.fillStyle = "#8a4a20"; ctx.fill();
      ctx.strokeStyle = "rgba(0,0,0,0.5)"; ctx.lineWidth = 0.6; ctx.stroke();
      ctx.restore();
    }
    ctx.textAlign = "right";
    ctx.font = "bold 8px Verdana, sans-serif";
    ctx.fillText(String(score), x + w - 3, y + 4.5);
  }

  function drawHUD() {
    var barH = FIELD_TOP - 3;
    var bg = ctx.createLinearGradient(0, 0, 0, barH);
    bg.addColorStop(0, "#0d1420"); bg.addColorStop(1, "#060a12");
    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, barH);
    ctx.fillStyle = MAIZE; ctx.fillRect(0, barH, W, 1);

    if (G.mode === "recap") {          // no clock, no down, no live score
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.font = "bold 9px Verdana, sans-serif"; ctx.fillStyle = MAIZE;
      ctx.fillText("VICTARD BOWL", W / 2, 7);
      ctx.font = "6px Verdana, sans-serif"; ctx.fillStyle = "rgba(255,255,255,0.6)";
      ctx.fillText("SEASON " + (season.year || 1) + " COMPLETE", W / 2, 15);
      ctx.textBaseline = "alphabetic";
      return;
    }

    var live = (G.mode !== "gameover");
    scoreChip(4, 1, 54, MAIZE, BLUE, "MICH", G.score[0], live && G.poss === 0);
    scoreChip(4, 10, 54, oppColor, "#ffffff", (opp.abbr || "OPP").slice(0, 5),
              G.score[1], live && G.poss === 1);

    var rec = seasonRecord();
    ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.font = "bold 6px Verdana, sans-serif";
    ctx.fillStyle = isRivalry(week) ? MAIZE : "rgba(255,255,255,0.6)";
    ctx.fillText(isRivalry(week) ? "RIVALRY" : "WEEK " + (week + 1), 62, 5.5);
    ctx.fillStyle = "rgba(255,255,255,0.75)";
    ctx.fillText(rec.text, 62, 14);

    ctx.textAlign = "center";
    ctx.font = "bold 9px Verdana, sans-serif";
    ctx.fillStyle = "#ffffff";
    ctx.fillText(fmtClock(G.clock), W / 2, 6);
    ctx.font = "bold 6px Verdana, sans-serif";
    ctx.fillStyle = MAIZE; ctx.fillText(ordinal(G.quarter) + " QUARTER", W / 2, 14);

    if (G.mode !== "gameover" && G.mode !== "oppdrive") {
      // the yard line belongs to whichever half of the field the ball is on
      var them = (opp.abbr || "OPP");
      var near = G.spot <= 50, mine = weHaveBall();
      var yl = (near ? (mine ? "MICH" : them) : (mine ? them : "MICH")) + " " +
               Math.round(near ? G.spot : 100 - G.spot);
      var togo = (G.spot + G.toGo >= 100) ? "GOAL" : Math.round(G.toGo);
      var txt = (weHaveBall() ? "" : (opp.abbr || "OPP") + " ") +
                ordinal(G.down) + " & " + togo;
      ctx.font = "bold 7px Verdana, sans-serif";
      var tw = ctx.measureText(txt).width + 8;
      ctx.fillStyle = "rgba(255,203,5,0.14)";
      ctx.fillRect(W - 6 - tw, 1, tw, 8);
      ctx.strokeStyle = "rgba(255,203,5,0.5)"; ctx.lineWidth = 1;
      ctx.strokeRect(W - 6 - tw + 0.5, 1.5, tw - 1, 7);
      ctx.textAlign = "center"; ctx.fillStyle = MAIZE;
      ctx.fillText(txt, W - 6 - tw / 2, 5.5);
      ctx.textAlign = "right"; ctx.font = "6px Verdana, sans-serif";
      ctx.fillStyle = "rgba(255,255,255,0.65)";
      ctx.fillText("BALL ON " + yl, W - 6, 14);
    } else {
      ctx.textAlign = "right"; ctx.font = "6px Verdana, sans-serif";
      ctx.fillStyle = "rgba(255,255,255,0.5)";
      ctx.fillText("WEEK " + (week + 1), W - 6, 8);
    }
    ctx.textBaseline = "alphabetic";
  }

  function button(x, y, w, h, label, hot) {
    ctx.fillStyle = "rgba(0,0,0,0.45)"; ctx.fillRect(x + 1, y + 1, w, h);
    var g2 = ctx.createLinearGradient(0, y, 0, y + h);
    if (hot) { g2.addColorStop(0, "#ffe066"); g2.addColorStop(1, "#e0b000"); }
    else { g2.addColorStop(0, "#0b3565"); g2.addColorStop(1, "#022043"); }
    ctx.fillStyle = g2; ctx.fillRect(x, y, w, h);
    ctx.fillStyle = hot ? "rgba(255,255,255,0.55)" : "rgba(255,203,5,0.22)";
    ctx.fillRect(x, y, w, 1);
    ctx.strokeStyle = hot ? "#fff3b0" : "rgba(255,203,5,0.65)";
    ctx.lineWidth = 1; ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    ctx.font = "bold 8px Verdana, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = hot ? "#00203f" : MAIZE;
    ctx.fillText(label, x + w / 2, y + h / 2 + 0.5);
    ctx.textBaseline = "alphabetic";
  }
  var BTNS = [];
  function drawOverlay() {
    BTNS = [];
    ctx.textAlign = "center";
    if (G.mode === "recap") {
      drawRecap();
      BTNS.push({ x: 46, y: FIELD_BOT + 3, w: 108, h: 11,
                  label: "NEW SEASON", act: "new" });
      BTNS.push({ x: 166, y: FIELD_BOT + 3, w: 108, h: 11,
                  label: "LEADERBOARD", act: "board" });
      BTNS.forEach(function (b) { button(b.x, b.y, b.w, b.h, b.label, true); });
      return;
    }
    if (G.mode === "presnap") {
      drawRouteGhosts();
      var inRange = (100 - G.spot + 17) <= 55;
      var y = FIELD_BOT + 3, slots = [];
      offered.forEach(function (pl, i) { slots.push({ label: pl.name, act: "play" + i, hot: i === chosen }); });
      if (G.down === 4 && weHaveBall()) {
        slots.push({ label: "PUNT", act: "punt" });
        if (inRange) slots.push({ label: "FG", act: "fg" });
      }
      var bw = Math.floor((W - 8 - 6 * (slots.length - 1)) / slots.length);
      slots.forEach(function (sl, i) {
        var b = { x: 4 + i * (bw + 6), y: y, w: bw, h: 11, label: sl.label, act: sl.act, hot: sl.hot };
        BTNS.push(b); button(b.x, b.y, b.w, b.h, b.label, !!b.hot);
      });
    } else if (G.mode === "play") {
      if (aim && carrier === qb) {
        var ax = clamp(aim.x, qb.x - 10, yardToPx(112)), ay = clamp(aim.y, FIELD_TOP + 1, FIELD_BOT - 1);
        ctx.strokeStyle = "rgba(255,255,255,0.8)"; ctx.setLineDash([2, 2]);
        ctx.beginPath(); ctx.moveTo(qb.x - camX, qb.y); ctx.lineTo(ax - camX, ay); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = MAIZE; ctx.fillRect(ax - camX - 2, ay - 2, 4, 4);
        if (aim.snap) {
          ctx.strokeStyle = MAIZE; ctx.lineWidth = 1;
          ctx.strokeRect(Math.round(aim.snap.x - camX) - 6.5, Math.round(aim.snap.y) - 12.5, 13, 17);
        }
      }
    } else if (G.mode === "oppdrive" && G.card) {
      ctx.fillStyle = "rgba(0,0,0,0.72)"; ctx.fillRect(0, 60, W, 60);
      ctx.fillStyle = "#fff"; ctx.font = "bold 9px monospace";
      wrapText(G.card, W / 2, 84, 300, 11);
      ctx.fillStyle = "#aaa"; ctx.font = "7px monospace"; ctx.fillText("tap to skip", W / 2, 112);
    } else if (G.mode === "gameover") {
      ctx.fillStyle = "rgba(0,0,0,0.8)"; ctx.fillRect(0, 30, W, 130);
      ctx.fillStyle = G.result === "W" ? MAIZE : "#fff"; ctx.font = "bold 12px monospace";
      ctx.fillText(G.result === "W" ? "MICHIGAN WINS" : G.result === "T" ? "TIE" : "MICHIGAN LOSES", W / 2, 52);
      ctx.font = "bold 10px monospace"; ctx.fillStyle = "#fff";
      ctx.fillText("MICH " + G.score[0] + "  —  " + (opp.abbr || "OPP") + " " + G.score[1], W / 2, 68);
      ctx.font = "8px monospace"; ctx.fillStyle = "#ccc";
      ctx.fillText(G.stats.yards + " yds · " + G.stats.tds + " TD · " + G.stats.ints + " INT · " + G.stats.sacks + " sacks · long " + G.stats.longest, W / 2, 84);
      if (G.record) ctx.fillText("Season: " + G.record.text + "  ·  week " + (week + 1) + " of " + schedule.length, W / 2, 98);
      BTNS.push({ x: 52, y: 118, w: 104, h: 13,
                  label: G.lastOfSeason ? "SEASON RECAP" : "NEXT GAME", act: "next" });
      BTNS.push({ x: 164, y: 118, w: 104, h: 13, label: "LEADERBOARD", act: "board" });
      BTNS.forEach(function (b) { button(b.x, b.y, b.w, b.h, b.label, true); });
    }
    if (G.banner && G.bannerT > 0) {
      ctx.fillStyle = "rgba(0,0,0,0.7)"; ctx.fillRect(W / 2 - 90, 74, 180, 22);
      ctx.fillStyle = G.banner.indexOf("TOUCHDOWN") !== -1 || G.banner.indexOf("FIRST") !== -1 ? MAIZE : "#fff";
      ctx.font = "bold 10px monospace"; ctx.textAlign = "center";
      ctx.fillText(G.banner, W / 2, 89);
    }
  }
  function drawRecap() {
    var rec = seasonRecord();
    ctx.fillStyle = "rgba(3,8,16,0.93)";
    ctx.fillRect(0, FIELD_TOP, W, FIELD_BOT - FIELD_TOP);
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = "bold 13px Verdana, sans-serif"; ctx.fillStyle = MAIZE;
    ctx.fillText("SEASON " + rec.text, W / 2, FIELD_TOP + 15);
    ctx.font = "7px Verdana, sans-serif"; ctx.fillStyle = "rgba(255,255,255,0.55)";
    var note = rec.l === 0 ? "undefeated. nobody will believe you."
             : rec.w === 0 ? "a rebuilding year."
             : rec.w > rec.l ? "a winning season." : "wait till next year.";
    ctx.fillText(note, W / 2, FIELD_TOP + 27);

    var rows = Math.ceil(schedule.length / 2);
    for (var i = 0; i < schedule.length; i++) {
      var r = season.results[i];
      var col = i < rows ? 0 : 1;
      var x = col === 0 ? 14 : W / 2 + 8;
      var y = FIELD_TOP + 42 + (i - col * rows) * 13;
      var g = schedule[i];
      ctx.textAlign = "left";
      if (!r) {
        ctx.font = "7px Verdana, sans-serif"; ctx.fillStyle = "rgba(255,255,255,0.28)";
        ctx.fillText((g.home ? "vs " : "at ") + (g.abbr || "OPP"), x + 24, y);
        continue;
      }
      var won = r.us > r.them, tie = r.us === r.them;
      ctx.font = "bold 8px Verdana, sans-serif";
      ctx.fillStyle = won ? MAIZE : tie ? "#c9c9c9" : "#e2757a";
      ctx.fillText(tie ? "T" : won ? "W" : "L", x, y);
      ctx.font = "8px Verdana, sans-serif"; ctx.fillStyle = "#ffffff";
      ctx.fillText(r.us + "-" + r.them, x + 10, y);
      ctx.font = "7px Verdana, sans-serif"; ctx.fillStyle = "rgba(255,255,255,0.65)";
      ctx.fillText((r.home ? "vs " : "at ") + r.a, x + 40, y);
    }
    ctx.textBaseline = "alphabetic";
  }

  function routeLine(points, color) {
    if (points.length < 2) return;
    ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(Math.round(points[0].x - camX) + 0.5, Math.round(points[0].y) + 0.5);
    for (var i = 1; i < points.length; i++) ctx.lineTo(Math.round(points[i].x - camX) + 0.5, Math.round(points[i].y) + 0.5);
    ctx.stroke();
    // arrowhead in the direction of the last segment
    var a = points[points.length - 2], b = points[points.length - 1];
    var dx = b.x - a.x, dy = b.y - a.y, len = Math.sqrt(dx * dx + dy * dy) || 1;
    dx /= len; dy /= len;
    var tx = Math.round(b.x - camX) + 0.5, ty = Math.round(b.y) + 0.5;
    ctx.beginPath();
    ctx.moveTo(tx, ty);
    ctx.lineTo(tx - dx * 4 - dy * 3, ty - dy * 4 + dx * 3);
    ctx.moveTo(tx, ty);
    ctx.lineTo(tx - dx * 4 + dy * 3, ty - dy * 4 - dx * 3);
    ctx.stroke();
  }
  function drawRouteGhosts() {
    if (!weHaveBall()) return;     // you don't get to see their play
    ctx.save();
    ctx.beginPath(); ctx.rect(0, FIELD_TOP, W, FIELD_BOT - FIELD_TOP); ctx.clip();
    players.forEach(function (p) {
      if (p.team !== "M" || !p.route || p.route === "block") return;
      var sim = { x: p.x, y: p.y, spd: p.spd, route: p.route, home: p.home };
      var pts = [{ x: sim.x, y: sim.y }];
      for (var t = 0; t < 1.7; t += 0.1) {
        var v = routeVel(sim, t);
        sim.x += v.vx * 0.1;
        sim.y = clamp(sim.y + v.vy * 0.1, FIELD_TOP + 3, FIELD_BOT - 3);
        pts.push({ x: sim.x, y: sim.y });
      }
      routeLine(pts, p.role === "RB" ? "rgba(255,203,5,0.95)" : "rgba(255,255,255,0.9)");
    });
    if (isRun()) {  // the back's opening lane
      var rb = players.filter(function (q) { return q.role === "RB"; })[0];
      if (rb) {
        var d = G.play.dir, x = rb.x, y = rb.y, pts2 = [{ x: x, y: y }];
        for (var k = 0; k < 12; k++) {
          if (G.play.cut && k > 5) d = G.play.cut;
          x += d[0] * 4; y = clamp(y + d[1] * 4, FIELD_TOP + 3, FIELD_BOT - 3); pts2.push({ x: x, y: y });
        }
        routeLine(pts2, "rgba(255,203,5,0.95)");
      }
    }
    ctx.restore();
  }
  function wrapText(text, x, y, maxW, lh) {
    var words = text.split(" "), line = "";
    for (var i = 0; i < words.length; i++) {
      var test = line + words[i] + " ";
      if (ctx.measureText(test).width > maxW && line) { ctx.fillText(line.trim(), x, y); line = words[i] + " "; y += lh; }
      else line = test;
    }
    ctx.fillText(line.trim(), x, y);
  }

  function render() {
    drawField();
    // draw in y order so nearer players overlap
    var sorted = players.slice().sort(function (a, b) { return a.y - b.y; });
    sorted.forEach(drawPlayer);
    drawBall();
    drawHUD();
    drawOverlay();
  }

  // ------------------------------------------------------------ input
  function toLogical(e) {
    var r = canvas.getBoundingClientRect();
    var cx = (e.touches ? e.touches[0].clientX : e.clientX), cy = (e.touches ? e.touches[0].clientY : e.clientY);
    return { x: (cx - r.left) * W / r.width, y: (cy - r.top) * H / r.height };
  }
  function hitButton(pt) {
    for (var i = 0; i < BTNS.length; i++) {
      var b = BTNS[i];
      if (pt.x >= b.x && pt.x <= b.x + b.w && pt.y >= b.y - 3 && pt.y <= b.y + b.h + 3) return b;
    }
    return null;
  }
  function act(a) {
    if (a.indexOf("play") === 0) {
      chosen = parseInt(a.slice(4), 10);
      if (weHaveBall()) { G.play = offered[chosen]; buildFormation(); }
      else { G.call = offered[chosen]; }
    }
    else if (a === "punt") { G.mode = "dead"; punt(); }
    else if (a === "fg") { fieldGoal(); }
    else if (a === "next") { location.reload(); }
    else if (a === "board") { location.href = "/bowl/leaderboard"; }
    else if (a === "new") {
      season = { year: (season.year || 1) + 1, week: 0, results: [] };
      saveSeason(); location.reload();
    }
  }
  var down = false;
  function onDown(e) {
    e.preventDefault();
    var pt = toLogical(e);
    var b = hitButton(pt);
    if (b) { act(b.act); return; }
    if (G.mode === "oppdrive") { G.cardT = 0; return; }
    if (G.mode === "presnap") { if (pt.y > FIELD_TOP && pt.y < FIELD_BOT) snapBall(); return; }
    if (G.mode !== "play") return;
    down = true;
    if (carrier === qb && isPass()) aim = { x0: pt.x, y0: pt.y, x: pt.x + camX, y: pt.y };
    else steer = { x0: pt.x, y0: pt.y, x: pt.x, y: pt.y };
  }
  function onMove(e) {
    if (!down) return;
    e.preventDefault();
    var pt = toLogical(e);
    if (aim) {
      // throw vector: from the QB, in the direction and distance of the drag
      var dx = (pt.x - aim.x0) * 1.6, dy = (pt.y - aim.y0) * 1.6;
      aim.x = qb.x + dx; aim.y = qb.y + dy; aim.snap = null;
      // assist: if the aim is near where a receiver WILL be, throw to him
      var best = null, bd = ASSIST_R;
      receivers().forEach(function (r) {
        var T = Math.max(0.35, dist(qb, r) / 150);
        var pr = projectReceiver(r, T);
        var q = dist(pr, { x: aim.x, y: aim.y });
        if (q < bd) { bd = q; best = { p: r, x: pr.x, y: pr.y }; }
      });
      if (best) { aim.snap = best.p; aim.x = best.x; aim.y = best.y; }
    } else if (steer) { steer.x = pt.x; steer.y = pt.y; }
    else if (carrier && carrier !== qb) steer = { x0: pt.x, y0: pt.y, x: pt.x, y: pt.y };
  }
  function onUp(e) {
    if (!down) return;
    down = false;
    if (aim && carrier === qb) {
      var dx = aim.x - qb.x, dy = aim.y - qb.y;
      if (Math.sqrt(dx * dx + dy * dy) > 8) throwBall(aim.x, aim.y, aim.snap);
    }
    aim = null; steer = null;
  }
  canvas.addEventListener("mousedown", onDown);
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  canvas.addEventListener("touchstart", onDown, { passive: false });
  canvas.addEventListener("touchmove", onMove, { passive: false });
  canvas.addEventListener("touchend", onUp);
  canvas.addEventListener("touchcancel", onUp);

  // ------------------------------------------------------------ main loop
  var last = performance.now();
  function frame(now) {
    var dt = Math.min(0.05, (now - last) / 1000); last = now;
    try {
      runTimers(dt);
      update(dt);
      presnapCamera();
      render();
    } catch (e) {
      // one bad frame must never end the game; say so and keep going
      if (window.console && console.error) console.error("bowl:", e);
    }
    requestAnimationFrame(frame);
  }
  // initial camera at the ball
  camX = clamp(yardToPx(G.spot) - 130, 0, yardToPx(110) - W);
  if (seasonOver) {
    G.mode = "recap";
  } else {
    enterPresnap();
    var rec0 = seasonRecord();
    G.banner = (isRivalry(week) ? "THE RIVALRY: " : "WEEK " + (week + 1) + ": ")
             + (opp.home ? "vs " : "at ") + (opp.name || "OPPONENT").toUpperCase()
             + (season.results.length ? "  (" + rec0.text + ")" : "");
    G.bannerT = 2.6;
  }
  window.__bowl = G;   // read-only peek for playtests
  window.__bowlTeam = { key: teamKey, color: colorFor, rating: ratingFor, opp: { color: oppColor, rating: oppRating } };
  window.__bowlPeek = function () { return { players: players, qb: qb, camX: camX, carrier: carrier, mode: G.mode, playT: playT, myDef: myDef, offered: offered.map(function (o) { return o.name; }) }; };
  requestAnimationFrame(frame);
})();
