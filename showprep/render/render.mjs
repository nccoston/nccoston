// Show prep renderer.
// Turns one episode file (JSON, see ../SCHEMA.md) into the three things a host actually uses:
//   talk-track.pdf   the lead host's script plus the co-host brief, timing, confirm list and sources
//   deck.html        one self-contained page of cards, no JavaScript, opens in iMessage and Quick Look
//   cards/NN.jpg     1920x1080 graphics, one per card (with --jpg)
//
// Usage: node render.mjs <episode.json> <out-dir> [--jpg]

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const [, , inPath, outArg, ...flags] = process.argv;
if (!inPath || !outArg) {
  console.error('Usage: node render.mjs <episode.json> <out-dir> [--jpg]');
  process.exit(2);
}
const ep = JSON.parse(readFileSync(inPath, 'utf8'));
const outDir = resolve(outArg);
mkdirSync(outDir, { recursive: true });

// ---------- checks that keep a bad file from rendering quietly ----------
const problems = [];
if (!ep.show?.name) problems.push('show.name is missing');
if (!ep.show?.hosts?.length) problems.push('show.hosts is empty');
if (!ep.episode?.title) problems.push('episode.title is missing');
if (!Array.isArray(ep.parts) || !ep.parts.length) problems.push('parts is empty');
if (!ep.confirm?.length) problems.push('confirm is empty: every episode ships with a confirm-before-recording list');
if (!ep.sources?.length) problems.push('sources is empty: every number needs a source');
const raw = JSON.stringify(ep);
if (raw.includes('—')) problems.push('contains an em dash (house style: none)');
if (problems.length) {
  console.error('Episode file has problems:\n- ' + problems.join('\n- '));
  process.exit(1);
}

const lead = ep.show.hosts.find(h => h.role === 'lead') || ep.show.hosts[0];
const cohost = ep.show.hosts.find(h => h !== lead);
const C = {
  ink: '#00274C', accent: '#FFCB05', body: '#1E2B3A', muted: '#5B6B7C', rule: '#D8DEE6', heart: '#7A3E00',
  ...(ep.show.colors || {}),
};

// ---------- fonts, embedded so every file stands alone ----------
function font(pkg, file) {
  const p = require.resolve(`${pkg}/files/${file}`);
  return readFileSync(p).toString('base64');
}
const FONTS = `
@font-face{font-family:Anton;src:url(data:font/woff2;base64,${font('@fontsource/anton', 'anton-latin-400-normal.woff2')}) format('woff2');font-weight:400}
@font-face{font-family:Barlow;src:url(data:font/woff2;base64,${font('@fontsource/barlow-semi-condensed', 'barlow-semi-condensed-latin-400-normal.woff2')}) format('woff2');font-weight:400}
@font-face{font-family:Barlow;src:url(data:font/woff2;base64,${font('@fontsource/barlow-semi-condensed', 'barlow-semi-condensed-latin-400-italic.woff2')}) format('woff2');font-weight:400;font-style:italic}
@font-face{font-family:Barlow;src:url(data:font/woff2;base64,${font('@fontsource/barlow-semi-condensed', 'barlow-semi-condensed-latin-600-normal.woff2')}) format('woff2');font-weight:600}
@font-face{font-family:Barlow;src:url(data:font/woff2;base64,${font('@fontsource/barlow-semi-condensed', 'barlow-semi-condensed-latin-700-normal.woff2')}) format('woff2');font-weight:700}
`;

// ---------- text ----------
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
// **bold**, *italic*, [text](url). Nothing else.
const md = s => esc(s)
  .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2">$1</a>')
  .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
  .replace(/\*([^*]+)\*/g, '<i>$1</i>');
const q = s => `“${md(s)}”`;

// ---------- talk track ----------
function block(b) {
  if (b.lead !== undefined) return `<p><b>${esc(lead.name)}:</b> ${md(b.lead)}</p>`;
  if (b.p !== undefined) return `<p>${md(b.p)}</p>`;
  if (b.say !== undefined) return `<p class="say">${q(b.say)}</p>`;
  if (b.bullets) return `<ul>${b.bullets.map(x => `<li>${md(x)}</li>`).join('')}</ul>`;
  if (b.cohost !== undefined) return `<p><b>${esc(cohost?.name || 'Co-host')}:</b> ${md(b.cohost)}</p>`;
  if (b.handoff !== undefined) return `<p class="handoff"><b>Handoff (${esc(lead.name)}):</b> ${q(b.handoff)}</p>`;
  if (b.table) return `<table><thead><tr>${b.table.head.map(h => `<th>${md(h)}</th>`).join('')}</tr></thead><tbody>${
    b.table.rows.map(r => `<tr>${r.map(c => `<td>${md(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  throw new Error('Unknown block: ' + JSON.stringify(b).slice(0, 80));
}

function cardHead(c) {
  const bits = [`CARD ${c.n}`, esc(c.title).toUpperCase()];
  if (c.grade) bits[1] += `: ${esc(c.grade)}`;
  let h = `${bits[0]} – ${bits[1]}`;
  if (c.minutes) h += ` · ${c.minutes} MIN`;
  if (c.heart) h += ` · <span class="heart">${esc(c.heart)}</span>`;
  return `<h3>${h}</h3>`;
}

function talkTrack() {
  const e = ep.episode;
  const parts = ep.parts.map(p => {
    const head = `<h2>${esc(p.title).toUpperCase()}</h2>`;
    const notes = (p.blocks || []).map(block).join('');
    const cards = (p.cards || []).map(c => `<section class="card">${cardHead(c)}${(c.blocks || []).map(block).join('')}</section>`).join('');
    return head + notes + cards;
  }).join('');

  const cb = ep.cohost_brief;
  const brief = cb ? `
    <h2>${esc(cohost?.name || 'Co-host').toUpperCase()} BRIEF</h2>
    ${cb.job ? `<p><b>Your job:</b> ${md(cb.job)}</p>` : ''}
    ${cb.numbers?.length ? `<h4>Numbers to memorize</h4><ul>${cb.numbers.map(x => `<li>${md(x)}</li>`).join('')}</ul>` : ''}
    ${cb.pushback?.length ? `<h4>Pushback positions</h4><ul>${cb.pushback.map(([a, b]) => `<li><i class="claim">“${md(a)}”</i> → ${md(b)}</li>`).join('')}</ul>` : ''}
    ${cb.one_number ? `<p><b>Suggested one-number:</b> ${md(cb.one_number)}</p>` : ''}` : '';

  const timing = ep.timing ? `<h2>TIMING</h2><p>${md(ep.timing)}</p>` : '';
  const confirm = `<h2>CONFIRM BEFORE RECORDING</h2><ul>${ep.confirm.map(c => `<li><b>${md(c.item)}.</b> ${md(c.detail || '')}</li>`).join('')}</ul>`;
  const sources = `<h2>SOURCES</h2><ul class="sources">${ep.sources.map(s => `<li><a href="${esc(s.url)}">${esc(s.title)}</a></li>`).join('')}</ul>`;

  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(e.title)}</title><style>${FONTS}
  @page{size:Letter;margin:0.7in 0.75in}
  *{box-sizing:border-box}
  body{font-family:Barlow,system-ui,sans-serif;color:${C.body};font-size:11.5pt;line-height:1.42;margin:0}
  h1,h2,h3{font-family:Anton,Impact,sans-serif;font-weight:400;color:${C.ink};letter-spacing:.005em;margin:0}
  h1{font-size:25pt;line-height:1.08;padding-bottom:6pt;border-bottom:4pt solid ${C.accent};margin-bottom:10pt}
  h2{font-size:22pt;padding-bottom:4pt;border-bottom:4pt solid ${C.accent};margin:20pt 0 10pt;break-after:avoid}
  h3{font-size:14.5pt;margin:16pt 0 6pt;break-after:avoid}
  h4{font-family:Barlow;font-weight:700;color:${C.ink};font-size:12pt;margin:12pt 0 4pt}
  .meta{color:${C.muted};font-weight:600;margin:0 0 10pt}
  p{margin:0 0 7pt} ul{margin:0 0 8pt;padding-left:17pt} li{margin:0 0 3pt}
  b{font-weight:700;color:${C.ink}}
  .heart{font-style:italic;color:${C.heart};text-transform:uppercase}
  .say{margin-left:0}
  .claim{color:${C.heart}}
  table{border-collapse:collapse;width:100%;margin:6pt 0 10pt;font-size:10.5pt;break-inside:avoid}
  th{background:${C.ink};color:${C.accent};text-align:left;padding:5pt 7pt;font-weight:700}
  td{padding:5pt 7pt;border-bottom:1px solid ${C.rule};vertical-align:top}
  a{color:#0B57A8;text-decoration:none}
  .card{break-inside:auto}
  </style></head><body>
  <h1>${esc(e.title).toUpperCase()}</h1>
  <p class="meta">${md(e.meta || '')}</p>
  ${e.intro ? `<p>${md(e.intro)}</p>` : ''}
  ${e.spine ? `<p><b>Spine (say it once, at the top):</b> ${q(e.spine)}</p>` : ''}
  ${e.cohost_job ? `<p><b>${esc(cohost?.name || 'Co-host')}'s job this week:</b> ${md(e.cohost_job)}</p>` : ''}
  ${e.before_you_record ? `<p><b>Before you record:</b> ${md(e.before_you_record)}</p>` : ''}
  ${parts}${brief}${timing}${confirm}${sources}
  </body></html>`;
}

// ---------- deck: cards sized by container units so one design serves phone, laptop and 1920x1080 ----------
function allCards() {
  return ep.parts.flatMap(p => (p.cards || []).map(c => ({ ...c, part: p.title })));
}
function textOf(b) {
  return b.bullets ? b.bullets : b.lead ? [b.lead] : b.say ? [`“${b.say}”`] : [];
}
function slide(c) {
  const d = c.deck || {};
  const points = (d.points || (c.blocks || []).flatMap(textOf)).slice(0, 4);
  const grade = c.grade ? `<div class="grade">${esc(c.grade)}</div>` : '';
  return `<section class="slide"><div class="in">
    <div class="eyebrow">${esc(c.part || '').toUpperCase()} · CARD ${c.n}</div>
    <div class="top"><h2>${esc(d.title || c.title).toUpperCase()}</h2>${grade}</div>
    ${d.stat ? `<div class="stat">${esc(d.stat)}${d.stat_label ? `<span>${md(d.stat_label)}</span>` : ''}</div>` : ''}
    <ul>${points.map(x => `<li>${md(x)}</li>`).join('')}</ul>
    <div class="foot">${esc(ep.show.name).toUpperCase()}</div>
  </div></section>`;
}
const SLIDE_CSS = `
  .slide{container-type:inline-size;width:100%;aspect-ratio:16/9;background:${C.ink};color:#fff;position:relative;overflow:hidden}
  .slide .in{position:absolute;inset:0;padding:5cqw 6cqw 4cqw;display:flex;flex-direction:column}
  .slide .in::before{content:"";position:absolute;left:0;top:0;bottom:0;width:1.2cqw;background:${C.accent}}
  .eyebrow{font-family:Barlow;font-weight:700;letter-spacing:.14em;color:${C.accent};font-size:1.5cqw}
  .top{display:flex;align-items:flex-start;justify-content:space-between;gap:3cqw;margin-top:1.2cqw}
  .slide h2{font-family:Anton,Impact,sans-serif;font-weight:400;font-size:5.4cqw;line-height:1.02;margin:0;max-width:78cqw}
  .grade{font-family:Anton;font-size:7cqw;line-height:1;color:${C.ink};background:${C.accent};padding:.6cqw 2cqw;border-radius:.6cqw}
  .stat{font-family:Anton;font-size:9cqw;line-height:1;color:${C.accent};margin-top:2.2cqw}
  .stat span{display:block;font-family:Barlow;font-weight:600;font-size:1.9cqw;color:#fff;opacity:.85;margin-top:.6cqw}
  .slide ul{list-style:none;margin:auto 0 0;padding:0;display:grid;gap:1.1cqw}
  .slide li{font-family:Barlow;font-size:2.3cqw;line-height:1.25;padding-left:2.2cqw;position:relative}
  .slide li::before{content:"";position:absolute;left:0;top:.75cqw;width:.9cqw;height:.9cqw;background:${C.accent}}
  .slide li b{color:${C.accent};font-weight:700}
  .foot{font-family:Barlow;font-weight:700;letter-spacing:.14em;font-size:1.2cqw;opacity:.6;margin-top:2cqw}
`;
function deck() {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${esc(ep.episode.title)}: deck</title><style>${FONTS}
  body{margin:0;background:#0b1622;font-family:Barlow,system-ui,sans-serif}
  main{max-width:1200px;margin:0 auto;padding:16px;display:grid;gap:16px}
  ${SLIDE_CSS}</style></head><body><main>${allCards().map(slide).join('')}</main></body></html>`;
}
function single(c) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${FONTS}body{margin:0;width:1920px;height:1080px}${SLIDE_CSS}</style></head><body>${slide(c)}</body></html>`;
}

// ---------- write ----------
const tt = talkTrack();
writeFileSync(join(outDir, 'talk-track.html'), tt);
writeFileSync(join(outDir, 'deck.html'), deck());

const { chromium } = require('playwright');
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.setContent(tt, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({ path: join(outDir, 'talk-track.pdf'), format: 'Letter', printBackground: true, preferCSSPageSize: true });

  if (flags.includes('--jpg')) {
    mkdirSync(join(outDir, 'cards'), { recursive: true });
    await page.setViewportSize({ width: 1920, height: 1080 });
    for (const c of allCards()) {
      await page.setContent(single(c), { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: join(outDir, 'cards', `${String(c.n).padStart(2, '0')}.jpg`), type: 'jpeg', quality: 92 });
    }
  }
} finally {
  await browser.close();
}
console.log(`Rendered ${allCards().length} cards to ${outDir}`);
