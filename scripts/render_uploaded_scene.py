#!/usr/bin/env python3
"""Watermark-free render of the actual uploaded clip with burned-in per-word ASS captions."""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

ASS_HEADER="""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,DejaVu Sans,56,&H00FFFFFF,&H0000FFFF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,4,1,8,50,50,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
def run(args):
    return subprocess.check_output(args,stderr=subprocess.STDOUT)
def fmt(t):
    cs=int(round(max(0,t)*100));h,cs=divmod(cs,360000);m,cs=divmod(cs,6000);s,cs=divmod(cs,100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
def words_in(segments, corrections):
    out=[]
    for s in segments:
        for w in s.get("words",[]):
            if not 0<=w["start"]<w["end"]:continue
            token=w["word"].strip()
            if not token:continue
            # User-required on-screen censorship: any grammatical casing,
            # punctuation or model's common typo for the same spoken word.
            bare=re.sub(r"^[^а-яё]+|[^а-яё]+$", "",token.lower())
            if bare in ("шалава", "шолава", "шалова"):
                token="******"+("!" if token.endswith("!") else ("?" if token.endswith("?") else ""))
            out.append({"start":w["start"],"end":w["end"],"word":token,"confidence":w.get("prob",1.)})
    simple=corrections.get("words",[]) if isinstance(corrections,dict) else corrections
    for c in simple:
        idx=int(c["index"])
        if idx<0 or idx>=len(out):raise ValueError(f"Invalid manual correction word index {idx}")
        assert out[idx]["word"]==c["expected"], f"Correction mismatch at {idx}: expected {c['expected']}, got {out[idx]['word']}"
        out[idx]["word"]=c["replace"]
    drops=corrections.get("drop_indices",[]) if isinstance(corrections,dict) else []
    for idx in sorted((int(x) for x in drops),reverse=True):
        assert 0<=idx<len(out)
        del out[idx]
    splices=corrections.get("splices",[]) if isinstance(corrections,dict) else []
    for p in sorted(splices,key=lambda x:x["from"],reverse=True):
        a,b=int(p["from"]),int(p["to"])
        assert 0<=a<=b<len(out)
        old=" ".join(w["word"] for w in out[a:b+1])
        assert old==p["expected"],f"Splice mismatch at {a}: {old}"
        repl=[{"start":w["start"],"end":w["end"],"word":w["word"],"confidence":1.}
              for w in p["replace"]]
        assert all(repl[i]["start"]<repl[i]["end"] for i in range(len(repl)))
        out[a:b+1]=repl
    for w in out:
        bare=re.sub(r"^[^а-яё]+|[^а-яё]+$","",w["word"].lower())
        if bare in ("шалава","шолава","шалова"):w["word"]="******"
    return out
def sentence_groups(words):
    groups=[];current=[]
    for w in words:
        last=current[-1] if current else None
        boundary=bool(last and (last["word"].endswith((".","?","!","…")) or w["start"]-last["end"]>.55))
        long=bool(current and (len(current)>=8 or sum(len(x["word"])+1 for x in current)>43))
        if current and (boundary or long):
            groups.append(current);current=[]
        current.append(w)
    if current:groups.append(current)
    return groups
def ass_line(group,starts,end,previous_end,next_start):
    first=group[0]["start"];last=group[-1]["end"]
    a=max(0,first-.15,previous_end)
    b=min(end,last+.42,next_start-.045 if next_start is not None else end)
    if b<=a:raise RuntimeError("Overlapping caption blocks")
    plain=[w["word"].replace("{","").replace("}","").replace("\\","") for w in group]
    if sum(len(x)+1 for x in plain)>34 and len(group)>=3:
        tally=0;mid=len(group)
        for j,x in enumerate(plain[:-1]):
            tally+=len(x)+1
            if tally>=sum(len(x)+1 for x in plain)/2:
                mid=j+1;break
    else:mid=len(group)
    encoded=[]
    for j,(w,token) in enumerate(zip(group,plain)):
        onset=max(a,w["start"]-.03)
        next_onset=(group[j+1]["start"]-.03 if j+1<len(group) else w["end"]+.07)
        off=min(b,max(onset+.025,next_onset))
        x=max(0,round((onset-a)*1000))
        y=max(x+1,round((off-a)*1000))
        if x==0:
            effect="{\\1c&H00D7FF&"+f"\\t({y},{y+1},\\1c&HFFFFFF&)"+"}"
        else:
            effect="{\\1c&HFFFFFF&"+f"\\t({x},{x+1},\\1c&H00D7FF&)\\t({y},{y+1},\\1c&HFFFFFF&)"+"}"
        encoded.append(effect+token)
    content=" ".join(encoded[:mid])+(r"\N"+" ".join(encoded[mid:]) if mid<len(encoded) else "")
    return a,b,f"Dialogue: 0,{fmt(a)},{fmt(b)},Karaoke,,0,0,0,,{{\\an8\\pos(540,1390)}}{content}"
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="scene.mp4")
    p.add_argument("--segments",default="scene_asr/medium_segments.json")
    p.add_argument("--corrections",default="scripts/scene_uploaded_corrections.json")
    p.add_argument("--output",default="КиноГрызь_сцена_вертикальная_субтитры.mp4")
    p.add_argument("--mirror-video-only",action="store_true",help="Flip video before adding ASS captions; subtitles stay normal and readable")
    args=p.parse_args()
    source=Path(args.source).resolve()
    report=Path("scene_render")
    report.mkdir(exist_ok=True)
    segs=json.loads(Path(args.segments).read_text(encoding="utf-8"))
    patches=json.loads(Path(args.corrections).read_text(encoding="utf-8")) if Path(args.corrections).exists() else []
    meta=json.loads(run(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate",
                          "-of","json",str(source)]))
    duration=float(meta["format"]["duration"])
    words=words_in(segs,patches)
    tailfile=Path("scripts/scene_uploaded_tail.json")
    if tailfile.exists():
        tail=json.loads(tailfile.read_text(encoding="utf-8"))
        words.extend({"start":w["start"],"end":w["end"],"word":w["word"],"confidence":w.get("confidence",.9)} for w in tail)
        words.sort(key=lambda w:w["start"])
    if len(words)<10:raise RuntimeError("Insufficient speech recognition for subtitles")
    groups=sentence_groups(words)
    lines=[];prev=0
    for i,g in enumerate(groups):
        nxt=groups[i+1][0]["start"] if i+1<len(groups) else None
        a,b,ln=ass_line(g,0,duration,prev,nxt)
        prev=b
        lines.append(ln)
    ass=report/"scene_captions.ass"
    ass.write_text(ASS_HEADER+"\n".join(lines)+"\n",encoding="utf-8")
    transcript=" ".join(w["word"] for w in words)
    (report/"screen_transcript.txt").write_text(transcript,encoding="utf-8")
    (report/"word_timestamps_final.json").write_text(json.dumps(words,ensure_ascii=False,indent=2),encoding="utf-8")
    for w in words:
        if re.search("шалав",w["word"].lower()):
            raise RuntimeError("User-requested censored word still visible")
    # Keep ALL original footage, preserve original frame cadence and audio bitstream.
    # Main frame is NEVER cropped; the extra vertical canvas is a blurred duplicate.
    video_input="[0:v]hflip,split=2[b][fg];" if args.mirror_video_only else "[0:v]split=2[b][fg];"
    graph=(video_input
           "[b]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,boxblur=20:2[bg];"
           "[fg]scale=1080:-2:flags=lanczos,unsharp=3:3:0.18[main];"
           f"[bg][main]overlay=x=(W-w)/2:y=(H-h)/2+65,ass={ass.as_posix()},format=yuv420p[v]")
    ff=["ffmpeg","-hide_banner","-y","-loglevel","error","-i",str(source),"-filter_complex",graph,
        "-map","[v]","-map","0:a:0","-c:v","libx264","-preset","slow","-crf","14",
        "-pix_fmt","yuv420p","-c:a","copy","-movflags","+faststart",args.output]
    print("RENDER",len(words),"words",len(groups),"groups","original",meta["streams"],flush=True)
    subprocess.run(ff,check=True)
    final=json.loads(run(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
          "-of","json",args.output]))
    video=[x for x in final["streams"] if x["codec_type"]=="video"]
    audio=[x for x in final["streams"] if x["codec_type"]=="audio"]
    assert len(video)==1 and video[0]["width"]==1080 and video[0]["height"]==1920
    assert len(audio)>=1
    assert abs(float(final["format"]["duration"])-duration)<.14
    (report/"quality_check.json").write_text(json.dumps({"original":meta,"output":final,"subtitle_words":len(words),"subtitle_phrases":len(groups),"censored":transcript.count("******")},ensure_ascii=False,indent=2))
    print("RENDERED_OK",args.output,"original_sec",duration,"output_sec",final["format"]["duration"],"masked",transcript.count("******"),"bytes",final["format"]["size"],flush=True)
if __name__=="__main__":main()
