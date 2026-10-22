#!/usr/bin/env node
/** debug-page.mjs —— 单页诊断：打开页面，抓 console / pageerror / 请求失败，打印 __CAFE__ 状态。 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const SCRATCH = path.join(ROOT, '.scratch', 'web');
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

const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${BPORT}`, defaultViewport: null });
const pages = await browser.pages();
const page = pages.length ? pages[0] : await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
const logs = [];
page.on('console', (m) => logs.push({ type: m.type(), text: m.text() }));
page.on('pageerror', (e) => logs.push({ type: 'pageerror', text: e.stack || e.message }));
page.on('requestfailed', (r) => logs.push({ type: 'reqfail', text: `${r.url()} ${r.failure()?.errorText}` }));
page.on('response', (r) => {
  if (r.status() >= 400) logs.push({ type: 'http', text: `${r.status()} ${r.url()}` });
});

await page.goto(`http://127.0.0.1:${PORT}/index.html?debug=1`, { waitUntil: 'domcontentloaded' });
await new Promise((r) => setTimeout(r, 6000));
const state = await page.evaluate(() => {
  const c = window.__CAFE__;
  if (!c) return { noCafe: true, hasApp: false };
  return {
    ready: c.ready,
    failed: c.failed,
    errors: c.errors,
    manifestSource: c.manifestSource,
    glbLoaded: c.glbLoaded,
    loaderLabel: document.querySelector('#loadlabel')?.textContent,
    hasCanvas: !!document.querySelector('#cafe-canvas'),
    canvasSize: (() => {
      const cv = document.querySelector('#cafe-canvas');
      return cv ? { w: cv.width, h: cv.height } : null;
    })(),
    webgl: (() => {
      try {
        const cv = document.createElement('canvas');
        const gl = cv.getContext('webgl2');
        return gl ? gl.getParameter(gl.VERSION) + ' | ' + gl.getParameter(gl.RENDERER) : 'no webgl2';
      } catch (e) {
        return 'err ' + e.message;
      }
    })(),
  };
});
const shot = path.join(ROOT, 'renders', 'web', '_debug.png');
await page.screenshot({ path: shot });
console.log(JSON.stringify({ state, logs: logs.slice(0, 40) }, null, 2));
await browser.disconnect();
