#!/usr/bin/env bash
set -euo pipefail
ffmpeg -hide_banner -loglevel error -y -ss 3095.4 -i season.mp4 -t 60.48 -vn -ac 1 -ar 16000 goose_audio.wav
python scripts/align_goose.py
python scripts/goose_captions.py
ffmpeg -hide_banner -y -ss 3095.4 -i season.mp4 -t 60.48 \
  -filter_complex "[0:v]split=2[base][front];[base]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=22:2[bg];[front]scale=1080:-2:flags=lanczos,unsharp=3:3:0.25[fg];[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2+45,ass=captions.ass,format=yuv420p[v]" \
  -map '[v]' -map 0:a:0 -c:v libx264 -preset veryfast -crf 17 -r 25 \
  -c:a aac -b:a 192k -movflags +faststart "КиноГрызь_Гусь_версия_GitHub.mp4"
ffprobe -v error -show_entries format=duration,size -of json "КиноГрызь_Гусь_версия_GitHub.mp4"
