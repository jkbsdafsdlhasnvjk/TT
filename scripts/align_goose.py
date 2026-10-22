#!/usr/bin/env python3
"""Align groups of contiguous dialogue to the ACTUAL waveform, not line-sized guesses."""
import ast
import json
from pathlib import Path
import whisperx

source = ast.parse(Path("scripts/goose_captions.py").read_text(encoding="utf-8"))
lines = next(ast.literal_eval(node.value) for node in source.body
             if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "lines" for t in node.targets))
audio = whisperx.load_audio("goose_audio.wav")
duration = len(audio) / 16000

# Crucial: the former windows had a -0.26s left boundary, and 10+ first
# words were pinned to that boundary. Their true beginnings were UNKNOWN.
# Align adjacent lines TOGETHER instead, allowing the acoustic model
# to locate words across the entire spoken dialogue block.
group_ranges = [(0,3),(3,6),(6,9),(9,11),(11,14),(14,16),(16,17),(17,18),(18,22)]
assert group_ranges[0][0] == 0 and group_ranges[-1][1] == len(lines)
assert all(group_ranges[i][1] == group_ranges[i+1][0] for i in range(len(group_ranges)-1))

blocks = []
for i,(lo,hi) in enumerate(group_ranges):
    left = max(0.0, lines[lo][0] - 0.6)
    right = min(duration, lines[hi-1][1] + 0.6)
    if i:
        previous_end = lines[group_ranges[i-1][1]-1][1]
        boundary = (previous_end + lines[lo][0]) / 2
        left = max(left, boundary)
    if i+1 < len(group_ranges):
        next_start = lines[group_ranges[i+1][0]][0]
        boundary = (lines[hi-1][1] + next_start) / 2
        right = min(right, boundary)
    assert right > left, (i,left,right)
    blocks.append({"start":left,"end":right,"text":" ".join(phrase for _,_,phrase in lines[lo:hi])})

model, meta = whisperx.load_align_model(language_code="ru", device="cpu")
result = whisperx.align(blocks, model, meta, audio, "cpu")
timings = []
problems = []
for gi,((lo,hi),block,aligned) in enumerate(zip(group_ranges,blocks,result["segments"])):
    raw_words = aligned.get("words", [])
    tokens = [token for _,_,sentence in lines[lo:hi] for token in sentence.split()]
    if len(raw_words) != len(tokens):
        problems.append(f"group {gi}: expected {len(tokens)} words, got {len(raw_words)}")
        continue
    events = []
    for token,entry in zip(tokens,raw_words):
        if "start" not in entry or "end" not in entry or entry["end"] <= entry["start"]:
            problems.append(f"group {gi}: unaligned {token}: {entry}")
            continue
        events.append([float(entry["start"]),float(entry["end"])])
    expected = [len(lines[i][2].split()) for i in range(lo,hi)]
    idx = 0
    for count in expected:
        timings.append(events[idx:idx+count])
        idx += count
    if events:
        print(f"GROUP {gi}: sound=[{blocks[gi]['start']:.2f},{blocks[gi]['end']:.2f}] first={events[0][0]:.3f} last={events[-1][1]:.3f} words={len(events)}")

if len(timings) != len(lines):
    problems.append(f"Incorrect phrase count: {len(timings)} != {len(lines)}")
for i,row in enumerate(timings):
    if not row: problems.append(f"empty phrase {i}"); continue
    for j,(a,b) in enumerate(row):
        if not 0 <= a < b <= duration: problems.append(f"bad word {i}:{j} [{a},{b}]")
    if i and row[0][0] < timings[i-1][-1][1] - .02:
        problems.append(f"overlapping words {i-1} and {i}")
if problems:
    raise RuntimeError("Refusing to export faulty timing:\n" + "\n".join(problems))
Path("goose_word_times.json").write_text(json.dumps(timings,ensure_ascii=False,indent=2),encoding="utf-8")
print("ALIGNED_PHRASES",len(timings),"ALIGNED_WORDS",sum(len(x) for x in timings))
for i,((a,b,txt),row) in enumerate(zip(lines,timings)):
    print(f"PHRASE {i:02}: old=[{a:.2f},{b:.2f}] acoustic=[{row[0][0]:.2f},{row[-1][1]:.2f}] {txt}")
