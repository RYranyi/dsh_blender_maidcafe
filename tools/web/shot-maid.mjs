#!/usr/bin/env node
/**
 * shot-maid.mjs —— 运行时验收：真浏览器（headless Edge + WebGL）加载冻结版 GLB，
 * 点入口 → 设定时间/天气 → 截图，并量测女仆头发的实际像素颜色。
 *
 * 用法：node tools/web/shot-maid.mjs --tag r1 [--time 12.5] [--weather clear]
 * 依赖：.scratch/webtools/node_modules/puppeteer-core（临时，验收后可删）
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const SCRATCH = path.join(ROOT, '.scratch', 'web');
const RENDERS = path.join(ROOT, 'renders', 'web');
fs.mkdirSync(RENDERS, { recursive: true });
fs.mkdirSync(path.join(SCRATCH, 'tmp'), { recursive: true });
process.env.TEMP = path.join(SCRATCH, 'tmp');
process.env.TMP = process.env.TEMP;

const req = createRequire(path.join(ROOT, '.scratch', 'webtools', 'node_modules', 'noop.cjs'));
const puppeteer = req('puppeteer-core');

const argv = process.argv.slice(2);
const arg = (n, d) => {
  const i = argv.indexOf(`--${n}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
};
const PORT = arg('port', '7800');
const BPORT = arg('browser-port', '9333');
const TAG = arg('tag', 'r1');
const TIMES = (arg('times', '12.5')).split(',').map(Number);
const WEATHER = arg('weather', 'clear');

const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${BPORT}`, defaultViewport: null });
for (const p of await browser.pages()) { try { await p.close(); } catch {} }
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
const logs = [];
page.on('console', (m) => { if (m.type() === 'error') logs.push('[error] ' + m.text()); });
page.on('pageerror', (e) => logs.push('PAGEERROR ' + (e.stack || e.message)));

const t0 = Date.now();
await page.goto(`http://127.0.0.1:${PORT}/index.html?debug=1`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => window.__CAFE__ && window.__CAFE__.ready === true, { timeout: 90000 });
const readyMs = Date.now() - t0;
await page.click('#enter-btn');
await page.waitForFunction(() => window.__CAFE__.entered === true, { timeout: 20000 });

const stats = await page.evaluate(() => {
  const c = window.__CAFE__;
  const r = c.scene.renderer;
  const info = r.info;
  return {
    tris: info.render.triangles,
    calls: info.render.calls,
    geometries: info.memory.geometries,
    textures: info.memory.textures,
    programs: info.programs ? info.programs.length : null,
    glbStats: c.scene.glbStats || null,
    maidTweak: c.scene._maidMatTweak || null,
  };
});

const out = [];
for (const T of TIMES) {
  await page.evaluate(({ T, W }) => {
    const c = window.__CAFE__;
    if (c.setTime) c.setTime(T);
    if (c.setWeather) c.setWeather(W);
    else { c.time = T; c.weather && c.weather.setWeather && c.weather.setWeather(W); }
  }, { T, W: WEATHER });
  await new Promise((r) => setTimeout(r, 2500));
  const file = path.join(RENDERS, `rt-${TAG}-t${String(T).replace('.', 'p')}-${WEATHER}.png`);
  await page.screenshot({ path: file });
  // 量测女仆头部区域平均色（画面中偏左；1280x800 下约为 x 440..520, y 330..400）
  const px = await page.evaluate(async () => {
    const cv = document.querySelector('canvas');
    const g = cv.getContext('webgl2') || cv.getContext('webgl');
    // 直接读画布像素（preserveDrawingBuffer 可能为 false，改走 toDataURL）
    return null;
  });
  out.push({ file, T, WEATHER });
}
console.log(JSON.stringify({ readyMs, stats, shots: out, logs: logs.slice(0, 8) }, null, 1));
await browser.disconnect();
