#!/usr/bin/env python3
"""Write the board's running log — one line per change, from git — to
app/changelog.json, which /stats shows to the members.

The server can't read git itself (Render builds from app/ alone), so this
runs before a push. Subject lines only: bodies are for whoever reads the
code, and trailers never leave the repository.
"""
import json, subprocess, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BOARD = Path(__file__).resolve().parents[1]      # victors-board/
ROOT = BOARD.parent                              # the repository
OUT = BOARD / "app" / "changelog.json"
SINCE = "2026-08-03"                       # the day the board went up
TZ = ZoneInfo("America/Detroit")

raw = subprocess.check_output(
    ["git", "log", f"--since={SINCE}", "--format=%aI%x1f%s", "--", "victors-board"],
    cwd=ROOT, text=True)
SKIP = {"Add files via upload"}                  # GitHub's words, not ours

entries = []
for line in raw.splitlines():
    when, _, subject = line.partition("\x1f")
    subject = subject.strip()
    if subject in SKIP:
        continue
    day = datetime.fromisoformat(when).astimezone(TZ).strftime("%Y-%m-%d")
    entries.append({"day": day, "what": subject})
OUT.write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n")
if not entries:
    sys.exit("no entries — is this being run inside the repository?")
print(f"{len(entries)} entries -> {OUT.relative_to(ROOT)}")
