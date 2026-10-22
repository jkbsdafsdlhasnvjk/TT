#!/usr/bin/env python3
"""Pick global processing shard boundaries at real dialogue gaps.

Each boundary is computed once for the whole season; adjacent jobs reuse the
identical timestamp so there are no unrendered/duplicated ranges at shard edges.
"""
import json,sys
from pathlib import Path
from faster_whisper import WhisperModel
from serial_parts import words_from_audio, optional_silences, possible_cuts, command

source=sys.argv[1] if len(sys.argv)>1 else "season.mp4"
dest=Path(sys.argv[2] if len(sys.argv)>2 else "serial_seams.json")
duration=float(json.loads(command(["ffprobe","-v","error","-show_entries","format=duration","-of","json",source]).stdout)["format"]["duration"])
model=WhisperModel("small",device="cpu",compute_type="int8",cpu_threads=4)
bounds=[0.]
reasons=[]
for i in range(1,4):
    desired=round(duration*i/4.,2)
    lo=max(0.,desired-70.)
    hi=min(duration,desired+70.)
    words=words_from_audio(model,source,lo,hi)
    silences=optional_silences(source,lo,hi)
    pool=[]
    for t,score,kind,gap in possible_cuts(words,silences,lo,hi):
        # Alignment and frame safety. 0.12 seconds of speech-free space.
        t=round(t*25)/25
        if abs(t-desired)>55:continue
        if any(w["start"]-.12<t<w["end"]+.12 for w in words):continue
        score=score-.050*abs(t-desired)
        pool.append((score,t,kind,gap))
    if not pool:
        for j in range(0,501):
            offset=(j//2)*.20*(1 if j%2 else -1)
            t=round((desired+offset)*25)/25
            if abs(t-desired)>55:continue
            if all(not w["start"]-.15<t<w["end"]+.15 for w in words):
                pool.append((-999,t,"nonword_fallback",0.))
                break
    if not pool:raise RuntimeError(f"No word-safe processing boundary near {desired}")
    best=max(pool,key=lambda x:x[0])
    bounds.append(best[1])
    reasons.append({"target":desired,"actual":best[1],"type":best[2],"gap":best[3],"score":best[0]})
    print("GLOBAL_SEAM",i,desired,best[1],best[2],"gap",best[3],flush=True)
bounds.append(duration)
parts=[{"part":i+1,"start":round(bounds[i],2),"end":round(bounds[i+1],2)} for i in range(4)]
assert parts[0]["start"]==0.
assert all(parts[i]["end"]==parts[i+1]["start"] for i in range(3))
assert abs(parts[-1]["end"]-duration)<.01
dest.write_text(json.dumps({"source_duration":duration,"parts":parts,"reasons":reasons},ensure_ascii=False,indent=2),encoding="utf-8")
print("GLOBAL_SEAMS_DONE",json.dumps(parts),flush=True)
