#!/usr/bin/env node
/** check-esm-syntax.mjs —— 只做 ESM 语法校验（不执行、不需要 DOM）。 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { pathToFileURL } from 'node:url';

const ROOT = process.argv[2] || process.cwd();
const files = [];
const walk = (d) => {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith('.js') || e.name.endsWith('.mjs')) files.push(p);
  }
};
for (const sub of ['js', 'tools']) walk(path.join(ROOT, sub));

let bad = 0;
for (const f of files) {
  let src = fs.readFileSync(f, 'utf8');
  if (src.charCodeAt(0) === 0xfeff) src = src.slice(1); // 去 BOM（Node 加载器会自动去，vm 不会）
  if (src.startsWith('#!')) src = '//' + src.slice(2); // 去掉 shebang，vm 解析器不认
  try {
    // vm.SourceTextModule 只解析不执行
    new vm.SourceTextModule(src, { identifier: pathToFileURL(f).href });
  } catch (e) {
    bad++;
    console.log('SYNTAX FAIL', path.relative(ROOT, f), '→', e.message);
  }
}
console.log(`checked ${files.length} files, ${bad} failed`);
process.exit(bad ? 1 : 0);
