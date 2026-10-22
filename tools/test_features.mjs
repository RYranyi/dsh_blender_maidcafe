/**
 * test_features.mjs —— 本轮新要求的功能验证
 *
 * 用户要求：
 *   A. 视角移动 = 一比一复刻 bedroom_scene（单循环驱动，不是两个 rAF 抢帧）
 *   B. 删除所有固定视角预设
 *   C. 新增「沉浸观看」按钮（隐藏全部 UI）
 *   D. 音乐音量与雨声音量分开控制
 */
import fs from 'node:fs';
import { fileURLToPath } from "node:url";

const R = fileURLToPath(new URL('../', import.meta.url));
const fc = fs.readFileSync(R + 'js/freecam.js', 'utf8');
const app = fs.readFileSync(R + 'js/app.js', 'utf8');
const scn = fs.readFileSync(R + 'js/scene.js', 'utf8');
const audio = fs.readFileSync(R + 'js/audio.js', 'utf8');
const html = fs.readFileSync(R + 'index.html', 'utf8');
const css = fs.readFileSync(R + 'css/style.css', 'utf8');

let pass = 0, fail = 0;
const ok = (c, n, e = '') => {
  if (c) { pass++; console.log('  PASS  ' + n + (e ? '   ' + e : '')); }
  else { fail++; console.log('  FAIL  ' + n + (e ? '   ' + e : '')); }
};

console.log('═'.repeat(72));
console.log('A. 相机：单循环驱动（bedroom_scene 的做法）');
console.log('═'.repeat(72));
ok(!/requestAnimationFrame\(this\._tick\)/.test(fc), 'freecam 不再自起 rAF 循环');
ok(!/\n\s*_tick\s*\(/.test(fc), 'freecam 无 _tick 方法');
ok(/^\s{2}update\(dt\)\s*\{/m.test(fc), 'freecam 有 update(dt) 方法');
ok(/this\.mode === 'fly'\) this\.updateFly\(d\)/.test(fc), 'update() 里 fly 模式调 updateFly(dt)');
ok(/else if \(this\.controls\) this\.controls\.update\(\)/.test(fc), 'update() 里 orbit 模式调 controls.update()');
ok(/Math\.min\(0\.05,/.test(fc), 'dt 上限 0.05（与 bedroom 的 Math.min(0.05,…) 一致）');
ok(/if \(app\.freecam && app\.freecam\.enabled\) app\.freecam\.update\(dt\);/.test(app),
   'app.js 主循环里调用 freecam.update(dt)');
{
  const iUpd = app.indexOf('app.freecam.update(dt)');
  const iTick = app.indexOf('app.scene.tick(dt)');
  const iRender = app.indexOf('app.scene.render()');
  ok(iUpd > 0 && iUpd < iTick && iTick < iRender,
     '调用顺序 update → tick → render（和 bedroom 的 loop 一致）');
}
ok(/if \(!this\._freecamActive\) this\.controls\.update\(\);/.test(scn),
   'scene.tick 不重复 controls.update');
ok(/_freecamActive = true/.test(fc) && (/_freecamActive = false/.test(fc)),
   'enable/disable 正确维护 _freecamActive');

console.log('\n' + '═'.repeat(72));
console.log('B. 固定视角预设已彻底删除');
console.log('═'.repeat(72));
ok(!/VIEW_PRESETS/.test(fc) && !/VIEW_PRESETS/.test(app), 'VIEW_PRESETS 全项目已无引用');
ok(!/setPreset/.test(fc) && !/setPreset/.test(app), 'setPreset 已删除');
ok(!/seat_window|bar_front|door_in|maid.*特写|display.*甜品柜/.test(app + fc) ||
   !/id:\s*'seat_window'/.test(app + fc), '无固定视角条目');
ok(!/btn-reset-cam/.test(html), 'HTML 已无「默认机位」按钮');
ok(!/btn-reset-cam/.test(app), 'app.js 已无 btn-reset-cam 引用');
ok(/id="view-presets"/.test(html), '（保留了 view-presets 容器，现用于模式/沉浸按钮）');

console.log('\n' + '═'.repeat(72));
console.log('C. 沉浸观看');
console.log('═'.repeat(72));
ok(/function setImmersive\(on\)/.test(app), '定义 setImmersive()');
ok(/btn-immersive/.test(app), '有沉浸按钮的创建逻辑');
ok(/document\.body\.classList\.toggle\('immersive'/.test(app), '切换 body.immersive 类');
ok(/if \(k === 'h'\) \{ setImmersive/.test(app), 'H 键切换沉浸');
ok(!/k === 'escape'/.test(app), 'Esc 不绑定任何功能（本轮改动：改用 H / 按钮退出沉浸）');
ok(/id="immersive-exit"/.test(html), 'HTML 有沉浸退出按钮');
ok(/#hud/.test(css) && /body\.immersive/.test(css), 'CSS 有 body.immersive 隐藏规则');
for (const sel of ['#panel-weather', '#panel-time', '#panel-audio', '#view-bar']) {
  ok(new RegExp('body\\.immersive\\s+' + sel.replace('#', '\\#')).test(css),
     'CSS 隐藏 ' + sel);
}

console.log('\n' + '═'.repeat(72));
console.log('D. 音乐 / 雨声音量分开');
console.log('═'.repeat(72));
ok(/function setMusicVolume/.test(app), 'app.js 有 setMusicVolume()');
ok(/function setRainVolume/.test(app), 'app.js 有 setRainVolume()');
ok(/app\.audio\.setMusicVolume/.test(app), '调用 audio.setMusicVolume');
ok(/app\.audio\.setRainVolume/.test(app), '调用 audio.setRainVolume');
ok(/setMusicVolume\(v\)\s*\{/.test(audio), 'audio.js 实现 setMusicVolume');
ok(/setRainVolume\(v\)\s*\{/.test(audio), 'audio.js 实现 setRainVolume');
ok(/this\.musicBus/.test(audio) && /this\.rainBus/.test(audio), 'audio.js 有独立 musicBus / rainBus');
ok(/id="music-vol"/.test(html), 'HTML 有音乐音量滑条');
ok(/id="rain-vol"/.test(html), 'HTML 有雨声音量滑条');
ok(!/id="volume-slider"/.test(html), '旧的总音量滑条已移除');
ok(/localStorage\.setItem\('cafe\.musicVol'/.test(app) &&
   /localStorage\.setItem\('cafe\.rainVol'/.test(app), '两个音量都持久化到 localStorage');
ok(/function initVolumesFromStorage/.test(app), '有启动时恢复音量的函数');

console.log('\n' + '─'.repeat(72));
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
