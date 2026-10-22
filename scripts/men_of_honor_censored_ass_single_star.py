#!/usr/bin/env python3
"""Build clean Russian captions from the original uploaded clip's SRT and model word onsets.
Mask racial slurs as asterisks, including inflections and alternate spelling.
"""
from pathlib import Path
import difflib,json,re,unicodedata

HEADER="""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,DejaVu Sans,56,&H00FFFFFF,&H0000FFFF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,4,1,8,50,50,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
slur=re.compile(r"^(?:ниг+\w*|негр\w*|ч[её]рножоп\w*|ч[её]рномаз\w*|ч[её]рнорыл\w*|ч[её]рноморд\w*)$",re.I)
def norm(t):
 return re.sub(r"[^а-яёa-z0-9]","",t.casefold()).replace("ё","е")
def mask(t):
 core=norm(t)
 if slur.match(core):
  suffix=re.search(r"([,.!?…]+)$",t)
  return "*"+(suffix.group(1) if suffix else "")
 return t
def stamp(t):
 cs=round(max(0,t)*100);h,cs=divmod(cs,360000);m,cs=divmod(cs,6000);s,cs=divmod(cs,100)
 return f"{h}:{m:02}:{s:02}.{cs:02}"
def clock(st):
 h,m,sec,ms=map(int,re.split(r"[:,]",st))
 return 3600*h+60*m+sec+ms/1000
def read_srt(p):
 all=[]
 for blk in re.split(r"\n\s*\n",p.read_text(encoding="utf-8-sig").replace("\r\n","\n")):
  lines=blk.strip().splitlines()
  if not lines:continue
  ti=next((x for x in lines if "-->" in x),None)
  if ti is None:continue
  pos=lines.index(ti)
  a,b=[v.strip() for v in ti.split("-->",1)]
  text=" ".join(x.strip() for x in lines[pos+1:]).strip()
  if text:all.append((clock(a),clock(b),text))
 assert len(all)>=50,("Only SRT segments",len(all))
 return all
def align_tokens(target,model,a,b):
 # Match reliably recognized words directly to their acoustics;
 # place model substitutions/omissions between adjacent acoustic anchors.
 candidates=[w for w in model if w["end"]>=a-.50 and w["start"]<=b+.50]
 cand=[norm(w["word"]) for w in candidates]
 toks=[norm(t) for t in target]
 sm=difflib.SequenceMatcher(None,cand,toks,autojunk=False)
 anchor={}
 for tag,i0,i1,j0,j1 in sm.get_opcodes():
  if tag!="equal":continue
  for z in range(j1-j0):
   index=j0+z;w=candidates[i0+z]
   anchor[index]=max(0,float(w["start"]))
 # Short lead/lag corrections from SRT time windows should never
 # erase an acoustically located exact word.
 n=len(target)
 if not anchor:
  scale=[len(norm(x))**.65+1.5 for x in target]
  total=sum(scale);cursor=a
  result=[]
  for v in scale:
   result.append(cursor);cursor+=(b-a)*v/total
  return result
 found=sorted(anchor)
 assigned={}
 for j in range(n):
  if j in anchor:
   assigned[j]=anchor[j]
   continue
  left=next((k for k in reversed(found) if k<j),None)
  right=next((k for k in found if k>j),None)
  if left is None and right is None:t=a+j*(b-a)/max(1,n)
  elif left is None:
   t=a+(anchor[right]-a)*j/max(1,right)
  elif right is None:
   t=anchor[left]+(b-anchor[left])*(j-left)/max(1,n-left)
  else:t=anchor[left]+(anchor[right]-anchor[left])*(j-left)/(right-left)
  assigned[j]=t
 # In unusual model errors avoid decreasing word onsets.
 out=[];previous=max(0,a-.18)
 for j in range(n):
  tt=max(previous+.035,min(b+.20,assigned[j]))
  out.append(tt);previous=tt
 return out
def main():
 clips=read_srt(Path("scripts/men_of_honor_reference.srt"))
 model=json.loads(Path("previous_qa/men_render/speech_words.json").read_text())
 lines=[];highlights=0;masked=[];last_end=0.0
 cue_data=[]
 for a,b,sentence in clips:
  if not a<b:continue
  tokens=sentence.split()
  onsets=align_tokens(tokens,model,a,b)
  chunks=[];now=[]
  for j,token in enumerate(tokens):
   # Keep whole small phrases on screen, maximum 8 tokens and ~44 characters.
   if now and (len(now)>=8 or sum(len(tokens[z])+1 for z in now)+len(token)>48 or
               onsets[j]-onsets[now[-1]]>1.15):
    chunks.append(now);now=[]
   now.append(j)
  if now:chunks.append(now)
  for ic,indices in enumerate(chunks):
   t0=max(0,last_end+.01,onsets[indices[0]]-.22)
   nstart=onsets[chunks[ic+1][0]] if ic+1<len(chunks) else None
   t1=(min(b+.20,nstart-.03) if nstart is not None else b+.20)
   t1=max(t0+.06,t1)
   t1=min(t1,179.60)
   if t1<=t0:continue
   parts=[]
   for jj,j in enumerate(indices):
    w=mask(tokens[j]).replace("{","").replace("}","").replace("\\","")
    if "*" in w:masked.append((a,w))
    t_on=max(t0,onsets[j]-.095)
    t_off=min(t1,onsets[indices[jj+1]]-.095 if jj+1<len(indices) else onsets[j]+.15)
    t_off=max(t_on+.012,t_off)
    start=max(0,round((t_on-t0)*1000));end=max(start+1,round((t_off-t0)*1000))
    if start==0:
     fx="{\\1c&H00D7FF&"+f"\\t({end},{end+1},\\1c&HFFFFFF&)"+"}"
    else:
     fx="{\\1c&HFFFFFF&"+f"\\t({start},{start+1},\\1c&H00D7FF&)\\t({end},{end+1},\\1c&HFFFFFF&)"+"}"
    parts.append(fx+w);highlights+=1
   text=" ".join(parts)
   # stable 1- or 2-line text; keep visual alignment over film center
   if len(text)>0 and len(indices)>4 and sum(len(tokens[z])+1 for z in indices)>34:
    cut=(len(indices)+1)//2
    text=" ".join(parts[:cut])+r"\N"+" ".join(parts[cut:])
   lines.append(f"Dialogue: 0,{stamp(t0)},{stamp(t1)},Word,,0,0,0,,{{\\an8\\pos(540,1390)}}{text}")
   cue_data.append((t0,t1,[mask(tokens[z]) for z in indices]))
   last_end=t1
 out=Path("censored_captions.ass")
 out.write_text(HEADER+"\n".join(lines)+"\n",encoding="utf-8")
 content=out.read_text(encoding="utf-8").casefold()
 assert "ниг" not in content and "негр" not in content and "чернож" not in content, "Unmasked slur in subtitles!"
 assert masked and len(lines)>45 and highlights>200,(masked,len(lines),highlights)
 Path("men_precise_qa").mkdir(exist_ok=True)
 Path("men_precise_qa/caption_checks.json").write_text(json.dumps({"phrases":len(lines),"words":highlights,"censored_words":masked,"last_end":last_end},ensure_ascii=False,indent=2))
 print("CAPTION_EVENTS",len(lines),"WORDS",highlights,"MASKED",masked,"LAST",last_end,flush=True)
if __name__=="__main__":main()
