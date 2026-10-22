#!/usr/bin/env python3
"""Inspect uploaded short video, Russian word timings and ambiguous recognition."""
import json,subprocess,sys
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel

source=sys.argv[1] if len(sys.argv)>1 else "scene.mp4"
out=Path(sys.argv[2] if len(sys.argv)>2 else "scene_asr")
out.mkdir(parents=True,exist_ok=True)
meta=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries",
 "format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,r_frame_rate,bit_rate",
 "-of","json",source]))
(out/"source_metadata.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
print("SOURCE",json.dumps(meta,ensure_ascii=False),flush=True)
raw=subprocess.check_output(["ffmpeg","-v","error","-i",source,"-vn","-ac","1","-ar","16000","-f","s16le","-"])
audio=np.frombuffer(raw,dtype=np.int16).astype("float32")/32768.0
results={}
for modelname in ("medium","small"):
    print("MODEL",modelname,flush=True)
    model=WhisperModel(modelname,device="cpu",compute_type="int8",cpu_threads=4)
    segments,_=model.transcribe(audio,language="ru",word_timestamps=True,beam_size=5,temperature=0.,
                                 condition_on_previous_text=False,vad_filter=True,
                                 vad_parameters={"min_silence_duration_ms":350},
                                 no_speech_threshold=.65)
    output=[]
    for s in segments:
        ww=[]
        for w in (s.words or []):
            if w.start is None or w.end is None or w.end<=w.start or not w.word.strip():continue
            ww.append({"word":w.word.strip(),"start":round(w.start,3),"end":round(w.end,3),"prob":round(w.probability or 0,3)})
        output.append({"start":round(s.start,3),"end":round(s.end,3),"text":s.text.strip(),"words":ww})
    (out/f"{modelname}_segments.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    results[modelname]=output
    for row in output:print(modelname,"SEGMENT",row["start"],row["end"],row["text"],flush=True)
    print("MODEL_WORDS",modelname,sum(len(x["words"]) for x in output),flush=True)
print("DONE_TRANSCRIBE",flush=True)
