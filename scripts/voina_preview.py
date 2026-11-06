#!/usr/bin/env python3
"""Generate an actual 1080x1920 screenshot for approval; no full MP4 render."""
import json,subprocess,base64
from pathlib import Path
from render_uploaded_scene import ASS_HEADER,sentence_groups,ass_line,fmt

source=Path("voina.mp4").resolve()
out=Path("voina_preview");out.mkdir(exist_ok=True)
data=json.loads(Path("voina_asr/medium_segments.json").read_text(encoding="utf-8"))
duration=32.6
words=[]
for row in data:
    for w in row["words"]:
        words.append({"start":w["start"],"end":w["end"],"word":w["word"]})
# Minimal proofreading of the representative line from the source video.
for w in words:
    if 9.0<w["start"]<12.7 and "фостер" in w["word"].lower():
        w["word"]="Фостера"
groups=sentence_groups(words)
events=[]
prev=0
for i,g in enumerate(groups):
    nxt=groups[i+1][0]["start"] if i+1<len(groups) else None
    start,end,line=ass_line(g,0,duration,prev,nxt)
    events.append(line);prev=end
style=("Style: Brand,DejaVu Sans,46,&H65FFFFFF,&H65FFFFFF,&H00000000,&H90000000,"
       "0,0,0,0,100,100,1.5,0,1,0,0,5,50,50,0,1\n")
header=ASS_HEADER.replace("[Events]",style+"[Events]")
brand=r"Dialogue: 1,0:00:00.00,0:00:32.60,Brand,,0,0,0,,{\\an5\\pos(540,1665)}КиноГрызь"
ass=out/"preview_subtitle_and_brand.ass"
ass.write_text(header+"\n".join(events)+"\n"+brand+"\n",encoding="utf-8")
vf=("[0:v]split=2[b][f];"
    "[b]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,boxblur=22:2[bg];"
    "[f]scale=1080:-2:flags=lanczos[fg];"
    f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2+45,ass={ass.resolve().as_posix()},format=yuv420p[v]")
shot=out/"Kinogryz_brand_preview_1080x1920.png"
subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(source),"-ss","10.65",
   "-filter_complex",vf,"-map","[v]","-frames:v","1",str(shot)],check=True)
# Generate compact preview for in-chat display and preserve full-res original.
from PIL import Image
import io
im=Image.open(shot).convert("RGB");small=im.copy();small.thumbnail((720,1280))
buf=io.BytesIO();small.save(buf,"JPEG",quality=76,optimize=True)
print("SCREENSHOT_READY",str(shot),shot.stat().st_size,flush=True)
print("IMAGE_PREVIEW_B64_START",flush=True)
print(base64.b64encode(buf.getvalue()).decode(),flush=True)
print("IMAGE_PREVIEW_B64_END",flush=True)
