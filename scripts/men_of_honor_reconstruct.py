#!/usr/bin/env python3
"""Reconstruct original reference edit from full 1080p Men of Honor master.
Independent cut per source shot; run source fingerprint consistency validation."""
import argparse,json,subprocess,math
from pathlib import Path

def call(argv):
 print("RUN", " ".join(str(a) for a in argv[:12]),flush=True)
 subprocess.run([str(a) for a in argv],check=True,stdout=subprocess.DEVNULL)
def probe(path):
 return json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,width,height","-of","json",path]))

def dp_select(rows):
 # The user montage tells a chronological story; strong temporal coherence is
 # needed because unrelated images can have accidentally similar 256-bit hashes.
 starts=[(float(q["clip_start"])+float(q["clip_end"]))/2 for q in rows]
 layers=[]
 for i,row in enumerate(rows):
  opts=row["matches"]
  choices=[]
  for j,option in enumerate(opts):
   second=float(option["movie_second"]); emission=float(option["distance"])
   if not i:
    choices.append((emission,-1))
    continue
   best=None
   for k,prev in enumerate(rows[i-1]["matches"]):
    prior=layers[-1][k][0]
    srcdiff=second-float(prev["movie_second"])
    clipdiff=starts[i]-starts[i-1]
    if srcdiff < -1.2:
     transition=95+min(100,abs(srcdiff)*.2)
    elif srcdiff < 0:
     transition=12
    else:
     transition=.014*max(0,srcdiff-clipdiff)
     if abs(srcdiff-clipdiff)<1.3:transition-=17
     elif abs(srcdiff-clipdiff)<4:transition-=9
     elif abs(srcdiff-clipdiff)<12:transition-=3
    trial=prior+emission+transition
    if best is None or trial<best[0]:best=(trial,k)
   choices.append(best)
  layers.append(choices)
 j=min(range(len(layers[-1])),key=lambda k:layers[-1][k][0])
 pick=[]
 for i in range(len(rows)-1,-1,-1):
  pick.append(rows[i]["matches"][j]);j=layers[i][j][1]
 pick.reverse()
 return pick
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--movie",required=True);p.add_argument("--shots",required=True)
 p.add_argument("--matches",required=True);p.add_argument("--output",required=True)
 args=p.parse_args()
 shots=json.load(open(args.shots))
 rows=json.load(open(args.matches))
 assert len(shots)==len(rows)==78
 dur=float(shots[-1][1])
 movie_meta=probe(args.movie)
 assert float(movie_meta["format"]["duration"])>7500,"film duration wrong"
 v=next(x for x in movie_meta["streams"] if x["codec_type"]=="video")
 assert v["width"]>=1920 and v["height"]>=1080,"HD stream not really 1080p"
 assert any(x["codec_type"]=="audio" for x in movie_meta["streams"])
 selected=dp_select(rows)
 segments=Path("men_segments");segments.mkdir(exist_ok=True)
 report=[]
 for i,((a,b,signature),picks,match) in enumerate(zip(shots,rows,selected)):
  assert abs(picks["clip_start"]-a)<.005
  assert abs(picks["clip_end"]-b)<.005
  length=b-a
  mid=(a+b)/2
  src_sec=float(match["movie_second"])-(mid-a)
  if src_sec<0:src_sec=0
  dist=int(match["distance"])
  info={"shot":i,"reference_start":a,"reference_end":b,
        "source_start":round(src_sec,3),"source_mid":match["movie_second"],
        "match_hamming_256":dist,"reference_duration":round(length,3)}
  report.append(info)
  out=segments/f"{i:03}.mp4"
  print("SHOT",json.dumps(info),flush=True)
  call(["ffmpeg","-y","-hide_banner","-loglevel","error",
        "-ss",f"{src_sec:.3f}","-i",args.movie,"-t",f"{length:.3f}",
        "-map","0:v:0","-map","0:a:0",
        "-vf","fps=30","-c:v","libx264","-preset","ultrafast","-crf","14",
        "-pix_fmt","yuv420p","-c:a","aac","-ac","2","-ar","48000","-b:a","192k",
        "-avoid_negative_ts","make_zero",out])
  assert out.stat().st_size>10000,"missing segment "+str(i)
 # Export the complete shot mapping independently for quality checking.
 Path("men_render").mkdir(exist_ok=True)
 Path("men_render/shot_selection.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
 weak=[q for q in report if q["match_hamming_256"]>=110]
 print("SHOT_MATCH_QA count",len(shots),"weak_match_ge_110",len(weak),flush=True)
 if len(weak)>15:
  raise RuntimeError("Too many uncertain film source matches to deliver a correct scene-by-scene remake")
 with open("men_segments/concat.txt","w") as f:
  for i in range(len(shots)):f.write(f"file '{i:03}.mp4'\n")
 call(["ffmpeg","-y","-hide_banner","-loglevel","error","-f","concat","-safe","0",
       "-i",str(segments/"concat.txt"),"-map","0:v:0","-map","0:a:0",
       "-c","copy","-movflags","+faststart",args.output])
 final=probe(args.output)
 got=float(final["format"]["duration"])
 print("HD_MONTAGE",got,"reference",dur,"output size",final["format"]["size"],flush=True)
 if abs(got-dur)>.9:
  # Never silently speed up or crop multiple seconds of movie footage.
  raise RuntimeError(f"Concat duration out of tolerance: {got:.3f} vs {dur:.3f}")
 Path("men_render/montage_quality.json").write_text(json.dumps({"movie":movie_meta,"montage":final,"weak_shots":weak},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
