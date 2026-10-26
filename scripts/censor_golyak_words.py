#!/usr/bin/env python3
"""Mask selected spoken words only in the on-screen subtitle timeline.
Keep the exact word intervals and copy the original soundtrack unchanged."""
import json
from pathlib import Path

p = Path("scripts/golyak_reviewed_words.json")
rows = json.loads(p.read_text(encoding="utf8"))
assert len(rows) == 74, f"Unexpected subtitle alignment count: {len(rows)}"
# These are verified by index against the versioned 74-word transcript.
mask = [10, 19, 23, 30, 49, 54, 58, 61]
for i in mask:
    w = rows[i]["word"]
    ending = w[-1] if w[-1] in ",.!?" else ""
    rows[i]["word"] = "******" + ending
assert sum("******" in w["word"] for w in rows) == len(mask)
assert rows[0]["word"].lower().startswith("смотрите")
assert rows[-1]["word"].lower().startswith("перехват")
p.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf8")
print("CENSORED_TEXT_ONLY", len(mask), "words, timestamps unchanged", flush=True)
