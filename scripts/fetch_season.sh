#!/usr/bin/env bash
set -euo pipefail
python -m pip install -q gdown
gdown 102EHQNQ-kDPZ18lKEgr5pWPDDoQnLe3T -O season.mp4
test "$(stat -c%s season.mp4)" -eq 1900888612
ffprobe -hide_banner -v error -show_entries stream=codec_name,codec_type,width,height,r_frame_rate:format=duration,size -of json season.mp4 | tee source-info.json
ffmpeg -hide_banner -loglevel error -y -ss 3095.4 -i season.mp4 -frames:v 1 -vf scale=960:-2 sample.jpg
