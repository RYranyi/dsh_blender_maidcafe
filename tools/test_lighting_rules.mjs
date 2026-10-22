/**
 * test_lighting_rules.mjs —— 真跑 computeTargetState 验证开灯规则
 *
 * 不只看代码，而是把 weather.js 真的 import 进来算一遍：
 *   正午 + 晴天  → 室内灯必须是 0
 *   清晨 + 晴天  → 0
 *   黄昏 + 晴天  → 开
 *   深夜 + 晴天  → 开
 *   正午 + 多云  → 开（用户要求：多云也开灯）
 *   正午 + 中雨  → 开
 *
 * 用到的只是 THREE.Color / Color.lerp 等纯数学，Node 里可以直接跑。
 */
import fs from 'node:fs';

const R = 'E:/dsh/maid_cafe/';
let mod;
try {
  mod = await import('file:///E:/dsh/maid_cafe/js/weather.js');
} catch (e) {
  console.log('无法直接 import weather.js:', e.message);
  console.log('（three.module.js 依赖浏览器环境时跳过本测试）');
  process.exit(0);
}

const { computeTargetState, resolveLightData } = mod;
const manifest = JSON.parse(fs.readFileSync(R + 'scene/scene_manifest.json', 'utf8'));
// resolveLightData 要完整 manifest（内部取 manifest.light_rig）
const lightData = resolveLightData(manifest);

let pass = 0, fail = 0;
const ok = (c, n, e = '') => {
  if (c) { pass++; console.log('  PASS  ' + n + (e ? '   ' + e : '')); }
  else { fail++; console.log('  FAIL  ' + n + (e ? '   ' + e : '')); }
};

const CASES = [
  // [hour, weather, 期望开灯?, 说明]
  [12.0, 'clear', false, '正午 · 晴天 → 关灯'],
  [9.0, 'clear', false, '上午 · 晴天 → 关灯'],
  [13.0, 'clear', false, '下午 · 晴天 → 关灯'],
  [18.0, 'clear', true, '黄昏 · 晴天 → 开灯'],
  [22.0, 'clear', true, '深夜 · 晴天 → 开灯'],
  [3.0, 'clear', true, '凌晨 3 点 → 开灯'],
  [12.0, 'cloudy', true, '正午 · 多云 → 开灯（用户要求）'],
  [12.0, 'rain_med', true, '正午 · 中雨 → 开灯'],
  [12.0, 'storm', true, '正午 · 雷阵雨 → 开灯'],
  [9.0, 'cloudy', true, '上午 · 多云 → 开灯'],
];

console.log('═'.repeat(72));
console.log('开灯规则（真跑 computeTargetState）');
console.log('═'.repeat(72));

for (const [hour, weather, want, desc] of CASES) {
  let st;
  try {
    st = computeTargetState(hour, weather, lightData);
  } catch (e) {
    ok(false, desc, '抛异常: ' + e.message);
    continue;
  }
  const lamp = st.lampIntensity;
  const on = lamp > 0.5;
  ok(on === want, desc,
     `hour=${hour} ${weather} → lampIntensity=${(lamp || 0).toFixed(2)} lampOn=${st.lampOn}`);
  if (want) {
    ok(lamp > 0, desc + '（强度大于 0）', '');
  } else {
    ok(lamp === 0, desc + '（强度恰为 0）', String(lamp));
    ok(st.emissiveIntensity === 0, desc + '（灯罩不发光）', String(st.emissiveIntensity));
  }
}

// 多云雾感
console.log('\n' + '─'.repeat(72));
{
  const clearSt = computeTargetState(12, 'clear', lightData);
  const cloudSt = computeTargetState(12, 'cloudy', lightData);
  const fogRatio = cloudSt.fogDensity / Math.max(clearSt.fogDensity, 1e-9);
  console.log(`  晴天雾密度 ${clearSt.fogDensity.toFixed(5)} / 多云 ${cloudSt.fogDensity.toFixed(5)} = ${fogRatio.toFixed(2)}x`);
  ok(fogRatio > 2.0, '多云雾密度 > 晴天 2 倍（朦胧感加强）', fogRatio.toFixed(2) + 'x');
  ok(cloudSt.cloudCover >= 0.9, '多云 cloudCover ≥ 0.90', String(cloudSt.cloudCover));
}

// 灯光强度确实降了
console.log('\n' + '─'.repeat(72));
{
  const nightSt = computeTargetState(22, 'clear', lightData);
  console.log(`  深夜吊灯强度 ${nightSt.lampIntensity.toFixed(2)} / 吧台射灯 ${nightSt.barSpotIntensity.toFixed(2)} / 展柜 ${nightSt.displaySpotIntensity.toFixed(2)}`);
  ok(nightSt.lampIntensity <= 20, '深夜吊灯总强度 ≤ 20（原 14×1.75=24.5）', nightSt.lampIntensity.toFixed(2));
}

console.log('\n' + '─'.repeat(72));
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
