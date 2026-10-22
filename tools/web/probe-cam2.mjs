#!/usr/bin/env node
/** probe-cam2.mjs —— 在**已加载 GLB 的页面**上做射线诊断（列出最近命中物体）。 */
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
// 只保留一个标签页（多个 WebGL 页面同时跑会拖慢到超时）
const all = await browser.pages();
let page = all.find((p) => p.url().includes('/index.html'));
for (const p of all) {
  if (p !== page) {
    try {
      await p.close();
    } catch {}
  }
}
if (!page) page = await browser.newPage();
page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
page.on('console', (m) => {
  if (m.type() === 'error' || m.type() === 'warning') console.log('CONSOLE', m.type(), m.text());
});
await page.setViewport({ width: 1280, height: 800 });
console.log('PAGE', page.url());
if (!page.url().includes('/index.html')) {
  await page.goto('http://127.0.0.1:7800/index.html?debug=1', { waitUntil: 'domcontentloaded' });
}
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => window.__CAFE__ && window.__CAFE__.ready === true, { timeout: 120000, polling: 300 });
await page.click('#enter-btn');
await new Promise((r) => setTimeout(r, 2500));

const out = await page.evaluate(async () => {
  const c = window.__CAFE__;
  const sc = c.scene;
  const mod = await import('/js/vendor/three.module.js');
  sc.resetCamera();
  sc.renderer.render(sc.scene, sc.camera);
  const cam = sc.camera;
  const dir = new mod.Vector3();
  cam.getWorldDirection(dir);
  const ray = new mod.Ray(cam.position.clone(), dir);
  const root = sc.glbRoot;
  if (!root) {
    return {
      glbLoaded: c.glbLoaded,
      glbError: sc.glbError,
      warnings: sc.warnings,
      stats: sc.stats(),
      hasPlaceholder: !!sc.placeholder,
      pageUrl: location.href,
    };
  }
  const hits = [];
  const box = new mod.Box3();
  const pt = new mod.Vector3();
  root.traverse((o) => {
    if (!o.isMesh) return;
    box.setFromObject(o);
    if (!box.containsPoint(cam.position) && ray.intersectBox(box, pt)) {
      const d = pt.distanceTo(cam.position);
      if (d < 10) {
        hits.push({
          d: +d.toFixed(3),
          name: o.name || '(unnamed)',
          mat: Array.isArray(o.material) ? o.material.map((m) => m.name) : o.material && o.material.name,
          transparent: !!(o.material && o.material.transparent),
        });
      }
    }
  });
  hits.sort((a, b) => a.d - b.d);
  // 视锥内的大物体
  const frustum = new mod.Frustum();
  const pm = new mod.Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
  frustum.setFromProjectionMatrix(pm);
  const big = [];
  root.traverse((o) => {
    if (!o.isMesh) return;
    box.setFromObject(o);
    const size = new mod.Vector3();
    box.getSize(size);
    if (size.length() < 1.2) return;
    if (!frustum.intersectsBox(box)) return;
    big.push({
      name: o.name || '(unnamed)',
      size: [+size.x.toFixed(2), +size.y.toFixed(2), +size.z.toFixed(2)],
      center: box.getCenter(new mod.Vector3()).toArray().map((v) => +v.toFixed(2)),
      dist: +box.distanceToPoint(cam.position).toFixed(2),
      mat: Array.isArray(o.material) ? o.material.map((m) => m.name) : o.material && o.material.name,
    });
  });
  big.sort((a, b) => a.dist - b.dist);
  return {
    glbLoaded: c.glbLoaded,
    glbStats: sc.glbStats,
    camPos: cam.position.toArray().map((v) => +v.toFixed(2)),
    dir: dir.toArray().map((v) => +v.toFixed(2)),
    nearHits: hits,
    bigInView: big.slice(0, 14),
  };
});
console.log(JSON.stringify(out, null, 2));
await browser.disconnect();
