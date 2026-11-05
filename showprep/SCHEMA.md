# Episode file

One JSON file per episode. `render/render.mjs` refuses a file with no confirm list, no sources or an em dash.
`examples/michigan-weekly-indiana-rutgers.json` is a complete one.

```text
show          name, team, hosts [{name, role: "lead" | "cohost"}], colors {ink, accent} (optional)
episode       title, meta (one line under the title), intro, spine, cohost_job, before_you_record
parts[]       title
              blocks[]   optional; a talk segment with no cards
              cards[]    n, title, minutes, grade (optional), heart (optional label)
                         deck {title, stat, stat_label, points[]}   optional; what the graphic shows
                         blocks[]                                    the script
cohost_brief  job, numbers[], pushback [[claim, response]], one_number
timing        one paragraph
confirm[]     {item, detail}
sources[]     {title, url}
```

Blocks, in any order inside a card:

| Block | Renders as |
|---|---|
| `{"lead": "..."}` | **Lead host:** text |
| `{"cohost": "..."}` | **Co-host:** text |
| `{"say": "..."}` | a quoted line for the host to say |
| `{"bullets": ["...", "..."]}` | a list |
| `{"p": "..."}` | a plain paragraph |
| `{"table": {"head": [...], "rows": [[...]]}}` | a table |
| `{"handoff": "..."}` | **Handoff (lead host):** "text" |

Inline text supports `**bold**` (numbers to say out loud), `*italic*` and `[text](url)`.

If a card has no `deck`, its graphic uses the card title and the first four lines of its script.
