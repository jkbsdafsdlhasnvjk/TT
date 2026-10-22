#!/usr/bin/env python3
"""Rebuild user reference montage from original HD frames, audio, scene-aligned timestamps and tracked portrait crop."""
import json,subprocess,math,argparse,os
from pathlib import Path
OFF=[300.528,300.528,300.528,300.524,300.524,300.524,303.728,303.728,315.094,317.061,335.028,335.028,337.428,337.428,465.437,467.037,470.204,473.37,474.937,474.937,498.835,498.835,498.835,498.837,3991.635,3991.635,3991.635,3991.635,4002.135,4002.131,4002.131,4002.131,4002.131,4002.131,4002.135,4002.135,4002.135,4016.702,4016.702,4017.835,4020.035,4024.869,4034.122,4034.127,4034.127,4099.026,4099.026,4099.026,4200.916,4217.25,4222.517,4222.517,4230.036,4230.036,4248.148,4288.568,4458.084,4458.085,4459.185,4459.185,4466.718,4467.218,4467.218,4467.214,4467.214,4467.214,4492.285,4492.985,4492.985,4495.252,4513.485,4513.485,4524.652,4557.718,4575.685,4575.685,4575.685,4575.685]
PAN=[0.168,0.461,0.105,0.496,0.211,0.023,0.188,0.184,0.184,0.148,0.160,0.309,0.086,0.231,0.422,0.231,0.422,0.223,0.402,0.504,0.363,0.211,0.203,0.395,0.000,0.535,0.164,0.590,0.098,0.422,0.141,0.484,0.156,0.574,0.344,0.324,0.207,0.539,0.539,0.242,0.519,0.324,0.055,0.543,0.043,0.043,0.371,0.398,0.363,0.000,0.000,0.281,0.473,0.477,0.371,0.469,0.391,0.359,0.363,0.430,0.582,0.535,0.598,0.328,0.418,0.348,0.434,0.285,0.477,0.004,0.148,0.242,0.332,0.391,0.223,0.492,0.223,0.527]
VIDEO_CHANGES={6:331.05,10:319.73,12:334.98}
PAN_CHANGES={6:0.285,10:0.277,12:0.406}
def run(x):subprocess.run(x,check=True)
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--movie",default="movie_1080.mp4");ap.add_argument("--shots",default="scripts/men_of_honor_shots.json");ap.add_argument("--output",default="men_montage_hd.mp4");z=ap.parse_args()
 shots=json.loads(Path(z.shots).read_text())
 assert len(OFF)==len(PAN)==len(shots)==78
 root=Path("men_hd_segments");root.mkdir(exist_ok=True)
 report=[];count=0
 for i,((a,b,h),off,pan) in enumerate(zip(shots,OFF,PAN)):
  frames=round(b*30)-round(a*30)
  seconds=frames/30
  x=min(1272,max(0,round(PAN_CHANGES.get(i,pan)*1920/2)*2))
  # Active film height about 808px after stripping original top/bottom cinemascope letterboxing.
  y=136
  source=a+VIDEO_CHANGES.get(i,off)
  audio_source=a+off
  out=root/f"{i:03}.mp4"
  print(f"EXTRACT {i:02} reference {a:.3f}-{b:.3f} source {source:.3f} duration {seconds:.3f} x {x}",flush=True)
  vf=f"crop=648:808:{x}:{y},scale=1080:1346:flags=lanczos,pad=1080:1350:0:2,setsar=1,fps=30"
  # Frame-exact durations keep the 179.6-second reference montage intact.
  inputs=["-ss",f"{source:.3f}","-i",z.movie]
  amap="0:a:0"
  if i in VIDEO_CHANGES:
   inputs+=["-ss",f"{audio_source:.3f}","-i",z.movie]
   amap="1:a:0"
  run(["ffmpeg","-hide_banner","-loglevel","error","-y"]+inputs+
      ["-map","0:v:0","-map",amap,
       "-vf",vf,"-frames:v",str(frames),"-c:v","libx264","-preset","ultrafast","-crf","18",
       "-pix_fmt","yuv420p","-c:a","aac","-ar","48000","-ac","2","-b:a","160k",
       "-af",f"aresample=async=1:first_pts=0,apad,atrim=duration={seconds:.6f}",
       "-avoid_negative_ts","make_zero",str(out)])
  assert out.stat().st_size>2500
  count+=frames
  report.append({"n":i,"clip_start":a,"clip_end":b,"source_start":round(source,3),"crop_x":x,"frames":frames})
 listfile=root/"concat.txt"
 listfile.write_text("".join(f"file '{i:03}.mp4'\nduration {(round(b*30)-round(a*30))/30:.9f}\n" for i,(a,b,_) in enumerate(shots)),encoding="utf-8")
 run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",str(listfile),
      "-map","0:v:0","-map","0:a:0","-t",f"{count/30:.6f}","-c","copy","-movflags","+faststart",z.output])
 Path("men_render").mkdir(exist_ok=True)
 Path("men_render/source_shot_map.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
 info=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration,size:stream=width,height,codec_type","-of","json",z.output]))
 secs=float(info["format"]["duration"])
 assert abs(secs-count/30)<1.,f"wrong concat duration {secs} expected {count/30}"
 print("HD_MONTAGE_DONE",secs,"REFERENCE",179.584,"FRAMES",count,flush=True)
if __name__=="__main__":main()
