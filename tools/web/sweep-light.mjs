#!/usr/bin/env node
/**
 * sweep-light.mjs —— 光照参数扫描：给定若干组 overrides，逐组截图并采样区域亮度。
 * 用法：node tools/web/sweep-light.mjs --tag s1
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const SCRATCH = path.join(ROOT, '.scratch', 'web');
const RENDERS = path.join(ROOT, 'renders', 'web', 'sweep');
process.env.TEMP = path.join(SCRATCH, 'tmp');
process.env.TMP = process.env.TEMP;
fs.mkdirSync(RENDERS, { recursive: true });

const req = createRequire(path.join(ROOT, '.scratch', 'webtools', 'node_modules', 'noop.cjs'));
const puppeteer = req('puppeteer-core');
const argv = process.argv.slice(2);
const arg = (n, d) => {
  const i = argv.indexOf(`--${n}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
};
const TAG = arg('tag', 's');
const PORT = arg('port', '7800');
const BPORT = arg('browser-port', '9333');

const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${BPORT}`, defaultViewport: null });
for (const p of await browser.pages()) {
  try {
    await p.close();
  } catch {}
}
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
await page.goto(`http://127.0.0.1:${PORT}/index.html?debug=1`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => window.__CAFE__ && window.__CAFE__.ready === true, { timeout: 120000, polling: 300 });
await page.click('#enter-btn');
await page.waitForFunction(() => window.__CAFE__.weather.hdriCache.size >= 4, { timeout: 40000, polling: 200 });
await new Promise((r) => setTimeout(r, 700));

/** 在页面内部读 canvas 像素（同源、无污染） */
async function shot(name, hour, weather, ov) {
  await page.evaluate(
    ({ hh, ww, overrides }) => {
      const c = window.__CAFE__;
      c.weather.overrides = overrides || null;
      c.setState({ hour: hh, weather: ww });
      c.weather.snap();
      c.scene.applyWeatherState(c.weather.state, 1, c.weather.targetState);
      c.scene.render();
    },
    { hh: hour, ww: weather, overrides: ov }
  );
  await new Promise((r) => setTimeout(r, 900));
  const f = path.join(RENDERS, `${TAG}-${name}.png`);
  await page.screenshot({ path: f });
  const px = await page.evaluate(() => {
    const cv = document.querySelector('#cafe-canvas');
    const tmp = document.createElement('canvas');
    tmp.width = cv.width;
    tmp.height = cv.height;
    const ctx = tmp.getContext('2d');
    ctx.drawImage(cv, 0, 0);
    const R = {
      ceiling: [0.5, 0.09],
      maidHair: [0.352, 0.44],
      maidFace: [0.352, 0.5],
      wallLeft: [0.1, 0.33],
      barFront: [0.78, 0.62],
      floor: [0.3, 0.85],
      windowSky: [0.42, 0.3],
    };
    const out = {};
    for (const [k, [fx, fy]] of Object.entries(R)) {
      const x = Math.round(fx * tmp.width);
      const y = Math.round(fy * tmp.height);
      const d = ctx.getImageData(x - 5, y - 5, 10, 10).data;
      let r = 0, g = 0, b = 0, n = 0;
      for (let i = 0; i < d.length; i += 4) {
        r += d[i]; g += d[i + 1]; b += d[i + 2]; n++;
      }
      out[k] = [Math.round(r / n), Math.round(g / n), Math.round(b / n)];
    }
    // 全画面平均亮度 + 过曝面积占比
    const full = ctx.getImageData(0, 0, tmp.width, tmp.height).data;
    let sum = 0, n = 0, blown = 0;
    for (let i = 0; i < full.length; i += 4 * 11) {
      const lum = 0.2126 * full[i] + 0.7152 * full[i + 1] + 0.0722 * full[i + 2];
      sum += lum; n++;
      if (lum > 250) blown++;
    }
    out.meanLum = Math.round(sum / n);
    out.blownPct = +((blown / n) * 100).toFixed(1);
    return out;
  });
  console.log(name.padEnd(28), JSON.stringify(px));
  return px;
}

const JOBS = (JSON.parse(arg('jobs', '[]')) || []);

// 默认扫描：夜晚与白天各跑几组
const plan = JOBS.length
  ? JOBS
  : [
      { name: 'n-baseline', hour: 21.5, weather: 'clear', ov: null },
      { name: 'n-dark1', hour: 21.5, weather: 'clear', ov: { exposure: 0.75, hemi: 0.4, ambient: 0.5, lampMul: 0.45, windowRect: 0, windowSky: 0, spots: 0.5 } },
      { name: 'n-dark2', hour: 21.5, weather: 'clear', ov: { exposure: 0.62, hemi: 0.28, ambient: 0.35, lampMul: 0.45, windowRect: 0, windowSky: 0, spots: 0.5 } },
      { name: 'n-dark3', hour: 21.5, weather: 'clear', ov: { exposure: 0.55, hemi: 0.2, ambient: 0.25, lampMul: 0.45, windowRect: 0, windowSky: 0, spots: 0.5 } },
      { name: 'd-baseline', hour: 12.5, weather: 'clear', ov: null },
      { name: 'd-dim1', hour: 12.5, weather: 'clear', ov: { exposure: 0.72, hemi: 0.75, ambient: 0.7 } },
      { name: 'd-dim2', hour: 12.5, weather: 'clear', ov: { exposure: 0.72, hemi: 0.62, ambient: 0.55, windowRect: 0.6 } },
      { name: 'dusk-baseline', hour: 18, weather: 'clear', ov: null },
      { name: 'dusk-dim1', hour: 18, weather: 'clear', ov: { exposure: 0.9, hemi: 0.6, ambient: 0.6, lampMul: 0.7 } },
      { name: 'storm-baseline', hour: 21.5, weather: 'storm', ov: null },
      { name: 'storm-dim1', hour: 21.5, weather: 'storm', ov: { exposure: 0.55, hemi: 0.2, ambient: 0.25, lampMul: 0.45, windowRect: 0, windowSky: 0, spots: 0.5 } },
    ];

for (const j of plan) await shot(j.name, j.hour, j.weather, j.ov || null);
await page.evaluate(() => {
  window.__CAFE__.weather.overrides = null;
});
await browser.disconnect();
