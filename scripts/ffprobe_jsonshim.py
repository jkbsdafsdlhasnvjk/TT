#!/usr/bin/env python3
"""Minimal ffprobe-compatible JSON inspection for portable FFmpeg environments."""
import json,sys,os
import av
path=sys.argv[-1]
with av.open(path) as c:
    streams=[]
    for st in c.streams:
        row={"index":st.index,"codec_type":st.type}
        co=st.codec_context
        row["codec_name"]=co.name if co else "unknown"
        if st.type=="video":
            row["width"]=st.width;row["height"]=st.height
            row["r_frame_rate"]=str(st.average_rate or "30/1")
        row["bit_rate"]=st.bit_rate or 0
        streams.append(row)
    duration=(c.duration/1000000) if c.duration else 0
    out={"streams":streams,"format":{"duration":f"{duration:.6f}","size":str(os.path.getsize(path))}}
print(json.dumps(out))
