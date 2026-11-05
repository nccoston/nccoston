// The episode file as a Zod schema, for structured outputs. The model fills this shape;
// toRenderer() turns it into the format render/render.mjs reads (see ../SCHEMA.md).
// Structured outputs needs every field present, so optional things are nullable.
import { z } from 'zod';

const Block = z.object({
  kind: z.enum(['lead', 'cohost', 'say', 'p', 'bullets', 'handoff', 'table']),
  text: z.string().nullable().describe('For lead, cohost, say, p, handoff. Null for bullets and table.'),
  items: z.array(z.string()).nullable().describe('For bullets only.'),
  table_head: z.array(z.string()).nullable().describe('For table only.'),
  table_rows: z.array(z.array(z.string())).nullable().describe('For table only.'),
});

const Card = z.object({
  n: z.number().int(),
  title: z.string(),
  minutes: z.number(),
  grade: z.string().nullable().describe('A to F for a unit card, else null.'),
  heart: z.string().nullable().describe('Label for the one card that is the heart of the episode, else null.'),
  deck: z.object({
    title: z.string().nullable(),
    stat: z.string().nullable().describe('One big number for the graphic, or null.'),
    stat_label: z.string().nullable(),
    points: z.array(z.string()).describe('Two to four short lines for the graphic.'),
  }),
  blocks: z.array(Block),
});

export const EpisodeSchema = z.object({
  episode: z.object({
    title: z.string(),
    meta: z.string(),
    intro: z.string(),
    spine: z.string(),
    cohost_job: z.string(),
    before_you_record: z.string().nullable(),
  }),
  parts: z.array(z.object({
    title: z.string(),
    blocks: z.array(Block).describe('Only for a talk segment with no cards; else empty.'),
    cards: z.array(Card),
  })),
  cohost_brief: z.object({
    job: z.string(),
    numbers: z.array(z.string()),
    pushback: z.array(z.object({ claim: z.string(), response: z.string() })),
    one_number: z.string(),
  }),
  timing: z.string(),
  confirm: z.array(z.object({ item: z.string(), detail: z.string() })),
  sources: z.array(z.object({ title: z.string(), url: z.string() })),
});

function block(b) {
  switch (b.kind) {
    case 'bullets': return { bullets: b.items ?? [] };
    case 'table': return { table: { head: b.table_head ?? [], rows: b.table_rows ?? [] } };
    default: return { [b.kind]: b.text ?? '' };
  }
}

/** Generated episode + show config -> the file render.mjs reads. */
export function toRenderer(gen, showConfig) {
  const clean = o => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== null && v !== undefined));
  return {
    show: showConfig.show,
    episode: clean(gen.episode),
    parts: gen.parts.map(p => ({
      title: p.title,
      ...(p.blocks?.length ? { blocks: p.blocks.map(block) } : {}),
      cards: p.cards.map(c => clean({
        n: c.n, title: c.title, minutes: c.minutes, grade: c.grade, heart: c.heart,
        deck: clean({ ...c.deck, points: c.deck.points?.length ? c.deck.points : null }),
        blocks: c.blocks.map(block),
      })),
    })),
    cohost_brief: { ...gen.cohost_brief, pushback: gen.cohost_brief.pushback.map(x => [x.claim, x.response]) },
    timing: gen.timing,
    confirm: gen.confirm,
    sources: gen.sources,
  };
}
