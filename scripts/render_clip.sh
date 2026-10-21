#!/usr/bin/env bash
set -euo pipefail
# Usage: bash scripts/render_clip.sh input.mp4 start_seconds duration_seconds captions.ass output.mp4
input="$1"; start="$2"; duration="$3"; subs="$4"; out="$5"
ffmpeg -hide_banner -y -ss "$start" -i "$input" -t "$duration" \
  -filter_complex "[0:v]split=2[b][f];[b]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=18:3[bg];[f]scale=1080:-2:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2+65,subtitles=$subs,format=yuv420p[v]" \
  -map '[v]' -map '0:a:0' -c:v libx264 -preset medium -crf 17 -c:a aac -b:a 192k -movflags +faststart "$out"
ffprobe -v error -show_entries format=duration,size -of json "$out"
