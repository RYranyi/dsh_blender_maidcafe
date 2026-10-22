#!/usr/bin/env node
/**
 * prepare-vendor.mjs —— 从 npm 包 three@0.160.0 解出本地 vendor 文件。
 *
 * 为什么不用 CDN：本机 cdn.jsdelivr.net 不可达；unpkg 虽可达但网页要求零外链。
 * 本脚本把 npm 包里的 ESM 文件复制到 js/vendor/，并改写裸说明符 `from 'three'`
 * 为相对路径 `./three.module.js`（浏览器 ES module 没有 import map 时不能解析裸名）。
 *
 * 用法：
 *   cd E:\dsh\maid_cafe\.scratch\web\npm
 *   E:\applications\nodejs\npm.cmd i three@0.160.0
 *   E:\applications\nodejs\node.exe E:\dsh\maid_cafe\tools\web\prepare-vendor.mjs
 *
 * 幂等：重复跑覆盖同名文件，内容一致则跳过写入。
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const NM = path.join(ROOT, '.scratch', 'web', 'npm', 'node_modules', 'three');
const OUT = path.join(ROOT, 'js', 'vendor');

const JOBS = [
  { src: 'build/three.module.js', dst: 'three.module.js', rewrites: [] },
  {
    src: 'examples/jsm/controls/OrbitControls.js',
    dst: 'OrbitControls.js',
    rewrites: [[/\bfrom\s+'three'/g, "from './three.module.js'"]],
  },
  {
    src: 'examples/jsm/utils/BufferGeometryUtils.js',
    dst: 'BufferGeometryUtils.js',
    rewrites: [[/\bfrom\s+'three'/g, "from './three.module.js'"]],
  },
  {
    src: 'examples/jsm/loaders/GLTFLoader.js',
    dst: 'GLTFLoader.js',
    rewrites: [
      [/\bfrom\s+'three'/g, "from './three.module.js'"],
      [/\bfrom\s+'\.\.\/utils\/BufferGeometryUtils\.js'/g, "from './BufferGeometryUtils.js'"],
    ],
  },
  {
    // RectAreaLight 必须配这张 LTC 查找表才能正确着色（窗光模拟用）
    src: 'examples/jsm/lights/RectAreaLightUniformsLib.js',
    dst: 'RectAreaLightUniformsLib.js',
    rewrites: [[/\bfrom\s+'three'/g, "from './three.module.js'"]],
  },
  {
    // 天空 HDRI（.hdr / Radiance）加载器：给 scene.environment 提供真实 IBL
    src: 'examples/jsm/loaders/RGBELoader.js',
    dst: 'RGBELoader.js',
    rewrites: [[/\bfrom\s+'three'/g, "from './three.module.js'"]],
  },
];

function md5(buf) {
  return crypto.createHash('md5').update(buf).digest('hex').slice(0, 12);
}

if (!fs.existsSync(NM)) {
  console.error(`[vendor] 找不到 three 包：${NM}`);
  console.error('[vendor] 先执行： npm i three@0.160.0  于 .scratch/web/npm');
  process.exit(1);
}
fs.mkdirSync(OUT, { recursive: true });

const ver = JSON.parse(fs.readFileSync(path.join(NM, 'package.json'), 'utf8')).version;
console.log(`[vendor] three@${ver} -> ${OUT}`);

const report = [];
for (const job of JOBS) {
  const srcPath = path.join(NM, job.src);
  if (!fs.existsSync(srcPath)) {
    console.error(`[vendor] MISSING ${job.src}`);
    process.exitCode = 1;
    continue;
  }
  let code = fs.readFileSync(srcPath, 'utf8');
  for (const [re, rep] of job.rewrites) code = code.replace(re, rep);
  const dstPath = path.join(OUT, job.dst);
  const buf = Buffer.from(code, 'utf8');
  const old = fs.existsSync(dstPath) ? fs.readFileSync(dstPath) : null;
  const same = old && md5(old) === md5(buf);
  if (!same) fs.writeFileSync(dstPath, buf);
  report.push({
    dst: job.dst,
    bytes: buf.length,
    md5: md5(buf),
    skipped: !!same,
    bareThreeLeft: /from\s+'three'/.test(code),
  });
  console.log(
    `[vendor] ${same ? 'same ' : 'write'} ${job.dst.padEnd(26)} ${String(buf.length).padStart(8)} B  md5=${md5(buf)}`
  );
}

// 自检：vendor 目录里不允许存在任何裸 'three' 说明符（否则浏览器会 404）
for (const f of fs.readdirSync(OUT)) {
  if (!f.endsWith('.js')) continue;
  const code = fs.readFileSync(path.join(OUT, f), 'utf8');
  if (/from\s+'three'/.test(code)) {
    console.error(`[vendor] FAIL 裸说明符残留: ${f}`);
    process.exitCode = 1;
  }
  if (/https?:\/\/[^\s'"]+\.(js|mjs)/.test(code)) {
    console.warn(`[vendor] WARN ${f} 含外链 URL 字面量（通常是注释/文档字符串，人工确认）`);
  }
}

fs.writeFileSync(
  path.join(OUT, 'VENDOR-REPORT.json'),
  JSON.stringify({ three: ver, generatedBy: 'tools/web/prepare-vendor.mjs', files: report }, null, 2)
);
console.log('[vendor] done');
