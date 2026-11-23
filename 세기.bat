@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
python "세기.py"
start "" "NERV 흐름도.html"
pause
