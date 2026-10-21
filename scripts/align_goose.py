#!/usr/bin/env python3
"""Align the existing verified Russian dialogue to the clip's ACTUAL speech."""
import ast
import json
from pathlib import Path
import whisperx

source = ast.parse(Path("scripts/goose_captions.py").read_text(encoding="utf-8"))
lines = next(ast.literal_eval(node.value) for node in source.body
             if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "lines" for t in node.targets))
audio = whisperx.load_audio("goose_audio.wav")
# Bound each search to its own speech turn: the previous wide, overlapping
# windows caused words from the next/previous line to be matched instead.
segments = []
for i, (a, b, phrase) in enumerate(lines):
    left = max(0.0, a - 0.26)
    right = min(len(audio)/16000, b + (0.60 if i == len(lines) - 1 else 0.28))
    if i:
        left = max(left, lines[i-1][1] + 0.02)
    if i + 1 < len(lines):
        right = min(right, lines[i+1][0] - 0.02)
    if right <= left:
        raise RuntimeError(f"Bad line boundaries: {i} [{left:.2f},{right:.2f}]")
    segments.append({"start": left, "end": right, "text": phrase})
model, meta = whisperx.load_align_model(language_code="ru", device="cpu")
result = whisperx.align(segments, model, meta, audio, "cpu")
timings = []
problems = []
for i, ((old_start, old_end, phrase), aligned) in enumerate(zip(lines, result["segments"])):
    tokens = phrase.split()
    words = aligned.get("words", [])
    if len(words) != len(tokens):
        problems.append(f"line {i}: expected {len(tokens)} words, got {len(words)}: {phrase}")
        continue
    events = []
    for token, entry in zip(tokens, words):
        if "start" not in entry or "end" not in entry or entry["end"] <= entry["start"]:
            problems.append(f"line {i}: unaligned word {token}: {entry}")
            continue
        events.append([float(entry["start"]), float(entry["end"])])
    timings.append(events)
# A word in one sentence must never be matched to speech from another.
for i in range(1, len(timings)):
    if timings[i][0][0] < timings[i-1][-1][1] - 0.005:
        problems.append(f"overlapping adjacent phrases {i-1} and {i}: "
                        f"{timings[i-1][-1][1]} > {timings[i][0][0]}")
if problems:
    raise RuntimeError("Alignment incomplete; not exporting approximate timings:\n" + "\n".join(problems))
Path("goose_word_times.json").write_text(json.dumps(timings, ensure_ascii=False, indent=2), encoding="utf-8")
print("ALIGNED_WORDS", sum(map(len, timings)))
for i, ((a,b,txt), found) in enumerate(zip(lines,timings)):
    first, last = found[0][0], found[-1][1]
    print(f"PHRASE {i:02} old=[{a:.2f},{b:.2f}] aligned=[{first:.2f},{last:.2f}] {txt}")
