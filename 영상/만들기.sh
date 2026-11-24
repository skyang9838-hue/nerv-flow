#!/usr/bin/env bash
# 녹화 → 카메라(중요한 곳만 16:9로 확대해 따라감) + SPEED배 빠르게 → mp4
# 사용: bash 만들기.sh <playwright 폴더> <작업 폴더> <출력 mp4>
# SPEED 기본 1.6 (11/24 "1.3배보다 빠르게"), 덱 화면 머무는 시간 HOLD_MS 기본 7000(빠르게 하기 전 기준)
# 녹화 배율 SCALE 기본 1.5 (확대해도 선명하게. 2는 초당 장수가 반으로 줄어 끊김)
set -e
export SPEED="${SPEED:-1.6}"
export HOLD_MS="${HOLD_MS:-7000}"
PW="$1"; WORK="$2"; OUT="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
node "$HERE/녹화.mjs" "$PW" "$WORK"
PYTHONUTF8=1 python -X utf8 "$HERE/카메라.py" "$WORK" "$OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
