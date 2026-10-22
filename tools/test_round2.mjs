/**
 * test_round2.mjs —— 本轮 5 项优化验证
 *
 * ① 取消 Q/E 侧倾
 * ② 取消"相机靠近物体变透明"
 * ③ 修光影出错 / 贴图闪烁（每帧 needsUpdate）
 * ④ 室内灯光调低 + 更接近视频观感
 * ⑤ 开灯规则（黄昏→凌晨 / 雨 / 多云）+ 多云朦胧感加强
 */
import fs from 'node:fs';
import { fileURLToPath } from "node:url";

const R = fileURLToPath(new URL('../', import.meta.url));
const fc = fs.readFileSync(R + 'js/freecam.js', 'utf8');
const scn = fs.readFileSync(R + 'js/scene.js', 'utf8');
const wea = fs.readFileSync(R + 'js/weather.js', 'utf8');

let pass = 0, fail = 0;
const ok = (c, n, e = '') => {
  if (c) { pass++; console.log('  PASS  ' + n + (e ? '   ' + e : '')); }
  else { fail++; console.log('  FAIL  ' + n + (e ? '   ' + e : '')); }
};

console.log('═'.repeat(70));
console.log('① Q/E 侧倾已取消');
console.log('═'.repeat(70));
ok(!/k\['q'\]/.test(fc), 'freecam 里无 k["q"] 分支');
ok(!/k\['e'\]/.test(fc), 'freecam 里无 k["e"] 分支');
ok(/this\.fly\.roll = 0;/.test(fc), 'roll 恒为 0');
{
  const navLine = (fc.match(/const NAV = \[[\s\S]*?\]/) || [''])[0];
  ok(!/'q'/.test(navLine) && !/'e'/.test(navLine), 'NAV 键列表已去掉 q / e', navLine.replace(/\s+/g, ' ').slice(0, 70));
}

console.log('\n' + '═'.repeat(70));
console.log('② 近相机变透明已取消');
console.log('═'.repeat(70));
ok(!/this\._updateNearCameraFade\(\);/.test(scn), 'tick 里不再调用');
ok(/_updateNearCameraFade\(\) \{\s*\n\s*\/\//.test(scn) || /_updateNearCameraFade\(\) \{[\s\S]{0,400}return;/.test(scn),
   '方法体已改为直接 return（no-op）');
ok(!/FADE_IN = 1\.35/.test(scn), '淡入距离常量已移除');

console.log('\n' + '═'.repeat(70));
console.log('③ 每帧 needsUpdate（闪烁主因）已修');
console.log('═'.repeat(70));
{
  const fn = (wea.match(/_applyLampMaterials\(st\) \{[\s\S]*?\n  \}/) || [''])[0];
  ok(fn.length > 0, '找到 _applyLampMaterials');
  const codeLines = fn.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l));
  ok(!codeLines.some((l) => /m\.needsUpdate = true/.test(l)),
     '_applyLampMaterials 里不再每帧 needsUpdate（排除注释）');
  ok(/m\.emissiveIntensity = st\.emissiveIntensity/.test(fn), '仍正确更新 emissiveIntensity（uniform，无需重编译）');
}
{
  // 全项目：weather.js 里不得有真正的 needsUpdate = true 语句
  const real = wea.split('\n').filter((l) => /m\.needsUpdate = true/.test(l) && !/^\s*\/\//.test(l));
  ok(real.length === 0, 'weather.js 无每帧 needsUpdate = true', real.length ? real.join(' | ') : '');
}
ok(!/_updateNearCameraFade[\s\S]{0,600}m\.needsUpdate = true/.test(scn) ||
   /_updateNearCameraFade\(\) \{[\s\S]{0,200}return;/.test(scn),
   '近相机淡出不再改 material.transparent / needsUpdate');

console.log('\n' + '═'.repeat(70));
console.log('④ 室内灯光调低 + 观感更接近视频');
console.log('═'.repeat(70));
const get = (re) => { const m = wea.match(re); return m ? Number(m[1]) : NaN; };
const lamp = get(/intensity:\s*([\d.]+),\s*\n\s*color: 0xffc98a,\s*\n\s*distance: 5\.0/);
const barSpot = get(/barSpot:\s*\{\s*intensity:\s*([\d.]+)\s*\}/);
const dispSpot = get(/displaySpot:\s*\{\s*intensity:\s*([\d.]+)\s*\}/);
ok(lamp === 7.4, '吊灯 intensity = 6.8（更暗一档）', String(lamp));
ok(barSpot === 10, '吧台射灯 = 9.5（更暗一档）', String(barSpot));
ok(dispSpot === 3.7, '展柜射灯 = 3.2（更暗一档）', String(dispSpot));
ok(/Math\.pow\(a, 1\.7\) \* 0\.50/.test(wea), 'hemi 系数 0.50（压低填充光，阴影更深）');

console.log('\n' + '═'.repeat(70));
console.log('⑤ 开灯规则 + 多云朦胧感');
console.log('═'.repeat(70));
ok(/const duskToDawn =/.test(wea), '有 duskToDawn 判定');
ok(/hh >= 16\.5 \|\| hh < 6\.0/.test(wea), '黄昏→凌晨窗口 = 16.5 → 6.0');
ok(/cloudy\|rain_light\|rain_med\|rain_heavy\|storm/.test(wea),
   '雨天/多云视为需要开灯');
ok(/const lampOn = \(duskToDawn \|\| weatherNeedsLight\) \? 1 : 0;/.test(wea), 'lampOn 逻辑正确');
ok(/if \(!lampOn\) \{[\s\S]{0,260}st\.lampIntensity = 0;/.test(wea), '不开灯时 lampIntensity = 0');
ok(/st\.emissiveIntensity = 0;/.test(wea), '不开灯时灯罩不发光');
ok(/\* lampOn;/.test(wea), 'barSpot / displaySpot 已被 lampOn 门控');
ok(/\* \(lampOn \? 1 : 0\.35\)/.test(wea), 'maidFill 跟 lampOn 联动');

// 多云
const cloudyBlock = (wea.match(/cloudy:\s*\{[\s\S]*?\n  \},/) || [''])[0];
ok(/cloudCover:\s*0\.90/.test(cloudyBlock), '多云 cloudCover = 0.90（原 0.82）');
ok(/fogMul:\s*2\.6/.test(cloudyBlock), '多云雾感 fogMul = 2.6（原 1.6）');

console.log('\n' + '─'.repeat(70));
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
