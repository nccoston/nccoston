# Show Prep

Weekly prep for team podcasts, built by an agent the night after the game and ready before the hosts sit down
to record. One run gives the hosts:

- **a talk track** (PDF): card by card, with the numbers to say out loud, the lead host's lines, cues for the
  co-host and the handoffs; then the co-host's brief, timing, a confirm-before-recording list and every source
- **a deck** (one HTML file, no JavaScript): the cards on screen, so it opens from a text message
- **graphics**: one 1920x1080 JPG per card, ready for video or social

It started as the prep for [Michigan Weekly](examples/michigan-weekly-indiana-rutgers.json), which I co-host on
Blue By Ninety. The example is a real episode's prep, rebuilt as data.

## How it works

| Piece | What it is |
|---|---|
| `PIPELINE.md` | The instructions the agent follows each week: facts first, every number sourced, the shape of an episode, the voice |
| `SCHEMA.md` | The episode file the agent writes |
| `render/` | Turns an episode file into the PDF, the deck and the JPGs |
| `shows/` | One small file per show: team, hosts, colors, what to avoid |
| `examples/` | A finished episode file to measure every run against |

Render the example:

```bash
cd showprep/render && npm install && node render.mjs ../examples/michigan-weekly-indiana-rutgers.json /tmp/prep --jpg
```

The example's source links point at each publication's home page; the original prep linked the articles.

## The accuracy rule

Every number traces to a source. Anything with one source, two sources that disagree, or a value that can move
before recording (lines, injuries, kickoff times) goes on the confirm list, so the hosts check it before they say
it. The renderer refuses an episode with no confirm list or no sources.
