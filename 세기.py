# -*- coding: utf-8 -*-
"""NERV 흐름도용 숫자 세기.

1) 이 컴퓨터의 클로드 세션 기록(~/.claude/projects/*NERV*)을 읽어
   '말 한 번(턴)'마다 클로드가 실제로 한 일을 단계별 칸으로 나누고 센다.
   → 기록/<컴퓨터이름>.json  (숫자만. 말 원문은 저장하지 않는다)
2) 드라이브의 NERV 카드·INBOX·IDEAS를 센다.
3) 기록/*.json 전부를 합쳐 data.js 를 쓴다. (HTML이 이걸 읽는다)

다른 컴퓨터에서: python 세기.py   (또는 세기.bat 더블클릭)
"""
import json, glob, os, re, socket, collections, datetime, sys

HERE = os.path.dirname(os.path.abspath(__file__))
NERV = r'G:\내 드라이브\Playground\NERV'  # 세 컴 모두 같은 주소 (저장소는 바탕화면\vibecoding에 있음)
HOST = socket.gethostname()

# ── 칸 정의 (열 순서대로) ─────────────────────────────
COLS = [
    ('말',       ['말']),
    ('종류',     ['명령', '작업 요청', '할 일·날짜', '완료 보고', '생각·보류', '질문·대화']),
    ('적는 곳',  ['프로젝트 카드', '생활 카드', '캘린더', 'INBOX', 'IDEAS·영감', '안 적음']),
    ('보여 줌',  ['홈', '상황판', '출근', '정리', '여유', '보드', '안 띄움']),
    ('일하는 방식', ['직접', '스킬', '하네스', '에이전트', '브라우저']),
    ('남는 곳',  ['2026 일지', 'Playground', 'vibecoding', '클로드 설정', '노션·캔바', '보관', '대답만']),
]

HARNESS_SKILLS = {'deck-harness', 'grad-week', 'kkokko-1115', 'muse-korea-bypass',
                  'insane-research:insane-research-main', 'insane-research:insane-research',
                  'anthropic-skills:deep-research', 'harness:harness'}

CMD = [
    ('홈',     r'^\s*(홈|오늘\s*뭐\s*해)'),
    ('출근',   r'^\s*출근'),
    ('상황판', r'^\s*상황판'),
    ('정리',   r'^\s*정리\s*$|^\s*정리\s*(하자|해|ㄱ)'),
    ('여유',   r'^\s*여유'),
    ('보드',   r'^\s*(보드|board)\s*$'),
]


WRITE_RX = re.compile(r"open\([^)]*['\"][wa]['\"]|sed -i|Set-Content|Out-File|Add-Content|write_text|\.write\(|>>?\s*['\"]?[\w/.\\-]*\.md")
NERV_FILES = [
    (r'projects[/\\][^\s\'"]+\.md', '프로젝트 카드'),
    (r'life[/\\][^\s\'"]+\.md', '생활 카드'),
    (r'INBOX\.md', 'INBOX'),
    (r'(IDEAS|INSIGHTS)\.md', 'IDEAS·영감'),
]
HOMEISH = re.compile(r'할\s*일\s*10|당장\s*할\s*일|할\s*만한\s*거|뭐\s*하지|뭐\s*해야|이제\s*뭐\s*해|지금\s*할\s*거')
DONEISH = re.compile(r'(했어|햇어|했따|했다|해놨|해 놨|끝냈|끝났|완료|보냈어|넣었어|냈어)')
DATEISH = re.compile(r'캘린더|일정\s*(넣|추가|잡)|넣어\s*놔|넣어줘|기억해|해야\s*해|마감')


def norm(p):
    return (p or '').replace('\\', '/').lower()


def place(p):
    """파일 경로 → 남는 곳/적는 곳 칸 이름"""
    p = norm(p)
    if '/nerv/archive/' in p: return '보관'
    if '/nerv/projects/' in p: return '프로젝트 카드'
    if '/nerv/life/' in p: return '생활 카드'
    if p.endswith('/nerv/inbox.md'): return 'INBOX'
    if p.endswith('/nerv/ideas.md') or p.endswith('/nerv/insights.md'): return 'IDEAS·영감'
    if '/nerv/' in p: return None            # RULES·HOME 등 NERV 자체 손질
    if '2026 일지' in p: return '2026 일지'
    if 'vibecoding' in p: return 'vibecoding'
    if '클로드 설정' in p or '/.claude/' in p: return '클로드 설정'
    if '/playground/' in p or '내 드라이브/playground' in p: return 'Playground'
    return None


def human_text(d):
    if d.get('type') != 'user' or d.get('isMeta') or d.get('isSidechain'):
        return None
    o = d.get('origin') or {}
    if o and o.get('kind') != 'human':
        return None
    c = (d.get('message') or {}).get('content')
    if isinstance(c, list):
        if any(isinstance(x, dict) and x.get('type') == 'tool_result' for x in c):
            return None
        c = ' '.join(x.get('text', '') for x in c if isinstance(x, dict) and x.get('type') == 'text')
    if not isinstance(c, str):
        return None
    t = c.strip()
    if not t or t.startswith('<') or t.startswith('[Request interrupted'):
        return None
    return t


def analyze_turn(text, tools):
    """한 턴 → 열별 칸 집합"""
    hit = {name: set() for name, _ in COLS}
    hit['말'].add('말')
    did_write_out = False
    card_new = card_done = False

    for name, inp in tools:
        inp = inp or {}
        fp = inp.get('file_path') or inp.get('notebook_path') or ''
        if name in ('Write', 'Edit', 'NotebookEdit'):
            pl = place(fp)
            if pl in ('프로젝트 카드', '생활 카드', 'INBOX', 'IDEAS·영감'):
                hit['적는 곳'].add(pl)
                s = (inp.get('new_string') or '') + (inp.get('content') or '')
                if '[x]' in s or 'status: done' in s: card_done = True
                elif pl in ('프로젝트 카드', '생활 카드'): card_new = True
            elif pl:
                hit['남는 곳'].add(pl)
                if pl != '보관': did_write_out = True
        elif name == 'Read':
            p = norm(fp)
            for rule, node in (('rules/홈.md', '홈'), ('rules/상황판.md', '상황판'),
                               ('rules/출근.md', '출근'), ('rules/정리.md', '정리')):
                if p.endswith(rule): hit['보여 줌'].add(node)
            if p.endswith('웹앱 보드.md'): hit['보여 줌'].add('보드')
        elif name in ('Bash', 'PowerShell'):
            cmd = inp.get('command') or ''
            if re.search(r'(mv|Move-Item|move)\b.*projects.*archive', cmd, re.S):
                hit['남는 곳'].add('보관'); card_done = True
            elif WRITE_RX.search(cmd):
                for rx, pl in NERV_FILES:
                    if re.search(rx, cmd):
                        hit['적는 곳'].add(pl)
                        if '[x]' in cmd or 'status: done' in cmd: card_done = True
                        elif pl in ('프로젝트 카드', '생활 카드'): card_new = True
            if re.search(r'git\b[^\n]*\b(commit|push)\b', cmd) and 'vibecoding' in cmd:
                hit['남는 곳'].add('vibecoding'); did_write_out = True
            elif '2026 일지' in cmd and (WRITE_RX.search(cmd) or re.search(r'\.save\(|Copy-Item|\bcp\b|SaveAs|output', cmd)):
                hit['남는 곳'].add('2026 일지'); did_write_out = True
            if re.search(r'aside', cmd, re.I):
                hit['일하는 방식'].add('브라우저')
        elif name == 'Skill':
            sk = inp.get('skill') or ''
            if sk == 'workflow-authoring': continue          # Workflow 앞에 읽는 참고서
            if sk in HARNESS_SKILLS: hit['일하는 방식'].add('하네스')
            elif sk == 'aside-browser': hit['일하는 방식'].add('브라우저')
            else: hit['일하는 방식'].add('스킬')
        elif name == 'Workflow':
            hit['일하는 방식'].add('하네스')
        elif name == 'Agent':
            hit['일하는 방식'].add('에이전트')
        elif name.startswith('mcp__claude-in-chrome') or name.startswith('mcp__playwright') \
                or name.startswith('mcp__Claude_Browser'):
            hit['일하는 방식'].add('브라우저')
        elif 'Google_Calendar__' in name and re.search(r'create|update|delete', name):
            hit['적는 곳'].add('캘린더')
        elif re.search(r'(Notion|Canva)__.*(create|update|edit|move|upload|autofill|generate|copy|merge)', name):
            hit['남는 곳'].add('노션·캔바'); did_write_out = True

    # 명령어
    cmd_hit = None
    if len(text) <= 20:
        for node, rx in CMD:
            if re.search(rx, text, re.I):
                cmd_hit = node; break
    if not cmd_hit and len(text) <= 40 and HOMEISH.search(text):
        cmd_hit = '홈'
    if cmd_hit:
        hit['보여 줌'].add(cmd_hit)
    if re.match(r'^\s*여유', text):
        hit['보여 줌'].add('여유')

    # 종류 (하나만, 앞쪽 우선)
    w = hit['일하는 방식']
    if cmd_hit or hit['보여 줌']:
        kind = '명령'
    elif did_write_out or w & {'하네스', '스킬', '에이전트', '브라우저'}:
        kind = '작업 요청'
    elif card_done or '보관' in hit['남는 곳']:
        kind = '완료 보고'
    elif card_new or '캘린더' in hit['적는 곳']:
        kind = '할 일·날짜'
    elif hit['적는 곳'] & {'INBOX', 'IDEAS·영감'}:
        kind = '생각·보류'
    elif len(text) <= 60 and DONEISH.search(text) and not re.search(r'\?|해줘|해 줘', text):
        kind = '완료 보고'
    elif DATEISH.search(text):
        kind = '할 일·날짜'
    else:
        kind = '질문·대화'
    hit['종류'].add(kind)

    if not w:
        w.add('직접')
    if not hit['적는 곳']:
        hit['적는 곳'].add('안 적음')
    if not hit['보여 줌']:
        hit['보여 줌'].add('안 띄움')
    if not hit['남는 곳']:
        hit['남는 곳'].add('대답만')
    return hit, kind


def count_logs():
    root = os.path.expanduser('~/.claude/projects')
    dirs = [d for d in glob.glob(os.path.join(root, '*')) if re.search(r'Playground-NERV$', d)]
    node = collections.Counter()
    edge = collections.Counter()
    paths = collections.Counter()
    daily = collections.Counter()
    kinds_daily = collections.defaultdict(collections.Counter)
    skills = collections.Counter()
    sessions = 0
    samples = collections.defaultdict(list)   # --samples 일 때만 화면에 찍음
    for d in dirs:
        for f in glob.glob(os.path.join(d, '*.jsonl')):
            turns = []
            cur = None
            for line in open(f, encoding='utf-8', errors='replace'):
                try: x = json.loads(line)
                except Exception: continue
                t = human_text(x)
                if t is not None:
                    cur = {'text': t, 'ts': x.get('timestamp', ''), 'tools': []}
                    turns.append(cur); continue
                if cur and x.get('type') == 'assistant' and not x.get('isSidechain'):
                    for c in (x.get('message') or {}).get('content') or []:
                        if isinstance(c, dict) and c.get('type') == 'tool_use':
                            cur['tools'].append((c.get('name', ''), c.get('input')))
                            if c.get('name') == 'Skill' and (c.get('input') or {}).get('skill') != 'workflow-authoring':
                                skills[(c.get('input') or {}).get('skill', '')] += 1
            if turns: sessions += 1
            for tr in turns:
                hit, kind = analyze_turn(tr['text'], tr['tools'])
                day = tr['ts'][:10]
                daily[day] += 1
                kinds_daily[day][kind] += 1
                if len(samples[kind]) < 400: samples[kind].append(tr['text'][:70].replace('\n', ' '))
                cols = [sorted(hit[name]) for name, _ in COLS]
                paths[' > '.join('+'.join(x) for x in cols)] += 1
                for name, _ in COLS:
                    for n in hit[name]: node[name + '|' + n] += 1
                # 연결: 비어 있지 않은 열끼리 차례로 이음 (빈 열은 건너뜀)
                filled = [c for c in cols if c]
                for a, b in zip(filled, filled[1:]):
                    for x1 in a:
                        for x2 in b:
                            ci = next(i for i, c in enumerate(cols) if c is a)
                            cj = next(i for i, c in enumerate(cols) if c is b)
                            edge[f'{COLS[ci][0]}|{x1}>{COLS[cj][0]}|{x2}'] += 1
    return {
        'host': HOST, 'counted_at': datetime.datetime.now().isoformat(timespec='minutes'),
        'sessions': sessions, 'turns': sum(daily.values()),
        'first_day': min(daily) if daily else None, 'last_day': max(daily) if daily else None,
        'node': dict(node), 'edge': dict(edge), 'paths': dict(paths), 'daily': dict(daily),
        'kinds_daily': {k: dict(v) for k, v in kinds_daily.items()},
        'skills': dict(skills),
    }, samples


def count_drive():
    def fm(path):
        txt = open(path, encoding='utf-8', errors='replace').read()
        m = re.search(r'^status:\s*(\S+)', txt, re.M)
        recs = re.findall(r'^- (20\d\d-\d\d-\d\d)', txt.split('## 기록', 1)[1], re.M) if '## 기록' in txt else []
        return (m.group(1) if m else ''), recs
    out = {'projects': collections.Counter(), 'life': collections.Counter(), 'archive': 0,
           'records_daily': collections.Counter()}
    for sub in ('projects', 'life'):
        for p in glob.glob(os.path.join(NERV, sub, '*.md')):
            st, recs = fm(p)
            out[sub][st or '?'] += 1
            for r in recs: out['records_daily'][r] += 1
    for p in glob.glob(os.path.join(NERV, 'archive', '**', '*.md'), recursive=True):
        if os.path.dirname(p) == os.path.join(NERV, 'archive'): out['archive'] += 1
        try:
            _, recs = fm(p)
            for r in recs: out['records_daily'][r] += 1
        except Exception: pass
    def lines(name):
        p = os.path.join(NERV, name)
        if not os.path.exists(p): return 0
        return sum(1 for l in open(p, encoding='utf-8', errors='replace') if l.startswith('- '))
    out['inbox'] = lines('INBOX.md'); out['ideas'] = lines('IDEAS.md'); out['insights'] = lines('INSIGHTS.md')
    out['projects'] = dict(out['projects']); out['life'] = dict(out['life'])
    out['records_daily'] = dict(out['records_daily'])
    return out


def main():
    logs, samples = count_logs()
    os.makedirs(os.path.join(HERE, '기록'), exist_ok=True)
    with open(os.path.join(HERE, '기록', HOST + '.json'), 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=1)
    print(f'[{HOST}] 세션 {logs["sessions"]}개 · 말 {logs["turns"]}번 ({logs["first_day"]} ~ {logs["last_day"]})')

    if '--samples' in sys.argv:
        for k, v in samples.items():
            print('\n##', k, len(v))
            for s in v[::max(1, len(v) // 25)][:25]: print('  ·', s)

    hosts = []
    for p in sorted(glob.glob(os.path.join(HERE, '기록', '*.json'))):
        hosts.append(json.load(open(p, encoding='utf-8')))
    data = {'cols': COLS, 'hosts': hosts, 'drive': count_drive(),
            'built_at': datetime.datetime.now().isoformat(timespec='minutes')}
    with open(os.path.join(HERE, 'data.js'), 'w', encoding='utf-8') as f:
        f.write('window.NERV_DATA = ' + json.dumps(data, ensure_ascii=False) + ';\n')
    print('합친 컴퓨터:', ', '.join(h['host'] for h in hosts), '→ data.js')


if __name__ == '__main__':
    main()
