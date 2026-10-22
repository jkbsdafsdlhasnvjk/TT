#!/usr/bin/env python3
"""Continuous sequential multipart edit. No scene selection and no omitted footage.

Only split at silence between words, scene transitions or true non-dialogue spans.
ASR transcript quality is reported separately; successful FFmpeg is not language QA.
"""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel

ASS_HEADER = """[Script Info]
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
MAX_WORDS_PER_LINE = 9
MIN_PART = 54.
TARGET_PART = 92.
MAX_PART = 126.

def command(argv):
    return subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
def stamp(x):
    cs=round(max(0,x)*100)
    hh,cs=divmod(cs,360000)
    mm,cs=divmod(cs,6000)
    ss,cs=divmod(cs,100)
    return f"{hh}:{mm:02}:{ss:02}.{cs:02}"
def audio_window(source,start,end):
    raw=command(["ffmpeg","-hide_banner","-loglevel","error",
       "-ss",f"{start:.3f}","-i",source,"-t",f"{end-start:.3f}",
       "-vn","-ac","1","-ar","16000","-f","s16le","-"]).stdout
    return np.frombuffer(raw,dtype="<i2").astype("float32")/32768.
def words_from_audio(model,source,lo,hi):
    all_words=[]
    # Full temporal coverage with 2s overlap at both edges of 95s windows.
    # Keep only words whose midpoint is in this window's non-overlap core.
    now=lo
    while now<hi-.10:
        stop=min(now+95.,hi)
        left=max(lo,now-2.)
        right=min(hi,stop+2.)
        samples=audio_window(source,left,right)
        segments,_=model.transcribe(samples,language="ru",beam_size=5,temperature=0.,
            word_timestamps=True,condition_on_previous_text=False,
            vad_filter=True,vad_parameters={"min_silence_duration_ms":320},
            no_speech_threshold=.65,compression_ratio_threshold=1.8)
        used=0
        for seg in segments:
            speech_text=(seg.text or "").lower().replace("ё","е")
            # Whisper can hallucinate credit titles and audio-description
            # labels over instrumentals. These aren't spoken dialogue.
            if any(x in speech_text for x in ("редактор субтитров","динамичная музыка","субтитры подготовил","переводчик")):
                print("ASR_FILTER_NON_SPEECH",round(left+seg.start,2),speech_text[:140],flush=True)
                continue
            for word in seg.words or ():
                if word.start is None or word.end is None or word.end<=word.start or not word.word.strip():
                    continue
                a=left+float(word.start);b=left+float(word.end)
                if not now<=.5*(a+b)<stop:continue
                if not lo<=a<=b<=hi+.07:continue
                if not re.search(r"[а-яёА-ЯЁ0-9]",word.word):
                    continue  # punctuation-only ASR tokens are not spoken words
                all_words.append({"start":round(a,3),"end":round(b,3),
                    "text":word.word.strip(),"confidence":round(float(word.probability or 0.),3)})
                used+=1
        print("ASR",round(now,2),round(stop,2),"words",used,flush=True)
        now=stop
    all_words.sort(key=lambda w:(w["start"],w["end"]))
    dedup=[]
    for w in all_words:
        if dedup and abs(w["start"]-dedup[-1]["start"])<.075 and w["text"].lower()==dedup[-1]["text"].lower():
            if w["confidence"]>dedup[-1]["confidence"]:dedup[-1]=w
        else:
            dedup.append(w)
    return dedup

def optional_silences(source,lo,hi):
    # Silent soundtrack moments are supplementary to spoken-word gaps.
    # Do not rely solely on amplitude silence in music-backed scenes.
    args=["ffmpeg","-hide_banner","-nostats","-ss",str(lo),"-i",source,
          "-t",str(hi-lo),"-vn","-af","silencedetect=noise=-32dB:d=0.27",
          "-f","null","-"]
    r=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    on=None;out=[]
    for line in r.stderr.splitlines():
        a=re.search(r"silence_start: ([0-9.]+)",line)
        b=re.search(r"silence_end: ([0-9.]+)",line)
        if a:on=lo+float(a.group(1))
        if b and on is not None:
            finish=lo+float(b.group(1))
            if finish>on+.27:out.append((on,finish))
            on=None
    return out

def possible_cuts(words,silences,lo,hi):
    cuts=[]
    for i in range(len(words)-1):
        w,n=words[i],words[i+1]
        gap=n["start"]-w["end"]
        if gap<.22:continue
        cut=(w["end"]+n["start"])/2.
        if cut<=lo or cut>=hi:continue
        punct=int(w["text"].rstrip().endswith((".","?","!","…")))
        score=min(2.5,gap)*1.6 +1.7*punct
        cuts.append((cut,score,"between_utterances",gap))
    for a,b in silences:
        cut=.5*(a+b)
        if lo<cut<hi and all(not w["start"]-.10<cut<w["end"]+.10 for w in words):
            cuts.append((cut,2.5+min(b-a,2.),"soundtrack_silence",b-a))
    return cuts

def closest_safe_boundary(cursor,hi,cuts,words):
    earliest=cursor+MIN_PART
    latest=min(cursor+MAX_PART,hi)
    near=[(t,s,kind,gap) for t,s,kind,gap in cuts if earliest<=t<=latest]
    if near:
        # Avoid tiny final part where possible.
        scored=sorted(near,key=lambda x:(x[1] - abs(x[0]-(cursor+TARGET_PART))*.065),reverse=True)
        choice=scored[0]
        return round(choice[0],2),choice[2],round(choice[1],2)
    # If the film has no gap in the desired window (continuous music etc.),
    # use a point outside ASR speech, and explicitly classify it as a fallback.
    for offset in [0,5,-5,10,-10,15,-15,20,-20,25,-25]:
        t=min(latest-.1,max(earliest+.1,cursor+TARGET_PART+offset))
        if all(not w["start"]-.14<t<w["end"]+.14 for w in words):
            return round(t,2),"nonword_fallback",0
    raise RuntimeError(f"No safe split at {cursor:.2f}. Never split an audible word.")

def build_spans(words,silences,lo,hi):
    cuts=possible_cuts(words,silences,lo,hi)
    spans=[]
    cursor=lo
    while hi-cursor>MAX_PART:
        cut,reason,score=closest_safe_boundary(cursor,hi,cuts,words)
        if cut<=cursor:raise RuntimeError("Bad split order")
        spans.append({"start":round(cursor,2),"end":cut,"reason":reason,"score":score})
        cursor=cut
    # A short final section is allowed: all frames still remain in order.
    spans.append({"start":round(cursor,2),"end":round(hi,2),"reason":"end_of_range","score":0})
    assert all(abs(spans[i]["end"]-spans[i+1]["start"])<.001 for i in range(len(spans)-1))
    assert abs(spans[0]["start"]-lo)<.01 and abs(spans[-1]["end"]-hi)<.01
    # No recognized word may be bisected at any internal cut.
    for sp in spans[:-1]:
        t=sp["end"]
        conflicts=[w for w in words if w["start"]-.08<t<w["end"]+.08]
        if conflicts:
            raise RuntimeError(f"Word-cut conflict at {t}: {conflicts[:2]}")
    return spans

def phrases_for_span(words,span):
    lo,hi=span["start"],span["end"]
    relevant=[w for w in words if lo-.02<=w["start"] and w["end"]<=hi+.02]
    # If a word is close to a cut, flag it rather than fabricate subtitles.
    overlaps=[w for w in words if w["start"]<hi and w["end"]>lo and w not in relevant]
    if overlaps:raise RuntimeError(f"Word straddling part: {overlaps[:2]}")
    phrases=[];group=[]
    for w in relevant:
        prev=group[-1] if group else None
        punctuation=bool(prev and prev["text"].rstrip().endswith((".","!","?","…")))
        pause=bool(prev and w["start"]-prev["end"]>.42)
        if group and (len(group)>=MAX_WORDS_PER_LINE or pause or punctuation):
            phrases.append(group);group=[]
        group.append(w)
    if group:phrases.append(group)
    return phrases,relevant

def captions(words,span,path):
    groups,relevant=phrases_for_span(words,span)
    begin,end=span["start"],span["end"]
    events=[];old_end=0.
    for i,g in enumerate(groups):
        a=max(0.,g[0]["start"]-begin-.15,old_end)
        b=min(end-begin,g[-1]["end"]-begin+.40)
        if i+1<len(groups):
            b=min(b,groups[i+1][0]["start"]-begin-.055)
        if b<=a:raise RuntimeError("Caption phrase overlap")
        split=len(g)
        visible=[w["text"].replace("\\","").replace("{","").replace("}","") for w in g]
        if sum(len(t)+1 for t in visible)>34 and len(g)>3:
            v=0
            for j,x in enumerate(visible[:-1]):
                v+=len(x)+1
                if v>=sum(len(t)+1 for t in visible)/2:
                    split=j+1;break
        decorated=[]
        for j,(w,token) in enumerate(zip(g,visible)):
            onset=max(a,w["start"]-begin-.075)
            finish=min(b, (g[j+1]["start"]-begin-.075 if j+1<len(g) else w["end"]-begin+.05))
            finish=max(onset+.01,finish)
            x=round((onset-a)*1000)
            y=round((finish-a)*1000)
            if x<=0:tag="{\\1c&H00D7FF&"+f"\\t({y},{y+1},\\1c&HFFFFFF&)"+"}"
            else:tag="{\\1c&HFFFFFF&"+f"\\t({x},{x+1},\\1c&H00D7FF&)\\t({y},{y+1},\\1c&HFFFFFF&)"+"}"
            decorated.append(tag+token)
        text=" ".join(decorated[:split])+(r"\N"+" ".join(decorated[split:]) if split<len(g) else "")
        events.append(f"Dialogue: 0,{stamp(a)},{stamp(b)},Word,,0,0,0,,{{\\an8\\pos(540,1390)}}{text}")
        old_end=b
    Path(path).write_text(ASS_HEADER+"\n".join(events)+"\n",encoding="utf-8")
    return len(events),len(relevant)

def issues(words):
    problems=[]
    for i,w in enumerate(words):
        token=w["text"]
        if w["confidence"]<.45:
            problems.append({"index":i,"time":w["start"],"type":"uncertain_word","text":token,"prob":w["confidence"]})
        if w["end"]-w["start"]>1.25:
            problems.append({"index":i,"time":w["start"],"type":"suspicious_duration","text":token,"duration":round(w["end"]-w["start"],2)})
        if not re.search(r"[а-яёА-ЯЁ]",token):
            problems.append({"index":i,"time":w["start"],"type":"non_cyrillic","text":token})
        if i>=5 and token.lower()==words[i-1]["text"].lower()==words[i-2]["text"].lower()==words[i-3]["text"].lower()==words[i-4]["text"].lower():
            problems.append({"index":i,"time":w["start"],"type":"repeated_word_maybe_music","text":token})
    return problems

def render(source,span,words,folder,index,quality):
    name=f"Kinogryz_S01_full_{index:04d}.mp4"
    target=folder/name
    subtitle=folder/f"Kinogryz_S01_full_{index:04d}.ass"
    phrase_count,word_count=captions(words,span,subtitle)
    filtergraph=(
        "[0:v]split=2[bgsrc][fgsrc];"
        "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=22:2[bg];"
        "[fgsrc]scale=1080:-2:flags=lanczos,unsharp=3:3:0.2[fg];"
        f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2+45,ass={subtitle.as_posix()},format=yuv420p[v]"
    )
    args=["ffmpeg","-hide_banner","-loglevel","error","-y",
          "-ss",str(span["start"]),"-i",source,"-t",str(round(span["end"]-span["start"],3)),
          "-filter_complex",filtergraph,"-map","[v]","-map","0:a:0",
          "-c:v","libx264","-preset","veryfast","-crf",str(quality),"-r","25",
          "-c:a","aac","-b:a","192k","-movflags","+faststart",str(target)]
    command(args)
    f=json.loads(command(["ffprobe","-v","error","-show_entries",
              "format=duration,size:stream=codec_type,width,height","-of","json",str(target)]).stdout)
    tracks=f["streams"]
    if not any(t.get("codec_type")=="audio" for t in tracks):raise RuntimeError("Missing audio")
    if not any(t.get("codec_type")=="video" and t.get("width")==1080 and t.get("height")==1920 for t in tracks):
        raise RuntimeError("Unexpected video format")
    duration=float(f["format"]["duration"])
    if abs(duration-(span["end"]-span["start"]))>.18:
        raise RuntimeError(f"Duration error {duration}")
    return {"name":name,"start":span["start"],"end":span["end"],
            "duration":duration,"size":int(f["format"]["size"]),
            "words":word_count,"phrases":phrase_count}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="season.mp4")
    p.add_argument("--start",type=float,default=0.)
    p.add_argument("--end",type=float,default=390.)
    p.add_argument("--model",default="medium")
    p.add_argument("--out",default="serial_output")
    p.add_argument("--max-render",type=int,default=3)
    p.add_argument("--crf",type=int,default=17)
    args=p.parse_args()
    output=Path(args.out).resolve()
    output.mkdir(parents=True,exist_ok=True)
    source=str(Path(args.source).resolve())
    duration=float(json.loads(command(["ffprobe","-v","error","-show_entries",
           "format=duration","-of","json",source]).stdout)["format"]["duration"])
    lo=max(0.,args.start);hi=min(duration,args.end)
    if hi<=lo+1:raise RuntimeError("Empty source range")
    print("SOURCE",source,"duration",duration,"range",lo,hi,flush=True)
    model=WhisperModel(args.model,device="cpu",compute_type="int8",cpu_threads=4)
    words=words_from_audio(model,source,lo,hi)
    problems=issues(words)
    silence=optional_silences(source,lo,hi)
    spans=build_spans(words,silence,lo,hi)
    (output/"word_timestamps.json").write_text(json.dumps(words,ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"transcript_review.json").write_text(json.dumps(problems,ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"continuous_cut_plan.json").write_text(json.dumps(
       {"range":[lo,hi],"full_coverage":True,"parts":spans,"word_count":len(words),
        "review_items":len(problems)},ensure_ascii=False,indent=2),encoding="utf-8")
    print("PLAN",len(spans),"parts","WORDS",len(words),"REVIEW",len(problems),flush=True)
    for i,span in enumerate(spans,1):
        print("PART",i,span["start"],span["end"],span["reason"],flush=True)
    limit=len(spans) if args.max_render==0 else min(args.max_render,len(spans))
    results=[]
    for i,span in enumerate(spans[:limit],1):
        record=render(source,span,words,output,i,args.crf)
        print("DONE",record["name"],record["words"],record["duration"],flush=True)
        results.append(record)
    (output/"rendered_parts.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print("RENDER_COMPLETE",len(results),flush=True)
if __name__=="__main__":main()
