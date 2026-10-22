#!/usr/bin/env node
/** probe-rain.mjs —— 临时诊断：为什么雨粒子数量为 0。 */
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

const browser = await puppeteer.connect({ browserURL: 'http://127.0.0.1:9333', defaultViewport: null });
const pages = await browser.pages();
const page = pages[0];
await page.goto('http://127.0.0.1:7800/index.html?debug=1', { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => window.__CAFE__ && window.__CAFE__.ready === true, { timeout: 30000 });
await page.click('#enter-btn');
await new Promise((r) => setTimeout(r, 800));

const out = await page.evaluate(async () => {
  const c = window.__CAFE__;
  c.setState({ weather: 'rain_med', hour: 18 });
  await new Promise((r) => setTimeout(r, 1500));
  const sc = c.scene;
  return {
    weatherStateRainLevel: c.weather.state.rainLevel,
    targetRainLevel: c.weather.targetState.rainLevel,
    rainTargetCount: sc.rainTargetCount,
    rainCount: sc.rainCount,
    drawRange: sc.rain.geometry.drawRange,
    rainVisible: sc.rain.visible,
    lastStateRain: sc._lastState && sc._lastState.rainLevel,
    hasApply: typeof sc.applyWeatherState,
    splashCount: sc.splash.geometry.drawRange.count,
    calls: sc.renderer.info.render,
  };
});
console.log(JSON.stringify(out, null, 2));
await browser.disconnect();
