# The weekly run

These are the instructions an agent follows to build one episode's prep for one show. A run starts after the
game and ends with three files in the host's hands: the talk track (PDF), the deck (one HTML file, no
JavaScript) and the card graphics (1920x1080 JPGs).

The model for every run is the Michigan Weekly prep in `examples/`. Read it first. Match its density: every
card carries real numbers and a line the host can say out loud, plus a cue for the co-host and a handoff into the
next card.

## Inputs

A show file in `shows/<slug>.json`:

```json
{
  "slug": "example-show",
  "team": "Penn State",
  "show": { "name": "Show name", "hosts": [{ "name": "Host A", "role": "lead" }, { "name": "Host B", "role": "cohost" }],
            "colors": { "ink": "#041E42", "accent": "#FFFFFF" } },
  "target_minutes": "45–55",
  "records": "Monday night",
  "avoid_sources": [],
  "notes": "Anything the hosts have asked for: segments they always run, running jokes, a prediction tracker."
}
```

When the show is a prospect and its host names are unknown, use the names from the show's own feed or site. If they
can't be found, use "Host A" and "Host B" and say so in the delivery note.

## Step 1. Facts first, all of them sourced

Collect these before writing a word of the script.

**The last game:** final score; the scoring summary, one line per score; team totals (yards, rushing, passing,
turnovers, third down); individual lines that decided it; the two or three sequences people will talk about,
told play by play; the head coach's postgame words, verbatim and linked; injuries.

**The next game:** opponent record and every result so far; opponent strengths and weaknesses as numbers;
the line and total, with the book or outlet and the date read; kickoff time and TV; series history.

**The season:** record overall and in conference; the show's own running storylines if they're public
(episode titles and descriptions are fair game); what's left on the schedule.

Rules:
- Every number in the episode traces to a source in `sources`. No number without a source, ever.
- A number goes on the **confirm list** when it has only one source, when two sources disagree (say which says what),
  or when it can change before recording (lines, injuries, kickoff times, depth charts).
- Quotes are verbatim and linked, or they are not used. Never paraphrase a coach inside quote marks.
- Prior picks or predictions are read back only if they are on the record publicly. Never invent them; if the
  show keeps a tracker you can't see, leave a line on the confirm list asking the host to read their own back.
- Respect `avoid_sources`.

## Step 2. The shape

- One **spine**: a single sentence the lead host says once at the top, in their voice, that the whole episode hangs on.
- **Parts**: postgame cards, then an optional talk segment with no graphic for anything opinion-heavy (the hosts
  decide whether to air it), then the preview cards, then picks.
- **10 to 14 cards.** Each card is one idea, 2 to 5 minutes. Each card has:
  - the lead host's beat, with the numbers to say out loud in **bold**
  - one quotable line, in the host's register (plain, specific, funny only because the facts are)
  - a co-host cue: a reaction, a counterpoint, or a line to land
  - a handoff sentence into the next card
- Unit grades (A to F) are proposals, labeled as such in the intro.
- One card marked as the heart of the episode.
- A picks card at the end that sets up next week's read-back.

## Step 3. The co-host brief

The co-host's job this week in one line; seven or so numbers to memorize; pushback positions as
claim-and-response pairs for the argument the episode is most likely to have; a suggested one-number pick.

## Step 4. Timing, confirm list, sources

Timing per part against `target_minutes`, plus what to cut first if it runs long. The confirm list, most
important first. Sources as titled links.

## Step 5. Voice

Plain and concrete. Short sentences. Real names, real numbers, real places. No em dashes. No marketing words. No
"let's dive in". Humor comes from the facts, never from jokes pasted on. Write it to be read aloud.

## Step 6. Build and check

1. Write `episode.json` following `SCHEMA.md` into a working folder outside the repo (for example
   `$TMPDIR/showprep/<slug>/<date>/`). Prospect prep is never committed: this repository is public.
2. `cd showprep/render && npm install && node render.mjs <episode.json> <out-dir> --jpg`
3. Open the PDF page count and look at three card JPGs. Fix anything that overflows or reads badly, and re-render.
4. Re-check the ten most important numbers against their sources. Anything shaky goes on the confirm list.

## Step 7. Deliver

Send the PDF, the deck and three representative card JPGs. Then a short message: the show, the game, the spine,
the number of confirm items, and anything you could not find.
