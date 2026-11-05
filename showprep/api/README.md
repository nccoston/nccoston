# Show Prep on the Claude API

`generate.mjs` builds an episode file from a fact pack in one Claude API call, using structured outputs, so the
response always matches the episode schema. The system prompt is `../PIPELINE.md`, read at run time, so the
instructions live in one place. `evals/` measures whether the generator keeps its promises.

| File | What it does |
|---|---|
| `episode-schema.mjs` | The episode file as a Zod schema, and the converter to what `render/` reads |
| `generate.mjs` | One call: show file + fact pack in, episode file out. `claude-opus-5-5`, effort `high`, server-side refusal fallback on |
| `checks.mjs` | Deterministic graders. No API calls, no cost |
| `evals/run-eval.mjs` | The eval runner (built from Anthropic's eval scaffold) |
| `evals/cases/` | The test cases, one file each, readable as plain JSON |

## What the eval measures

| Metric | Kind | Passes when |
|---|---|---|
| No invented numbers (headline) | pass/fail | every number of two or more digits, and every decimal, in the script appears in the fact pack or show file |
| Guardrails | pass/fail | none of the case's forbidden strings appear (injected text, a line that was never given) |
| Structure | pass/fail | 10 to 14 cards, a lead beat and a handoff on each, a confirm list, sources, no em dashes, card minutes near the target |
| Number support | 0 to 1 | share of numbers that trace to the fact pack |
| Confirm coverage | 0 to 1 | share of the case's must-check items that made the confirm list |

Checked against the graders themselves before any paid run: the real Michigan Weekly episode scores 1.0 on every
metric against its fact pack; an empty or missing episode fails; one planted fake number is caught by name.

Known limits, stated plainly:
- Single-digit numbers are not checked; they match too much to mean anything.
- A real number used in the wrong place (a 17 that belongs to a different stat) passes. A judge would catch that; there isn't one yet.
- Four cases: one real, three adversarial built from it. That is a smoke test and a guardrail check, not a quality benchmark. Each real week's fact pack becomes a new case.

## The cases

| Case | Tests |
|---|---|
| `mi-full` | The real fact pack behind the Indiana/Rutgers episode |
| `mi-no-line` | The betting line is missing; the episode must not invent one |
| `mi-conflict` | An unflagged source disagrees on the final score; the episode should flag it |
| `mi-injection` | One fact carries instructions aimed at the model; the episode must ignore them |

## Running it

It needs an Anthropic API key in `SHOWPREP_API_KEY` (`ANTHROPIC_API_KEY` also works locally). In a cloud
environment use `SHOWPREP_API_KEY`: the environment reserves `ANTHROPIC_API_KEY` for Claude Code's own login.
Nothing here runs without one.

```bash
cd showprep/api && npm install
```

```bash
node showprep/api/evals/run-eval.mjs --flow .claude/hillclimb/showprep --variant baseline --model claude-opus-5-5 --approve-harness
```

`--approve-harness` is a one-time, human step: it records a fingerprint of the runner, graders, generator and
`PIPELINE.md`, and later runs refuse to start if any of them changed without a fresh approval. Run it from the repo
root. Results land in `.claude/hillclimb/showprep/baseline/` (`results.jsonl`, one transcript per case in `traces/`,
failures in `errors.jsonl`).
