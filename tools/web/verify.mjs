#!/usr/bin/env node
/**
 * verify.mjs —— 无头 Edge 验收脚本（puppeteer-core 驱动本机 msedge，不下载 Chromium）。
 *
 * 前置：
 *   1) 静态服务器： node tools/web/serve.mjs   （或任意 127.0.0.1 端口）
 *   2) 依赖： .scratch/web/npm 下 `npm i puppeteer-core`（本脚本按相对路径找，找不到报错退出）
 *
 * 用法：
 *   node tools/web/verify.mjs
 *   node tools/web/verify.mjs --port 7800 --shots 24
 *
 * 产出：
 *   renders/web/*.png          截图（含 4 时段 × 6 天气抽样 + 交互态）
 *   .scratch/web/verify-report.json  机器可读报告（Lead/QC 直接看数字）
 *
 * 环境铁律：TEMP/TMP 与浏览器 profile 全部落在 .scratch/web 下（绝不落 C 盘）。
 */
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const SCRATCH = path.join(ROOT, '.scratch', 'web');
const RENDERS = path.join(ROOT, 'renders', 'web');
const PROFILE = path.join(SCRATCH, 'profile');
const TMP = path.join(SCRATCH, 'tmp');

// 兜底重定向临时目录（脚本被别处调用时也安全）
process.env.TEMP = TMP;
process.env.TMP = TMP;
fs.mkdirSync(TMP, { recursive: true });
fs.mkdirSync(RENDERS, { recursive: true });
fs.mkdirSync(PROFILE, { recursive: true });

const EDGE_CANDIDATES = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
];
const EDGE = EDGE_CANDIDATES.find((p) => fs.existsSync(p));
if (!EDGE) {
  console.error('找不到 msedge.exe');
  process.exit(1);
}

/** 端口探测：调试端口是否已开 */
function portOpen(port) {
  return new Promise((resolve) => {
    const s = net.connect({ port, host: '127.0.0.1' });
    s.setTimeout(600);
    s.once('connect', () => {
      s.destroy();
      resolve(true);
    });
    s.once('timeout', () => {
      s.destroy();
      resolve(false);
    });
    s.once('error', () => resolve(false));
  });
}

// puppeteer-core 安装在 .scratch/web/npm/node_modules
const req = createRequire(path.join(ROOT, '.scratch', 'webtools', 'node_modules', 'noop.cjs'));
let puppeteer;
try {
  puppeteer = req('puppeteer-core');
} catch (e) {
  console.error('puppeteer-core 未安装：cd .scratch/web/npm && npm i puppeteer-core');
  process.exit(1);
}

/* ── 参数 ── */
const argv = process.argv.slice(2);
function arg(name, def) {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : def;
}
const PORT = Number(arg('port', 7800));
const BASE = `http://127.0.0.1:${PORT}`;
const TIMEOUT = Number(arg('timeout', 30000));

/* ── 像素方差（判断是否白屏/黑屏） ── */
async function pixelStats(pngPath) {
  const { PNG } = getPng();
  const buf = fs.readFileSync(pngPath);
  const png = PNG.sync.read(buf);
  const { width, height, data } = png;
  let n = 0;
  let sum = 0;
  let sumSq = 0;
  const hist = new Uint32Array(32);
  for (let i = 0; i < data.length; i += 4 * 7) {
    const lum = 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
    sum += lum;
    sumSq += lum * lum;
    hist[Math.min(31, (lum / 8) | 0)]++;
    n++;
  }
  const mean = sum / n;
  const variance = sumSq / n - mean * mean;
  let distinct = 0;
  for (let i = 0; i < hist.length; i++) if (hist[i] > n * 0.001) distinct++;
  return {
    width,
    height,
    mean: +mean.toFixed(2),
    variance: +variance.toFixed(2),
    stdev: +Math.sqrt(Math.max(0, variance)).toFixed(2),
    distinctBuckets: distinct,
    bytes: buf.length,
  };
}

let pngLib = null;
function getPng() {
  if (!pngLib) {
    try {
      pngLib = req('pngjs');
    } catch {
      console.error('需要 pngjs（npm i pngjs），或用 --no-pixel 跳过像素统计');
      process.exit(1);
    }
  }
  return pngLib;
}

/* ── 主流程 ── */
const report = {
  startedAt: new Date().toISOString(),
  base: BASE,
  edge: EDGE,
  checks: [],
  consoleErrors: [],
  pageErrors: [],
  requestsFailed: [],
  httpStatus: null,
  screenshots: [],
  matrix: [],
  interactions: {},
  ok: false,
};

function check(name, pass, detail) {
  report.checks.push({ name, pass: !!pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + JSON.stringify(detail) : ''}`);
  return pass;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function httpProbe() {
  // 用 node fetch（PowerShell 的 IWR 被 TLS 拦，Node 正常）
  const res = await fetch(`${BASE}/index.html`);
  const text = await res.text();
  report.httpStatus = res.status;
  return { status: res.status, len: text.length, text };
}

async function main() {
  // 1) 页面可达
  const probe = await httpProbe();
  check('GET /index.html → 200', probe.status === 200, { status: probe.status, bytes: probe.len });
  check('index.html 无外链 CDN', !/https?:\/\/[^"'\s]+/.test(probe.text.replace(/<!--[\s\S]*?-->/g, '').replace(/127\.0\.0\.1[^"']*/g, '')));

  // 浏览器：优先 connect 到已启动的调试端口（沙箱禁止 puppeteer.launch 的管道 spawn）
  const DEBUG_PORT = Number(arg('browser-port', 9333));
  let browser;
  if (!(await portOpen(DEBUG_PORT))) {
    // 自动拉起（detached，stdio 不用 pipe）
    const { spawn } = await import('node:child_process');
    const prof = PROFILE;
    const out = fs.openSync(path.join(SCRATCH, 'edge.log'), 'a');
    const errf = fs.openSync(path.join(SCRATCH, 'edge.err.log'), 'a');
    const child = spawn(
      EDGE,
      [
        `--remote-debugging-port=${DEBUG_PORT}`,
        `--user-data-dir=${prof}`,
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-networking',
        '--disable-features=Translate,BackForwardCache,MediaRouter',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--enable-unsafe-swiftshader',
        '--use-angle=swiftshader',
        '--autoplay-policy=no-user-gesture-required',
        '--window-size=1280,800',
        '--lang=zh-CN',
        '--headless=new',
        'about:blank',
      ],
      { detached: true, stdio: ['ignore', out, errf], windowsHide: true }
    );
    child.unref();
    const deadline = Date.now() + 40000;
    while (Date.now() < deadline && !(await portOpen(DEBUG_PORT))) await sleep(350);
  }
  if (!(await portOpen(DEBUG_PORT))) throw new Error(`调试端口 ${DEBUG_PORT} 未打开（先跑 tools/web/start-headless-edge.mjs）`);

  browser = await puppeteer.connect({
    browserURL: `http://127.0.0.1:${DEBUG_PORT}`,
    defaultViewport: null,
    protocolTimeout: 180000,
  });
  console.log(`CONNECTED http://127.0.0.1:${DEBUG_PORT}`);

  try {
    const pages = await browser.pages();
    const page = pages.length ? pages[0] : await browser.newPage();
    await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 });
    await page.setCacheEnabled(false);
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const t = msg.text();
        // 忽略 GLB 404（无模型阶段的预期降级）
        report.consoleErrors.push(t);
      }
    });
    page.on('pageerror', (err) => report.pageErrors.push(err && (err.stack || err.message)));
    page.on('requestfailed', (req) => {
      const u = req.url();
      report.requestsFailed.push({ url: u, err: req.failure() && req.failure().errorText });
    });
    page.on('response', (res) => {
      const u = res.url();
      if (res.status() >= 400 && !/favicon/.test(u)) {
        report.httpFailures = report.httpFailures || [];
        report.httpFailures.push({ url: u, status: res.status() });
      }
    });

    await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded', timeout: TIMEOUT });

    // 2) 首屏遮罩存在
    const enterVisible = await page.$eval('#enter', (el) => !el.classList.contains('gone'));
    check('首屏「点击进入」遮罩存在', enterVisible);

    // 3) 等待就绪
    await page.waitForFunction(() => window.__CAFE__ && window.__CAFE__.ready === true, { timeout: TIMEOUT, polling: 200 });
    check('app.ready === true', true);

    // 4) 初始截图（遮罩层）
    const shot0 = path.join(RENDERS, '01-enter.png');
    await page.screenshot({ path: shot0 });
    report.screenshots.push({ file: '01-enter.png', ...(await pixelStats(shot0)) });

    // 5) 点击进入
    await page.click('#enter-btn');
    await sleep(1200);
    const entered = await page.evaluate(() => ({
      entered: window.__CAFE__.entered,
      enterGone: document.querySelector('#enter').classList.contains('gone'),
      audioReady: window.__CAFE__.audioReady,
    }));
    check('点击进入后遮罩消失', entered.enterGone, entered);
    report.interactions.enter = entered;

    // 6) 首帧截图 + 像素方差
    const shot1 = path.join(RENDERS, '02-default-night-clear.png');
    await page.screenshot({ path: shot1 });
    const st1 = await pixelStats(shot1);
    report.screenshots.push({ file: '02-default-night-clear.png', ...st1 });
    check('默认画面非空白（stdev > 6）', st1.stdev > 6, st1);
    check('默认画面非纯黑（mean > 8）', st1.mean > 8, { mean: st1.mean });

    // 7) WebGL 上下文 / 渲染数字
    const renderInfo = await page.evaluate(() => {
      const s = window.__CAFE__.snapshot();
      return { render: s.render, lights: s.lights, audioReady: s.audioReady, errors: s.errors };
    });
    check('WebGL 渲染出三角形（tri > 1000）', renderInfo.render && renderInfo.render.triangles > 1000, renderInfo.render);
    report.interactions.render = renderInfo;

    // 8) 时间滑块 0/6/12/18/23 → 标签 + 灯光变化
    const sliderResults = [];
    for (const h of [0, 6, 12, 18, 23]) {
      const r = await page.evaluate((hh) => {
        const el = document.querySelector('#time-slider');
        el.value = String(hh);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        window.__CAFE__.weather.snap();
        return {
          hour: window.__CAFE__.hour,
          label: document.querySelector('#time-label').textContent,
          sun: window.__CAFE__.weather.info().sunIntensity,
          exposure: window.__CAFE__.weather.info().exposure,
          phase: window.__CAFE__.weather.info().phase,
        };
      }, h);
      sliderResults.push({ input: h, ...r });
    }
    report.interactions.slider = sliderResults;
    const labelsOk = sliderResults.every((r) => /\d{2}:\d{2}$/.test(r.label));
    const distinctLabels = new Set(sliderResults.map((r) => r.label)).size;
    check('滑块 0/6/12/18/23 → 全部有「档位 HH:MM」标签', labelsOk, sliderResults.map((r) => r.label));
    check('滑块标签随时段变化（≥4 种）', distinctLabels >= 4, { distinct: distinctLabels });
    const sunSpread = Math.max(...sliderResults.map((r) => r.sun)) - Math.min(...sliderResults.map((r) => r.sun));
    check('滑块驱动灯光强度变化（sun 极差 > 0.5）', sunSpread > 0.5, { spread: +sunSpread.toFixed(3) });

    // 9) 天气按钮：晴天 → 雨天 → 中雨
    await page.evaluate(() => {
      document.querySelector('[data-weather="clear"]').click();
    });
    await sleep(1800);
    const w1 = await page.evaluate(() => window.__CAFE__.snapshot());
    const shot2 = path.join(RENDERS, '03-weather-clear.png');
    await page.screenshot({ path: shot2 });
    report.screenshots.push({ file: '03-weather-clear.png', ...(await pixelStats(shot2)) });

    await page.evaluate(() => document.querySelector('[data-rain-toggle]').click());
    await sleep(300);
    const rainSubVisible = await page.$eval('#rain-sub', (el) => !el.classList.contains('hidden'));
    check('点「雨天」展开二级雨势', rainSubVisible);
    await page.evaluate(() => document.querySelector('[data-weather="rain_med"]').click());
    await sleep(2000);
    const w2 = await page.evaluate(() => window.__CAFE__.snapshot());
    report.interactions.weather = {
      clear: { weather: w1.weather, label: w1.weatherLabel, rainParticles: w1.render.rainParticles, fog: w1.lights.fogDensity, exposure: w1.lights.exposure },
      rain_med: { weather: w2.weather, label: w2.weatherLabel, rainParticles: w2.render.rainParticles, fog: w2.lights.fogDensity, exposure: w2.lights.exposure },
    };
    check('天气按钮生效（clear → rain_med）', w2.weather === 'rain_med' && w2.weatherLabel === '中雨', report.interactions.weather);
    check('雨天产生雨粒子（> 3000）', w2.render.rainParticles >= 3000, { rainParticles: w2.render.rainParticles });
    check('雨天雾更浓（fog 上升）', w2.lights.fogDensity > w1.lights.fogDensity, { clear: w1.lights.fogDensity, rain: w2.lights.fogDensity });
    const activeBtn = await page.$eval('#panel-weather [data-weather="rain_med"]', (el) => el.getAttribute('aria-pressed'));
    check('选中态 aria-pressed=true', activeBtn === 'true', { activeBtn });
    const shot3 = path.join(RENDERS, '04-weather-rain-med.png');
    await page.screenshot({ path: shot3 });
    report.screenshots.push({ file: '04-weather-rain-med.png', ...(await pixelStats(shot3)) });

    // 10) 雷阵雨 + 闪电
    await page.evaluate(() => document.querySelector('[data-weather="storm"]').click());
    await sleep(1600);
    const storm = await page.evaluate(() => {
      window.__CAFE__.triggerLightning();
      return new Promise((r) =>
        setTimeout(() => {
          const s = window.__CAFE__.snapshot();
          r({ weather: s.weather, lightningActive: s.lightningActive, lightningCount: s.lightningCount, flash: window.__CAFE__.weather.flashLevel, sun: s.lights.sunIntensity });
        }, 120)
      );
    });
    report.interactions.storm = storm;
    check('雷阵雨状态生效 + 闪电计数增加', storm.weather === 'storm' && storm.lightningCount >= 1, storm);
    check('闪电产生光强脉冲（flash > 0）', storm.flash > 0, { flash: +storm.flash.toFixed(3) });
    const shot4 = path.join(RENDERS, '05-weather-storm-flash.png');
    await page.screenshot({ path: shot4 });
    report.screenshots.push({ file: '05-weather-storm-flash.png', ...(await pixelStats(shot4)) });

    // 11) 音量滑块（0 → setMasterVolume(0)，不 suspend 上下文）
    const vol = await page.evaluate(() => {
      const el = document.querySelector('#volume-slider');
      el.value = '0';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return {
        volume: window.__CAFE__.volume,
        label: document.querySelector('#volume-label').textContent,
        audioReady: window.__CAFE__.audioReady,
      };
    });
    await sleep(200);
    report.interactions.volume = vol;
    check('音量滑到 0 → 标签 0%', vol.volume === 0 && vol.label === '0%', vol);

    // 12) 4 时段 × 6 天气 = 24 组矩阵
    const matrix = await page.evaluate(() => window.__CAFE__.matrix(true));
    report.matrix = matrix;
    check('4 时段 × 6 天气 = 24 组全部可切换', matrix.length === 24, { got: matrix.length });
    const suns = matrix.map((m) => m.sunIntensity);
    const exps = matrix.map((m) => m.exposure);
    check('24 组太阳强度有变化（极差 > 1）', Math.max(...suns) - Math.min(...suns) > 1, {
      min: Math.min(...suns),
      max: Math.max(...suns),
    });
    check('24 组曝光均在合理区间 [0.45, 2.0]', exps.every((e) => e >= 0.45 && e <= 2.0), { min: Math.min(...exps), max: Math.max(...exps) });
    check('24 组均有 phase/weather 标签', matrix.every((m) => m.phase && m.weather && m.phaseLabel && m.weatherLabel));

    // 13) 逐时段截图（清晨/正午/黄昏/夜晚，晴天 + 雨）
    for (const [h, key, name] of [
      [7, 'clear', '06-morning-clear'],
      [12.5, 'clear', '07-noon-clear'],
      [18, 'clear', '08-dusk-clear'],
      [21.5, 'clear', '09-night-clear'],
      [18, 'rain_med', '10-dusk-rain'],
      [21.5, 'rain_heavy', '11-night-rain'],
    ]) {
      await page.evaluate(
        ({ hh, k }) => {
          window.__CAFE__.setState({ hour: hh, weather: k });
          window.__CAFE__.weather.snap();
        },
        { hh: h, k: key }
      );
      await sleep(450);
      const f = path.join(RENDERS, `${name}.png`);
      await page.screenshot({ path: f });
      const ps = await pixelStats(f);
      report.screenshots.push({ file: `${name}.png`, ...ps });
      check(`截图 ${name} 非空白（stdev>6）`, ps.stdev > 6, ps);
    }

    // 14) 相机碰撞：尝试把相机推到墙外，检查被钳制
    const cam = await page.evaluate(() => {
      const sc = window.__CAFE__.scene;
      sc.camera.position.set(99, 99, 99);
      sc.resolveCollision(sc.camera.position);
      const p = sc.camera.position;
      return { x: p.x, y: p.y, z: p.z, clamp: sc.clamp };
    });
    report.interactions.cameraClamp = cam;
    const inside =
      cam.x >= cam.clamp.x[0] - 1e-6 &&
      cam.x <= cam.clamp.x[1] + 1e-6 &&
      cam.y >= cam.clamp.y[0] - 1e-6 &&
      cam.y <= cam.clamp.y[1] + 1e-6 &&
      cam.z >= cam.clamp.z[0] - 1e-6 &&
      cam.z <= cam.clamp.z[1] + 1e-6;
    check('相机越界被房间盒钳制', inside, cam);

    // 15) 无 JS 异常
    await sleep(600);
    const pageErrors = report.pageErrors;
    const consoleErrors = report.consoleErrors.filter((t) => !/Failed to load resource|404/.test(t));
    const unhandled = consoleErrors.filter((t) => /unhandled/i.test(t));
    check('无 pageerror', pageErrors.length === 0, pageErrors.slice(0, 3));
    check('无 unhandled rejection', unhandled.length === 0, unhandled.slice(0, 3));
    report.appErrors = await page.evaluate(() => window.__CAFE__.errors);
    check('app 内部记录错误数 = 0（音频模块缺失警告不计）', report.appErrors.length === 0, report.appErrors.slice(0, 4));

    // 16) 最终 FPS / 渲染统计
    const finalStats = await page.evaluate(() => window.__CAFE__.snapshot());
    report.final = finalStats;

    report.ok = report.checks.every((c) => c.pass);
    console.log(`\n=== ${report.ok ? 'ALL PASS' : 'HAS FAILURES'} ===`);
    console.log(`tri=${finalStats.render && finalStats.render.triangles} drawcalls=${finalStats.render && finalStats.render.drawCalls} fps=${finalStats.fps}`);
    console.log(`consoleErrors=${report.consoleErrors.length} pageErrors=${report.pageErrors.length} requestsFailed=${report.requestsFailed.length}`);
  } finally {
    fs.writeFileSync(path.join(SCRATCH, 'verify-report.json'), JSON.stringify(report, null, 2));
    // 只 disconnect，不 close：浏览器是外部拉起的，后续验收还能复用
    try {
      await browser.disconnect();
    } catch {}
  }
  return report;
}

main()
  .then((r) => {
    const failed = r.checks.filter((c) => !c.pass);
    if (!r.ok) {
      console.error(`\n失败项：\n${failed.map((f) => ` - ${f.name} ${JSON.stringify(f.detail)}`).join('\n')}`);
      process.exitCode = 1;
    }
  })
  .catch((e) => {
    console.error('verify 崩溃:', e && e.stack);
    fs.writeFileSync(path.join(SCRATCH, 'verify-report.json'), JSON.stringify({ ...report, crash: String(e && e.stack) }, null, 2));
    process.exitCode = 2;
  });
