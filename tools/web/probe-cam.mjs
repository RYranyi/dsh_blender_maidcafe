#!/usr/bin/env node
/** probe-cam.mjs —— 诊断默认机位前方到底是什么物体（射线命中）。 */
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
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
await page.goto('http://127.0.0.1:7800/index.html?debug=1', { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => window.__CAFE__ && window.__CAFE__.ready === true, { timeout: 60000 });
await page.click('#enter-btn');
await new Promise((r) => setTimeout(r, 1200));

const out = await page.evaluate(async () => {
  const c = window.__CAFE__;
  const sc = c.scene;
  const THREE = sc.scene.constructor;
  // 用 three 模块构造射线（从 scene.js 内部的 THREE 实例同一份模块）
  const mod = await import('/js/vendor/three.module.js');
  const rc = new mod.Raycaster();
  sc.resetCamera();
  const cam = sc.camera;
  const dir = new mod.Vector3();
  cam.getWorldDirection(dir);
  rc.set(cam.position.clone(), dir);
  rc.far = 8;
  rc.camera = cam;
  const targets = [sc.glbRoot, sc.placeholder].filter(Boolean);
  const hits = rc.intersectObjects(targets, true).slice(0, 12).map((h) => ({
    d: +h.distance.toFixed(3),
    name: h.object.name,
    mat: (h.object.material && (Array.isArray(h.object.material) ? h.object.material[0].name : h.object.material.name)) || null,
    type: h.object.type,
    parent: h.object.parent && h.object.parent.name,
  }));

  // 也朝窗口方向打
  const toWin = new mod.Vector3(0.2, 1.4, 3.0).sub(cam.position).normalize();
  rc.set(cam.position.clone(), toWin);
  const hitsWin = rc.intersectObjects(targets, true).slice(0, 8).map((h) => ({
    d: +h.distance.toFixed(3),
    name: h.object.name,
    mat: (h.object.material && (Array.isArray(h.object.material) ? h.object.material[0].name : h.object.material.name)) || null,
  }));

  // 相机附近的大物体
  const near = [];
  const box = new mod.Box3();
  sc.glbRoot &&
    sc.glbRoot.traverse((o) => {
      if (!o.isMesh) return;
      box.setFromObject(o);
      const size = box.getSize(new mod.Vector3());
      const d = box.distanceToPoint(cam.position);
      if (d < 0.9) near.push({ name: o.name, size: [+size.x.toFixed(2), +size.y.toFixed(2), +size.z.toFixed(2)], d: +d.toFixed(2), mat: o.material && (Array.isArray(o.material) ? o.material[0].name : o.material.name) });
    });
  return { camPos: cam.position.toArray(), dir: dir.toArray(), hits, hitsWin, near: near.slice(0, 12), clamp: sc.clamp };
});
console.log(JSON.stringify(out, null, 2));
await browser.disconnect();
