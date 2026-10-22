#!/usr/bin/env python3
"""Diagnostic independent small-scene recognition, no fake repeated dialogue."""
import json, wave
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel
with wave.open("goose_audio.wav","rb") as f:
    assert f.getframerate()==16000 and f.getnchannels()==1
    audio=np.frombuffer(f.readframes(f.getnframes()),dtype="<i2").astype(np.float32)/32768.0
model=WhisperModel("small",device="cpu",compute_type="int8",cpu_threads=4)
# Short real-audio windows stop Whisper's persistent hallucination of 'Убей!'
windows=[(0,3.4),(3.4,7.4),(7.4,11.7),(11.7,16.7),(16.7,23.5),
(23.5,29.5),(29.5,35.5),(35.5,40.5),(40.5,44.7),(44.7,49.1),
(49.1,53.1),(53.1,58.6)]
result=[]
for lo,hi in windows:
    part=audio[int(lo*16000):int(hi*16000)]
    segments,_=model.transcribe(part,language="ru",beam_size=5,word_timestamps=True,
        vad_filter=True,vad_parameters={"min_silence_duration_ms":280},
        condition_on_previous_text=False,temperature=0.0,
        compression_ratio_threshold=1.7,no_speech_threshold=0.65)
    row=[]
    for seg in segments:
        words=[]
        for w in seg.words or []:
            words.append({"word":w.word.strip(),"start":round(lo+w.start,3),"end":round(lo+w.end,3),"p":round(w.probability or 0,2)})
        row.append({"text":seg.text,"start":round(lo+seg.start,2),"end":round(lo+seg.end,2),"words":words})
    print(f"CHUNK [{lo:4.1f},{hi:4.1f}]: "+" / ".join(r["text"] for r in row),flush=True)
    result.append({"from":lo,"to":hi,"segments":row})
Path("asr_chunk_review.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
