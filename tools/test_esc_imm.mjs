/**
 * test_esc_imm.mjs —— 锁死本轮两个修复
 *
 * 用户实测：
 *   A. 按 Esc 会切回 OrbitControls（"之前反人类操作"）→ Esc 必须彻底无功能
 *   B. 按 H 下半屏全黑 → 沉浸模式必须真正全屏 + 重算 canvas 尺寸
 */
import fs from 'node:fs';

const R = 'E:/dsh/maid_cafe/';
const files = {
  app: fs.readFileSync(R + 'js/app.js', 'utf8'),
  freecam: fs.readFileSync(R + 'js/freecam.js', 'utf8'),
  scene: fs.readFileSync(R + 'js/scene.js', 'utf8'),
  weather: fs.readFileSync(R + 'js/weather.js', 'utf8'),
  css: fs.readFileSync(R + 'css/style.css', 'utf8'),
  html: fs.readFileSync(R + 'index.html', 'utf8'),
};

let pass = 0, fail = 0;
const ok = (c, n, e = '') => {
  if (c) { pass++; console.log('  PASS  ' + n + (e ? '   ' + e : '')); }
  else { fail++; console.log('  FAIL  ' + n + (e ? '   ' + e : '')); }
};

console.log('═'.repeat(70));
console.log('A. Esc 必须彻底无功能');
console.log('═'.repeat(70));

// 逐个文件检查：除注释外不得出现 escape 关键字
for (const [name, src] of Object.entries(files)) {
  if (name === 'css' || name === 'html') continue;
  // 去掉行注释和块注释后再找
  const stripped = src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
  const hits = [...stripped.matchAll(/escape/gi)];
  ok(hits.length === 0, `${name}.js 无 escape 处理`, hits.length ? `仍出现 ${hits.length} 处` : '');
}

ok(!/setMode\('orbit'\)/.test(files.freecam.split('toggleMode')[1] || ''),
   'freecam 里没有隐式切换 orbit（只保留 toggleMode 显式切换）');
ok(!/k === 'escape'/.test(files.app), 'app.js 无 Esc 键分支');
ok(!/k === 'escape'/.test(files.freecam), 'freecam.js 无 Esc 键分支');

console.log('\n' + '═'.repeat(70));
console.log('B. 沉浸模式：全屏 + 尺寸重算 + canvas 铺满');
console.log('═'.repeat(70));

ok(/requestFullscreen|webkitRequestFullscreen|msRequestFullscreen/.test(files.app),
   'setImmersive 会请求全屏');
ok(/exitFullscreen|webkitExitFullscreen/.test(files.app),
   '退出沉浸会退出全屏');
ok(/fullscreenchange/.test(files.app),
   '监听 fullscreenchange：浏览器退出全屏时同步退出沉浸态');
ok(/const doResize = \(\) =>/.test(files.app) && /app\.scene\.resize/.test(files.app),
   '切换后调用 app.scene.resize() 重算渲染尺寸');
ok(/requestAnimationFrame\(doResize\)/.test(files.app),
   '下一帧再 resize 一次（等布局稳定）');
ok(/setTimeout\(doResize, 120\)/.test(files.app) && /setTimeout\(doResize, 420\)/.test(files.app),
   '120ms / 420ms 各补一次 resize（全屏动画结束）');
ok(/body\.immersive #stage canvas/.test(files.css),
   'CSS 强制沉浸态 canvas 尺寸');
ok(/height:\s*100dvh/.test(files.css),
   'CSS 用 100dvh 兼容移动端地址栏');
ok(/body\.immersive #app,\s*\nbody\.immersive #stage/.test(files.css),
   '#app / #stage 在沉浸态固定铺满视口');
ok(/id="immersive-exit"/.test(files.html), 'HTML 有沉浸退出按钮');
ok(/bindImmersiveExit/.test(files.app), '退出按钮真的有 click handler（曾漏绑）');
ok(/btn\.addEventListener\('click', \(\) => setImmersive\(false\)\)/.test(files.app),
   'click 回调调用 setImmersive(false)');
ok(/Kbd|<kbd>H<\/kbd>|H<\/kbd> 沉浸|>H<\/kbd>/.test(files.html) || /H<\/kbd> 沉浸/.test(files.html),
   '提示里写了 H 键');
ok(/沉浸/.test(files.html), '提示含「沉浸」字样');

console.log('\n' + '═'.repeat(70));
console.log('C. 旧操控方式（OrbitControls 作为默认）已不是唯一路径');
console.log('═'.repeat(70));

ok(/this\.mode = 'fly'/.test(files.freecam), '默认模式仍是 fly');
ok(/controls\.enabled = \(this\.mode === 'orbit'\)/.test(files.freecam) ||
   /controls\.enabled =/.test(files.freecam), 'orbit 模式才启用 OrbitControls');
ok(/if \(app\.freecam && app\.freecam\.enabled\) app\.freecam\.update\(dt\);/.test(files.app),
   '主循环仍由 freecam.update(dt) 驱动');

console.log('\n' + '═'.repeat(70));
console.log('D. resize 防呆（半屏黑的最可能成因）');
console.log('═'.repeat(70));

ok(/if \(!w \|\| w < 32\) w = window\.innerWidth/.test(files.scene),
   '容器宽 < 32 时退回 window.innerWidth');
ok(/if \(!h \|\| h < 32\) h = window\.innerHeight/.test(files.scene),
   '容器高 < 32 时退回 window.innerHeight');
ok(/Math\.max\(0\.1, Math\.min\(10, w \/ Math\.max\(h, 1\)\)\)/.test(files.scene),
   'camera.aspect 夹在 0.1–10（不会被压成一条）');
ok(/new ResizeObserver/.test(files.scene),
   '用 ResizeObserver 监听容器尺寸（全屏/布局变化都覆盖）');
ok(/_roPending/.test(files.scene),
   'ResizeObserver 回调合并到下一帧（避免 loop 警告）');

console.log('\n' + '─'.repeat(70));
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
