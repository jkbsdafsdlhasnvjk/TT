#!/usr/bin/env python3
"""No watermark; preserve full user video and copied audio, re-render in vertical
frame with Russian corrected word-level burned subtitles in original orientation."""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0,"scripts")
from render_uploaded_scene import ASS_HEADER, sentence_groups, ass_line

SRC=Path("golyak_original.mp4").resolve()
OUT=Path("golyak_ready").resolve()
WORDS=Path("scripts/golyak_reviewed_words.json")
FILENAME="Kinogryz_Golyak_Belka_37s_Vertical_RU_Captions.mp4"
def run(args):
    return subprocess.check_output(args,stderr=subprocess.STDOUT,text=True)
def main():
    OUT.mkdir(exist_ok=True)
    meta=json.loads(run(["ffprobe","-v","error","-show_entries",
      "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
      "-of","json",str(SRC)]))
    dur=float(meta["format"]["duration"])
    assert abs(dur-37.233333)<.13,(dur,"unexpected source")
    vi=next(x for x in meta["streams"] if x["codec_type"]=="video")
    audio=next(x for x in meta["streams"] if x["codec_type"]=="audio")
    words=json.loads(WORDS.read_text(encoding="utf8"))
    assert 55<len(words)<110,len(words)
    assert words[0]["word"].lower().startswith("смотрите")
    assert words[-1]["word"].lower().startswith("перехват")
    for i,w in enumerate(words):
        assert 0<=w["start"]<w["end"]<=dur+.07,(i,w)
        assert w["word"].strip(),(i,w)
    groups=sentence_groups(words)
    prev=0.;lines=[]
    for i,group in enumerate(groups):
        nex=groups[i+1][0]["start"] if i+1<len(groups) else None
        a,b,ln=ass_line(group,0,dur,prev,nex)
        lines.append(ln)
        prev=b
    ass=OUT/"burned_word_subtitles.ass"
    ass.write_text(ASS_HEADER+"\n".join(lines)+"\n",encoding="utf8")
    (OUT/"corrected_transcript.txt").write_text(" ".join(w["word"] for w in words),encoding="utf8")
    (OUT/"corrected_word_timestamps.json").write_text(json.dumps(words,ensure_ascii=False,indent=2),encoding="utf8")
    # Keep full picture in center, use additional blurred duplicate as 9:16 canvas.
    # ASS subtitles are overlaid AFTER images; no hflip (no mirror) and no logo.
    graph=("[0:v]split=2[bgsrc][fgsrc];"
       "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,boxblur=22:2[bg];"
       "[fgsrc]scale=1080:-2:flags=lanczos[main];"
       f"[bg][main]overlay=x=(W-w)/2:y=(H-h)/2+45,ass={ass.as_posix()},format=yuv420p[v]")
    target=OUT/FILENAME
    ff=["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(SRC),
        "-filter_complex",graph,"-map","[v]","-map","0:a:0",
        "-c:v","libx264","-preset","slow","-crf","14","-pix_fmt","yuv420p",
        "-r",vi["r_frame_rate"],"-c:a","copy","-movflags","+faststart",str(target)]
    print("RENDER_BEGIN",dur,"words",len(words),"lines",len(lines),flush=True)
    subprocess.run(ff,check=True)
    result=json.loads(run(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
     "-of","json",str(target)]))
    outv=next(x for x in result["streams"] if x["codec_type"]=="video")
    outa=next(x for x in result["streams"] if x["codec_type"]=="audio")
    assert (outv["width"],outv["height"])==(1080,1920)
    assert audio["codec_name"]==outa["codec_name"]
    assert abs(dur-float(result["format"]["duration"]))<.15
    qa={"source":meta,"finished":result,"subtitle_word_count":len(words),"groups":len(lines),
       "no_mirror":True,"audio_bitstream_copy":True,"original_full_frame":True,
       "human_listening_reviewed":False,
       "subtitle_source":"large-v3 + medium + small word alignments, manually proofread candidate text"}
    (OUT/"quality_checks.json").write_text(json.dumps(qa,indent=2,ensure_ascii=False),encoding="utf8")
    print("RENDER_OK",target.name,"duration",result["format"]["duration"],
         "size",result["format"]["size"],"words",len(words),flush=True)
if __name__=="__main__":main()
