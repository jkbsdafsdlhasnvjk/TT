#!/usr/bin/env python3
"""Render the user's original 41s pony scene in portrait with visible per-word subtitles.
No cuts, no mirroring, no watermark, original audio bitstream copied."""
import json, subprocess, re, sys
from pathlib import Path

sys.path.insert(0, "scripts")
from render_uploaded_scene import ASS_HEADER, sentence_groups, ass_line

def cmd(args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True)

def get_words(src, corrections):
    segments=json.loads(Path(src).read_text(encoding="utf-8"))
    words=[]
    for segment in segments:
        for w in segment.get("words",[]):
            if w.get("start") is None or w.get("end") is None:
                continue
            if w["end"]<=w["start"]:continue
            words.append({"start":float(w["start"]),"end":float(w["end"]),
                          "word":w["word"].strip(),"prob":w.get("prob",0)})
    fixes=json.loads(Path(corrections).read_text(encoding="utf-8"))
    replacements=fixes["words"]
    if len(words)!=len(replacements):
        raise RuntimeError(f"Wrong source ASR word count {len(words)} != {len(replacements)}")
    for i,(word,replacement) in enumerate(zip(words,replacements)):
        if not replacement:
            raise RuntimeError(f"Empty corrected transcript item {i}, {word}")
        word["before"]=word["word"]
        word["word"]=replacement
    # Two weak ASR tokens sometimes span a single Russian profanity.
    for item in sorted(fixes.get("merges",[]), key=lambda p:p["from"],reverse=True):
        a,b=int(item["from"]),int(item["to"])
        if not (0<=a<b<len(words)):raise RuntimeError("Bad word merge")
        merged=dict(words[a])
        merged["end"]=words[b]["end"]
        merged["word"]=item["text"]
        words[a:b+1]=[merged]
    words.sort(key=lambda x:x["start"])
    return words

def main():
    src=Path("pony.mp4").resolve()
    dest=Path("pony_finished").resolve();dest.mkdir(exist_ok=True)
    meta=json.loads(cmd(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate","-of","json",str(src)]))
    duration=float(meta["format"]["duration"])
    video=next(s for s in meta["streams"] if s["codec_type"]=="video")
    audio=next(s for s in meta["streams"] if s["codec_type"]=="audio")
    words=get_words("pony_asr/medium_segments.json","scripts/pony_manual_corrections.json")
    if words[-1]["end"]>duration+.1:raise RuntimeError("Last word after end")
    if len(words)<40:raise RuntimeError("Insufficient speech words")
    caption_groups=sentence_groups(words)
    captions=[];previous=0.0
    for i,g in enumerate(caption_groups):
        nxt=caption_groups[i+1][0]["start"] if i+1<len(caption_groups) else None
        a,b,row=ass_line(g,0,duration,previous,nxt)
        captions.append(row);previous=b
    ass=dest/"pony_subtitles_corrected.ass"
    ass.write_text(ASS_HEADER+"\n".join(captions)+"\n",encoding="utf8")
    (dest/"pony_words_corrected.json").write_text(json.dumps(words,indent=2,ensure_ascii=False),encoding="utf8")
    (dest/"pony_full_transcript.txt").write_text(" ".join(w["word"] for w in words),encoding="utf8")
    # 9:16 blurred duplicate background; complete original frame in the center,
    # NO cropped action, NO mirroring, subtitles composited AFTER video.
    vf=(
      "[0:v]split=2[bgsrc][fgsrc];"
      "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,boxblur=22:2[bg];"
      "[fgsrc]scale=1080:-2:flags=lanczos[fg];"
      f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2+45,ass={ass.as_posix()},format=yuv420p[v]"
    )
    output=dest/"Kinogryz_Pony_41s_Vertical_Synced_RU_Captions.mp4"
    ff=["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(src),
      "-filter_complex",vf,"-map","[v]","-map","0:a:0",
      "-c:v","libx264","-preset","slow","-crf","14",
      "-pix_fmt","yuv420p","-r",video["r_frame_rate"],"-c:a","copy",
      "-movflags","+faststart",str(output)]
    print("RENDER_START",duration,"original",video,"captions",len(words),"phrases",len(captions),flush=True)
    subprocess.run(ff,check=True)
    new=json.loads(cmd(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate","-of","json",str(output)]))
    streams=new["streams"]
    vi=next(s for s in streams if s["codec_type"]=="video")
    au=next(s for s in streams if s["codec_type"]=="audio")
    assert (vi["width"],vi["height"])==(1080,1920)
    assert au["codec_name"]==audio["codec_name"],"Original audio not preserved"
    assert abs(float(new["format"]["duration"])-duration)<.15,"Duration truncated"
    report={"input":meta,"output":new,"words":len(words),"phrases":len(captions),"mirrored":False,"watermark":False,"censored_count":sum(w["word"].count("******") for w in words)}
    (dest/"quality_check.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf8")
    print("RENDERED_OK",output.name,"duration",new["format"]["duration"],"size",new["format"]["size"],"words",len(words),flush=True)

if __name__=="__main__":main()
