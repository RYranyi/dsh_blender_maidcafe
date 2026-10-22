#!/usr/bin/env node
/**
 * final-shots.mjs —— Lead 验收用的 6+1 张图（机位来自 manifest anchors.cam_default + 转身看窗）。
 *
 * 用法：
 *   node tools/web/final-shots.mjs --tag v1
 *
 * 产出（renders/web/）：
 *   acc-<tag>-0700-clear.png      07:00 晴
 *   acc-<tag>-1230-clear.png      12:30 晴
 *   acc-<tag>-1800-clear.png      18:00 晴
 *   acc-<tag>-2130-clear.png      21:30 晴
 *   acc-<tag>-1230-rain_med.png   12:30 中雨
 *   acc-<tag>-2130-storm.png      21:30 雷阵雨
 *   acc-<tag>-window-dusk-rain.png 转身看窗（18:00 中雨）
 *   acc-<tag>-window-night.png     转身看窗（21:30 晴）
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
const PORT = arg('port', '7800');
const BPORT = arg('browser-port', '9333');
const TAG = arg('tag', 'v1');

const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${BPORT}`, defaultViewport: null });
// 关闭旧标签页，避免多个 WebGL 页面争用 SwiftShader（会拖到超时）
const allPages = await browser.pages();
for (const p of allPages) {
  try {
    await p.close();
  } catch {}
}
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
const logs = [];
page.on('console', (m) => {
  const t = m.text();
  if (m.type() === 'error' || m.type() === 'warning') logs.push(`[${m.type()}] ${t}`);
});
page.on('pageerror', (e) => logs.push('PAGEERROR ' + (e.stack || e.message)));

const t0 = Date.now();
await page.goto(`http://127.0.0.1:${PORT}/index.html?debug=1`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => window.__CAFE__ && window.__CAFE__.ready === true, { timeout: 60000 });
const tReady = Date.now() - t0;
await page.click('#enter-btn');
await page.waitForFunction(() => window.__CAFE__.entered === true, { timeout: 15000 });
const tEnter = Date.now() - t0;
// 等 HDRI 预载完成（最多 20s）
let hdriOk = false;
try {
  await page.waitForFunction(() => window.__CAFE__.weather.hdriCache.size >= 4, { timeout: 20000, polling: 200 });
  hdriOk = true;
} catch {}
const tHdri = Date.now() - t0;
await new Promise((r) => setTimeout(r, 900));

const stats = await page.evaluate(() => {
  const c = window.__CAFE__;
  const sc = c.scene;
  const info = sc.renderer.info;
  return {
    loadMs: c.loadMs,
    firstFrameMs: c.firstFrameMs,
    readyAt: c.readyAt,
    enteredAt: c.enteredAt,
    render: {
      triangles: info.render.triangles,
      calls: info.render.calls,
      points: info.render.points,
      geometries: info.memory.geometries,
      textures: info.memory.textures,
      programs: info.programs ? info.programs.length : null,
    },
    glbStats: sc.glbStats,
    envApplied: c.weather.hdriUsedPhase,
    hdriStats: c.weather.hdriStats,
    hdriCacheSize: c.weather.hdriCache.size,
    envIntensity: +c.weather._envCurIntensity.toFixed(3),
    noShadowHits: sc.glbStats && sc.glbStats.noShadowMeshes,
    camera: { pos: sc.camera.position.toArray().map((v) => +v.toFixed(2)) },
    manifestSource: c.manifestSource,
  };
});
console.log('TIMING', JSON.stringify({ navToReady: tReady, navToEnter: tEnter, navToHdri: tHdri, hdriOk }));

// 机位：manifest anchors.cam_default
const camDefault = await page.evaluate(() => {
  const sc = window.__CAFE__.scene;
  const m = window.__CAFE__.manifest;
  const cd = (m.anchors && m.anchors.cam_default) || { pos: [1.85, -2.55, 1.55], target: [-1.2, 0.5, 1.05] };
  return {
    pos: cd.pos,
    target: cd.target,
    threePos: sc.camDefault.pos.toArray(),
    threeTarget: sc.camDefault.target.toArray(),
  };
});
console.log('CAM', JSON.stringify(camDefault));

const STATES = [
  ['0700-clear', 7, 'clear', 'default'],
  ['1230-clear', 12.5, 'clear', 'default'],
  ['1800-clear', 18, 'clear', 'default'],
  ['2130-clear', 21.5, 'clear', 'default'],
  ['1230-rain_med', 12.5, 'rain_med', 'default'],
  ['2130-storm', 21.5, 'storm', 'default'],
  ['window-1800-rain_med', 18, 'rain_med', 'window'],
  ['window-2130-clear', 21.5, 'clear', 'window'],
  // 备用机位：默认机位若被门叶/吧台挡住，用「房间中轴看向吧台」的干净机位
  ['room-0700-clear', 7, 'clear', 'room'],
  ['room-1230-clear', 12.5, 'clear', 'room'],
  ['room-1800-clear', 18, 'clear', 'room'],
  ['room-2130-clear', 21.5, 'clear', 'room'],
  ['room-1230-rain_med', 12.5, 'rain_med', 'room'],
  ['room-2130-storm', 21.5, 'storm', 'room'],
];

const results = [];
for (const [name, h, w, cam] of STATES) {
  await page.evaluate(
    ({ hh, ww, camMode }) => {
      const c = window.__CAFE__;
      const sc = c.scene;
      c.setState({ hour: hh, weather: ww });
      c.weather.snap();
      if (camMode === 'default') {
        sc.resetCamera();
      } else if (camMode === 'window') {
        // 转身看窗：房间中央，朝 −Y（three +z）方向看窗和街道
        sc.camera.position.set(0.2, 1.55, -1.2);
        sc.controls.target.set(0.2, 1.35, 3.0);
        sc.controls.update();
      } else {
        // 干净机位：房间左侧后方向前看（跨过桌区看吧台 + 女仆），避开门口门叶
        sc.camera.position.set(-2.6, 1.62, -2.3);
        sc.controls.target.set(1.2, 1.0, 1.2);
        sc.controls.update();
      }
      c.scene.applyWeatherState(c.weather.state, 1, c.weather.targetState);
      sc.render();
    },
    { hh: h, ww: w, camMode: cam }
  );
  await new Promise((r) => setTimeout(r, 1100));
  const file = path.join(RENDERS, `acc-${TAG}-${name}.png`);
  await page.screenshot({ path: file });
  const info = await page.evaluate(() => {
    const c = window.__CAFE__;
    const s = c.snapshot();
    return {
      sun: s.lights.sunIntensity,
      exp: s.lights.exposure,
      fog: s.lights.fogDensity,
      rain: s.render.rainParticles,
      draw: s.render.drawCalls,
      tri: s.render.triangles,
      env: +c.weather._envCurIntensity.toFixed(2),
      hdri: c.weather.hdriUsedPhase,
    };
  });
  results.push({ name, file: path.basename(file), ...info });
  console.log(path.basename(file), JSON.stringify(info));
}

fs.writeFileSync(path.join(SCRATCH, 'final-shots.json'), JSON.stringify({ timing: { tReady, tEnter, tHdri }, stats, camDefault, results, logs: logs.slice(0, 40) }, null, 2));

// 平均亮度（用 page 内部 canvas 采样，避免额外依赖）
console.log('LOGS', JSON.stringify(logs.slice(0, 12)));
await browser.disconnect();
