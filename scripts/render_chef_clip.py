#!/usr/bin/env python3
"""Restore clean picture from an older captioned vertical render, correct every
subtitle, cut after chef's compliment line; normal (unmirrored) picture."""
import json
import re
import subprocess
from pathlib import Path
from render_uploaded_scene import ASS_HEADER, sentence_groups, ass_line

SOURCE_OFFSET=3804.43
CUT=32.58
# Corrected dialogue and preserved matching word-timestamp positions.
# Each key is the absolute second in the original season.
CORRECTIONS={
 3804.71:["Педя!"],
 3805.45:["Да,","шеф?"],
 3806.43:["Дуй","в","аптеку."],
 3808.66:["Ой,","шеф,","классика."],
 3810.96:["А","гусок?"],
 3811.50:["Где","гусь?"],
 3815.02:["Я","его","только","что","прикончил."],
 3816.84:["А","что","ты","такой","чистенький?"],
 3818.20:["Что,","ни","капельки","крови","на","тебя","не","попало?"],
 3820.30:["Я","его","не","зарезал,","я","его","задушил."],
 3824.56:["Какой","ужас."],
 3826.16:["Ладно,","Отелло,","тащи","свою","Дездемону","су-шефу."],
 3829.20:["Лёва,","начинай","готовить","гуся,","а","то","время","уже."],
 3832.82:["Ой,","шеф,","а","я","займусь","комплиментом","от","шефа."],
}

def command(args):
    return subprocess.check_output(args,stderr=subprocess.STDOUT,text=True)

def adjusted_words(segs):
    output=[]
    seen=[]
    for s in segs:
        t=s["start"]
        if t<SOURCE_OFFSET-.1 or t>SOURCE_OFFSET+CUT+.05:continue
        old=s.get("words",[])
        if not old: continue
        key=min(CORRECTIONS,key=lambda k:abs(k-t))
        if abs(key-t)>.3:
            raise ValueError("An unreviewed spoken segment at "+str(t)+": "+s.get("text",""))
        corrected=CORRECTIONS[key]
        seen.append(key)
        # ASR occasionally glued 'А гусок?' and split 'су-шефу'.
        if abs(key-3810.96)<.1:
            if len(old)!=1:raise ValueError("Unexpected goose token count")
            z=old[0]
            midpoint=z["start"]+.2*(z["end"]-z["start"])
            aligned=[(z["start"],midpoint,corrected[0]),(midpoint,z["end"],corrected[1])]
        elif abs(key-3826.16)<.1:
            if len(old)!=7:raise ValueError("Unexpected Othello phrase count")
            aligned=[(w["start"],w["end"],new) for w,new in zip(old[:5],corrected[:5])]
            aligned.append((old[5]["start"],old[6]["end"],corrected[5]))
        else:
            if len(old)!=len(corrected):
                raise ValueError(f"Mismatch near {key}: got {len(old)} versus {len(corrected)}")
            aligned=[(w["start"],w["end"],new) for w,new in zip(old,corrected)]
        for a,b,word in aligned:
            begin=round(a-SOURCE_OFFSET,3)
            end=round(b-SOURCE_OFFSET,3)
            if begin<0 or end>CUT:raise ValueError(f"Subtitle word outside video {word}")
            output.append({"start":begin,"end":end,"word":word})
    if set(seen)!=set(CORRECTIONS):
        raise ValueError("Missing dialogue lines: "+str(set(CORRECTIONS)-set(seen)))
    output.sort(key=lambda w:w["start"])
    assert output[0]["word"]=="Педя!"
    assert output[-1]["word"]=="шефа."
    return output

def main():
    path=Path("source_candidates")
    src=path/"Kinogryz_S01_01h03m_05.mp4"
    words=adjusted_words(json.loads((path/"transcript.json").read_text()))
    dest=Path("chef_final")
    dest.mkdir(exist_ok=True)
    subtitles=dest/"chef_corrected.ass"
    groups=sentence_groups(words)
    lines=[]
    previous=0.
    for i,group in enumerate(groups):
        nex=groups[i+1][0]["start"] if i+1<len(groups) else None
        a,b,line=ass_line(group,0,CUT,previous,nex)
        lines.append(line)
        previous=b
    subtitles.write_text(ASS_HEADER+"\n".join(lines)+"\n",encoding="utf8")
    (dest/"corrected_words.json").write_text(json.dumps(words,indent=2,ensure_ascii=False),encoding="utf-8")
    title="Kinogryz_Chef_Kompliment_33s_corrected_not_mirrored.mp4"
    target=dest/title
    # Prior vertical 1080x1920 frame was constructed with main 1080x608
    # at y=701, and captions below it at y=1390.
    # Extract only clean central picture and recompose blurred background.
    # This eliminates *all* earlier burned-in wrong subtitle glyphs.
    vf=(
      "[0:v]crop=1080:608:0:701,split=2[bgbase][main];"
      "[bgbase]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
      "crop=1080:1920,boxblur=22:2[bg];"
      f"[bg][main]overlay=x=0:y=701,ass={subtitles.resolve().as_posix()},format=yuv420p[v]"
    )
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(src),
      "-t",str(CUT),"-filter_complex",vf,"-map","[v]","-map","0:a:0",
      "-c:v","libx264","-preset","slow","-crf","16","-pix_fmt","yuv420p",
      "-c:a","copy","-movflags","+faststart",str(target)]
    print("RENDER",len(words),"corrected words",len(groups),"caption groups",flush=True)
    subprocess.run(cmd,check=True)
    meta=json.loads(command(["ffprobe","-v","error","-show_entries",
      "format=duration,size:stream=codec_type,codec_name,width,height",
      "-of","json",str(target)]))
    streams=meta["streams"]
    assert any(s.get("codec_type")=="video" and s.get("width")==1080 and s.get("height")==1920 for s in streams)
    assert any(s.get("codec_type")=="audio" for s in streams)
    assert abs(float(meta["format"]["duration"])-CUT)<.15
    (dest/"qa.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding="utf-8")
    print("RENDER_OK",title,"length",meta["format"]["duration"],"bytes",meta["format"]["size"],flush=True)
if __name__=="__main__": main()
