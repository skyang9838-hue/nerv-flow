#!/usr/bin/env bash
# 녹화 → SPEED배 빠르게 → mp4.  사용: bash 만들기.sh <playwright 폴더> <작업 폴더> <출력 mp4>
# 덱 화면 머무는 시간은 HOLD_MS(기본 7000, 빠르게 하기 전 기준)
set -e
SPEED="${SPEED:-1.6}"   # 빠르기 (11/24 사용자: 1.3배보다 빠르게)
export HOLD_MS="${HOLD_MS:-7000}"
PW="$1"; WORK="$2"; OUT="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
node "$HERE/녹화.mjs" "$PW" "$WORK"
cd "$WORK"
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i frames.txt -i audio.wav -filter_complex \
  "[0:v]fps=60,setpts=PTS/${SPEED},fps=30,format=yuv420p[v];[1:a]atempo=${SPEED},volume=18dB,alimiter=limit=0.89,apad[a]" \
  -map "[v]" -map "[a]" -shortest -c:v libx264 -crf 18 -preset slow -c:a aac -b:a 192k -movflags +faststart out.mp4
cp out.mp4 "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
