#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg
ffmpeg -hide_banner -version | head -n 1
ffprobe -hide_banner -version | head -n 1
