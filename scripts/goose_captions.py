#!/usr/bin/env python3
import re
from pathlib import Path
# Timings relative to clip_3 excerpt, obtained from existing transcription.
lines=[
(0,.78,"Доброе утро, шеф."),(1.359,2.199,"Чем сегодня займемся?"),
(2.719,3.939,"Иди разгружай продукты."),(4.459,5.899,"Шеф, но я же не грузчик, я повар."),
(6.339,8.019,"Я тут уже неделю разгружаю, убираю."),
(8.219,10.739,"Пришел я к вам, чтобы готовить, а не разгружать."),
(13.323,14.443,"Тем более я все уже разгрузил."),(16.003,17.964,"Хорошо, убей гуся."),
(18.583,19.023,"В смысле?"),(20.223,22.443,"Ухни этого гуся для сегодняшнего банкета."),
(22.744,23.563,"Что прям насмерть?"),
(28.483,30.283,"А ты что, хочешь от живого куски отрезать?"),
(30.583,33.383,"Или ты думаешь, что мясо кусочками на деревьях растет?"),
(33.663,35.323,"Каждый повар должен быть готов убить."),
(36.684,37.383,"Убей гуся,"),(38.563,39.343,"Убей!"),
(39.443,42.733,"Убей, убей, убей, убей, убей, убей, убей, убей,"),
(47.024,47.483,"Убей, убей, убей, убей!"),
(53.419,53.56,"Ха!"),(53.96,54.66,"Убей гуся."),
(54.94,55.72,"Легко сказать."),(55.979,58.84,"Я в жизни никого не убивал, а этот еще на моего дядю похож."),
]
def stamp(t):
    cs=int(round(t*100)); h,r=divmod(cs,360000);m,r=divmod(r,6000);s,c=divmod(r,100)
    return f"{h}:{m:02}:{s:02}.{c:02}"
def esc(x):
    return x.replace("{","").replace("}","").replace("\\","")
head="""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,DejaVu Sans,53,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,8,50,50,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
items=[]
for start,end,sentence in lines:
    words=sentence.split()
    n=len(words)
    if not n:continue
    for j in range(n):
        a=start+(end-start)*j/n
        b=end if j==n-1 else start+(end-start)*(j+1)/n
        # Align text in two lines top-to-bottom; never use independent overlapping captions.
        raw=[esc(w) for w in words]
        width=sum(len(x)+1 for x in raw)
        if width>34 and len(raw)>3:
            half=width/2;acc=0;split=1
            for k,w in enumerate(raw[:-1]):
                acc+=len(w)+1
                if acc>=half:
                    split=k+1;break
        else:split=None
        styled=[(r"{\1c&H00D7FF&}"+w+r"{\1c&HFFFFFF&}") if k==j else w for k,w in enumerate(raw)]
        msg=(" ".join(styled[:split])+r"\N"+" ".join(styled[split:])) if split else " ".join(styled)
        # Centered above the lower control zone, with stable position and no micro-pause flicker.
        items.append(f"Dialogue: 0,{stamp(a)},{stamp(b)},Word,,0,0,0,,{{\\an8\\pos(540,1390)}}{msg}")
    # keep last word/phrase through short intra-scene silence (<0.35 sec)
    nxt=next((k[0] for k in lines if k[0]>start),None)
    if nxt is not None and nxt-end<.35 and nxt>end:
        prior=items[-1]
        a=prior.split(",")
        a[2]=stamp(nxt)
        items[-1]=",".join(a)
Path("captions.ass").write_text(head+"\n".join(items)+"\n",encoding="utf-8")
print("SUBTITLE_EVENTS",len(items))
