#!/usr/bin/env python3
"""Recover contiguous ~60-second clips from previously rendered long MP4s.

This is a technical reconstruction only, not an assertion that ASR is correct.
The previous captioned background is discarded, clean central image is retained,
and ASS captions are regenerated from original per-word timings.
"""
import argparse,json,subprocess,sys
from pathlib import Path
from serial_parts import build_spans,captions,issues

def cmd(*args):
    return subprocess.check_output(args,stderr=subprocess.STDOUT,text=True)
def ffprobe(path):
    return json.loads(cmd("ffprobe","-v","error","-show_entries",
      "format=duration,size:stream=codec_type,width,height,codec_name","-of","json",str(path)))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="long_archive")
    ap.add_argument("--output",default="recut_preview")
    ap.add_argument("--shard",type=int,default=1)
    ap.add_argument("--limit",type=int,default=3)
    ap.add_argument("--crf",type=int,default=18)
    a=ap.parse_args()
    root=Path(a.input);out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    recs=json.loads((root/"rendered_parts.json").read_text())
    transcript=json.loads((root/"word_timestamps.json").read_text())
    review=json.loads((root/"transcript_review.json").read_text())
    plan=json.loads((root/"continuous_cut_plan.json").read_text())
    print("ORIGINAL",len(recs),"records",len(transcript),"words",len(review),"suspects",flush=True)
    assert len(recs)==len(plan["parts"])
    assert recs[0]["start"]==plan["range"][0]
    assert recs[-1]["end"]==plan["range"][1]
    assert all(abs(recs[i]["end"]-recs[i+1]["start"])<.005 for i in range(len(recs)-1))
    # Verify every old file, and construct an exact demuxer timeline.
    accum=0.
    mapping=[]
    listfile=out/"concat.txt"
    with listfile.open("w") as fp:
      for i,r in enumerate(recs):
        src=(root/r["name"]).resolve()
        if not src.is_file():raise RuntimeError("Missing original rendered video: "+str(src))
        probe=ffprobe(src)
        dur=float(probe["format"]["duration"])
        assert abs(dur-(r["end"]-r["start"]))<.20,(i,dur,r)
        assert any(s.get("codec_type")=="video" and s.get("width")==1080 and s.get("height")==1920 for s in probe["streams"])
        assert any(s.get("codec_type")=="audio" for s in probe["streams"])
        fp.write("file '"+str(src).replace("'","'\\''")+"'\n")
        fp.write("duration "+str(dur)+"\n")
        mapping.append((r["start"],r["end"],accum,accum+dur))
        accum+=dur
    def convert(t):
      for lo,hi,a0,b0 in mapping:
        if lo-.001<=t<=hi+.001:
          return a0+(t-lo)*(b0-a0)/(hi-lo)
      raise ValueError("Timestamp outside source "+str(t))
    new_words=[]
    for w in transcript:
      try:
        x=dict(w,start=round(convert(w["start"]),3),end=round(convert(w["end"]),3))
      except ValueError:
        continue
      if x["end"]>x["start"]:new_words.append(x)
    new_words.sort(key=lambda w:w["start"])
    new_spans=build_spans(new_words,[],0.,round(accum,2))
    print("COVERAGE",plan["range"],"source_seconds",round(accum,2),"RECUT_PARTS",len(new_spans),flush=True)
    print("DURATION_BOUNDS",min(s["end"]-s["start"] for s in new_spans),max(s["end"]-s["start"] for s in new_spans),flush=True)
    print("SUSPECT_COUNT",len(issues(new_words)),flush=True)
    (out/"recut_plan.json").write_text(json.dumps({
      "original_range":plan["range"],"total_recovered_seconds":round(accum,3),
      "new_parts":new_spans,"original_file_count":len(recs),
      "original_suspect_asr":len(review),"quality_status":"NOT_LANGUAGE_VERIFIED"
    },indent=2,ensure_ascii=False))
    qa=[]
    for idx,span in enumerate(new_spans[:a.limit] if a.limit else new_spans,1):
      basename=f"Kinogryz_S01_recut_{a.shard:02}_{idx:04}"
      sub=out/(basename+".ass")
      captions(new_words,span,sub)
      target=out/(basename+".mp4")
      filt=(
        "[0:v]crop=1080:608:0:701,split=2[bgbase][main];"
        "[bgbase]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=1080:1920,boxblur=22:2[bg];"
        f"[bg][main]overlay=x=0:y=701,ass={sub.resolve().as_posix()},format=yuv420p[v]"
      )
      duration=round(span["end"]-span["start"],3)
      print("RENDER",basename,span["start"],span["end"],flush=True)
      subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
        "-ss",str(span["start"]),"-f","concat","-safe","0","-i",str(listfile),
        "-t",str(duration),"-filter_complex",filt,"-map","[v]","-map","0:a:0",
        "-c:v","libx264","-preset","veryfast","-crf",str(a.crf),"-r","25",
        "-c:a","aac","-b:a","192k","-movflags","+faststart",str(target)],check=True)
      actual=ffprobe(target)
      secs=float(actual["format"]["duration"])
      assert abs(secs-duration)<.16,(basename,secs,duration)
      assert any(s.get("codec_type")=="audio" for s in actual["streams"])
      qa.append({"name":target.name,"start":span["start"],"end":span["end"],"expected":duration,"actual":secs})
      print("PASS",basename,secs,flush=True)
    (out/"qa.json").write_text(json.dumps(qa,ensure_ascii=False,indent=2))
    print("DONE",len(qa),"videos","NOT_ASR_VERIFIED",flush=True)
if __name__=="__main__":main()
