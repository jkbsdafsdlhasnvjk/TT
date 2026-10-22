#!/usr/bin/env python3
"""Independent ASR alignment: timing comes from the audio, not uniform shifts."""
import ast, json, re, unicodedata, wave
import numpy as np
from difflib import SequenceMatcher
from pathlib import Path
from faster_whisper import WhisperModel

source = ast.parse(Path("scripts/goose_captions.py").read_text(encoding="utf-8"))
lines = next(ast.literal_eval(n.value) for n in source.body if isinstance(n, ast.Assign) and any(isinstance(t,ast.Name) and t.id=="lines" for t in n.targets))
reference = [w for _,_,phrase in lines for w in phrase.split()]
model=WhisperModel("small",device="cpu",compute_type="int8",cpu_threads=4,num_workers=1)
with wave.open("goose_audio.wav", "rb") as wf:
    assert wf.getnchannels() == 1 and wf.getframerate() == 16000 and wf.getsampwidth() == 2
    audio_samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype="<i2").astype("float32") / 32768
segments,info=model.transcribe(audio_samples,language="ru",beam_size=5,word_timestamps=True,vad_filter=False,condition_on_previous_text=False, initial_prompt="Кухня. Шеф. Убей гуся. Я же не грузчик. В смысле? Каждый повар должен быть готов убить.")
segments=list(segments)
found=[]
for seg in segments:
    for w in (seg.words or []):
        if w.start is not None and w.end is not None and w.end > w.start:
            found.append({"word":w.word.strip(),"start":round(w.start,3),"end":round(w.end,3),"probability":round(w.probability or 0,3)})
Path("asr_raw_words.json").write_text(json.dumps({"segments":[{"start":round(s.start,2),"end":round(s.end,2),"text":s.text} for s in segments],"words":found},ensure_ascii=False,indent=2),encoding="utf-8")
def norm(x):
    return re.sub(r"[^а-яa-z0-9]", "", x.lower().replace("ё","е"))
refs=[norm(w) for w in reference]
obs=[norm(x["word"]) for x in found]
N,M=len(refs),len(obs)
gap=0.75
dp=[[float("inf")]*(M+1) for _ in range(N+1)]
back=[[None]*(M+1) for _ in range(N+1)]
dp[0][0]=0
for i in range(N+1):
    for j in range(M+1):
        d=dp[i][j]
        if i<N and d+gap<dp[i+1][j]:dp[i+1][j]=d+gap;back[i+1][j]=(i,j,"skip-ref")
        if j<M and d+gap<dp[i][j+1]:dp[i][j+1]=d+gap;back[i][j+1]=(i,j,"skip-asr")
        if i<N and j<M:
            ratio=SequenceMatcher(None,refs[i],obs[j]).ratio()
            mismatch=1-ratio
            if d+mismatch<dp[i+1][j+1]:dp[i+1][j+1]=d+mismatch;back[i+1][j+1]=(i,j,"pair")
mapping={}
i,j=N,M
while i or j:
    prev=back[i][j]
    if prev is None:raise RuntimeError(f"DP path broken at {i},{j}")
    pi,pj,what=prev
    if what=="pair":mapping[pi]=pj
    i,j=pi,pj
matches=sum(refs[i]==obs[j] for i,j in mapping.items())
adequate=sum(SequenceMatcher(None,refs[i],obs[j]).ratio()>=.6 for i,j in mapping.items())
print("ASR_WORDS",M,"REFERENCE_WORDS",N,"EXACT",matches,"SIMILAR",adequate,"MAPPED",len(mapping),"MISSING",N-len(mapping))
for i,j in mapping.items():
    if SequenceMatcher(None,refs[i],obs[j]).ratio()<.6:
        print("BAD_MATCH",i,reference[i],found[j]["word"],found[j]["start"])
for i in range(N):
    if i not in mapping:print("MISSING_WORD",i,reference[i])
for n,s in enumerate(segments):print(f"ASR_SEG {n}: {s.start:.2f}-{s.end:.2f}: {s.text}")
# Output per-word entries. Unrecognized words are marked and do not inherit
# fabricated times: fail QA for those, rather than silently stretching.
output=[]
cursor=0
for a,b,phrase in lines:
    row=[]
    for word in phrase.split():
        if cursor in mapping:
            w=found[mapping[cursor]]
            similarity=SequenceMatcher(None,refs[cursor],obs[mapping[cursor]]).ratio()
            row.append({"word":word,"start":w["start"],"end":w["end"],"recognized":w["word"],"similarity":round(similarity,3),"verified":similarity>=.6})
        else:
            row.append({"word":word,"start":None,"end":None,"verified":False})
        cursor+=1
    output.append(row)
Path("goose_audio_alignment_review.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
# Output both raw words and review even on failed alignment, so QA can repair.
if adequate < .75*N:
    raise RuntimeError("Low transcript correspondence. Inspect ASR diagnostics before rendering captions.")
# Missing words: use local reference times as explicit fallback, never hide that fact.
baseline=json.loads(Path("scripts/goose_word_times_baseline.json").read_text(encoding="utf-8"))
timings=[]
for idx,row in enumerate(output):
    tmp=[]
    for j,item in enumerate(row):
        if item["start"] is not None and item["verified"]:
            tmp.append([item["start"],item["end"]])
        else:
            tmp.append(baseline[idx][j])
    timings.append(tmp)
Path("goose_word_times.json").write_text(json.dumps(timings,ensure_ascii=False,indent=2),encoding="utf-8")
print("AUDIO_DERIVED",sum(item["verified"] for row in output for item in row),"FALLBACK",sum(not item["verified"] for row in output for item in row))
