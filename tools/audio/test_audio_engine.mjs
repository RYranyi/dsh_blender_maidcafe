/**
 * test_audio_engine.mjs —— 用真实浏览器（Edge via CDP）验收 audio.js
 *
 * 不依赖 playwright：用 Node 原生 WebSocket 直连 Chrome DevTools Protocol。
 * 临时 profile 强制落在 .scratch，绝不写 C:\Users\win10。
 *
 * 验收项：
 *   1. init() 加载 manifest + 全部 buffer 成功
 *   2. resume() 在用户手势语义下进入 running
 *   3. setTimePhase/setWeather 切换床层正确
 *   4. 每个 one-shot 都能 playOnce 成功
 *   5. notifyLightning 触发 'lightning' 回调 + 延时雷
 *   6. 交叉淡化 / 暂停 / 音量接口不抛错
 *   7. 全程无 console error / pageerror
 *
 * 用法: node test_audio_engine.mjs
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const ROOT = 'E:\\dsh\\maid_cafe';
const SCRATCH = path.join(ROOT, '.scratch', 'audio-dev', 'profile');
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 8731;
const CDP_PORT = 9333;

const MIME = {
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.ogg': 'audio/ogg',
  '.html': 'text/html; charset=utf-8',
};

// ---------------- 静态服务器 ----------------
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/test_page.html';
  const fp = path.join(ROOT, p.replace(/^\/+/, ''));
  if (!fp.startsWith(ROOT)) { res.writeHead(403); res.end('forbidden'); return; }
  fs.readFile(fp, (err, buf) => {
    if (err) { res.writeHead(404); res.end('404 ' + p); return; }
    res.writeHead(200, {
      'content-type': MIME[path.extname(fp).toLowerCase()] || 'application/octet-stream',
      'content-length': buf.length,
      'cache-control': 'no-store',
    });
    res.end(buf);
  });
});

const TEST_HTML = `<!doctype html>
<html><head><meta charset="utf-8"><title>audio engine test</title></head>
<body>
<script type="module">
  import { AudioEngine } from '/js/audio.js';
  window.AudioEngine = AudioEngine;
  window.__ready = true;
</script>
</body></html>`;

// ---------------- 极简 CDP 客户端 ----------------
class CDP {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.handlers = new Map();
    ws.addEventListener('message', (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      } else if (msg.method) {
        const hs = this.handlers.get(msg.method) || [];
        for (const h of hs) { try { h(msg.params); } catch {} }
      }
    });
  }
  on(method, cb) {
    if (!this.handlers.has(method)) this.handlers.set(method, []);
    this.handlers.get(method).push(cb);
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.has(id)) { this.pending.delete(id); reject(new Error('CDP timeout ' + method)); }
      }, 60000);
    });
  }
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function waitForCdp(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`);
      if (res.ok) return await res.json();
    } catch {}
    await sleep(250);
  }
  throw new Error('CDP 端口没起来');
}

async function main() {
  fs.mkdirSync(SCRATCH, { recursive: true });
  const htmlPath = path.join(ROOT, 'test_page.html');
  fs.writeFileSync(htmlPath, TEST_HTML, 'utf8');
  await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
  console.log('static server: http://127.0.0.1:' + PORT);

  const args = [
    `--remote-debugging-port=${CDP_PORT}`,
    '--user-data-dir=' + SCRATCH,
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--autoplay-policy=no-user-gesture-required',
    '--mute-audio',
    'about:blank',
  ];
  console.log('launching edge...');
  const proc = spawn(EDGE, args, { stdio: 'ignore', detached: false });

  let browser = null;
  try {
    await waitForCdp();
    // 连到 browser endpoint 拿一个 page target
    const targets = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
    let pageTarget = targets.find((t) => t.type === 'page');
    if (!pageTarget) {
      // 新建一个
      const created = await fetch(`http://127.0.0.1:${CDP_PORT}/json/new?about:blank`, { method: 'PUT' });
      pageTarget = await created.json();
    }
    const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
    await new Promise((res, rej) => {
      ws.addEventListener('open', res, { once: true });
      ws.addEventListener('error', rej, { once: true });
    });
    const cdp = new CDP(ws);

    const consoleErrors = [];
    const pageErrors = [];
    cdp.on('Runtime.consoleAPICalled', (p) => {
      if (p.type === 'error') {
        consoleErrors.push(p.args.map((a) => a.value ?? a.description ?? '').join(' '));
      }
    });
    cdp.on('Runtime.exceptionThrown', (p) => {
      const d = p.exceptionDetails || {};
      pageErrors.push((d.exception && (d.exception.description || d.exception.value)) || d.text);
    });
    await cdp.send('Runtime.enable');
    await cdp.send('Page.enable');

    await cdp.send('Page.navigate', { url: `http://127.0.0.1:${PORT}/test_page.html` });
    await sleep(1500);

    // 等模块加载
    for (let i = 0; i < 40; i++) {
      const r = await cdp.send('Runtime.evaluate', {
        expression: 'window.__ready === true', returnByValue: true, awaitPromise: false,
      });
      if (r.result && r.result.value === true) break;
      await sleep(250);
    }

    // 跑验收脚本
    const script = `(async () => {
      const out = { ok: false, log: [], errors: [] };
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      try {
        if (!window.AudioEngine) { out.errors.push('AudioEngine 未加载'); return out; }
        const audio = new window.AudioEngine('/assets/audio/');
        window.__audio = audio;

        await audio.init();
        out.log.push('init ok ctx=' + audio.ctx.state);
        const totalKeys = Object.keys(audio.manifest.sounds).length;
        out.log.push('manifest 声明 ' + totalKeys + ' 个 key');
        out.log.push('成功解码 buffer: ' + audio.buffers.size + '/' + totalKeys);
        if (audio.buffers.size < totalKeys) out.errors.push('buffer 缺失 ' + (totalKeys - audio.buffers.size));

        await audio.resume();
        out.log.push('resume -> ' + audio.ctx.state);
        if (audio.ctx.state !== 'running') out.errors.push('AudioContext 没进入 running');

        audio.setTimePhase('morning', { fadeMs: 300 });
        audio.setWeather('rain_med', { fadeMs: 300 });
        await sleep(600);
        out.log.push('morning+rain_med beds=' + JSON.stringify(audio.getActiveBeds()));
        const set1 = audio.getActiveBeds();
        if (!set1.includes('amb_morning') || !set1.includes('amb_rain_med')) out.errors.push('晨+中雨床层不对: ' + JSON.stringify(set1));

        audio.setTimePhase('night', { fadeMs: 300 });
        audio.setWeather('storm', { fadeMs: 300 });
        await sleep(600);
        const set2 = audio.getActiveBeds();
        out.log.push('night+storm beds=' + JSON.stringify(set2));
        if (!set2.includes('amb_night') || !set2.includes('amb_storm')) out.errors.push('夜+雷阵雨床层不对: ' + JSON.stringify(set2));
        if (set2.includes('amb_morning')) out.errors.push('旧的晨间床没有淡出');

        // one-shot：逐个等待并发槽位释放再播，验证 19 个都能播出来
        const sfx = Object.keys(audio.manifest.sounds).filter((k) => audio.manifest.sounds[k].layer === 'one_shot');
        let played = 0;
        for (const k of sfx) {
          // 等并发槽位空出来（engine 的 maxConcurrent 保护）
          for (let t = 0; t < 100; t++) {
            if (audio._activeSfx < audio.opts.maxConcurrent) break;
            await sleep(100);
          }
          if (audio.playOnce(k, { gain: -18 })) played++;
          await sleep(30);
        }
        out.log.push('playOnce 成功 ' + played + '/' + sfx.length + '（逐个等槽位）');
        out.sfxPlayed = played; out.sfxTotal = sfx.length;
        if (played < sfx.length) out.errors.push('有 ' + (sfx.length - played) + ' 个 one-shot 没播出来');

        // 并发上限验证：一次性狂发，超出部分应被拒绝而不是叠爆
        for (let i = 0; i < 100; i++) await sleep(100);
        let accepted = 0;
        for (let i = 0; i < 20; i++) {
          if (audio.playOnce('sfx_cup_clink', { gain: -30 })) accepted++;
        }
        out.log.push('并发上限测试：狂发 20 个，接受 ' + accepted + ' 个（上限 ' + audio.opts.maxConcurrent + '）');
        if (accepted > audio.opts.maxConcurrent) {
          out.errors.push('并发上限失效：接受了 ' + accepted + ' > ' + audio.opts.maxConcurrent);
        }
        // 等所有音效播完，避免影响后续测试
        for (let i = 0; i < 200; i++) { if (audio._activeSfx <= 0) break; await sleep(100); }

        // lightning
        let cbCount = 0, lastPayload = null;
        audio.on('lightning', (p) => { cbCount++; lastPayload = p; });
        await sleep(500);
        const ln = audio.notifyLightning();
        await sleep(150);
        out.log.push('notifyLightning -> ' + JSON.stringify(ln) + ' callback=' + cbCount);
        if (cbCount < 1) out.errors.push('lightning 回调未触发');

        // scheduler
        audio.startEventScheduler();
        await sleep(300);
        audio.stopEventScheduler();
        out.log.push('scheduler start/stop ok');

        // pause
        audio.setPaused(true);
        await sleep(200);
        out.pausedState = audio.ctx.state;
        audio.setPaused(false);
        await sleep(200);
        out.log.push('pause -> ' + out.pausedState + ' -> ' + audio.ctx.state);

        // volume
        audio.setMasterVolume(0.5);
        out.log.push('master=' + audio.getMasterVolume());

        out.bufferCount = audio.buffers.size;
        out.totalKeys = totalKeys;
        out.maxConcurrent = audio.opts.maxConcurrent;
        audio.destroy();
        out.ok = out.errors.length === 0;
      } catch (e) {
        out.errors.push('异常: ' + (e && e.message ? e.message : String(e)));
        out.stack = e && e.stack ? String(e.stack) : '';
      }
      return out;
    })()`;

    const evalRes = await cdp.send('Runtime.evaluate', {
      expression: script,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    });
    browser = evalRes.result && evalRes.result.value;
    if (!browser) console.log('evaluate 返回空：', JSON.stringify(evalRes).slice(0, 800));

    console.log('\n--- 引擎验收 ---');
    if (browser) {
      browser.log.forEach((l) => console.log('  ' + l));
      if (browser.stack) console.log(browser.stack);
    }
    if (consoleErrors.length) {
      console.log('\nconsole.error:'); consoleErrors.slice(0, 20).forEach((e) => console.log('  ' + e));
    }
    if (pageErrors.length) {
      console.log('\npageerror:'); pageErrors.slice(0, 20).forEach((e) => console.log('  ' + e));
    }

    const bad = [...((browser && browser.errors) || []), ...consoleErrors, ...pageErrors];
    console.log('\n结论: ' + (bad.length === 0 && browser && browser.ok
      ? 'PASS ✅ 全部接口正常、无 console 报错'
      : 'FAIL ❌ ' + bad.length + ' 个问题'));
    bad.forEach((e) => console.log('  - ' + e));

    try { ws.close(); } catch {}
    process.exitCode = (bad.length === 0 && browser && browser.ok) ? 0 : 1;
  } finally {
    try { proc.kill(); } catch {}
    server.close();
    try { fs.unlinkSync(htmlPath); } catch {}
    await sleep(300);
  }
}

main().catch((e) => { console.error(e); server.close(); process.exit(1); });
