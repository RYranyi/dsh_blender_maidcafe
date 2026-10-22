/**
 * test_api.mjs —— 跨模块 API 交叉检查
 *
 * 背景：用户实测"滑条全是100%没反应"的根因，是 app.js 调用了
 *       freecam.js 里**已被删掉**的 widenLimits()，异常被 try/catch 吞掉，
 *       导致后面两行初始化静默跳过。
 * 这类"调了不存在的方法"必须一次性全排掉，否则永远在修表面症状。
 *
 * 做法：解析 app.js / scene.js / weather.js 里所有 `x.method(` 调用，
 *       和对应模块里实际定义的方法名做差集。
 */
import fs from 'node:fs';

const R = 'E:/dsh/maid_cafe/js/';
const read = (f) => fs.readFileSync(R + f, 'utf8');

const files = {
  app: read('app.js'),
  scene: read('scene.js'),
  weather: read('weather.js'),
  freecam: read('freecam.js'),
  audio: read('audio.js'),
};

/** 提取模块里定义的方法名（类方法 / 对象字面量简写 / getter） */
function definedMethods(src) {
  const out = new Set();
  for (const m of src.matchAll(/^\s{2,6}(?:static\s+|async\s+|get\s+|set\s+)?([a-zA-Z_$][\w$]*)\s*\(/gm)) {
    out.add(m[1]);
  }
  // this.x = () => {}   /  this.x = function
  for (const m of src.matchAll(/this\.([a-zA-Z_$][\w$]*)\s*=\s*(?:\(|function|async|this\.)/g)) {
    out.add(m[1]);
  }
  // 顶层 function 名字
  for (const m of src.matchAll(/^(?:async\s+)?function\s+([a-zA-Z_$][\w$]*)/gm)) {
    out.add(m[1]);
  }
  // const x = (...) => / const x = function
  for (const m of src.matchAll(/^(?:const|let|var)\s+([a-zA-Z_$][\w$]*)\s*=\s*(?:\(|async|function)/gm)) {
    out.add(m[1]);
  }
  return out;
}

let pass = 0, fail = 0;
const ok = (c, n, e = '') => {
  if (c) { pass++; console.log('  PASS  ' + n + (e ? '   ' + e : '')); }
  else { fail++; console.log('  FAIL  ' + n + (e ? '   ' + e : '')); }
};

console.log('═'.repeat(70));
console.log('跨模块 API 交叉检查（防"调了不存在的方法"）');
console.log('═'.repeat(70));

// app.js 里对 app.<module>.<method> 的调用
const targets = [
  ['freecam', definedMethods(files.freecam)],
  ['scene', definedMethods(files.scene)],
  ['weather', definedMethods(files.weather)],
  ['audio', definedMethods(files.audio)],
];

for (const [mod, defined] of targets) {
  const re = new RegExp(`app\\.${mod}\\.([a-zA-Z_$][\\w$]*)\\s*\\(`, 'g');
  const calls = new Set();
  for (const src of [files.app, files.scene, files.weather]) {
    for (const m of src.matchAll(re)) calls.add(m[1]);
  }
  const missing = [...calls].filter((c) => !defined.has(c));
  const sorted = [...calls].sort();
  console.log(`\n[app.${mod}.*]  调用 ${sorted.length} 个`);
  console.log('  ' + (sorted.join(', ') || '(无)'));
  ok(missing.length === 0, `app.${mod}.* 全部已定义`,
     missing.length ? '缺失: ' + missing.join(', ') : '');
}

// freecam 特判（fc.xxx / app.freecam.xxx 混用）
{
  const defined = definedMethods(files.freecam);
  const calls = new Set();
  for (const m of files.app.matchAll(/(?:app\.freecam|fc)\.([a-zA-Z_$][\w$]*)\s*\(/g)) calls.add(m[1]);
  const missing = [...calls].filter((c) => !defined.has(c));
  ok(missing.length === 0, 'fc.* / app.freecam.* 全部已定义',
     missing.length ? '缺失: ' + missing.join(', ') : '');
}

// 关键方法存在性（本节用户实测出问题的两个）
console.log('\n关键方法：');
{
  const fc = definedMethods(files.freecam);
  ok(fc.has('widenLimits'), 'freecam.widenLimits 存在（曾丢失导致初始化中断）');
  ok(fc.has('enable') && fc.has('setMode') && fc.has('update') && fc.has('updateFly'),
     'freecam.enable / setMode / update / updateFly 存在');
  ok(!fc.has('setPreset'), 'freecam.setPreset 已删除（固定视角废弃）');
  const app = files.app;
  ok(/function\s+bindBrightnessUI/.test(app), 'app.js 定义 bindBrightnessUI');
  ok(/bindBrightnessUI\(\);/.test(app), 'app.js 调用 bindBrightnessUI()');
  const h = fs.readFileSync('E:/dsh/maid_cafe/index.html', 'utf8');
  ok(/id="brightness"/.test(h), 'index.html 有 #brightness 滑条');
  ok(/id="brightness-val"/.test(h), 'index.html 有 #brightness-val 标签');
}

// 曝光公式数值
console.log('\n曝光数值（系数 0.78）：');
{
  const m = JSON.parse(fs.readFileSync('E:/dsh/maid_cafe/scene/scene_manifest.json', 'utf8'));
  const ph = m.light_rig.phases;
  const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
  // 从 weather.js 里读真实系数，避免测试与实现脱节
  const wjs = fs.readFileSync('E:/dsh/maid_cafe/js/weather.js', 'utf8');
  const km = wjs.match(/Math\.pow\(2, stops\) \* ([0-9.]+), ([0-9.]+), ([0-9.]+)\)/);
  const EXP_K = km ? parseFloat(km[1]) : 0.6;
  const EXP_LO = km ? parseFloat(km[2]) : 0.34;
  const EXP_HI = km ? parseFloat(km[3]) : 1.0;
  console.log('  (从 weather.js 读到系数 ' + EXP_K + '，区间 ' + EXP_LO + '–' + EXP_HI + ')');
  for (const [k, p] of Object.entries(ph)) {
    const stops = p.exposure == null ? 0 : p.exposure;
    const exp = clamp(Math.pow(2, stops) * EXP_K, EXP_LO, EXP_HI);
    // 旧公式：baseExp 按太阳强度分三档，再 + stops*0.5
    const sunE = (p.sun_energy || 0) * 0.62;
    const base = sunE < 0.5 ? 0.6 : sunE < 2.6 ? 0.9 : 0.74;
    const old = clamp(base + stops * 0.5, 0.5, 1.4);
    console.log(`  ${k.padEnd(8)} 旧 ${old.toFixed(3)} → 新 ${exp.toFixed(3)}  (${exp < old ? '更暗' : '更亮'})`);
    // 用户要求「不要太亮也不至于看不清」：夜晚原先太暗看不清书架，
    // 允许比旧公式略亮（上限 1.12 倍），其余时段必须更暗。
    const LIMIT = k === 'night' ? old * 1.12 : old + 1e-6;
    ok(exp <= LIMIT, `${k} 曝光不超标`, `${old.toFixed(3)} → ${exp.toFixed(3)}`);
  }
}

console.log('\n' + '─'.repeat(70));
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
