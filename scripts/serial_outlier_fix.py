#!/usr/bin/env python3
"""Repair only out-of-spec contiguous short-video boundaries from an already
completed season artifact. Reuse original cached source and existing word
timestamps; never redownload from Drive, never re-run ASR.
Structural QA is not human speech verification.
"""
import argparse,json,math,os,shutil
from pathlib import Path
from serial_parts import possible_cuts,render
from serial_validate import main as validate_main

def local_plan(words,spans,left,right):
    lo=spans[left]["start"];hi=spans[right]["end"]
    relevant=[w for w in words if lo-.1<=w["start"] and w["end"]<=hi+.1]
    orig=[spans[i]["end"] for i in range(left,right)]
    # The original ASR has a 183-second stretch without any recognized
    # speech in shard 3. possible_cuts() supplies only ONE midpoint for
    # that gap, which mathematically makes 45-76s clips impossible.
    # Supply additional boundaries entirely INSIDE word-free regions.
    # These are structurally safe relative to ASR, but NOT proof that
    # there is no missed dialogue; flag them for separate audio review.
    no_asr_gap_cuts=[]
    edges=([(lo,relevant[0]["start"])] +
           [(a["end"],b["start"]) for a,b in zip(relevant,relevant[1:])] +
           [(relevant[-1]["end"],hi)]) if relevant else [(lo,hi)]
    for a,b in edges:
        if b-a<85.:continue
        t=a+12.
        while t<b-12.:
            no_asr_gap_cuts.append((round(t,2),2.1,
                "no_ASR_words_gap_audio_review_required",round(b-a,2)))
            t+=12.
    if no_asr_gap_cuts:
        print("NO_ASR_WORD_GAP_EXTRA_CUTS",len(no_asr_gap_cuts),
              no_asr_gap_cuts[:5],flush=True)
    def try_solve(allow_weak):
        options=[]
        for t,score,reason,gap in [*possible_cuts(relevant,[],lo,hi),*no_asr_gap_cuts]:
            if not allow_weak and not (gap>=.40 or score>=2.05):continue
            if any(w["start"]-.10<t<w["end"]+.10 for w in relevant):continue
            options.append((round(t,2),float(score),gap,reason))
        for t in orig:
            if not any(abs(t-x[0])<.04 for x in options):
                if all(not w["start"]-.10<t<w["end"]+.10 for w in relevant):
                    options.append((round(t,2),2.5,.4,"old_boundary"))
        # Deduplicate, keeping highest confidence in natural boundary.
        d={}
        for p in options:
            if p[0] not in d or p[1]>d[p[0]][1]:d[p[0]]=p
        arr=[(lo,0,0,"begin")]+sorted(d.values())+[(hi,0,0,"end")]
        # shortest path with duration hard bounds, penalty for additional clips
        dp={0:(0,[])}
        for j in range(1,len(arr)):
            choices=[]
            for i,(cost,path) in dp.items():
                dt=arr[j][0]-arr[i][0]
                if 45.-.005<=dt<=76.+.005:
                    reward=0 if j==len(arr)-1 else min(6.,arr[j][1])*.6
                    preserved=0.5 if any(abs(arr[j][0]-b)<.05 for b in orig) else 0
                    extra=1.2
                    choices.append((cost+abs(dt-60)*.13+extra-reward-preserved,path+[j]))
            if choices:dp[j]=min(choices,key=lambda x:x[0])
        if len(arr)-1 not in dp:return None
        idxs=dp[len(arr)-1][1]
        ends=[arr[i] for i in idxs]
        cursor=lo;result=[]
        for t,score,gap,reason in ends:
            result.append({"start":round(cursor,2),"end":round(t,2),
                           "reason":"repaired_"+reason if t!=hi else "repaired_end_of_range",
                           "score":round(score,2)})
            cursor=t
        return result
    ans=try_solve(False)
    if ans is None:ans=try_solve(True)
    if ans is None:
        possible=sorted((round(t,2),round(score,2),round(gap,2)) for t,score,reason,gap in possible_cuts(relevant,[],lo,hi))
        times=[lo]+[x[0] for x in possible]+[hi]
        holes=sorted(((round(b-a,2),round(a,2),round(b,2)) for a,b in zip(times,times[1:])),reverse=True)
        print("NO_SAFE_PATH",left+1,right+1,"DURATION",round(hi-lo,2),
              "CANDIDATES",len(possible),"LONGEST_UNCUT_GAPS",holes[:6],
              "CANDIDATE_EXAMPLES",possible[:18],flush=True)
        raise RuntimeError(f"No natural word-safe 45-76s repair for {left+1}..{right+1} [{lo},{hi}]")
    return ans

def fix(words,spans):
    bad=[i for i,s in enumerate(spans) if not 45<=s["end"]-s["start"]<=76]
    windows=[]
    for i in bad:
        a=max(0,i-1);b=min(len(spans)-1,i+1) if spans[i]["end"]-spans[i]["start"]>76 else i
        if windows and a<=windows[-1][1]+1:
            windows[-1]=(windows[-1][0],max(windows[-1][1],b))
        else:windows.append((a,b))
    replacements=[]
    for idx,(a,b) in enumerate(windows):
        previous_end=windows[idx-1][1] if idx else -1
        next_start=windows[idx+1][0] if idx+1<len(windows) else len(spans)
        attempt=None
        for margin in range(0,8):
            aa=max(previous_end+1,a-margin)
            bb=min(next_start-1,b+margin)
            try:
                attempt=local_plan(words,spans,aa,bb)
                a,b=aa,bb
                break
            except RuntimeError as exc:
                print("TRY_WIDER_WINDOW",margin,str(exc),flush=True)
        if attempt is None:
            raise RuntimeError(f"Could not find natural 45-76s cuts near original parts {a+1}..{b+1}")
        print("REPAIR_WINDOW",a+1,b+1,"OLD",[(round(s["end"]-s["start"],2)) for s in spans[a:b+1]],
              "NEW",[(round(s["end"]-s["start"],2)) for s in attempt],flush=True)
        replacements.append((a,b,attempt))
    new=[];old_to_new={}
    i=0
    for a,b,replacement in replacements:
        for old in range(i,a):
            old_to_new[len(new)]=old
            new.append(spans[old])
        new.extend(replacement)
        i=b+1
    for old in range(i,len(spans)):
        old_to_new[len(new)]=old
        new.append(spans[old])
    assert all(abs(x["end"]-y["start"])<.011 for x,y in zip(new,new[1:]))
    assert new[0]["start"]==spans[0]["start"] and new[-1]["end"]==spans[-1]["end"]
    assert all(45<=s["end"]-s["start"]<=76 for s in new)
    for p in new[:-1]:
        t=p["end"]
        assert not any(w["start"]-.08<t<w["end"]+.08 for w in words),(t,"bisects word")
    return new,old_to_new,bad,windows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--source",default="season.mp4")
    ap.add_argument("--part",type=int,required=True)
    ap.add_argument("--plan-only",action="store_true")
    args=ap.parse_args()
    root=Path(args.input);dest=Path(args.output);dest.mkdir(parents=True,exist_ok=True)
    plan=json.loads((root/"continuous_cut_plan.json").read_text())
    old=json.loads((root/"rendered_parts.json").read_text())
    words=json.loads((root/"word_timestamps.json").read_text())
    new,mapping,bad,windows=fix(words,plan["parts"])
    assert len(old)==len(plan["parts"])
    print("NEW_PLAN",len(old),"to",len(new),"outliers",len(bad),flush=True)
    (dest/"repair_diagnostic.json").write_text(json.dumps({"source_range":plan["range"],
      "original_parts":len(old),"new_parts":len(new),"bad_indices":[i+1 for i in bad],
      "windows":[[a+1,b+1] for a,b in windows],"new_spans":new,
      "speech_qa":"NOT_VERIFIED"},indent=2,ensure_ascii=False))
    if args.plan_only:return
    prefix=f"Kinogryz_S01_{args.part:02d}"
    records=[]
    for index,span in enumerate(new,1):
        oldidx=mapping.get(index-1)
        if oldidx is not None:
            record=dict(old[oldidx])
            orig=root/record["name"]
            newname=f"{prefix}_{index:04d}.mp4"
            for extension in (".mp4",".ass"):
                oldfile=orig.with_suffix(extension)
                target=dest/(Path(newname).stem+extension)
                assert oldfile.is_file(),oldfile
                os.link(oldfile,target)
            record["name"]=newname
        else:
            record=render(args.source,span,words,dest,index,17,prefix)
            print("RERENDERED",record["name"],round(record["duration"],2),flush=True)
        records.append(record)
    for filename in ("word_timestamps.json","transcript_review.json"):
        shutil.copy2(root/filename,dest/filename)
    updated=dict(plan,parts=new)
    (dest/"continuous_cut_plan.json").write_text(json.dumps(updated,ensure_ascii=False,indent=2))
    (dest/"rendered_parts.json").write_text(json.dumps(records,ensure_ascii=False,indent=2))
    import sys
    sys.argv=["serial_validate.py",str(dest),"--strict"]
    validate_main()
    print("REPAIR_QA_PASS",args.part,"parts",len(records),"reencoded",len(records)-len(mapping),flush=True)
if __name__=="__main__":main()
