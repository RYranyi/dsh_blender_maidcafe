/**
 * test_integration.mjs —— 静态集成检查（抓"引用了不存在的东西"）
 *
 * 1) app.js 里 $('#id') / getElementById('id') 引用的元素，必须真的在 index.html 里
 * 2) app.js 里调用的本文件函数，必须真的定义过（function xxx 或 const xxx = () =>）
 * 3) app.js 里用的 CSS 类，必须在 style.css 里出现
 *
 * 这类问题静态检查能提前抓到，不用等运行时报错。
 */
import fs from 'node:fs';

const R = 'E:/dsh/maid_cafe/';
const app = fs.readFileSync(R + 'js/app.js', 'utf8');
const html = fs.readFileSync(R + 'index.html', 'utf8');
const css = fs.readFileSync(R + 'css/style.css', 'utf8');

let pass = 0, fail = 0;
const ok = (c, n, e = '') => {
  if (c) { pass++; }
  else { fail++; console.log('  FAIL  ' + n + (e ? '   ' + e : '')); }
};
const okv = (c, n, e = '') => {
  if (c) { pass++; console.log('  PASS  ' + n + (e ? '   ' + e : '')); }
  else { fail++; console.log('  FAIL  ' + n + (e ? '   ' + e : '')); }
};

console.log('═'.repeat(72));
console.log('集成检查 1：DOM ID 引用');
console.log('═'.repeat(72));

const idsInHtml = new Set();
for (const m of html.matchAll(/\bid="([^"]+)"/g)) idsInHtml.add(m[1]);

const idsReferenced = new Set();
for (const m of app.matchAll(/\$\('#([A-Za-z0-9_-]+)'\)/g)) idsReferenced.add(m[1]);
for (const m of app.matchAll(/getElementById\('([A-Za-z0-9_-]+)'\)/g)) idsReferenced.add(m[1]);

// 这些 ID 是 JS 在运行时创建/注入的，不需要出现在 index.html
const DYNAMIC_IDS = new Set(['btn-immersive', 'immersive-exit', 'dock-restore']);
const missingIds = [...idsReferenced].filter(
  (id) => !idsInHtml.has(id) && !DYNAMIC_IDS.has(id));
okv(missingIds.length === 0, `app.js 引用的 ${idsReferenced.size} 个 DOM ID 全部存在`,
    missingIds.length ? '缺失: ' + missingIds.join(', ') : '');

// 反向：本轮新增/删除的关键 ID
for (const id of ['music-vol', 'rain-vol', 'music-vol-label', 'rain-vol-label',
                  'immersive-exit', 'brightness', 'brightness-val',
                  'panel-time', 'time-slider', 'view-presets', 'view-mode-hint',
                  'music-select', 'btn-music-prev', 'btn-music-next', 'btn-music-random']) {
  ok(idsInHtml.has(id), `HTML 存在 #${id}`);
}
for (const id of ['volume-slider', 'volume-label', 'btn-reset-cam']) {
  ok(!idsInHtml.has(id) && !idsReferenced.has(id), `已移除 #${id}`);
}

console.log('\n' + '═'.repeat(72));
console.log('集成检查 2：app.js 内部函数定义');
console.log('═'.repeat(72));

const defined = new Set();
// 顶层或嵌套的 function 声明（允许缩进）
for (const m of app.matchAll(/(?:^|\n)[ \t]*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/g)) defined.add(m[1]);
// 具名 IIFE：(function name() { ... })()
for (const m of app.matchAll(/\(function\s+([A-Za-z_$][\w$]*)\s*\(/g)) defined.add(m[1]);
// const/let/var = (...) =>  /  = x =>  /  = async () =>   （允许缩进）
for (const m of app.matchAll(/(?:^|\n)[ \t]*(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/g)) defined.add(m[1]);
for (const m of app.matchAll(/(?:^|\n)[ \t]*(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function/g)) defined.add(m[1]);
// import { a, b as c } from '...'
for (const m of app.matchAll(/import\s*\{([^}]+)\}\s*from/g)) {
  m[1].split(',').forEach((s) => {
    const nm = s.trim().split(/\s+as\s+/).pop().trim();
    if (nm) defined.add(nm);
  });
}
// 局部数值工具函数兜底
['min', 'max', 'clamp', 'lerp', 'mul', 'lerp3'].forEach((k) => defined.add(k));

// 只挑出「看起来像本文件内的函数调用」
const CALL_WHITELIST = new Set([
  'if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'function',
  'requestAnimationFrame', 'cancelAnimationFrame', 'setTimeout', 'clearTimeout',
  'setInterval', 'clearInterval', 'parseFloat', 'parseInt', 'isFinite', 'isNaN',
  'String', 'Number', 'Boolean', 'Array', 'Object', 'Math', 'JSON', 'Date',
  'encodeURIComponent', 'decodeURIComponent', 'structuredClone', 'fetch',
  'import', 'console', 'alert', 'confirm', 'URLSearchParams', 'Promise',
  'Map', 'Set', 'Error', 'RegExp', 'Symbol', 'BigInt', 'queueMicrotask',
  'postMessage', 'addEventListener', 'removeEventListener', 'dispatchEvent',
  'async', 'await', 'super', 'new', 'delete', 'void', 'in', 'of', 'do', 'else',
]);

const calls = new Set();
for (const m of app.matchAll(/(?:^|[\s;{}()=,])([a-z][A-Za-z0-9_$]*)\s*\(/g)) {
  const name = m[1];
  if (CALL_WHITELIST.has(name)) continue;
  if (/^(?:get|set|has|add|remove|toggle|push|pop|slice|split|join|map|filter|find|forEach|reduce|some|every|includes|indexOf|replace|match|test|trim|toFixed|charAt|charCodeAt|startsWith|endsWith|padStart|concat|sort|keys|values|entries|then|catch|finally|bind|call|apply|querySelector|querySelectorAll|closest|appendChild|removeChild|createElement|setAttribute|getAttribute|removeAttribute|classList|toString|valueOf|toLowerCase|toUpperCase|substring|substr|at|flat|fill|from|isArray|assign|freeze|create|defineProperty)$/.test(name)) continue;
  calls.add(name);
}

const missingFns = [...calls].filter((n) => !defined.has(n) && !CALL_WHITELIST.has(n));
okv(missingFns.length === 0, `app.js 内部调用的函数均有定义（检查 ${calls.size} 个）`,
    missingFns.length ? '未定义: ' + missingFns.join(', ') : '');

for (const fn of ['setMusicVolume', 'setRainVolume', 'setImmersive', 'buildViewUI',
                  'bindBrightnessUI', 'initVolumesFromStorage', 'bindMusicUI',
                  'preloadAudioModule', 'unlockAudioSync']) {
  ok(defined.has(fn), `定义了 ${fn}()`);
}

console.log('\n' + '═'.repeat(72));
console.log('集成检查 3：CSS 类');
console.log('═'.repeat(72));

const cssClasses = new Set();
for (const m of css.matchAll(/\.([A-Za-z][\w-]*)/g)) cssClasses.add(m[1]);

const usedClasses = new Set();
for (const m of app.matchAll(/classList\.(?:add|remove|toggle)\('([\w-]+)'/g)) usedClasses.add(m[1]);

const missingCls = [...usedClasses].filter((c) => !cssClasses.has(c));
okv(missingCls.length === 0, `app.js 操作的 CSS 类均在 style.css 中（检查 ${usedClasses.size} 个）`,
    missingCls.length ? '缺失: ' + missingCls.join(', ') : '');

console.log('\n' + '─'.repeat(72));
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
