#!/usr/bin/env python3
"""Stable phrase captions: one libass event per sentence and timed per-word color."""
import ast
import json
from pathlib import Path

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
word_times = json.loads(Path('goose_word_times.json').read_text(encoding='utf-8'))
assert len(lines) == len(word_times), 'Caption/transcription count mismatch'

HEADER = '''[Script Info]
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
'''
def stamp(t):
    cs = int(round(max(0, t) * 100))
    h, r = divmod(cs, 360000); m, r = divmod(r, 6000); s, c = divmod(r, 100)
    return f'{h}:{m:02}:{s:02}.{c:02}'
def esc(s):
    return s.replace('\\','').replace('{','').replace('}','')
def split_at(words):
    width = sum(len(word) + 1 for word in words)
    if width <= 34 or len(words) <= 3: return len(words)
    half = width / 2; accum = 0
    for i, word in enumerate(words[:-1]):
        accum += len(word) + 1
        if accum >= half: return i + 1
    return len(words)

CAPTION_PRE_ROLL = 0.10
CAPTION_HOLD = 0.70
HIGHLIGHT_LEAD = 0.22
MAX_HIGHLIGHT = 0.85
CLIP_DURATION = 60.48

# Calculate ALL caption starts before calculating ends. Adjacent phrases
# never occupy the screen simultaneously, even with very short pauses.
starts = []
for i, words in enumerate(word_times):
    first = words[0][0]
    # Show the stable phrase before the very first phoneme is heard.
    # Do not pin its onset to the END of the previous spoken word: that
    # previously caused late captions in rapid, back-to-back dialogue.
    early = max(0.0, first - HIGHLIGHT_LEAD - CAPTION_PRE_ROLL)
    starts.append(max(early, starts[-1] + 0.04 if starts else 0.0))
events = []
for i, (_, _, sentence) in enumerate(lines):
    words = [esc(w) for w in sentence.split()]
    timings = word_times[i]
    assert len(words) == len(timings), f'Word count mismatch on line {i}'
    for j, (begin,end) in enumerate(timings):
        assert 0 <= begin < end <= CLIP_DURATION + 0.01, (i,j,begin,end)
    first = timings[0][0]; last = timings[-1][1]
    start = starts[i]
    end = min(CLIP_DURATION, last+CAPTION_HOLD)
    if i+1 < len(lines):
        end = min(end, starts[i+1]-0.01)
    assert end >= last-0.015 and end > start, (i,start,end,last)
    cut = split_at(words)
    # Exclusive, anticipatory karaoke: each word illuminates BEFORE its
    # acoustic onset. The previous highlight turns off at that instant.
    # This guarantees there is never a visibly late per-word color change
    # caused by a gap between separately timed subtitle events.
    onsets = [max(start, a - HIGHLIGHT_LEAD) for a, b in timings]
    assert all(onsets[k+1] >= onsets[k]-0.001 for k in range(len(onsets)-1)), (i,onsets)
    styled = []
    for j,token in enumerate(words):
        begin = onsets[j]
        next_onset = onsets[j+1] if j+1<len(words) else min(end, timings[j][1]-HIGHLIGHT_LEAD+0.06)
        finish = min(end, begin + MAX_HIGHLIGHT, max(begin, next_onset))
        b = int(round(1000*(begin-start))); e=int(round(1000*(finish-start)))
        if b <= 0:
            tag = '{\\1c&H00D7FF&' + f'\\t({e},{e+1},\\1c&HFFFFFF&)' + '}'
        else:
            tag = '{\\1c&HFFFFFF&' + f'\\t({b},{b+1},\\1c&H00D7FF&)' + f'\\t({e},{e+1},\\1c&HFFFFFF&)' + '}'
        styled.append(tag+token)
    txt = ' '.join(styled[:cut])
    if cut < len(words): txt += r'\N'+' '.join(styled[cut:])
    events.append(f'Dialogue: 0,{stamp(start)},{stamp(end)},Word,,0,0,0,,{{\\an8\\pos(540,1390)}}{txt}')
Path('captions.ass').write_text(HEADER+'\n'.join(events)+'\n',encoding='utf-8')
print('STABLE_PHRASE_EVENTS',len(events), 'WORDS',sum(map(len,word_times)))

# Validate the actual ASS file events, not only the word-alignment source.
from math import isfinite
for i in range(1,len(starts)):
    assert starts[i] > starts[i-1]
assert len(events) == len(lines) == len(word_times)
for i, e in enumerate(events):
    assert e.count(chr(92)+'t(') >= len(word_times[i]), (i,'missing highlight transforms')
