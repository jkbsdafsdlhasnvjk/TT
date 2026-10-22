#!/usr/bin/env python3
"""Match every scene in the 179.584 s user reference montage to original movie timestamps.
Uses 256-bit perceptual DCT + spatial shift variations to suppress random collisions."""
import cv2,numpy as np,subprocess,heapq,json,sys
reference=json.load(open("scripts/men_of_honor_hash16.json"))
shots=json.load(open("scripts/men_of_honor_shots.json"))
assert len(reference)==len(shots)
VIDEO=sys.argv[1] if len(sys.argv)>1 else "film_360.mp4"
p=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-i",VIDEO,"-vf","fps=1,scale=256:144","-pix_fmt","gray","-f","rawvideo","-"],stdout=subprocess.PIPE)
targets=[int(x,16) for x in reference]
tops=[[] for _ in targets]
def phash(im):
 g=cv2.resize(im,(64,64),interpolation=cv2.INTER_AREA).astype(np.float32)
 d=cv2.dct(g)[:16,:16]; m=np.median(d[1:,:])
 return sum(int(v>m)<<(255-i) for i,v in enumerate(d.flatten()))
sec=0
while True:
 b=p.stdout.read(256*144)
 if len(b)<256*144:break
 f=np.frombuffer(b,dtype=np.uint8).reshape(144,256)
 hashes=[]
 for shift in (-25,-12,0,12,25):
  x=int((256-144*.804)/2)+shift
  im=f[int(144*.154):int(144*.891),x:x+int(144*.804)]
  if im.shape[1]>75:hashes.append((phash(im),shift))
 for i,h in enumerate(targets):
  d,s=min(((hh^h).bit_count(),sh) for hh,sh in hashes)
  if len(tops[i])<9:heapq.heappush(tops[i],(-d,sec,s))
  elif d < -tops[i][0][0]:heapq.heapreplace(tops[i],(-d,sec,s))
 sec+=1
 if sec%750==0:print("PROGRESS",sec,flush=True)
p.wait()
rows=[]
for i,((a,b,_),picks) in enumerate(zip(shots,tops)):
 mid=(a+b)/2
 ms=[{"movie_second":ts,"distance":-neg,"crop_shift":shift,"movie_minus_reference":round(ts-mid,3)} for neg,ts,shift in sorted(picks,reverse=True)]
 rows.append({"index":i,"clip_start":a,"clip_end":b,"clip_mid":round(mid,3),"matches":ms})
 print(f"SHOT {i:02} ref={a:7.3f}-{b:7.3f} best="+str([(m["movie_second"],m["distance"]) for m in ms[:5]]),flush=True)
open("men_shots_matched16.json","w").write(json.dumps(rows,ensure_ascii=False,indent=2))
print("FINISHED",sec,"SHOTS",len(rows),"LOWDIST",sum(m["matches"][0]["distance"]<75 for m in rows),flush=True)
