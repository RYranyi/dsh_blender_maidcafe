#!/usr/bin/env node
/**
 * shots.mjs —— 快速多状态截图（调光迭代用，不跑完整验收）。
 *
 * 用法：
 *   node tools/web/shots.mjs --tag tune1
 *   node tools/web/shots.mjs --state 18,clear --state 21.5,rain_heavy --tag rainy
 *
 * 产出 renders/web/shot-<tag>-<hour>-<weather>.png
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const SCRATCH = path.join(ROOT, '.scratch', 'web');
const RENDERS = path.join(ROOT, 'renders', 'web');
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
const all = (n) => argv.reduce((a, v, i) => (v === `--${n}` && argv[i + 1] ? [...a, argv[i + 1]] : a), []);

const PORT = arg('port', '7800');
const BPORT = arg('browser-port', '9333');
const TAG = arg('tag', 'shot');
const states = all('state').length
  ? all('state').map((s) => s.split(','))
  : [
      ['7', 'clear'],
      ['12.5', 'clear'],
      ['18', 'clear'],
      ['21.5', 'clear'],
      ['18', 'rain_med'],
      ['21.5', 'rain_heavy'],
    ];

const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${BPORT}`, defaultViewport: null });
const pages = await browser.pages();
const page = pages.length ? pages[0] : await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
const logs = [];
page.on('console', (m) => {
  if (m.type() === 'error') logs.push(m.text());
});
page.on('pageerror', (e) => logs.push('PAGEERROR ' + (e.stack || e.message)));

await page.goto(`http://127.0.0.1:${PORT}/index.html?debug=1`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => window.__CAFE__ && window.__CAFE__.ready === true, { timeout: 30000 });
await page.click('#enter-btn');
await new Promise((r) => setTimeout(r, 900));

for (const [h, w] of states) {
  await page.evaluate(
    ({ hh, ww }) => {
      window.__CAFE__.setState({ hour: Number(hh), weather: ww });
      window.__CAFE__.weather.snap();
    },
    { hh: h, ww: w }
  );
  await new Promise((r) => setTimeout(r, 700));
  const file = path.join(RENDERS, `shot-${TAG}-${String(h).replace('.', 'p')}-${w}.png`);
  await page.screenshot({ path: file });
  const info = await page.evaluate(() => {
    const s = window.__CAFE__.snapshot();
    return { sun: s.lights.sunIntensity, exp: s.lights.exposure, fog: s.lights.fogDensity, rain: s.render.rainParticles };
  });
  console.log(path.basename(file), JSON.stringify(info));
}
if (logs.length) console.log('LOGS:', logs.slice(0, 8));
await browser.disconnect();
