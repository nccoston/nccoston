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
  var CATCH_R = 11, TACKLE_R = 5;

  var canvas = document.getElementById("bowl");
  var ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;

  var CFG = window.BOWL || {};
  var schedule = CFG.schedule || [];
  var week = parseInt(load("bowlWeek") || "0", 10);
  if (!schedule.length) schedule = [{ name: "Opponent", abbr: "OPP", home: true }];
  if (week >= schedule.length) week = 0;

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
  function ratingFor(name) {
    var n = (name || "").toLowerCase();
    for (var k in RATINGS) if (n.indexOf(k) !== -1) return RATINGS[k];
    return 0.5;
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
  function colorFor(name) {
    var n = (name || "").toLowerCase();
    for (var k in TEAM_COLORS) if (n.indexOf(k) !== -1) return TEAM_COLORS[k];
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
  var oppRating = ratingFor(opp.name);
  var oppColor = colorFor(opp.name);
  var G = {
    mode: "presnap",       // presnap | play | dead | oppdrive | gameover
    score: [0, 0],         // [Michigan, opponent]
    quarter: 1, clock: QUARTER_SECS,
    spot: 25, down: 1, toGo: 10,   // spot = yards from own goal (0..100)
    play: null,            // "pass" | "run"
    banner: null, bannerT: 0,
    card: null, cardT: 0,  // opponent-drive card
    stats: { yards: 0, tds: 0, longest: 0, ints: 0, sacks: 0 },
    result: null
  };

  var players = [], ball = null, carrier = null, qb = null, camX = 0;
  var aim = null;            // {x0,y0,x,y} while aiming a pass
  var steer = null;          // {x0,y0,x,y} while steering a runner
  var playT = 0;

  // ------------------------------------------------------------ setup a play
  function fieldY(frac) { return FIELD_TOP + (FIELD_BOT - FIELD_TOP) * frac; }

  function setupPlay() {
    players = []; ball = null; carrier = null; aim = null; steer = null; playT = 0;
    var los = yardToPx(G.spot);
    function P(team, role, x, y, spd) {
      var p = { team: team, role: role, x: x, y: y, vx: 0, vy: 0, spd: spd,
                anim: Math.random() * 10, engaged: 0, stun: 0, route: null, t: 0,
                mark: null, zone: null };
      players.push(p); return p;
    }
    // offense (Michigan, drives left -> right)
    qb = P("M", "QB", los - 20, fieldY(0.5), 46);
    var rb = P("M", "RB", los - 28, fieldY(0.56), 58);
    var wrs = [P("M", "WR", los - 2, fieldY(0.12), 62),
               P("M", "WR", los - 2, fieldY(0.88), 62),
               P("M", "WR", los - 8, fieldY(0.30), 60)];
    var ols = [];
    for (var i = 0; i < 5; i++) ols.push(P("M", "OL", los - 4, fieldY(0.38 + i * 0.06), 30));
    // routes
    var ROUTES = ["go", "out", "in", "post", "curl"];
    wrs.forEach(function (w) { w.route = ROUTES[Math.floor(Math.random() * ROUTES.length)]; });
    rb.route = G.play === "pass" ? "flat" : null;
    // defense
    var dls = [];
    for (var j = 0; j < 4; j++) {
      var d = P("O", "DL", los + 5, fieldY(0.36 + j * 0.09), 44);
      d.engaged = rnd(1.4, 3.0) * (1.15 - oppRating * 0.5);   // blocked this long
      dls.push(d);
    }
    var lbs = [P("O", "LB", los + 28, fieldY(0.38), 50), P("O", "LB", los + 28, fieldY(0.62), 50)];
    lbs[0].zone = { x: los + 30, y: fieldY(0.35) }; lbs[1].zone = { x: los + 30, y: fieldY(0.65) };
    wrs.forEach(function (w, k) {
      var cb = P("O", "CB", los + 26, w.y, 58 + oppRating * 8);
      cb.mark = w;
    });
    var s = P("O", "S", los + 60, fieldY(0.5), 56 + oppRating * 6); s.role = "S";
    G.mode = "play";
    ball = { x: qb.x, y: qb.y, z: 0, flying: false, tx: 0, ty: 0, t: 0, dur: 0, holder: qb };
    carrier = qb;
  }

  // route running: returns velocity for a receiver at time t
  function routeVel(p, t) {
    var s = p.spd;
    switch (p.route) {
      case "go":   return { vx: s, vy: 0 };
      case "out":  return t < 0.9 ? { vx: s, vy: 0 } : { vx: s * 0.4, vy: (p.y < H / 2 ? -1 : 1) * s * 0.9 };
      case "in":   return t < 1.1 ? { vx: s, vy: 0 } : { vx: s * 0.5, vy: (p.y < H / 2 ? 1 : -1) * s * 0.85 };
      case "post": return t < 1.2 ? { vx: s, vy: 0 } : { vx: s * 0.8, vy: (p.y < H / 2 ? 1 : -1) * s * 0.5 };
      case "curl": return t < 1.3 ? { vx: s, vy: 0 } : t < 1.7 ? { vx: -s * 0.4, vy: 0 } : { vx: 0, vy: 0 };
      case "flat": return t < 0.5 ? { vx: s * 0.3, vy: (p.y < H / 2 ? -1 : 1) * s * 0.6 } : { vx: s * 0.7, vy: 0 };
    }
    return { vx: 0, vy: 0 };
  }

  // ------------------------------------------------------------ simulation
  function update(dt) {
    if (G.bannerT > 0) { G.bannerT -= dt; if (G.bannerT <= 0) G.banner = null; }
    if (G.mode === "oppdrive") { G.cardT -= dt; if (G.cardT <= 0) endOppDrive(); return; }
    if (G.mode !== "play") return;
    playT += dt;
    var los = yardToPx(G.spot);

    // --- offense ---
    players.forEach(function (p) {
      if (p.team !== "M") return;
      if (p.role === "QB") {
        if (carrier === p) {
          // drop back, then stand in the pocket
          if (playT < 0.5) { p.x -= 30 * dt; }
          if (G.play === "run" && playT > 0.3) {
            // handoff
            var rb = players.filter(function (q) { return q.role === "RB"; })[0];
            carrier = rb; ball.holder = rb;
          }
        }
      } else if (p.role === "RB") {
        if (carrier === p) moveCarrier(p, dt);
        else if (G.play === "run") { // come get the ball
          if (dist(p, qb) > 3) stepToward(p, qb, p.spd * 0.9, dt);
        } else if (p.route) { var v = routeVel(p, playT); p.x += v.vx * dt; p.y += v.vy * dt; }
      } else if (p.role === "WR") {
        if (carrier === p) moveCarrier(p, dt);
        else { var v2 = routeVel(p, playT); p.x += v2.vx * dt; p.y += v2.vy * dt; p.anim += dt * 10; }
      } else if (p.role === "OL") {
        p.x += 6 * dt; // lean forward
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
    players.forEach(function (d) {
      if (d.team !== "O") return;
      if (d.stun > 0) { d.stun -= dt; return; }
      var target = null;
      if (d.role === "DL") {
        if (d.engaged > 0) { d.engaged -= dt; d.x += rnd(-4, 4) * dt; return; }
        target = carrier;
      } else if (d.role === "CB") {
        target = (carrier && carrier !== qb) ? carrier : (ball.flying ? { x: ball.tx, y: ball.ty } : d.mark);
        if (target === d.mark) { // trail the receiver, a step behind
          target = { x: d.mark.x + 6, y: d.mark.y };
        }
      } else if (d.role === "LB") {
        if (carrier && carrier !== qb) target = carrier;
        else if (ball.flying) target = { x: ball.tx, y: ball.ty };
        else if (playT > 2.2 + (1 - oppRating)) target = qb;     // blitz late
        else target = d.zone;
      } else if (d.role === "S") {
        if (carrier && carrier !== qb) target = carrier;
        else if (ball.flying) target = { x: ball.tx, y: ball.ty };
        else { // shade the deepest receiver
          var deep = null;
          players.forEach(function (q) { if (q.team === "M" && q.role === "WR" && (!deep || q.x > deep.x)) deep = q; });
          target = deep ? { x: deep.x + 24, y: (deep.y + H / 2) / 2 } : d;
        }
      }
      if (target) stepToward(d, target, d.spd, dt);
      d.y = clamp(d.y, FIELD_TOP + 2, FIELD_BOT - 2);
      // tackles and sacks
      if (carrier && !ball.flying && dist(d, carrier) < TACKLE_R) {
        if (carrier === qb) { endPlay("sack"); }
        else if (Math.random() < 0.14 * (1 - oppRating * 0.4)) { d.stun = 0.7; } // broke it
        else endPlay("tackle");
      }
    });

    // pocket collapses eventually even if the line holds
    if (carrier === qb && G.play === "pass" && playT > 5.5) endPlay("sack");

    // scoring / boundaries for a live carrier
    if (carrier && !ball.flying && G.mode === "play") {
      if (carrier.x >= yardToPx(100)) endPlay("td");
      else if (carrier !== qb && (carrier.y <= FIELD_TOP + 2 || carrier.y >= FIELD_BOT - 2)) endPlay("oob");
    }
    camX = clamp((ball.x) - 130, 0, yardToPx(110) - W);
  }

  function stepToward(p, t, spd, dt) {
    var dx = t.x - p.x, dy = t.y - p.y, d = Math.sqrt(dx * dx + dy * dy);
    if (d < 0.5) return;
    p.x += dx / d * spd * dt; p.y += dy / d * spd * dt; p.anim += dt * 10;
  }
  function moveCarrier(p, dt) {
    var vx = p.spd, vy = 0;
    if (steer) {
      var dx = steer.x - steer.x0, dy = steer.y - steer.y0, d = Math.sqrt(dx * dx + dy * dy);
      if (d > 4) { vx = dx / d * p.spd; vy = dy / d * p.spd; }
    }
    p.x += vx * dt; p.y += vy * dt; p.anim += dt * 10;
  }

  function throwBall(tx, ty) {
    if (!qb || carrier !== qb || ball.flying) return;
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
      var pInt = dd < 5 ? 0.35 : dd < 10 ? 0.15 : 0.02;
      var pInc = dd < 5 ? 0.40 : dd < 10 ? 0.30 : 0.08;
      if (r < pInt) { endPlay("int", land); return; }
      if (r < pInt + pInc) { endPlay("incomplete"); return; }
      carrier = rcv; ball.holder = rcv; rcv.route = null;
      G.banner = "CAUGHT"; G.bannerT = 0.5;
    } else if (def && dd < 5 && Math.random() < 0.25) {
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
        gain = 100 - spotBefore; text = "TOUCHDOWN!";
        G.score[0] += 7; G.stats.tds++;
        G.stats.longest = Math.max(G.stats.longest, gain);
        G.stats.yards += gain;
        after(1.6, function () { startOppDrive(25); });
        break;
      case "sack":
        gain = -Math.round(rnd(4, 9)); text = "SACK " + gain;
        G.stats.sacks++; nextDown(gain); break;
      case "int":
        text = "INTERCEPTED"; G.stats.ints++;
        var iy = Math.round(clamp(pxToYard(at.x), 1, 99));
        secs = 12;
        after(1.6, function () { startOppDrive(100 - iy); });
        break;
      case "incomplete":
        text = "INCOMPLETE"; secs = 8; nextDown(0); break;
      case "oob":
        secs = 10; /* fallthrough */
      case "tackle":
      default:
        gain = Math.round(endYd - spotBefore);
        if (gain > 0) { G.stats.yards += gain; G.stats.longest = Math.max(G.stats.longest, 0); }
        text = (gain >= 0 ? "+" : "") + gain + " YDS";
        nextDown(gain);
    }
    G.clock -= secs;
    if (text) { G.banner = text; G.bannerT = 1.3; }
    if (G.clock <= 0) { G.clock = 0; tickQuarter(); }
  }

  function nextDown(gain) {
    G.spot = clamp(G.spot + gain, 0, 99.5);
    if (G.spot <= 0.5 && gain < 0) { // safety
      G.score[1] += 2; G.banner = "SAFETY"; G.bannerT = 1.5;
      after(1.6, function () { startOppDrive(35); }); return;
    }
    if (gain >= G.toGo) { G.down = 1; G.toGo = Math.min(10, 100 - G.spot); G.banner = "FIRST DOWN"; }
    else { G.down++; G.toGo -= Math.max(0, gain); if (gain < 0) G.toGo -= gain; }
    if (G.down > 4) { G.banner = "TURNOVER ON DOWNS"; G.bannerT = 1.6;
      after(1.6, function () { startOppDrive(100 - G.spot); }); return; }
    after(1.2, function () { G.mode = "presnap"; });
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
    after(1.5, function () { startOppDrive(oppSpot); });
  }
  function fieldGoal() {
    var yds = 100 - G.spot + 17;
    var p = yds <= 30 ? 0.97 : yds <= 40 ? 0.86 : yds <= 50 ? 0.7 : 0.5;
    G.clock -= 6;
    if (Math.random() < p) { G.score[0] += 3; G.banner = yds + " YD FIELD GOAL — GOOD"; }
    else G.banner = yds + " YD FIELD GOAL — NO GOOD";
    G.bannerT = 1.6; G.mode = "dead";
    var missSpot = clamp(100 - G.spot + 7, 20, 80);
    after(1.7, function () { startOppDrive(G.banner.indexOf("GOOD") !== -1 && G.banner.indexOf("NO") === -1 ? 25 : missSpot); });
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
    G.spot = G.nextSpot || 25; G.down = 1; G.toGo = 10; G.mode = "presnap";
  }

  function finishGame() {
    G.mode = "gameover";
    var w = G.score[0] > G.score[1];
    G.result = w ? "W" : (G.score[0] === G.score[1] ? "T" : "L");
    var rec = JSON.parse(load("bowlRecord") || "[0,0,0]");
    if (G.result === "W") rec[0]++; else if (G.result === "L") rec[1]++; else rec[2]++;
    store("bowlRecord", JSON.stringify(rec)); G.record = rec;
    var best = parseInt(load("bowlLongest") || "0", 10);
    if (G.stats.longest > best) store("bowlLongest", String(G.stats.longest));
    store("bowlWeek", String(week + 1 < schedule.length ? week + 1 : 0));
  }

  // ------------------------------------------------------------ drawing
  function drawField() {
    ctx.fillStyle = "#1c2a1c"; ctx.fillRect(0, 0, W, H);
    // grass stripes, 5-yard bands
    for (var yd = -10; yd < 110; yd += 5) {
      var x = yardToPx(yd) - camX;
      ctx.fillStyle = ((yd / 5) % 2 === 0) ? GRASS_A : GRASS_B;
      ctx.fillRect(x, FIELD_TOP, 5 * PX, FIELD_BOT - FIELD_TOP);
    }
    // endzones
    ctx.fillStyle = BLUE; ctx.fillRect(yardToPx(-10) - camX, FIELD_TOP, 10 * PX, FIELD_BOT - FIELD_TOP);
    ctx.fillStyle = oppColor; ctx.fillRect(yardToPx(100) - camX, FIELD_TOP, 10 * PX, FIELD_BOT - FIELD_TOP);
    ctx.fillStyle = MAIZE; ctx.font = "bold 9px monospace"; ctx.textAlign = "center";
    ctx.save(); ctx.translate(yardToPx(-5) - camX, (FIELD_TOP + FIELD_BOT) / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillText("MICHIGAN", 0, 3); ctx.restore();
    ctx.fillStyle = "#fff";
    ctx.save(); ctx.translate(yardToPx(105) - camX, (FIELD_TOP + FIELD_BOT) / 2); ctx.rotate(Math.PI / 2);
    ctx.fillText(opp.abbr || "OPP", 0, 3); ctx.restore();
    // yard lines + numbers
    ctx.fillStyle = LINE;
    for (var y2 = 0; y2 <= 100; y2 += 5) {
      var lx = yardToPx(y2) - camX;
      ctx.fillRect(lx, FIELD_TOP, 1, FIELD_BOT - FIELD_TOP);
      if (y2 % 10 === 0 && y2 > 0 && y2 < 100) {
        var n = y2 > 50 ? 100 - y2 : y2;
        ctx.font = "7px monospace"; ctx.textAlign = "center";
        ctx.fillText(String(n), lx, FIELD_TOP + 14); ctx.fillText(String(n), lx, FIELD_BOT - 8);
      }
    }
    // hashes
    for (var y3 = 0; y3 <= 100; y3++) {
      var hx = yardToPx(y3) - camX;
      ctx.fillRect(hx, FIELD_TOP + 44, 1, 2); ctx.fillRect(hx, FIELD_BOT - 46, 1, 2);
    }
    // sidelines
    ctx.fillStyle = "#e8e8e8";
    ctx.fillRect(0, FIELD_TOP - 1, W, 2); ctx.fillRect(0, FIELD_BOT - 1, W, 2);
    // line of scrimmage + first-down marker
    if (G.mode === "presnap" || G.mode === "play" || G.mode === "dead") {
      ctx.fillStyle = "rgba(60,120,255,0.75)"; ctx.fillRect(yardToPx(G.spot) - camX, FIELD_TOP, 1, FIELD_BOT - FIELD_TOP);
      ctx.fillStyle = "rgba(255,230,0,0.85)"; ctx.fillRect(yardToPx(Math.min(100, G.spot + G.toGo)) - camX, FIELD_TOP, 1, FIELD_BOT - FIELD_TOP);
    }
  }

  // ------------------------------------------------------------ sprites
  // 8x13 pixel players, baked once per (team, skin, frame, facing) to tiny
  // offscreen canvases. Michigan: winged helmet, navy jersey, maize pants.
  // Opponent: their color with a white helmet stripe and white pants.
  var SPRITE_ROWS = [
    "..HHHH..",
    ".HWWWWH.",
    ".HHHHHF.",
    ".HHHHHF.",
    "...SS...",
    "JJJJJJJ.",
    "JJJJJJJ.",
    ".JJJJJ..",
    ".SJJJS..",
    "..PPP...",
    "..PPP..."
  ];
  var LEG_FRAMES = [
    ["..P.P...", "..K.K..."],   // standing / mid-stride
    [".P...P..", ".K...K.."],   // full stride
    ["..PP....", "..KK...."]    // legs together
  ];
  var SKINS = ["#f1c9a5", "#c68642", "#6b3e22"];
  var spriteCache = {};
  function bakeSprite(team, skin, frame, faceRight) {
    var key = team + skin + frame + (faceRight ? "R" : "L");
    if (spriteCache[key]) return spriteCache[key];
    var c = document.createElement("canvas"); c.width = 8; c.height = 13;
    var g = c.getContext("2d");
    var colors = team === "M"
      ? { H: "#001a38", W: MAIZE, F: "#2a2a2a", S: SKINS[skin], J: BLUE, P: MAIZE, K: "#1a1a1a" }
      : { H: oppColor, W: "#f4f4f4", F: "#2a2a2a", S: SKINS[skin], J: oppColor, P: "#ececec", K: "#1a1a1a" };
    var rows = SPRITE_ROWS.concat(LEG_FRAMES[frame]);
    for (var r = 0; r < rows.length; r++) {
      for (var col = 0; col < 8; col++) {
        var ch = rows[r][col];
        if (ch === ".") continue;
        g.fillStyle = colors[ch];
        g.fillRect(faceRight ? col : 7 - col, r, 1, 1);
      }
    }
    spriteCache[key] = c;
    return c;
  }
  var RUN_CYCLE = [0, 1, 0, 2];

  function drawPlayer(p) {
    var x = Math.round(p.x - camX), y = Math.round(p.y);
    if (p.skin === undefined) p.skin = Math.floor(Math.random() * SKINS.length);
    // facing: carriers by motion, otherwise offense right / defense left
    var faceRight = p.team === "M";
    if (p === carrier && steer) {
      var sdx = steer.x - steer.x0;
      if (Math.abs(sdx) > 4) faceRight = sdx > 0;
    }
    var moving = (p === carrier) || p.team === "O" || (p.route && G.mode === "play");
    var frame = moving ? RUN_CYCLE[Math.floor(p.anim) % 4] : 0;
    // shadow
    ctx.fillStyle = "rgba(0,0,0,0.28)"; ctx.fillRect(x - 3, y + 2, 7, 2);
    ctx.drawImage(bakeSprite(p.team, p.skin, frame, faceRight), x - 4, y - 10);
    if (p === carrier && !ball.flying) {   // marker over the ball carrier
      ctx.fillStyle = MAIZE; ctx.fillRect(x - 1, y - 14, 2, 2); ctx.fillRect(x, y - 13, 1, 1);
    }
  }

  function drawBall() {
    if (!ball) return;
    var x = Math.round(ball.x - camX), y = Math.round(ball.y - (ball.z || 0));
    if (ball.flying) { ctx.fillStyle = "rgba(0,0,0,0.3)"; ctx.fillRect(Math.round(ball.x - camX) - 1, Math.round(ball.y) + 3, 3, 1); }
    ctx.fillStyle = "#8b4a1c"; ctx.fillRect(x - 2, y - 1, 4, 2);
    ctx.fillStyle = "#fff"; ctx.fillRect(x, y - 1, 1, 1);
  }

  function drawHUD() {
    ctx.fillStyle = "#0a0a12"; ctx.fillRect(0, 0, W, FIELD_TOP - 2);
    ctx.font = "bold 9px monospace"; ctx.textAlign = "left";
    ctx.fillStyle = MAIZE; ctx.fillText("MICH " + G.score[0], 4, 9);
    ctx.fillStyle = "#fff"; ctx.fillText((opp.abbr || "OPP") + " " + G.score[1], 4, 18);
    ctx.textAlign = "center";
    ctx.fillStyle = "#ddd"; ctx.fillText("Q" + G.quarter + "  " + fmtClock(G.clock), W / 2, 9);
    if (G.mode !== "gameover" && G.mode !== "oppdrive") {
      var yl = G.spot <= 50 ? "MICH " + Math.round(G.spot) : (opp.abbr || "OPP") + " " + Math.round(100 - G.spot);
      var togo = (G.spot + G.toGo >= 100) ? "GOAL" : Math.round(G.toGo);
      ctx.fillText(ordinal(G.down) + " & " + togo + "  ·  " + yl, W / 2, 18);
    }
    ctx.textAlign = "right"; ctx.fillStyle = "#9aa";
    ctx.fillText("WK " + (week + 1) + "  vs " + (opp.abbr || "OPP"), W - 4, 9);
    ctx.fillStyle = "#777"; ctx.font = "7px monospace";
    ctx.fillText("VICTARD BOWL", W - 4, 17);
  }

  function button(x, y, w, h, label, hot) {
    ctx.fillStyle = hot ? MAIZE : "rgba(0,39,76,0.92)";
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = MAIZE; ctx.lineWidth = 1; ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    ctx.fillStyle = hot ? BLUE : MAIZE; ctx.font = "bold 9px monospace"; ctx.textAlign = "center";
    ctx.fillText(label, x + w / 2, y + h / 2 + 3);
  }
  var BTNS = [];
  function drawOverlay() {
    BTNS = [];
    ctx.textAlign = "center";
    if (G.mode === "presnap") {
      var inRange = (100 - G.spot + 17) <= 55;
      if (G.down === 4) {
        var y = FIELD_BOT + 3;
        BTNS.push({ x: 8, y: y, w: 70, h: 11, label: "PASS", act: "pass" });
        BTNS.push({ x: 86, y: y, w: 70, h: 11, label: "RUN", act: "run" });
        BTNS.push({ x: 164, y: y, w: 70, h: 11, label: "PUNT", act: "punt" });
        if (inRange) BTNS.push({ x: 242, y: y, w: 70, h: 11, label: "FG", act: "fg" });
      } else {
        BTNS.push({ x: 70, y: FIELD_BOT + 3, w: 80, h: 11, label: "PASS", act: "pass" });
        BTNS.push({ x: 170, y: FIELD_BOT + 3, w: 80, h: 11, label: "RUN", act: "run" });
      }
      BTNS.forEach(function (b) { button(b.x, b.y, b.w, b.h, b.label, false); });
    } else if (G.mode === "play") {
      ctx.fillStyle = "rgba(255,255,255,0.7)"; ctx.font = "7px monospace";
      var hint = carrier === qb && G.play === "pass" ? "drag to aim · release to throw"
               : carrier ? "drag to steer" : "";
      ctx.fillText(hint, W / 2, H - 4);
      if (aim && carrier === qb) {
        var ax = clamp(aim.x, qb.x - 10, yardToPx(112)), ay = clamp(aim.y, FIELD_TOP + 1, FIELD_BOT - 1);
        ctx.strokeStyle = "rgba(255,255,255,0.8)"; ctx.setLineDash([2, 2]);
        ctx.beginPath(); ctx.moveTo(qb.x - camX, qb.y); ctx.lineTo(ax - camX, ay); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = MAIZE; ctx.fillRect(ax - camX - 2, ay - 2, 4, 4);
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
      if (G.record) ctx.fillText("Season: " + G.record[0] + "-" + G.record[1] + (G.record[2] ? "-" + G.record[2] : ""), W / 2, 98);
      BTNS.push({ x: 110, y: 118, w: 100, h: 13, label: "NEXT GAME", act: "next" });
      BTNS.forEach(function (b) { button(b.x, b.y, b.w, b.h, b.label, true); });
    }
    if (G.banner && G.bannerT > 0) {
      ctx.fillStyle = "rgba(0,0,0,0.7)"; ctx.fillRect(W / 2 - 90, 74, 180, 22);
      ctx.fillStyle = G.banner.indexOf("TOUCHDOWN") !== -1 || G.banner.indexOf("FIRST") !== -1 ? MAIZE : "#fff";
      ctx.font = "bold 10px monospace"; ctx.textAlign = "center";
      ctx.fillText(G.banner, W / 2, 89);
    }
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
    if (a === "pass" || a === "run") { G.play = a; setupPlay(); }
    else if (a === "punt") { G.mode = "dead"; punt(); }
    else if (a === "fg") { fieldGoal(); }
    else if (a === "next") { location.reload(); }
  }
  var down = false;
  function onDown(e) {
    e.preventDefault();
    var pt = toLogical(e);
    var b = hitButton(pt);
    if (b) { act(b.act); return; }
    if (G.mode === "oppdrive") { G.cardT = 0; return; }
    if (G.mode !== "play") return;
    down = true;
    if (carrier === qb && G.play === "pass") aim = { x0: pt.x, y0: pt.y, x: pt.x + camX, y: pt.y };
    else steer = { x0: pt.x, y0: pt.y, x: pt.x, y: pt.y };
  }
  function onMove(e) {
    if (!down) return;
    e.preventDefault();
    var pt = toLogical(e);
    if (aim) {
      // throw vector: from the QB, in the direction and distance of the drag
      var dx = (pt.x - aim.x0) * 1.6, dy = (pt.y - aim.y0) * 1.6;
      aim.x = qb.x + dx; aim.y = qb.y + dy;
    } else if (steer) { steer.x = pt.x; steer.y = pt.y; }
    else if (carrier && carrier !== qb) steer = { x0: pt.x, y0: pt.y, x: pt.x, y: pt.y };
  }
  function onUp(e) {
    if (!down) return;
    down = false;
    if (aim && carrier === qb) {
      var dx = aim.x - qb.x, dy = aim.y - qb.y;
      if (Math.sqrt(dx * dx + dy * dy) > 8) throwBall(aim.x, aim.y);
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
    runTimers(dt);
    update(dt);
    render();
    requestAnimationFrame(frame);
  }
  // initial camera at the ball
  camX = clamp(yardToPx(G.spot) - 130, 0, yardToPx(110) - W);
  G.banner = "WEEK " + (week + 1) + ": vs " + opp.name.toUpperCase(); G.bannerT = 2.2;
  requestAnimationFrame(frame);
})();
