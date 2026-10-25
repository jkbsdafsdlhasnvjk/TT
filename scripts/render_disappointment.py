#!/usr/bin/env python3
"""Loss-conscious, watermark-free vertical rendering of the user's Disenchantment clip.
Word timings from audio with medium Whisper no-VAD, compared with two other reads.
Subtitles are burned AFTER background and centered original picture are composed."""
import json, subprocess, sys, re
from pathlib import Path
sys.path.insert(0,"scripts")
from render_uploaded_scene import ASS_HEADER, sentence_groups, ass_line
SRC=Path("disappointment.mp4").resolve()
OUT=Path("disappointment_ready").resolve()
LENGTH=44.936667

# Exact indexed corrections preserve the speech timing from the medium non-VAD
# word timestamp run. Song lyrics are more reliable with VAD disabled.
REPLACE={
 0:"Ты",1:"никогда",2:"не",3:"мечтала",4:"найти",5:"место,",
 6:"где",7:"люди",8:"счастливы",
 11:"Всюду",12:"ха",13:"-ха",14:"-ха,",15:"всюду",
 16:"тра",17:"-ла",18:"-ла.",
 19:"Жизнь",20:"эльфийская",21:"весела.",
 22:"Рад",23:"трудиться",24:"народ",25:"весной.",
 26:"Ну,",27:"он",28:"слабый,",29:"но",30:"чистый",31:"душой.",
 32:"От",33:"счастья",34:"песни",35:"поём",36:"мы",37:"днём.",
 38:"А",39:"по",40:"ночам",41:"беспробудно",42:"пьём.",
 43:"Так",44:"что",45:"хо",46:"-хо",47:"-хо,",
 48:"так",49:"что",50:"трам",51:"-пам",52:"-пам.",
 53:"А",54:"сейчас",55:"припев",56:"просвистим",57:"вам."
}
MERGES=[
 (9,10,"по-настоящему?"),
 (12,14,"ха-ха-ха,"),
 (16,18,"тра-ла-ла."),
 (45,47,"хо-хо-хо,"),
 (50,52,"трам-пам-пам.")
]
def call(args):return subprocess.check_output(args,stderr=subprocess.STDOUT,text=True)
def words_from_asr():
    d=json.loads(Path("disappointment_song_review.json").read_text(encoding="utf8"))
    original=[dict(w) for seg in d["medium_no_vad"] for w in seg["words"]]
    assert len(original)==60,(len(original),"Expected original alignment to have 60 tokens")
    for i in (58,59):
        assert original[i]["word"].lower() in ("спокойная","музыка")
    original=original[:58] # Delete hallucinated credit/music cues (no actual spoken words)
    for i,w in enumerate(original):
        if i in REPLACE:w["word"]=REPLACE[i]
    for a,b,value in sorted(MERGES,reverse=True):
        assert 0<=a<b<len(original),(a,b)
        first=dict(original[a])
        first["end"]=original[b]["end"]
        first["word"]=value
        original[a:b+1]=[first]
    original.sort(key=lambda w:w["start"])
    assert len(original)==48, (len(original),"unexpected postmerge count")
    assert original[-1]["word"]=="вам."
    assert original[-1]["end"]<27
    return original
def main():
    OUT.mkdir(exist_ok=True)
    inp=json.loads(call(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate","-of","json",str(SRC)]))
    duration=float(inp["format"]["duration"])
    assert abs(duration-LENGTH)<.12,("Wrong input",duration)
    vi=next(x for x in inp["streams"] if x["codec_type"]=="video")
    au=next(x for x in inp["streams"] if x["codec_type"]=="audio")
    words=words_from_asr()
    groups=sentence_groups(words)
    lines=[];prev=0.
    for i,g in enumerate(groups):
        nxt=groups[i+1][0]["start"] if i+1<len(groups) else None
        a,b,line=ass_line(g,0,duration,prev,nxt)
        lines.append(line);prev=b
    ass=OUT/"subtitles_embedded_source.ass"
    ass.write_text(ASS_HEADER+"\n".join(lines)+"\n",encoding="utf8")
    (OUT/"word_timestamps.json").write_text(json.dumps(words,ensure_ascii=False,indent=2),encoding="utf8")
    (OUT/"reviewed_transcript.txt").write_text(" ".join(x["word"] for x in words),encoding="utf8")
    # Compose original complete clean frame, blurred duplicate only in letterbox space.
    # Note hflip is deliberately NOT applied (per last user preference).
    vf=("[0:v]split=2[bgsrc][fgsrc];"
        "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,boxblur=22:2[bg];"
        "[fgsrc]scale=1080:-2:flags=lanczos[fg];"
        f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2+45,ass={ass.as_posix()},format=yuv420p[v]")
    out=OUT/"Kinogryz_Razocharovanie_45s_Vertical_Subtitles.mp4"
    ff=["ffmpeg","-hide_banner","-y","-loglevel","error","-i",str(SRC),
        "-filter_complex",vf,"-map","[v]","-map","0:a:0",
        "-c:v","libx264","-preset","slow","-crf","14","-pix_fmt","yuv420p",
        "-r",vi["r_frame_rate"],"-c:a","copy","-movflags","+faststart",str(out)]
    print("RENDER_START",len(words),"words",len(groups),"caption groups",flush=True)
    subprocess.run(ff,check=True)
    output=json.loads(call(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate","-of","json",str(out)]))
    ovi=next(x for x in output["streams"] if x["codec_type"]=="video")
    oau=next(x for x in output["streams"] if x["codec_type"]=="audio")
    assert (ovi["width"],ovi["height"])==(1080,1920)
    assert oau["codec_name"]==au["codec_name"]
    assert abs(float(output["format"]["duration"])-duration)<.15
    (OUT/"qa_report.json").write_text(json.dumps({"input":inp,"output":output,"caption_words":len(words),"caption_groups":len(groups),"mirrored":False,"source_audio_copied":True,"caption_method":"medium no VAD + manual correction of obvious recognition issues","caveat":"Singing-word exactness inferred; not individually listened to by a person."},ensure_ascii=False,indent=2),encoding="utf8")
    print("RENDERED_OK",out.name,"duration",output["format"]["duration"],"size",output["format"]["size"],"words",len(words),flush=True)
if __name__=="__main__":main()
