#!/usr/bin/env python3
"""Men of Honor: transcribe Russian speech, validate word times, produce stable two-line ASS captions, render without mirror."""
import argparse,json,re,subprocess
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel

HEADER="""[Script Info]
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
def cmd(xs):
    print("RUN",xs[:6],flush=True)
    subprocess.run(xs,check=True)
def timestamp(t):
    cs=round(max(0,t)*100)
    h,cs=divmod(cs,360000);m,cs=divmod(cs,6000);s,cs=divmod(cs,100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"
def regroup(words):
    rows=[];row=[]
    for w in words:
        prev=row[-1] if row else None
        gap=w["start"]-prev["end"] if prev else 0
        boundary=prev and (gap>.42 or prev["word"].endswith((".","?","!","…")))
        oversize=len(row)>=8 or sum(len(z["word"])+1 for z in row)+len(w["word"])>48
        if row and (boundary or oversize):
            rows.append(row);row=[]
        row.append(w)
    if row:rows.append(row)
    return rows
def create_ass(words,length,path):
    rows=regroup(words)
    starts=[]
    for row in rows:starts.append(max(0.0,row[0]["start"]-.13))
    events=[]
    for i,row in enumerate(rows):
        t0=starts[i]
        if i: t0=max(t0,rows[i-1][-1]["end"]+.005)
        t1=min(length,row[-1]["end"]+.68)
        if i+1<len(rows):t1=min(t1,starts[i+1]-.025)
        if t1<=t0:t1=t0+.05
        clean=[re.sub(r"[{}\\]","",x["word"]) for x in row]
        total=sum(len(x)+1 for x in clean)
        split=len(clean)
        if total>35 and len(clean)>=3:
            sub=0
            for j,x in enumerate(clean[:-1]):
                sub+=len(x)+1
                if sub>=total/2:
                    split=j+1;break
        part=[]
        for j,(w,txt) in enumerate(zip(row,clean)):
            on=max(t0,w["start"]-.04)
            off=min(t1,((row[j+1]["start"]-.04) if j+1<len(row) else w["end"]+.03))
            off=max(off,on+.015)
            a=max(0,round((on-t0)*1000));b=max(a+1,round((off-t0)*1000))
            if a==0:effect="{\\1c&H00D7FF&"+f"\\t({b},{b+1},\\1c&HFFFFFF&)"+"}"
            else:effect="{\\1c&HFFFFFF&"+f"\\t({a},{a+1},\\1c&H00D7FF&)\\t({b},{b+1},\\1c&HFFFFFF&)"+"}"
            part.append(effect+txt)
        inner=" ".join(part[:split])+(r"\N"+" ".join(part[split:]) if split<len(part) else "")
        events.append(f"Dialogue: 0,{timestamp(t0)},{timestamp(t1)},Karaoke,,0,0,0,,{{\\an8\\pos(540,1390)}}{inner}")
    path.write_text(HEADER+"\n".join(events)+"\n",encoding="utf-8")
    print("SUBTITLES",len(words),"words",len(rows),"stable phrases",flush=True)
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    output=Path("men_render");output.mkdir(exist_ok=True)
    probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_type,width,height","-of","json",args.source]))
    length=float(probe["format"]["duration"])
    audio=subprocess.check_output(["ffmpeg","-v","error","-i",args.source,"-vn","-ac","1","-ar","16000","-f","s16le","-"])
    audio=np.frombuffer(audio,dtype=np.int16).astype(np.float32)/32768.0
    print("TRANSCRIBE medium ru WAV secs",round(len(audio)/16000,2),flush=True)
    model=WhisperModel("medium",device="cpu",compute_type="int8",cpu_threads=4)
    segments,_=model.transcribe(audio,language="ru",word_timestamps=True,beam_size=5,temperature=0.,
                                condition_on_previous_text=False,vad_filter=True,vad_parameters={"min_silence_duration_ms":290})
    words=[]
    segment_rows=[]
    for s in segments:
        word_items=[]
        for w in s.words or []:
            if w.start is None or w.end is None or not w.word.strip():continue
            if w.end<=w.start or w.start<0 or w.start>length+.05:continue
            z={"start":round(float(w.start),3),"end":round(min(length,float(w.end)),3),"word":w.word.strip(),
               "probability":round(float(w.probability or 0),3)}
            if z["end"]<=z["start"]:continue
            word_items.append(z);words.append(z)
        segment_rows.append({"start":s.start,"end":s.end,"text":s.text.strip(),"words":word_items})
        print("SPEECH",round(s.start,1),s.text.strip(),flush=True)
    words.sort(key=lambda z:z["start"])
    (output/"speech_words.json").write_text(json.dumps(words,ensure_ascii=False,indent=2))
    (output/"speech_segments.json").write_text(json.dumps(segment_rows,ensure_ascii=False,indent=2))
    (output/"transcript.txt").write_text(" ".join(w["word"] for w in words),encoding="utf-8")
    if len(words)<45:raise RuntimeError("Automatic Russian speech recognition returned too few spoken words")
    ass=output/"captions.ass"
    rows=create_ass(words,length,ass)
    graph=("[0:v]split=2[b][fg];"
           "[b]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
           "crop=1080:1920,boxblur=20:2[bg];"
           "[fg]scale=1080:-2:flags=lanczos,unsharp=3:3:0.15[main];"
           "[bg][main]overlay=x=(W-w)/2:y=(H-h)/2+65,"
           f"ass={ass.as_posix()},format=yuv420p[v]")
    cmd(["ffmpeg","-hide_banner","-y","-loglevel","error","-i",args.source,"-filter_complex",graph,
         "-map","[v]","-map","0:a:0","-c:v","libx264","-preset","veryfast","-crf","17",
         "-r","30","-pix_fmt","yuv420p","-c:a","copy","-movflags","+faststart",args.output])
    result=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,width,height","-of","json",args.output]))
    streams=result["streams"];v=next(x for x in streams if x["codec_type"]=="video")
    assert (v["width"],v["height"])==(1080,1920)
    assert any(x["codec_type"]=="audio" for x in streams)
    assert abs(float(result["format"]["duration"])-length)<.3
    (output/"quality_check.json").write_text(json.dumps({"input":probe,"output":result,"words":len(words),"phrases":len(rows)},ensure_ascii=False,indent=2))
    print("COMPLETE",args.output,"DURATION",result["format"]["duration"],"BYTES",result["format"]["size"],flush=True)
if __name__=="__main__":main()
