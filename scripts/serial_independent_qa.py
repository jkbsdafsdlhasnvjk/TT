#!/usr/bin/env python3
"""Independent QA of completed sequential clips.
Does NOT certify ASR accuracy or silently rewrite words.
Inspect all MP4 AV durations, then cross-transcribe the lowest-confidence
speech samples with an independently trained Whisper model.
"""
import argparse, json, re, subprocess, unicodedata
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel

def run(args):
    return subprocess.check_output(args,stderr=subprocess.PIPE)
def norm(x):
    return re.sub(r"[^а-яё0-9]","",x.lower())
def audio(path,start,end):
    pcm=run(["ffmpeg","-hide_banner","-loglevel","error","-ss",str(max(0,start)),
       "-i",str(path),"-t",str(max(.2,end-max(0,start))),"-vn",
       "-ac","1","-ar","16000","-f","s16le","-"])
    return np.frombuffer(pcm,dtype="<i2").astype(np.float32)/32768
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--count",type=int,default=40)
    ap.add_argument("--skip",type=int,default=0,help="Skip earlier priority samples after spacing deduplication")
    ap.add_argument("--model",default="large-v3-turbo")
    args=ap.parse_args()
    root=Path(args.folder)
    review=json.loads((root/"transcript_review.json").read_text())
    words=json.loads((root/"word_timestamps.json").read_text())
    parts=json.loads((root/"rendered_parts.json").read_text())
    plan=json.loads((root/"continuous_cut_plan.json").read_text())
    issues=[]
    for item in review:
        if item["type"] not in ("uncertain_word","suspicious_duration"):continue
        index=item["index"]
        word=words[index]
        if not any(p["start"]<=word["start"]<p["end"] for p in parts):continue
        issues.append((word["confidence"],item["time"],item))
    issues.sort(key=lambda x:(x[0],x[1]))
    picked=[];times=[]
    for conf,t,item in issues:
        if any(abs(t-s)<5.0 for s in times):continue
        picked.append(item);times.append(t)
        if len(picked)>=args.count+args.skip:break
    picked=picked[args.skip:]
    print("PLAN",plan["range"],"MP4S",len(parts),"REVIEW_TOTAL",len(review),"SAMPLED",len(picked),flush=True)
    # Verify all MP4 streams, not just filenames and reported metadata.
    av_errors=[]
    for i,p in enumerate(parts):
        name=p["name"];f=root/name
        try:
            obj=json.loads(run(["ffprobe","-v","error","-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of","json",str(f)]))
            tracks=obj["streams"]
            dur=float(obj["format"]["duration"])
            assert abs(dur-(p["end"]-p["start"]))<.18
            assert any(x.get("codec_type")=="audio" for x in tracks)
            assert any(x.get("codec_type")=="video" and x.get("width")==1080 and x.get("height")==1920 for x in tracks)
        except Exception as exc:
            av_errors.append({"file":name,"error":str(exc)})
    print("AV_CHECK",len(parts),"FILES","ERRORS",len(av_errors),flush=True)
    if av_errors:
        print("AV_ERRORS",json.dumps(av_errors[:15],ensure_ascii=False),flush=True)
    model=WhisperModel(args.model,device="cpu",compute_type="int8",cpu_threads=4)
    comparisons=[]
    for n,item in enumerate(picked,1):
        t=item["time"]
        p=next(x for x in parts if x["start"]<=t<x["end"])
        rel=t-p["start"]
        a=max(0,rel-3.3);b=min(p["end"]-p["start"],rel+4.2)
        signal=audio(root/p["name"],a,b)
        segs,_=model.transcribe(signal,language="ru",beam_size=5,temperature=0,
                                vad_filter=False,condition_on_previous_text=False,
                                word_timestamps=True)
        segs=list(segs)
        alt=" ".join(s.text.strip() for s in segs)
        w=words[item["index"]]
        alt_tokens=[norm(k) for k in re.findall(r"[а-яёА-ЯЁ0-9-]+",alt)]
        agrees=norm(w["text"]) in alt_tokens
        # Independent word timing is relative to the extracted MP4 audio window.
        # Convert to original season time before comparing against source ASR.
        alt_words=[]
        for seg in segs:
            for aw in seg.words or ():
                if aw.start is None or aw.end is None:continue
                alt_words.append({"text":aw.word.strip(),
                    "start":round(p["start"]+a+float(aw.start),3),
                    "end":round(p["start"]+a+float(aw.end),3)})
        candidates=[x for x in alt_words if norm(x["text"])==norm(w["text"])]
        closest=min(candidates,key=lambda x:abs(x["start"]-w["start"])) if candidates else None
        timing_delta=round(closest["start"]-w["start"],3) if closest else None
        timing_consistent=abs(timing_delta)<=.60 if timing_delta is not None else None
        row={"file":p["name"],"source_time":t,"relative_time":round(rel,2),
             "original_word":w["text"],"original_confidence":w["confidence"],
             "issue_type":item["type"],"alternate_transcript":alt,
             "exact_word_present_in_alt":agrees,
             "independent_word_match":closest,
             "word_start_delta_seconds":timing_delta,
             "timing_within_0_60s":timing_consistent,
             "review_status":"NEEDS_HUMAN_AUDIO_REVIEW"}
        comparisons.append(row)
        print("CROSSCHECK",n,"/",len(picked),round(t,2),repr(w["text"]),
              "MATCH" if agrees else "DISAGREES",alt[:145],flush=True)
    report={"source_range":plan["range"],"mp4_checked":len(parts),
            "mp4_errors":av_errors,"all_review_items":len(review),
            "sampled":len(comparisons),"crosscheck":comparisons,
            "independent_text_disagreements":sum(not x["exact_word_present_in_alt"] for x in comparisons),
            "independent_timing_disagreements":sum(x["timing_within_0_60s"] is False for x in comparisons),
            "subtitle_language_qa":"NOT_CERTIFIED",
            "note":"Alternative ASR is diagnostic only, not ground truth."}
    Path(f"qa_crosscheck_{int(plan['range'][0])}_{args.skip}_{args.count}.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    if av_errors:raise SystemExit("MP4 integrity check failed")
if __name__=="__main__":main()
