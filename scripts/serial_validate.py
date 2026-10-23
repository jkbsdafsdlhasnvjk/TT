#!/usr/bin/env python3
"""Structural QA for continuous season segments; NOT a speech accuracy certificate."""
import argparse,json,sys
from pathlib import Path

def stamp(s):
    h,m,sec=s.split(":")
    return int(h)*3600+int(m)*60+float(sec)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("folder")
    p.add_argument("--strict",action="store_true")
    args=p.parse_args()
    d=Path(args.folder)
    plan=json.loads((d/"continuous_cut_plan.json").read_text())
    rendered=json.loads((d/"rendered_parts.json").read_text())
    words=json.loads((d/"word_timestamps.json").read_text())
    review=json.loads((d/"transcript_review.json").read_text())
    spans=plan["parts"]
    assert len(rendered)==len(spans)>0,(len(rendered),len(spans))
    assert abs(spans[0]["start"]-plan["range"][0])<.01
    assert abs(spans[-1]["end"]-plan["range"][1])<.01
    assert all(abs(a["end"]-b["start"])<.011 for a,b in zip(spans,spans[1:]))
    assert all(s["end"]>s["start"] for s in spans)
    assert len({r["name"] for r in rendered})==len(rendered)
    assert all(a["start"]<=b["start"] for a,b in zip(words,words[1:]))
    outliers=[]
    count=0
    for i,(s,r) in enumerate(zip(spans,rendered),1):
        dur=s["end"]-s["start"]
        assert abs(r["start"]-s["start"])<.01 and abs(r["end"]-s["end"])<.01
        assert abs(r["duration"]-dur)<.18
        assert (d/r["name"]).is_file() and (d/r["name"]).stat().st_size>50000
        ass=d/r["name"].replace(".mp4",".ass")
        assert ass.is_file()
        last=0
        for line in ass.read_text().splitlines():
            if not line.startswith("Dialogue:"):continue
            fields=line.split(",",9)
            assert len(fields)==10
            start,end=stamp(fields[1]),stamp(fields[2])
            assert start>=last-.02,(ass.name,start,last)
            assert end>start and end<=dur+.03,(ass.name,start,end,dur)
            last=end
        if not 45<=dur<=76:
            outliers.append(dict(file=r["name"],duration=round(dur,2),reason=s["reason"]))
        if "REVIEW" in s["reason"]:
            outliers.append(dict(file=r["name"],duration=round(dur,2),reason=s["reason"]))
        count+=r["words"]
    assert count==len(words),f"Transcript words {len(words)} != subtitle words {count}"
    result={"structural_qa":"PASS","speech_qa":"NOT_VERIFIED","source_range":plan["range"],
            "parts":len(spans),"words":len(words),"review_items":len(review),
            "out_of_range_or_fallback":outliers,"all_video_files_present":True,
            "no_gaps_or_overlaps_in_cut_plan":True,"no_detected_caption_event_overlaps":True}
    (d/"structural_qa.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print("QA_REPORT",json.dumps(result,ensure_ascii=False),flush=True)
    if args.strict and outliers:raise SystemExit("Some cuts need duration/manual dialogue review")
if __name__=="__main__":main()
