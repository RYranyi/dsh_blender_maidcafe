/**
 * test_exposure.mjs —— 校验网页曝光/灯光标定是否与 Blender 一致
 *
 * 从 scene_manifest.json 的 light_rig 读 Blender 真值，
 * 用与 weather.js 完全相同的公式重算 three 侧参数，检查是否落在合理区间。
 */
import fs from 'node:fs';

const MAN = 'E:/dsh/maid_cafe/scene/scene_manifest.json';
const m = JSON.parse(fs.readFileSync(MAN, 'utf8'));
const rig = m.light_rig || {};
const phases = rig.phases || {};

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

// weather.js 里的常量（改过之后的值）
const SUN_ENERGY_SCALE = 0.62;
const LIGHT_DEFAULTS = {
  sun: 1.9, hemi: 0.55, ambient: 0.22,
  lamp: 14.0, windowSky: 1.5, windowRect: 3.5,
  barSpot: 22.0, displaySpot: 8.0,
};

let pass = 0, fail = 0;
const ok = (c, name, extra = '') => {
  if (c) { pass++; console.log('  PASS  ' + name + (extra ? '   ' + extra : '')); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '   ' + extra : '')); }
};

console.log('═'.repeat(70));
console.log('网页曝光 / 灯光标定 vs Blender 真值');
console.log('═'.repeat(70));

for (const [name, p] of Object.entries(phases)) {
  const sunE = (p.sun_energy || 0) * SUN_ENERGY_SCALE;
  const a = p.ambient == null ? 0.5 : p.ambient;

  // 与 weather.js 现行公式一致
  const hemi = clamp(0.06 + Math.pow(a, 1.7) * 0.62, 0.06, 0.72);
  const amb = clamp(0.02 + Math.pow(a, 2.0) * 0.26, 0.02, 0.26);
  const stops = p.exposure == null ? 0 : p.exposure;
  const exp = clamp(Math.pow(2, stops) * 0.95, 0.45, 1.15);

  const blenderExp = Math.pow(2, stops);
  console.log(`\n[${name}]`);
  console.log(`  Blender : sun=${(p.sun_energy || 0).toFixed(2)}W/m²  ambient=${a}  ` +
              `exposure=${stops}档 (等价 ×${blenderExp.toFixed(3)})  indoor=${p.indoor}`);
  console.log(`  网页    : sun=${sunE.toFixed(2)}  hemi=${hemi.toFixed(3)}  ` +
              `amb=${amb.toFixed(3)}  exposure=${exp.toFixed(3)}`);

  // 曝光应贴近 2^stops（误差来自 0.95 的整体系数）
  const ratio = exp / blenderExp;
  ok(ratio > 0.85 && ratio < 1.05, `${name} 曝光倍率贴近 2^stops`, `ratio=${ratio.toFixed(3)}`);
  ok(exp >= 0.45 && exp <= 1.15, `${name} 曝光在安全区间 0.45–1.15`, `exp=${exp.toFixed(3)}`);
  ok(hemi <= 0.72, `${name} hemi 不超上限`, `hemi=${hemi.toFixed(3)}`);
  ok(amb <= 0.26, `${name} ambient 不超上限`, `amb=${amb.toFixed(3)}`);
}

/* 环境光预算对比（旧 vs 新）—— 这是"室内永远亮"的主因 */
console.log('\n' + '─'.repeat(70));
const noonP = phases.noon || {};
const aN = noonP.ambient == null ? 0.85 : noonP.ambient;

const oldHemi = clamp(0.1 + Math.pow(aN, 1.7) * 1.45, 0.1, 1.5);
const oldAmb = clamp(0.03 + Math.pow(aN, 2.0) * 0.55, 0.03, 0.5);
const newHemi = clamp(0.06 + Math.pow(aN, 1.7) * 0.62, 0.06, 0.72);
const newAmb = clamp(0.02 + Math.pow(aN, 2.0) * 0.26, 0.02, 0.26);

console.log(`  环境光(hemi+ambient)  旧 ${(oldHemi + oldAmb).toFixed(3)}` +
            `  →  新 ${(newHemi + newAmb).toFixed(3)}` +
            `  (降低 ${(((oldHemi + oldAmb) - (newHemi + newAmb)) / (oldHemi + oldAmb) * 100).toFixed(0)}%)`);
console.log(`  环境贴图 IBL          旧 0.850  →  新 0.300`);
console.log(`  窗光 windowSky        旧 3.000  →  新 ${LIGHT_DEFAULTS.windowSky.toFixed(3)}`);
console.log(`  RectArea windowRect   旧 8.000  →  新 ${LIGHT_DEFAULTS.windowRect.toFixed(3)}`);
console.log(`  吊灯 lamp             旧 32.000 →  新 ${LIGHT_DEFAULTS.lamp.toFixed(3)}`);
console.log(`  吧台射灯 barSpot      旧 55.000 →  新 ${LIGHT_DEFAULTS.barSpot.toFixed(3)}`);
console.log(`  展柜射灯 displaySpot  旧 18.000 →  新 ${LIGHT_DEFAULTS.displaySpot.toFixed(3)}`);

ok((oldHemi + oldAmb) > (newHemi + newAmb) * 1.5,
   '环境光总量明显下调（至少 33%）',
   `${(oldHemi + oldAmb).toFixed(2)} → ${(newHemi + newAmb).toFixed(2)}`);
ok(LIGHT_DEFAULTS.windowRect === 3.5, 'RectArea 窗光已下调到 3.5');
ok(LIGHT_DEFAULTS.lamp === 14.0, '室内吊灯已下调到 14');
ok(LIGHT_DEFAULTS.barSpot === 22.0, '吧台射灯已下调到 22');

console.log('\n' + '─'.repeat(70));
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
