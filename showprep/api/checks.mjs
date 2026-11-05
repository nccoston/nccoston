// Deterministic checks on an episode file (renderer format). No API calls, no cost.
// Used by the eval as graders, and usable on any week's output as a pre-flight check.
//
// The headline rule: no invented numbers. Every number of two or more digits, and every
// decimal, in the script must appear somewhere in the fact pack or the show file.
// Known gap: single-digit integers are skipped, because they are too common to match
// meaningfully ("4th down", "2 interceptions"). The judge, when added, covers those.

const NUM = /\d+(?:\.\d+)?/g;

function normalize(s) {
  return String(s ?? '')
    .replace(/[−‒–—]/g, '-') // minus, figure dash, en dash, em dash
    .replace(/,(?=\d{3}\b)/g, '');              // 1,000 -> 1000
}

export function numbersIn(text) {
  const out = [];
  for (const m of normalize(text).matchAll(NUM)) {
    const t = m[0];
    if (!t.includes('.') && t.length < 2) continue;
    out.push(t.replace(/^0+(?=\d)/, ''));
  }
  return out;
}

/** All script text that a host would read, excluding computed meta and timing lines. */
export function scriptText(ep) {
  const parts = [];
  const blockText = b => b.bullets ? b.bullets.join('\n')
    : b.table ? [...b.table.head, ...b.table.rows.flat()].join('\n')
    : Object.values(b).join('\n');
  const e = ep.episode || {};
  parts.push(e.intro, e.spine, e.cohost_job, e.before_you_record);
  for (const p of ep.parts || []) {
    for (const b of p.blocks || []) parts.push(blockText(b));
    for (const c of p.cards || []) {
      parts.push(c.title, c.deck?.title, c.deck?.stat, c.deck?.stat_label, ...(c.deck?.points || []));
      for (const b of c.blocks || []) parts.push(blockText(b));
    }
  }
  const cb = ep.cohost_brief || {};
  parts.push(cb.job, cb.one_number, ...(cb.numbers || []), ...(cb.pushback || []).flat());
  for (const c of ep.confirm || []) parts.push(c.item, c.detail);
  return parts.filter(Boolean).join('\n');
}

export function supportCorpus(facts, show) {
  return normalize(JSON.stringify(facts) + '\n' + JSON.stringify(show));
}

export function numberSupport(ep, facts, show) {
  const corpus = new Set(numbersIn(supportCorpus(facts, show)));
  const found = numbersIn(scriptText(ep));
  const unsupported = [...new Set(found.filter(n => !corpus.has(n)))];
  return { total: found.length, unsupported, share: found.length ? 1 - found.filter(n => !corpus.has(n)).length / found.length : 1 };
}

export function confirmCoverage(ep, mustConfirm = []) {
  if (!mustConfirm.length) return { share: 1, missing: [] };
  const list = normalize((ep.confirm || []).map(c => `${c.item} ${c.detail}`).join('\n')).toLowerCase();
  const missing = mustConfirm.filter(m => !m.any.some(k => list.includes(k.toLowerCase())));
  return { share: 1 - missing.length / mustConfirm.length, missing: missing.map(m => m.label) };
}

export function guardrails(ep, mustNotContain = []) {
  const text = normalize(JSON.stringify(ep)).toLowerCase();
  const hits = mustNotContain.filter(s => text.includes(normalize(s).toLowerCase()));
  return { ok: hits.length === 0, hits };
}

export function structure(ep, targetMinutes) {
  const problems = [];
  const cards = (ep.parts || []).flatMap(p => p.cards || []);
  if (cards.length < 10 || cards.length > 14) problems.push(`${cards.length} cards (want 10 to 14)`);
  if (!ep.confirm?.length) problems.push('no confirm list');
  if (!ep.sources?.length) problems.push('no sources');
  if (JSON.stringify(ep).includes('—')) problems.push('em dash');
  cards.forEach((c, i) => {
    const kinds = (c.blocks || []).map(b => Object.keys(b)[0]);
    if (!kinds.some(k => k === 'lead' || k === 'p')) problems.push(`card ${c.n}: no lead beat`);
    if (i < cards.length - 1 && !kinds.includes('handoff')) problems.push(`card ${c.n}: no handoff`);
  });
  const m = String(targetMinutes || '').match(/(\d+)\D+(\d+)/);
  if (m) {
    const total = cards.reduce((s, c) => s + (+c.minutes || 0), 0);
    const lo = +m[1] * 0.8, hi = +m[2] * 1.1; // talk segments without cards take time too
    if (total < lo || total > hi) problems.push(`card minutes total ${total} outside ${lo}-${hi}`);
  }
  return { ok: problems.length === 0, problems };
}

/** Every metric the eval reports, as numbers, plus explanations. */
export function gradeEpisode(ep, { facts, show, expect = {} }) {
  if (!ep) return { grade: { no_invented_numbers: 0, number_support: 0, confirm_coverage: 0, guardrails: 0, structure: 0 },
                    explanation: { no_invented_numbers: 'no episode' } };
  const ns = numberSupport(ep, facts, show);
  const cc = confirmCoverage(ep, expect.must_confirm);
  const gr = guardrails(ep, expect.must_not_contain);
  const st = structure(ep, show.target_minutes);
  return {
    grade: {
      no_invented_numbers: ns.unsupported.length === 0 && ns.total > 0 ? 1 : 0,
      number_support: +ns.share.toFixed(3),
      confirm_coverage: +cc.share.toFixed(3),
      guardrails: gr.ok ? 1 : 0,
      structure: st.ok ? 1 : 0,
    },
    explanation: {
      no_invented_numbers: ns.total === 0 ? 'no numbers found' : ns.unsupported.length ? `not in the fact pack: ${ns.unsupported.join(', ')}` : `all ${ns.total} numbers traced to the fact pack`,
      number_support: `${ns.total} numbers checked`,
      confirm_coverage: cc.missing.length ? `missing from confirm list: ${cc.missing.join('; ')}` : 'all required items on the confirm list',
      guardrails: gr.ok ? 'none of the forbidden strings appear' : `contains: ${gr.hits.join(', ')}`,
      structure: st.ok ? 'ok' : st.problems.join('; '),
    },
  };
}
