// 스레드용 영상 녹화: 말풍선 "시키기 → 하네스" → 하네스 7단계 → 발표 덱 화면에서 끝.
// 화면은 CDP 스크린캐스트(1920×1080 JPEG). 효과음은 웹앱 click()/tick()이 불린 시각을 적어 두었다가
// 끝난 뒤 같은 합성식으로 OfflineAudioContext에 다시 그려 WAV로 뽑는다 (헤드리스 MediaRecorder는 조용한 구간을 건너뛰어 어긋남).
// 실행: node 녹화.mjs <playwright 폴더> <출력 폴더>   → 출력 폴더에 frames/, audio.wav, frames.txt, meta.json
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';
import { fileURLToPath, pathToFileURL } from 'url';

const [pwDir, outDir] = process.argv.slice(2);
const require = createRequire(path.join(pwDir, 'x.js'));
const { chromium } = require('playwright');
const here = path.dirname(fileURLToPath(import.meta.url));
const url = pathToFileURL(path.join(here, '..', 'index.html')).href;

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(path.join(outDir, 'frames'), { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
await ctx.addInitScript(() => {
  // 마우스 커서 + 누를 때 동그라미
  addEventListener('DOMContentLoaded', () => {
    const st = document.createElement('style');
    st.textContent = `#__cur{position:fixed;left:0;top:0;width:34px;height:34px;pointer-events:none;z-index:2147483647;transform:translate(-200px,-200px);filter:drop-shadow(0 2px 4px rgba(0,0,0,.5))}
      .__rip{position:fixed;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;border:3px solid rgba(255,140,50,.95);pointer-events:none;z-index:2147483646;animation:__r .55s ease-out forwards}
      @keyframes __r{to{transform:scale(4.2);opacity:0}}`;
    document.head.appendChild(st);
    const c = document.createElement('div');
    c.id = '__cur';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    addEventListener('mousemove', e => { c.style.transform = `translate(${e.clientX - 4}px,${e.clientY - 3}px)`; }, true);
    addEventListener('mousedown', e => {
      const r = document.createElement('div'); r.className = '__rip';
      r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
      document.body.appendChild(r); setTimeout(() => r.remove(), 700);
    }, true);
  });
});

const page = await ctx.newPage();
await page.goto(url);
await page.waitForSelector('#chList .chb');
await page.evaluate(() => {
  // 웹앱 전역 함수 click/tick을 감싸 불린 시각만 적는다 (소리는 그대로 남)
  window.__ev = [];
  const c0 = window.click, t0 = window.tick;
  window.click = (vol = .3, rate = 1) => { if (soundOn) __ev.push({ k: 'c', vol, rate, t: Date.now() }); return c0(vol, rate); };
  window.tick = (freq = 660, vol = .06) => { if (soundOn) __ev.push({ k: 't', freq, vol, t: Date.now() }); return t0(freq, vol); };
});
await page.mouse.move(1150, 760);

const cdp = await ctx.newCDPSession(page);
const frames = [];
cdp.on('Page.screencastFrame', async f => {
  const n = frames.length + 1;
  const file = `f${String(n).padStart(5, '0')}.jpg`;
  fs.writeFileSync(path.join(outDir, 'frames', file), Buffer.from(f.data, 'base64'));
  frames.push({ file, t: f.metadata.timestamp });
  cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
});
await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });

const sleep = ms => new Promise(r => setTimeout(r, ms));
async function glideClick(sel) {
  const b = await page.locator(sel).boundingBox();
  await page.mouse.move(b.x + b.width * 0.45, b.y + b.height / 2, { steps: 28 });
  await sleep(250);
  await page.mouse.down(); await sleep(70); await page.mouse.up();
}

await sleep(1200);
const tStart = Date.now() / 1000 - 0.4;
await glideClick('#chList .chb:nth-child(3)');          // 일 좀 시켜 볼까? (시키기)
await sleep(1100);
await glideClick('#chList .chb:nth-child(3)');          // 이 글로 발표 덱 만들어 (하네스)
await sleep(450);
await page.evaluate(() => { const c = document.getElementById('__cur'); c.style.transition = 'opacity .4s'; c.style.opacity = 0; }); // 다 누르면 커서 숨김
const tClick = Date.now() / 1000;
await page.waitForFunction(() => document.querySelector('#tnext')?.classList.contains('pulse'), null, { timeout: 90000 });
const tDone = Date.now() / 1000;
await sleep(Number(process.env.HOLD_MS || 9000));        // 덱 화면에서 머물기
const tEnd = Date.now() / 1000;
await cdp.send('Page.stopScreencast');

const audio = await page.evaluate(async ({ tStart, tEnd }) => {
  // 적어 둔 시각대로 웹앱과 같은 합성식으로 다시 그림 (index.html의 click·tick과 같은 값)
  const SR = 48000, dur = tEnd - tStart + 0.5;
  const oc = new OfflineAudioContext(1, Math.ceil(SR * dur), SR);
  const noise = oc.createBuffer(1, oc.sampleRate * .03, oc.sampleRate);
  const d = noise.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / d.length, 4);
  let last = -1e9, n = 0;
  for (const e of window.__ev) {
    const t = e.t / 1000 - tStart; if (t < 0 || t > dur) continue;
    if (e.k === 'c') {
      if (e.t - last < 18) continue; last = e.t;
      const s = oc.createBufferSource(), f = oc.createBiquadFilter(), g = oc.createGain();
      s.buffer = noise; s.playbackRate.value = e.rate * (0.9 + Math.random() * .2);
      f.type = 'bandpass'; f.frequency.value = 2200; f.Q.value = .8; g.gain.value = e.vol;
      s.connect(f).connect(g).connect(oc.destination); s.start(t);
    } else {
      const o = oc.createOscillator(), g = oc.createGain();
      o.type = 'sine'; o.frequency.value = e.freq;
      g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(e.vol, t + .008); g.gain.exponentialRampToValueAtTime(.0001, t + .25);
      o.connect(g).connect(oc.destination); o.start(t); o.stop(t + .3);
    }
    n++;
  }
  const buf = await oc.startRendering(), ch = buf.getChannelData(0);
  const pcm = new DataView(new ArrayBuffer(44 + ch.length * 2));
  const w = (o, str) => { for (let i = 0; i < str.length; i++) pcm.setUint8(o + i, str.charCodeAt(i)); };
  w(0, 'RIFF'); pcm.setUint32(4, 36 + ch.length * 2, true); w(8, 'WAVEfmt '); pcm.setUint32(16, 16, true);
  pcm.setUint16(20, 1, true); pcm.setUint16(22, 1, true); pcm.setUint32(24, SR, true); pcm.setUint32(28, SR * 2, true);
  pcm.setUint16(32, 2, true); pcm.setUint16(34, 16, true); w(36, 'data'); pcm.setUint32(40, ch.length * 2, true);
  for (let i = 0; i < ch.length; i++) pcm.setInt16(44 + i * 2, Math.max(-1, Math.min(1, ch[i])) * 0x7fff, true);
  const u = new Uint8Array(pcm.buffer); let s = '';
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000));
  return { b64: btoa(s), events: n };
}, { tStart, tEnd });
fs.writeFileSync(path.join(outDir, 'audio.wav'), Buffer.from(audio.b64, 'base64'));

// ffmpeg concat 목록 (프레임마다 다음 프레임까지 머무는 시간)
const before = frames.filter(f => f.t <= tStart);
const fr = (before.length ? [before[before.length - 1]] : []).concat(frames.filter(f => f.t > tStart && f.t <= tEnd));
let txt = '';
for (let i = 0; i < fr.length; i++) {
  const next = i + 1 < fr.length ? fr[i + 1].t : tEnd;
  const t0 = i === 0 ? tStart : fr[i].t;
  txt += `file 'frames/${fr[i].file}'\nduration ${Math.max(0.001, next - t0).toFixed(4)}\n`;
}
txt += `file 'frames/${fr[fr.length - 1].file}'\n`;
fs.writeFileSync(path.join(outDir, 'frames.txt'), txt);
const meta = { tStart, tClick, tDone, tEnd, soundEvents: audio.events, frames: fr.length };
fs.writeFileSync(path.join(outDir, 'meta.json'), JSON.stringify(meta, null, 2));
console.log(JSON.stringify(meta));
await browser.close();
