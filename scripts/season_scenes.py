#!/usr/bin/env python3
"""Season 1 dialogue-driven vertical short-video maker.
Selection is heuristic; outputs are review candidates, not human-approved scenes.
"""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel

BAD=("субтитр","в предыдущей серии","продолжение следует","перевод","подпишись")
FUN=("шеф","баринов","макс","вика","идиот","дурак","почему","чего","что за","совсем","ненавиж","убей","серьезно","серьёзно","нельзя","врёшь","ресторан","повар")
HEADER="""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,DejaVu Sans,53,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,8,50,50,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
def run(args):
    return subprocess.run(args,check=True,capture_output=True).stdout
def fmt(t):
    cs=int(round(max(0,t)*100));h,cs=divmod(cs,360000);m,cs=divmod(cs,6000);s,cs=divmod(cs,100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"
def audio(source,start,duration):
    pcm=run(["ffmpeg","-hide_banner","-loglevel","error","-ss",str(start),"-i",source,"-t",str(duration),"-vn","-ac","1","-ar","16000","-f","s16le","-"])
    return np.frombuffer(pcm,dtype="<i2").astype("float32")/32768
def transcribe(model,source,start,end):
    transcript=[]
    now=start
    while now<end-.1:
        limit=min(now+150,end)
        segments,_=model.transcribe(audio(source,now,limit-now),language="ru",word_timestamps=True,
            beam_size=4,temperature=0.0,vad_filter=True,
            vad_parameters={"min_silence_duration_ms":400},
            condition_on_previous_text=False,no_speech_threshold=.64)
        for s in segments:
            words=[{"text":w.word.strip(),"start":round(now+w.start,3),"end":round(now+w.end,3)}
                   for w in s.words or [] if w.start is not None and w.end is not None and w.end>w.start and w.word.strip()]
            if words:
                transcript.append({"start":words[0]["start"],"end":words[-1]["end"],"text":s.text.strip(),"words":words})
        now=limit
        print("ASR_PROGRESS",round(now,1),"segments",len(transcript),flush=True)
    return sorted(transcript,key=lambda s:s["start"])
def candidates(segs,start,end,per_bin):
    pool=[]
    for i in range(0,len(segs),2):
        for j in range(i+2,len(segs)):
            duration=segs[j]["end"]-segs[i]["start"]
            if duration<29:continue
            if duration>61:break
            gap=segs[j+1]["start"]-segs[j]["end"] if j+1<len(segs) else 1
            if gap<.4 and not segs[j]["text"].rstrip().endswith((".","!","?","…")):continue
            lo=max(start,segs[i]["start"]-.28)
            hi=min(end,segs[j]["end"]+min(.4,max(.15,gap/2)))
            if not 30<=hi-lo<=63:continue
            group=segs[i:j+1]
            text=" ".join(x["text"] for x in group).lower()
            if len(text)<95 or any(b in text for b in BAD):continue
            voice=sum(max(0,x["end"]-x["start"]) for x in group)/(hi-lo)
            if voice<.30 or voice>.96:continue
            score=5+min(4,sum(text.count(x) for x in FUN)*.8)
            score+=min(3,text.count("?")*.7+text.count("!")*.4)
            score+=2*max(0,1-abs(voice-.63)/.45)
            score+=2*max(0,1-abs((hi-lo)-48)/26)
            score+=1.5 if gap>.65 else 0
            score-=max(0,text.count("убей")-4)*.5
            pool.append({"start":round(lo,2),"end":round(hi,2),"score":round(score,2),
                         "title":text[:110],"segments":[i,j]})
    chosen=[]
    # These are coverage bins, NOT asserted episode boundaries.
    bound=math.floor(start/1440)*1440
    while bound<end:
        possibles=sorted((x for x in pool if bound<=x["start"]<bound+1440),key=lambda x:x["score"],reverse=True)
        count=0
        for cand in possibles:
            if all(cand["start"]>x["end"]+50 or cand["end"]<x["start"]-50 for x in chosen):
                chosen.append(cand);count+=1
                if count==per_bin:break
        bound+=1440
    return sorted(chosen,key=lambda x:x["start"]),len(pool)
def ass_for_clip(segs,start,end,path):
    # One stationary phrase, only the highlighted word changes colour.
    phrases=[]
    for s in segs:
        words=s["words"]
        if not words:continue
        if words[0]["start"]<start-.04 or words[-1]["end"]>end+.04:continue
        # Split unusually long sentences on word boundaries.
        for offset in range(0,len(words),10):
            phrases.append(words[offset:offset+10])
    if not phrases:raise ValueError("No aligned speech")
    output=[]
    for i,p in enumerate(phrases):
        a=max(0,p[0]["start"]-start-.14)
        b=min(end-start,p[-1]["end"]-start+.4)
        if i+1<len(phrases):
            b=min(b,phrases[i+1][0]["start"]-start-.06)
        if i and a<output[-1][1]:
            a=output[-1][1]
        if b<=a or b<p[-1]["end"]-start-.22:
            raise ValueError("Overlapping text/audio boundaries")
        raw=[w["text"].replace("{","").replace("}","").replace("\\","") for w in p]
        sizes=[len(t)+1 for t in raw]
        cut=len(raw)
        if sum(sizes)>34 and len(raw)>3:
            acc=0
            for j,v in enumerate(sizes[:-1]):
                acc+=v
                if acc>=sum(sizes)/2:cut=j+1;break
        pieces=[]
        for j,(w,t) in enumerate(zip(p,raw)):
            on=max(a,w["start"]-start-.08)
            off=(max(on+.04,p[j+1]["start"]-start-.08) if j+1<len(p) else min(b,w["end"]-start+.05))
            x=round(1000*(on-a));y=round(1000*(min(b,off)-a))
            if x<=0:
                effect=r"{\1c&H00D7FF&"+f"\\t({y},{y+1},\\1c&HFFFFFF&)"+"}"
            else:
                effect=r"{\1c&HFFFFFF&"+f"\\t({x},{x+1},\\1c&H00D7FF&)\\t({y},{y+1},\\1c&HFFFFFF&)"+"}"
            pieces.append(effect+t)
        caption=" ".join(pieces[:cut])+(r"\N"+" ".join(pieces[cut:]) if cut<len(pieces) else "")
        output.append((a,b,f"Dialogue: 0,{fmt(a)},{fmt(b)},Word,,0,0,0,,{{\\an8\\pos(540,1390)}}{caption}"))
    Path(path).write_text(HEADER+"\n".join(x[2] for x in output)+"\n",encoding="utf-8")
    return len(output),sum(map(len,phrases))
def render(source,c,segs,destination,ordinal):
    start,end=c["start"],c["end"]
    clip=destination/f"Kinogryz_S01_{int(start//3600):02d}h{int(start%3600//60):02d}m_{ordinal:02d}.mp4"
    subtitle=clip.with_suffix(".ass")
    events,words=ass_for_clip(segs,start,end,subtitle)
    if words<15:raise ValueError("Too few words")
    graph=("[0:v]split=2[base][fg];"
        "[base]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=22:2[bg];"
        "[fg]scale=1080:-2:flags=lanczos,unsharp=3:3:0.20[front];"
        f"[bg][front]overlay=x=(W-w)/2:y=(H-h)/2+45,ass={subtitle.as_posix()},format=yuv420p[v]")
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss",str(start),"-i",source,"-t",str(end-start),
         "-filter_complex",graph,"-map","[v]","-map","0:a:0","-c:v","libx264","-preset","veryfast",
         "-crf","16","-r","25","-c:a","aac","-b:a","192k","-movflags","+faststart",str(clip)])
    metadata=json.loads(run(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,width,height","-of","json",str(clip)]))
    tracks=metadata.get("streams",[])
    assert any(x.get("codec_type")=="audio" for x in tracks),"Audio track missing"
    assert any(x.get("codec_type")=="video" and x.get("width")==1080 and x.get("height")==1920 for x in tracks),"Video dimensions wrong"
    assert abs(float(metadata["format"]["duration"])-(end-start))<.14,"Clip duration wrong"
    return {"file":clip.name,"start":start,"end":end,"title":c["title"],"words":words,"events":events,"bytes":int(metadata["format"]["size"])}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="season.mp4")
    p.add_argument("--start",type=float,default=0)
    p.add_argument("--end",type=float,default=1440)
    p.add_argument("--per-bin",type=int,default=3)
    p.add_argument("--max-clips",type=int,default=3)
    p.add_argument("--model",default="small")
    p.add_argument("--out",default="season_output")
    p.add_argument("--plan-only",action="store_true")
    args=p.parse_args()
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    source=str(Path(args.source).resolve())
    total=float(json.loads(run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",source]))["format"]["duration"])
    start=max(0,args.start);end=min(total,args.end)
    model=WhisperModel(args.model,device="cpu",compute_type="int8",cpu_threads=4)
    segs=transcribe(model,source,start,end)
    selected,num=candidates(segs,start,end,args.per_bin)
    if args.max_clips>0:selected=selected[:args.max_clips]
    (out/"transcript.json").write_text(json.dumps(segs,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"season_plan.json").write_text(json.dumps({"range":[start,end],"candidates":num,"selected":selected},ensure_ascii=False,indent=2),encoding="utf-8")
    print("CANDIDATES",num,"SELECTED",len(selected),flush=True)
    for c in selected:print("PICK",c["start"],c["end"],c["score"],c["title"][:85],flush=True)
    if args.plan_only:return
    results=[]
    for i,c in enumerate(selected,1):
        try:
            a,b=c["segments"]
            qa=render(source,c,segs[a:b+1],out,i)
            print("SUCCESS",qa["file"],qa["words"],flush=True)
            results.append(qa)
        except Exception as exc:
            print("REJECTED",c["start"],repr(exc),flush=True)
    (out/"render_results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    if not results:raise RuntimeError("No clips passed audio/subtitle QA")
    print("FINISHED",len(results),flush=True)
if __name__=="__main__":main()
