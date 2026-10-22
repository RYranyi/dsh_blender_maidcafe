#!/usr/bin/env node
/**
 * probe-maid-mat.mjs —— 在 Node 里直接用项目自带的 three + GLTFLoader 解析冻结版 GLB，
 * 检查女仆各网格的「顶点色是否真的挂到材质上」，定位网页端头发发白的根因。
 *
 * 用法：node tools/probe-maid-mat.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const GLB = path.join(ROOT, 'scene', 'maid_cafe.glb');

const THREE = await import(new URL('../js/vendor/three.module.js', import.meta.url).href);
const { GLTFLoader } = await import(new URL('../js/vendor/GLTFLoader.js', import.meta.url).href);

const buf = fs.readFileSync(GLB);
const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
const loader = new GLTFLoader();

const gltf = await new Promise((res, rej) => loader.parse(ab, '', res, rej));
const root = gltf.scene;

const MAID = ['M_Skin', 'M_Hair', 'M_Iris', 'M_Sclera', 'M_White', 'M_Navy', 'M_Satin', 'M_EyeLight', 'M_EyeRed', 'M_Mouth', 'M_Blush'];
const rows = [];
root.traverse((o) => {
  if (!o.isMesh) return;
  const m = Array.isArray(o.material) ? o.material[0] : o.material;
  if (!m) return;
  const hasColor = !!(o.geometry.attributes && o.geometry.attributes.color);
  const isMaid = MAID.includes(m.name) || hasColor;
  if (!isMaid) return;
  const attr = o.geometry.attributes.color;
  let sample = null;
  if (attr && attr.count) {
    sample = [attr.getX(0), attr.getY(0), attr.getZ(0)].map((v) => +v.toFixed(4));
  }
  rows.push({
    mesh: o.name,
    mat: m.name,
    type: m.type,
    vertexColors: m.vertexColors,
    hasColorAttr: hasColor,
    colorItemSize: attr ? attr.itemSize : null,
    colorSample: sample,
    baseColor: m.color ? '#' + m.color.getHexString() : null,
    sheen: m.sheen,
    clearcoat: m.clearcoat,
  });
});

console.log('== 女仆相关网格（' + rows.length + ' 个）==');
for (const r of rows) {
  console.log(
    `${r.mesh.padEnd(14)} mat=${r.mat.padEnd(10)} type=${String(r.type).padEnd(20)}` +
      ` vertexColors=${String(r.vertexColors).padEnd(5)} colorAttr=${String(r.hasColorAttr).padEnd(5)}` +
      ` itemSize=${r.colorItemSize} sample=${JSON.stringify(r.colorSample)} base=${r.baseColor}`
  );
}
const bad = rows.filter((r) => r.hasColorAttr && r.vertexColors !== true);
console.log('\n== 结论 ==');
console.log('带 COLOR_0 但材质 vertexColors !== true 的网格数:', bad.length);
if (bad.length) console.log('受影响的网格:', bad.map((b) => b.mesh + '(' + b.mat + ')').join(', '));

// 模拟「强制 vertexColors」后的有效颜色
const eff = rows
  .filter((r) => r.hasColorAttr && r.colorSample)
  .map((r) => {
    const c = new THREE.Color(r.colorSample[0], r.colorSample[1], r.colorSample[2]);
    if (r.vertexColors !== true) c.multiply(new THREE.Color(r.baseColor || '#ffffff'));
    return `${r.mesh.padEnd(14)} → #${c.getHexString()}`;
  });
console.log('\n== 修正后有效颜色（sRGB 近似）==');
for (const e of eff) console.log('  ' + e);
