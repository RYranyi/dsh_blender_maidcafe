#!/usr/bin/env node
/**
 * ablate.mjs —— 光照/材质 A/B 二分：把可疑项逐个关掉截图，判断谁在把画面打爆。
 * 用法：node tools/web/ablate.mjs --tag a1
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const SCRATCH = path.join(ROOT, '.scratch', 'web');
const RENDERS = path.join(ROOT, 'renders', 'web', 'ablate');
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
const TAG = arg('tag', 'ab');
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
await page.waitForFunction(() => window.__CAFE__.weather.hdriCache.size >= 4, { timeout: 30000, polling: 200 });
await new Promise((r) => setTimeout(r, 800));

// 采样某个屏幕区域的平均亮度和色相（女仆头部大概在屏幕 0.35,0.45 处）
async function sample(name, label) {
  await new Promise((r) => setTimeout(r, 700));
  const f = path.join(RENDERS, `${TAG}-${name}.png`);
  await page.screenshot({ path: f });
  const px = await page.evaluate(() => {
    const cv = document.querySelector('#cafe-canvas');
    const gl = cv.getContext('webgl2', { preserveDrawingBuffer: true });
    // 用 2D 拷贝画布读像素（简单可靠）
    const tmp = document.createElement('canvas');
    tmp.width = cv.width;
    tmp.height = cv.height;
    tmp.getContext('2d').drawImage(cv, 0, 0);
    const ctx = tmp.getContext('2d');
    const regions = {
      ceiling: [0.5, 0.08],
      maidHead: [0.352, 0.47],
      maidDress: [0.36, 0.63],
      wallLeft: [0.08, 0.35],
      barTop: [0.78, 0.55],
    };
    const out = {};
    for (const [k, [fx, fy]] of Object.entries(regions)) {
      const x = Math.round(fx * tmp.width);
      const y = Math.round(fy * tmp.height);
      const d = ctx.getImageData(x - 6, y - 6, 12, 12).data;
      let r = 0,
        g = 0,
        b = 0,
        n = 0;
      for (let i = 0; i < d.length; i += 4) {
        r += d[i];
        g += d[i + 1];
        b += d[i + 2];
        n++;
      }
      out[k] = [Math.round(r / n), Math.round(g / n), Math.round(b / n)];
    }
    return out;
  });
  console.log(name.padEnd(26), label, JSON.stringify(px));
  return px;
}

async function apply(fn) {
  await page.evaluate(fn);
}

// 基准：21:30 晴
await page.evaluate(() => {
  window.__CAFE__.setState({ hour: 21.5, weather: 'clear' });
  window.__CAFE__.weather.snap();
  window.__CAFE__.scene.applyWeatherState(window.__CAFE__.weather.state, 1, window.__CAFE__.weather.targetState);
});
await sample('00-baseline-night', 'baseline');

// A: 关掉 RectAreaLight
await apply(() => {
  window.__CAFE__.__rectSave = window.__CAFE__.weather.windowRectLight.intensity;
  window.__CAFE__.weather.windowRectLight.intensity = 0;
  window.__CAFE__.scene.render();
});
await sample('01-no-rectarea', 'rect=0');

// B: 关掉窗光方向光
await apply(() => {
  window.__CAFE__.weather.windowRectLight.intensity = window.__CAFE__.__rectSave;
  window.__CAFE__.__skySave = window.__CAFE__.weather.windowSkyLight.intensity;
  window.__CAFE__.weather.windowSkyLight.intensity = 0;
  window.__CAFE__.scene.render();
});
await sample('02-no-windowsky', 'winsky=0');

// C: 关掉女仆补光
await apply(() => {
  window.__CAFE__.weather.windowSkyLight.intensity = window.__CAFE__.__skySave;
  window.__CAFE__.__fillSave = window.__CAFE__.weather.maidFill.intensity;
  window.__CAFE__.weather.maidFill.intensity = 0;
  window.__CAFE__.scene.render();
});
await sample('03-no-maidfill', 'fill=0');

// D: 关掉所有室内点光
await apply(() => {
  window.__CAFE__.weather.maidFill.intensity = window.__CAFE__.__fillSave;
  window.__CAFE__.__lampSave = window.__CAFE__.weather.lamps.map((l) => l.intensity);
  for (const l of window.__CAFE__.weather.lamps) l.intensity = 0;
  window.__CAFE__.scene.render();
});
await sample('04-no-pointlights', 'points=0');

// E: 关掉半球光 + 环境光
await apply(() => {
  window.__CAFE__.weather.lamps.forEach((l, i) => (l.intensity = window.__CAFE__.__lampSave[i]));
  window.__CAFE__.__hemiSave = window.__CAFE__.weather.hemi.intensity;
  window.__CAFE__.__ambSave = window.__CAFE__.weather.ambient.intensity;
  window.__CAFE__.weather.hemi.intensity = 0;
  window.__CAFE__.weather.ambient.intensity = 0;
  window.__CAFE__.scene.render();
});
await sample('05-no-hemi-ambient', 'hemi+amb=0');

// F: 关掉 HDRI 环境
await apply(() => {
  window.__CAFE__.weather.hemi.intensity = window.__CAFE__.__hemiSave;
  window.__CAFE__.weather.ambient.intensity = window.__CAFE__.__ambSave;
  window.__CAFE__.__envSave = window.__CAFE__.weather._envCurIntensity;
  window.__CAFE__.weather._envCurIntensity = 0;
  window.__CAFE__.weather._envCurIntensity = 0;
  window.__CAFE__.scene.scene.environment = null;
  window.__CAFE__.scene.render();
});
await sample('06-no-hdri-env', 'env=0');

// G: 关掉所有射灯
await apply(() => {
  window.__CAFE__.scene.scene.environment = window.__CAFE__.weather.activeHdri.pmrem;
  window.__CAFE__.weather._envCurIntensity = window.__CAFE__.__envSave;
  window.__CAFE__.__spotSave = (window.__CAFE__.weather.spots || []).map((s) => s.intensity);
  for (const s of window.__CAFE__.weather.spots || []) s.intensity = 0;
  window.__CAFE__.__dspotSave = (window.__CAFE__.weather.displaySpots || []).map((s) => s.intensity);
  for (const s of window.__CAFE__.weather.displaySpots || []) s.intensity = 0;
  window.__CAFE__.scene.render();
});
await sample('07-no-spots', 'spots=0');

// 打印女仆材质与灯光当前值
const dump = await page.evaluate(() => {
  const w = window.__CAFE__.weather;
  const mats = {};
  for (const m of window.__CAFE__.scene.glbMaterials || []) {
    if (!/^M_(Skin|Hair|Iris|White|Satin|Sclera|Navy|Brow)$/.test(m.name || '')) continue;
    mats[m.name] = {
      vs: m.vertexColors,
      col: '#' + (m.color ? m.color.getHexString() : ''),
      sheen: +(+m.sheen || 0).toFixed(2),
      cc: +(+m.clearcoat || 0).toFixed(2),
      rough: +(+m.roughness || 0).toFixed(2),
      env: +(+('envMapIntensity' in m ? m.envMapIntensity : 0)).toFixed(2),
    };
  }
  return {
    lamps: w.lamps.map((l) => ({ n: l.name, i: +l.intensity.toFixed(1), d: l.distance, dec: l.decay, pos: l.position.toArray().map((v) => +v.toFixed(2)) })),
    maidFill: { i: +w.maidFill.intensity.toFixed(2), pos: w.maidFill.position.toArray().map((v) => +v.toFixed(2)) },
    rect: { i: +w.windowRectLight.intensity.toFixed(1) },
    winsky: { i: +w.windowSkyLight.intensity.toFixed(2) },
    hemi: +w.hemi.intensity.toFixed(2),
    amb: +w.ambient.intensity.toFixed(2),
    exposure: +window.__CAFE__.scene.renderer.toneMappingExposure.toFixed(2),
    mats,
  };
});
console.log('DUMP', JSON.stringify(dump, null, 1));
await browser.disconnect();
