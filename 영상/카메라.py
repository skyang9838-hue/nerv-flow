# 폰에서 보기 좋게 중요한 곳만 16:9로 확대해 따라가는 카메라.
# 녹화.mjs가 남긴 frames/·frames.txt·meta.json(장면 시각·칸 위치)을 읽어
# 출력 프레임마다 잘라 1920×1080으로 키운 뒤 ffmpeg에 raw로 넘긴다. 소리는 audio.wav를 SPEED배로.
# 사용: python -X utf8 카메라.py <작업 폴더> <출력 mp4>   (환경변수 SPEED 기본 1.6)
import json, os, re, subprocess, sys
from PIL import Image

work, out = sys.argv[1], sys.argv[2]
SPEED = float(os.environ.get('SPEED', '1.6'))
FPS = 30
m = json.load(open(os.path.join(work, 'meta.json'), encoding='utf-8'))
S = m['scale']
R = m['rects']

# 프레임 시간표
txt = open(os.path.join(work, 'frames.txt'), encoding='utf-8').read()
items = re.findall(r"file 'frames/(f\d+\.jpg)'\nduration ([\d.]+)", txt)
tl, t = [], m['tStart']
for f, d in items:
    tl.append((t, f)); t += float(d)

H = lambda w: w * 9 / 16
def clampx(x, w): return max(0, min(1920 - w, x))

# ── 카메라 위치 (1920×1080 기준, (x, y, w)) ──
# A: 말풍선 고르기 — 제목 + 말풍선
A = (80, 76, 1250)
# B: 하네스 — 제목 + 단계 칸, 켜지는 칸을 따라 오른쪽으로
BW = 1102
BY = 100
rights = sorted({b[2] for b in R['boxes']})            # 칸 오른쪽 끝 (열마다)
def bx(col_next, w=BW, pad=100):                       # 다음 칸이 화면 안에 들어오게
    return clampx(min(max(110, rights[col_next] + pad - w), 1920 - w - 60), w)
# B2: 제목을 읽은 뒤엔 단계 칸으로 더 당김 (칸 위·아래 + '걸리면 다시' 글자까지)
B2W = 860
boxes_cy = (min(b[1] for b in R['boxes']) - 60 + max(b[3] for b in R['boxes'])) / 2
B2Y = boxes_cy - H(B2W) / 2
# C: 덱 창을 꽉 차게
d = R['deck']; cw = max(d[2] - d[0], (d[3] - d[1]) * 16 / 9) + 60
C = (clampx((d[0] + d[2]) / 2 - cw / 2, cw), (d[1] + d[3]) / 2 - H(cw) / 2, cw)

ticks = m['ticks']   # 칸2·칸3·칸4·칸5·칸6 켜짐, 걸리면 다시, 칸7 켜짐
keys = [  # (시작 시각, 옮겨 가는 시간, 목표)
    (m['tStart'], 0, A),
    (m['tHarness'] + 0.1, 0.9, (bx(1), BY, BW)),
]
for i, col_next in [(1, 3), (2, 4), (3, 5), (4, 6)]:
    keys.append((ticks[i], 0.9 if i == 1 else 0.8, (bx(col_next, B2W, 70), B2Y, B2W)))
keys.append((m['tDeck'] + 0.05, 1.0, C))

def ease(u): return 4 * u ** 3 if u < .5 else 1 - (-2 * u + 2) ** 3 / 2
def cam(T):
    cur = keys[0][2]
    for t0, dur, tgt in keys:
        if T < t0: break
        if dur and T < t0 + dur:
            u = ease((T - t0) / dur)
            return tuple(a + (b - a) * u for a, b in zip(cur, tgt))
        cur = tgt
    return cur

def frame_at(T):
    lo, hi = 0, len(tl) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if tl[mid][0] <= T: lo = mid
        else: hi = mid - 1
    return tl[lo][1]

dur_out = (m['tEnd'] - m['tStart']) / SPEED
n = int(dur_out * FPS)
ff = subprocess.Popen([
    'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '1920x1080', '-r', str(FPS), '-i', '-',
    '-i', os.path.join(work, 'audio.wav'),
    '-filter_complex', f'[1:a]atempo={SPEED},volume=18dB,alimiter=limit=0.89,apad[a]',
    '-map', '0:v', '-map', '[a]', '-shortest',
    '-c:v', 'libx264', '-crf', '18', '-preset', 'slow', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
cache = {}
for k in range(n):
    T = m['tStart'] + k / FPS * SPEED
    f = frame_at(T)
    if f not in cache:
        cache.clear(); cache[f] = Image.open(os.path.join(work, 'frames', f)).convert('RGB')
    x, y, w = cam(T)
    box = (x * S, y * S, (x + w) * S, (y + H(w)) * S)
    ff.stdin.write(cache[f].resize((1920, 1080), Image.LANCZOS, box=box).tobytes())
ff.stdin.close(); ff.wait()
print(f'{n} frames, {dur_out:.1f}s, A={A} C={tuple(round(v) for v in C)}')
