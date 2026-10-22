#!/usr/bin/env bash
set -euo pipefail
# The previous cut included the beginning of the NEXT dialogue at 59.6s.
# The previous completed spoken phrase ends near 58.0s.
DURATION=58.60
ffmpeg -hide_banner -loglevel error -y -ss 3095.4 -i season.mp4 -t "$DURATION" \
-filter_complex "[0:v]split=2[base][front];[base]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=22:2[bg];[front]scale=1080:-2:flags=lanczos,unsharp=3:3:0.25[fg];[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2+45,format=yuv420p[v]" \
-map '[v]' -map 0:a:0 -c:v libx264 -preset veryfast -crf 17 -r 25 \
-af 'afade=t=out:st=58.35:d=0.25' -c:a aac -b:a 192k -movflags +faststart 'КиноГрызь_Гусь_без_субтитров.mp4'
ffprobe -v error -show_entries format=duration,size -of json 'КиноГрызь_Гусь_без_субтитров.mp4'
