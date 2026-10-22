#!/usr/bin/env python3
import cv2, numpy as np, json, subprocess, heapq, sys
REF=[[0,"ec0ff986bf003738"],[3,"bdcfd0941f0bf229"],[6,"c31ef0c799b49296"],[9,"c33ce1cf19b2929c"],[12,"b36343e4e4d2f3a1"],[15,"b4b0f055179af2e1"],[18,"c83ec1569cd83d38"],[21,"f3b2928e3e6ce0e3"],[24,"e5e3c14f3db090d6"],[27,"bffb7a1350a1b5a8"],[30,"aa0a5f5541f8a5ea"],[33,"cf52f22ac5c6de98"],[36,"ede47f590e07c896"],[39,"acb05c4f2364ebb1"],[42,"b5e25d99461b1b5a"],[45,"ede2ffd92607c882"],[48,"ede47d192627d0b6"],[51,"b5e21d9b461b1b5a"],[54,"cae8f7372d2982a1"],[57,"e8eef395314e9c08"],[60,"e0e07dd97e268382"],[63,"95c51aa6557b5a25"],[66,"b34c3e7a603d81bb"],[69,"c2c06e00ced6fa8f"],[72,"906029637b10f7c7"],[75,"cd87f81ede8df800"],[78,"c5817f1b7e84f980"],[81,"a659dc9715e38296"],[84,"905c23705327dd17"],[87,"92ad3c966744524f"],[90,"ac84a7541bdacb66"],[93,"b7c2796ce6b49456"],[96,"c5f57605c682df82"],[99,"b1998ceb1c658a2f"],[102,"94df236952e18752"],[105,"ae5c1c4ccc269bb7"],[108,"8b0b4bcd2dbd9426"],[111,"d3d4bc2c4e8dc9a5"],[114,"a90e7455652bbc8b"],[117,"d896c390dad692ce"],[120,"959663c17adb3846"],[123,"a2c06de463a3bd1c"],[126,"b4cc926b9bc2cd92"],[129,"c16719181ccef7c1"],[132,"e4a3c07afe885e43"],[135,"f4834278ffc81c5e"],[138,"a5c9dcd2d091d9d1"],[141,"9b732cf480dbd964"],[144,"8bb82536c6b399cc"],[147,"c98b2bae26a4eaa5"],[150,"9bb126e4c3d94576"],[153,"863619145efc55a3"],[156,"ceef3e6c9021b23a"],[159,"9c1de60b7cf0872c"],[162,"804fdea83d4cc289"],[165,"9061e25bb4c656e4"],[168,"c6a1387cf20f1c8f"],[171,"c603b5fe010f73e2"],[174,"a5055e5afa4a8778"],[177,"c643b5fe800ff1e0"]]
VIDEO=sys.argv[1] if len(sys.argv)>1 else "film_360.mp4"
size=(256,144)
p=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-i",VIDEO,"-vf","fps=1,scale=256:144","-pix_fmt","gray","-f","rawvideo","-"],stdout=subprocess.PIPE)
targets=[(t,int(h,16)) for t,h in REF]; tops=[[] for _ in targets]
def phash(im):
 g=cv2.resize(im,(32,32),interpolation=cv2.INTER_AREA).astype(np.float32)
 a=cv2.dct(g)[:8,:8]
 m=np.median(a[1:,:])
 return sum(int(v>m)<<(63-i) for i,v in enumerate(a.flatten()))
sec=0
while True:
 b=p.stdout.read(size[0]*size[1])
 if len(b)<size[0]*size[1]:break
 fr=np.frombuffer(b,dtype=np.uint8).reshape(size[1],size[0])
 # Reference: film full image was centrally cropped to 360x448, then interior y=165:495 was hashed
 # Vary crop offset to tolerate face-tracking in portrait reframe.
 hashes=[]
 for shift in [-25,-12,0,12,25]:
  x=int((256-144*.804)/2)+shift
  im=fr[int(144*.154):int(144*.891),max(0,x):min(256,x+int(144*.804))]
  if im.shape[1]<75:continue
  hashes.append((phash(im),shift))
 for i,(t,h) in enumerate(targets):
  best=min(((a^h).bit_count(),shift) for a,shift in hashes)
  score,shift=best
  if len(tops[i])<5:heapq.heappush(tops[i],(-score,sec,shift))
  elif score < -tops[i][0][0]:
   heapq.heapreplace(tops[i],(-score,sec,shift))
 if sec%600==0:print('processed source second',sec,flush=True)
 sec+=1
p.wait()
results=[]
for (t,h),picks in zip(targets,tops):
 best=[{"distance":-neg,"movie_second":ts,"shift":s,"offset":ts-t} for neg,ts,s in sorted(picks,reverse=True)]
 results.append({"clip_second":t,"matches":best})
 print(f"{t:>3}s: "+str([(v['movie_second'],v['distance'],v['offset']) for v in best[:3]]))
open("men_match.json","w").write(json.dumps(results,ensure_ascii=False,indent=2))
print('FRAMES',sec,'matches under 20',sum(r['matches'][0]['distance']<=20 for r in results),flush=True)
