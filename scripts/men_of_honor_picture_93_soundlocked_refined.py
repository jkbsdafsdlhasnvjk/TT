#!/usr/bin/env python3
"""Audio-aligned HD re-cut from 87 frame-verified visual edits, no title graphics or audio.
Use original user's clip audio when finalizing: editing movie audio creates audible glitches."""
import csv,json,subprocess,sys
from pathlib import Path
import argparse

CUTS={
 25:[65.8333333333],33:[86.8],34:[87.7333333333],37:[92.0666666667],
 57:[133.0666666667],65:[156.1],69:[160.8666666667],72:[164.8,167.1333333333]
}
def run(xs):
 subprocess.run([str(x) for x in xs],check=True)
def probe(file):
 return json.loads(subprocess.check_output([
  "ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,width,height,r_frame_rate",
  "-of","json",str(file)]))
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--movie",default="movie_1080.mp4")
 ap.add_argument("--output",default="men_precise_picture_1080x1920_silent.mp4")
 opts=ap.parse_args()
 originals=json.loads(Path("scripts/men_of_honor_shots.json").read_text())
 edits=[]
 for i,(a,b,_) in enumerate(originals):
  bds=[a]+CUTS.get(i,[])+[b]
  for start,end in zip(bds,bds[1:]):edits.append((start,end,i))
 positions=list(csv.DictReader(open("scripts/men_of_honor_87_audio_matched_map.csv",encoding="utf-8")))
 assert len(edits)==len(positions)==87,(len(edits),len(positions))
 info=probe(opts.movie)
 vsrc=next(x for x in info["streams"] if x["codec_type"]=="video")
 assert vsrc["width"] in (1280,1920)
 factor=vsrc["width"]/640
 crop_width=round(260*factor)
 crop_height=round(270*factor)
 crop_y=round(45*factor)
 maxcrop=vsrc["width"]-crop_width
 assert float(info["format"]["duration"])>7700
 # Source montage hides 6 extra time jumps INSIDE shots of the same actor.
 # Confirmed via original/reference Russian audio correlation and frame cuts.
 extras={14:[36.8666667],16:[45.1333333,46.7666667,48.7],44:[98.3333333],51:[113.3666667]}
 audio_jumps={14:[-1.6,0],16:[0,1.337,3.170,4.445],44:[-2.2,0],51:[0,1.8]}
 full=[]
 for parent,((a,b,i),setting) in enumerate(zip(edits,positions)):
  bounds=[a]+extras.get(parent,[])+[b]
  jumps=audio_jumps.get(parent,[0]*(len(bounds)-1))
  assert len(bounds)-1==len(jumps)
  xa=int(setting["x_start_640"]);xb=int(setting["x_end_640"])
  for k,(aa,bb) in enumerate(zip(bounds,bounds[1:])):
   u=(aa-a)/(b-a);v=(bb-a)/(b-a)
   subsetting={"source_start":float(setting["source_start"])+(aa-a)+jumps[k],
      "x_start_640":round(xa+(xb-xa)*u),"x_end_640":round(xa+(xb-xa)*v)}
   full.append((aa,bb,i,subsetting,parent))
 assert len(full)==93,len(full)
 folder=Path("men_precise_segments");folder.mkdir(exist_ok=True)
 frames_total=0;log=[]
 for idx,(a,b,i,setting,parent) in enumerate(full):
  source_start=float(setting["source_start"])
  x0=round(int(setting["x_start_640"])*factor)
  x1=round(int(setting["x_end_640"])*factor)
  assert 0<=x0<=maxcrop and 0<=x1<=maxcrop
  frames=round(b*30)-round(a*30)
  assert 2<=frames<=350, (idx,frames)
  duration=frames/30
  den=max(1,frames-1)
  dx=x1-x0
  # Exact center crop from reference. Pan independently inside each shot.
  crop=f"crop={crop_width}:{crop_height}:{x0}+({dx})*n/{den}:{crop_y},scale=1080:1350:flags=lanczos,setsar=1,fps=30"
  out=folder/f"{idx:03}.mp4"
  print("SHOT",idx,"original",i,"ref",a,b,"source",source_start,"x",x0,x1,"frames",frames,flush=True)
  run(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss",f"{source_start:.3f}",
       "-i",opts.movie,"-vf",crop,"-an","-frames:v",str(frames),
       "-c:v","libx264","-preset","ultrafast","-crf","18","-pix_fmt","yuv420p",
       "-r","30","-movflags","+faststart",out])
  if out.stat().st_size<3000:raise RuntimeError("Empty shot "+str(idx))
  frames_total+=frames
  log.append({"cut":idx,"parent_87_shot":parent,"source_original_shot":i,"reference":[a,b],"source_start":source_start,
              "x_start":x0,"x_end":x1,"frames":frames})
 playlist=folder/"concat.txt"
 playlist.write_text("".join(f"file '{j:03}.mp4'\nduration {(round(b*30)-round(a*30))/30:.9f}\n"
                             for j,(a,b,i,setting,parent) in enumerate(full)),encoding="utf-8")
 center=Path("men_precise_center.mp4")
 run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",playlist,
      "-map","0:v:0","-an","-t",f"{frames_total/30:.6f}","-c:v","copy",
      "-movflags","+faststart",center])
 cprobe=probe(center)
 assert abs(float(cprobe["format"]["duration"])-frames_total/30)<.1,cprobe
 # Build full portrait frame like reference clip, retaining the complete foreground.
 background=("[0:v]split=2[background][picture];"
             "[background]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
             "crop=1080:1920,boxblur=20:2[blur];"
             "[blur][picture]overlay=x=(W-w)/2:y=(H-h)/2,format=yuv420p[video]")
 run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",center,
      "-filter_complex",background,"-map","[video]","-an",
      "-c:v","libx264","-preset","veryfast","-crf","17","-r","30",
      "-movflags","+faststart",opts.output])
 p=probe(opts.output)
 v=next(x for x in p["streams"] if x["codec_type"]=="video")
 assert v["width"]==1080 and v["height"]==1920
 assert not any(x["codec_type"]=="audio" for x in p["streams"])
 assert abs(float(p["format"]["duration"])-179.6)<.2,p
 folder_out=Path("men_precise_qa");folder_out.mkdir(exist_ok=True)
 (folder_out/"edit_decisions.json").write_text(json.dumps(log,ensure_ascii=False,indent=2))
 (folder_out/"output_probe.json").write_text(json.dumps(p,ensure_ascii=False,indent=2))
 print("READY_SILENT_PICTURE",opts.output,p["format"]["duration"],p["format"]["size"],flush=True)
if __name__=="__main__":main()
