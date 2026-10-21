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
segments = [{"start": max(0.0, a - 0.70), "end": min(len(audio)/16000, b + 0.55),
             "text": phrase} for a, b, phrase in lines]
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
if problems:
    raise RuntimeError("Alignment incomplete; not exporting approximate timings:\n" + "\n".join(problems))
Path("goose_word_times.json").write_text(json.dumps(timings, ensure_ascii=False, indent=2), encoding="utf-8")
print("ALIGNED_WORDS", sum(map(len, timings)))
for i, ((a,b,txt), found) in enumerate(zip(lines,timings)):
    first, last = found[0][0], found[-1][1]
    print(f"PHRASE {i:02} old=[{a:.2f},{b:.2f}] aligned=[{first:.2f},{last:.2f}] {txt}")
