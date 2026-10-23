#!/usr/bin/env python3
"""Build an audio-backed, explicitly UNVERIFIED review queue from prior ASR audits.

No edits to videos or subtitles. Does not call Google Drive or download source.
Consumes previous two independent-ASR reports plus completed short MP4 artifacts.
"""
import argparse
import csv
import html
import json
import subprocess
from pathlib import Path


def load_reports(root):
    files = sorted(root.rglob('qa_crosscheck_*.json'))
    if len(files) < 2:
        raise RuntimeError(f'Expected independent audit reports under {root}, found {len(files)}')
    grouped = {}
    for path in files:
        data = json.loads(path.read_text(encoding='utf-8'))
        span = tuple(float(x) for x in data['source_range'])
        grouped.setdefault(span, []).extend(data.get('crosscheck', []))
    return grouped, files


def issue_class(row):
    if not row.get('exact_word_present_in_alt'):
        return 'ASR_TEXT_DISAGREEMENT'
    if row.get('timing_within_0_60s') is False:
        return 'WORD_TIMING_DISAGREEMENT'
    if row.get('timing_within_0_60s') is None:
        return 'WORD_TIMING_UNRESOLVED'
    return None


def context(words, t):
    if not words:
        return ''
    k = min(range(len(words)), key=lambda i: abs(float(words[i]['start']) - t))
    lo, hi = max(0, k-8), min(len(words), k+9)
    return ' '.join(w['text'] for w in words[lo:hi])


def extract_audio(video, dest, center, duration):
    left = max(0, center-3.0)
    remaining = max(.2, duration-left)
    length = min(7.0, remaining)
    proc = subprocess.run([
        'ffmpeg','-hide_banner','-loglevel','error','-y',
        '-ss',f'{left:.3f}','-i',str(video),'-t',f'{length:.3f}',
        '-vn','-ac','1','-ar','16000','-codec:a','libmp3lame',
        '-b:a','64k',str(dest)], capture_output=True, text=True)
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 500:
        raise RuntimeError(f'ffmpeg audio extraction failed for {video}: {proc.stderr[-500:]}')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--completed', type=Path, required=True)
    parser.add_argument('--part', type=int, choices=(1,2,3,4), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-clips', type=int, default=150)
    args=parser.parse_args()
    grouped, report_files = load_reports(args.reports)
    spans = sorted(grouped)
    if len(spans) != 4:
        raise RuntimeError(f'Expected four distinct season spans, got {spans}')
    span = spans[args.part-1]
    rows = grouped[span]
    plan_paths = list(args.completed.rglob('continuous_cut_plan.json'))
    if len(plan_paths) != 1:
        raise RuntimeError(f'Expected one completed clip plan, got {len(plan_paths)}')
    root = plan_paths[0].parent
    plan = json.loads(plan_paths[0].read_text())
    if any(abs(float(a)-float(b))>.02 for a,b in zip(plan['range'],span)):
        raise RuntimeError(f'Part {args.part} plan range {plan["range"]} != audit range {span}')
    words = json.loads((root/'word_timestamps.json').read_text())
    review = json.loads((root/'transcript_review.json').read_text())
    parts = json.loads((root/'rendered_parts.json').read_text())
    clips = {p['name']:p for p in parts}
    queue = []
    for r in rows:
        flag = issue_class(r)
        if flag is None:
            continue
        t=float(r['source_time'])
        queue.append({'flag':flag, 'time':t, 'file':r['file'],
            'relative_time':float(r['relative_time']),
            'original_word':r['original_word'],
            'original_confidence':r.get('original_confidence'),
            'independent_transcript':r.get('alternate_transcript',''),
            'independent_word_match':r.get('independent_word_match'),
            'timing_delta':r.get('word_start_delta_seconds'),
            'context':context(words,t)})
    extra_count=0
    for r in review:
        if r['type'] not in ('non_cyrillic','repeated_word_maybe_music'):
            continue
        t=float(r['time'])
        if any(abs(x['time']-t)<1.8 for x in queue):
            continue
        p=next((p for p in parts if p['start']<=t<p['end']),None)
        if not p:
            continue
        queue.append({'flag':'UNSAMPLED_'+r['type'].upper(),
            'time':t, 'file':p['name'], 'relative_time':t-p['start'],
            'original_word':r['text'], 'original_confidence':None,
            'independent_transcript':'NOT IN INDEPENDENT AUDIT',
            'independent_word_match':None, 'timing_delta':None,
            'context':context(words,t)})
        extra_count+=1
    priority={'ASR_TEXT_DISAGREEMENT':0,'WORD_TIMING_DISAGREEMENT':1,
              'WORD_TIMING_UNRESOLVED':2,'UNSAMPLED_NON_CYRILLIC':3,
              'UNSAMPLED_REPEATED_WORD_MAYBE_MUSIC':4}
    queue.sort(key=lambda r:(priority.get(r['flag'],10), r['time']))
    selected=[]
    for row in queue:
        if any(abs(row['time']-x['time'])<2.0 for x in selected):
            continue
        selected.append(row)
        if len(selected)>=args.max_clips:
            break
    selected.sort(key=lambda r:r['time'])
    args.output.mkdir(parents=True,exist_ok=True)
    audio_dir=args.output/'audio';audio_dir.mkdir(exist_ok=True)
    errors=[]
    for n,row in enumerate(selected,1):
        file=row['file'];video=root/file
        if file not in clips or not video.is_file():
            errors.append(f'Missing completed MP4: {file}');continue
        p=clips[file]
        dur=float(p['end'])-float(p['start'])
        rel=float(row['relative_time'])
        if not 0<=rel<=dur+.1:
            errors.append(f'Out-of-range review timestamp: {file} {rel}');continue
        dest=audio_dir/f'qa_{args.part}_{n:03}.mp3'
        try:
            extract_audio(video,dest,rel,dur)
            row['audio_file']='audio/'+dest.name
        except Exception as exc:
            errors.append(str(exc))
    with (args.output/'review_queue.csv').open('w',newline='',encoding='utf-8-sig') as f:
        columns=['flag','time','file','relative_time','original_word','original_confidence',
                 'independent_transcript','timing_delta','context','audio_file']
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(selected)
    table=[]
    for row in selected:
        play=(f'<audio controls preload="none" src="{html.escape(row["audio_file"])}"></audio>'
              if row.get('audio_file') else 'AUDIO EXTRACTION FAILED')
        cells=[f'{row["time"]:.2f}',row['flag'],row['original_word'],
               row['context'],row['independent_transcript'],
               str(row['timing_delta']),row['file']]
        table.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in cells)+
                     '<td>'+play+'</td></tr>')
    doc='''<!doctype html><html lang="ru"><head><meta charset="utf-8">
    <title>Кухня — проверка спорных субтитров</title><style>
    body{font:15px system-ui,sans-serif;margin:2rem;line-height:1.5}
    table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px;vertical-align:top}
    th{background:#eee;position:sticky;top:0}audio{width:230px}
    </style></head><body><h1>Кухня — спорные субтитры, участок %d</h1>
    <p><b>НИ ОДНА СТРОКА НЕ ПОДТВЕРЖДЕНА ПРОСЛУШИВАНИЕМ.</b>
    Это диагностический материал, а не готовые исправления.
    Фрагменты содержат звук исходного MP4 и оба варианта распознавания.</p>
    <table><thead><tr><th>Время сезона</th><th>Риск</th><th>Слово</th><th>Контекст</th>
    <th>Вторая ASR</th><th>Сдвиг, с</th><th>MP4</th><th>Звук</th></tr></thead>
    <tbody>%s</tbody></table></body></html>'''%(args.part,'\n'.join(table))
    (args.output/'index.html').write_text(doc,encoding='utf-8')
    summary={'part':args.part,'source_range':span,
       'independent_samples':len(rows),'independent_text_disagreements':sum(
            not r.get('exact_word_present_in_alt') for r in rows),
       'independent_timing_disagreements':sum(
            r.get('timing_within_0_60s') is False for r in rows),
       'independent_timing_unresolved':sum(
            r.get('timing_within_0_60s') is None for r in rows),
       'unsampled_non_cyrillic_or_repeated':extra_count,
       'review_queue_total':len(queue),'audio_review_samples':len(selected),
       'audio_extraction_errors':errors,
       'language_qa':'NOT_VERIFIED',
       'source':'completed GitHub Actions MP4 artifacts only; no Google Drive source access'}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('TRIAGE_SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
    if errors:
        raise SystemExit(f'Audio extraction errors: {len(errors)}')

if __name__=='__main__':main()
