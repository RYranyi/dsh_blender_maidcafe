#!/usr/bin/env node
/**
 * probe-final.mjs —— 定位「默认机位遮挡」与「女仆发白」。
 * 用法：node tools/web/probe-final.mjs
 */
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
for (const p of await browser.pages()) {
  try {
    await p.close();
  } catch {}
}
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
page.on('console', (m) => {
  if (m.type() === 'error' || m.type() === 'warning') console.log('CONSOLE', m.type(), m.text().slice(0, 200));
});
await page.setViewport({ width: 1280, height: 800 });
await page.goto('http://127.0.0.1:7800/index.html?debug=1', { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => window.__CAFE__ && window.__CAFE__.ready === true, { timeout: 120000, polling: 300 });
await page.click('#enter-btn');
await new Promise((r) => setTimeout(r, 2000));

const out = await page.evaluate(async () => {
  const c = window.__CAFE__;
  const sc = c.scene;
  const mod = await import('/js/vendor/three.module.js');
  sc.resetCamera();
  sc.renderer.render(sc.scene, sc.camera);

  const cam = sc.camera;
  const dir = new mod.Vector3();
  cam.getWorldDirection(dir);

  // 沿视线做 ray-box 检测（不依赖 primitive raycast 的 group 问题）
  const ray = new mod.Ray(cam.position.clone(), dir);
  const box = new mod.Box3();
  const pt = new mod.Vector3();
  const hits = [];
  sc.glbRoot.traverse((o) => {
    if (!o.isMesh) return;
    box.setFromObject(o);
    if (box.containsPoint(cam.position)) {
      hits.push({ d: 0, name: o.name || '(unnamed)', inside: true, mat: mname(o), size: sizeOf(box) });
      return;
    }
    if (ray.intersectBox(box, pt)) {
      const d = pt.distanceTo(cam.position);
      if (d < 2.5) hits.push({ d: +d.toFixed(3), name: o.name || '(unnamed)', mat: mname(o), size: sizeOf(box) });
    }
  });
  hits.sort((a, b) => a.d - b.d);

  function mname(o) {
    if (!o.material) return null;
    return Array.isArray(o.material) ? o.material.map((m) => m && m.name) : o.material.name;
  }
  function sizeOf(b) {
    const s = b.getSize(new mod.Vector3());
    return [+s.x.toFixed(2), +s.y.toFixed(2), +s.z.toFixed(2)];
  }

  // 女仆材质清单
  const maidMats = {};
  const wanted = ['M_Skin', 'M_Hair', 'M_Iris', 'M_White', 'M_Satin', 'M_Navy', 'M_Sclera', 'M_Brow', 'M_Shoe'];
  for (const m of sc.glbMaterials || []) {
    if (!wanted.includes(m.name)) continue;
    maidMats[m.name] = {
      type: m.type,
      vertexColors: m.vertexColors,
      color: m.color ? '#' + m.color.getHexString() : null,
      hasColorAttr: m.vertexColors === true,
      roughness: m.roughness,
      metalness: m.metalness,
      sheen: m.sheen,
      sheenColor: m.sheenColor ? '#' + m.sheenColor.getHexString() : null,
      clearcoat: m.clearcoat,
      transmission: m.transmission,
      opacity: m.opacity,
      transparent: m.transparent,
      envMapIntensity: m.envMapIntensity,
      emissive: m.emissive ? '#' + m.emissive.getHexString() : null,
      emissiveIntensity: m.emissiveIntensity,
    };
  }

  // 女仆 mesh 上是否带 COLOR_0
  let maidMeshes = 0;
  let maidWithColor = 0;
  const camWorld = cam.position.clone();
  sc.glbRoot.traverse((o) => {
    if (!o.isMesh || !o.material) return;
    const names = (Array.isArray(o.material) ? o.material : [o.material]).map((m) => m && m.name);
    if (!names.some((n) => n && (n.startsWith('M_') || n === 'M_Skin'))) return;
    maidMeshes++;
    if (o.geometry.attributes.color) maidWithColor++;
  });

  return {
    camera: { pos: cam.position.toArray().map((v) => +v.toFixed(3)), target: sc.controls.target.toArray().map((v) => +v.toFixed(3)), dir: dir.toArray().map((v) => +v.toFixed(3)) },
    clamp: sc.clamp,
    glbStats: sc.glbStats,
    nearHits: hits.slice(0, 12),
    maidMaterials: maidMats,
    maidMeshes,
    maidWithColor,
    vertexColorMeshesStat: sc.glbStats.vertexColorMeshes,
    lights: {
      windowRect: c.weather.windowRectLight ? { intensity: c.weather.windowRectLight.intensity, pos: c.weather.windowRectLight.position.toArray() } : null,
      windowSky: c.weather.windowSkyLight ? c.weather.windowSkyLight.intensity : null,
      maidFill: c.weather.maidFill ? { i: c.weather.maidFill.intensity, p: c.weather.maidFill.position.toArray() } : null,
      envCur: c.weather._envCurIntensity,
      exposure: sc.renderer.toneMappingExposure,
    },
  };
});
console.log(JSON.stringify(out, null, 2));
await browser.disconnect();
