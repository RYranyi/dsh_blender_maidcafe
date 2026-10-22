#!/usr/bin/env node
/**
 * start-headless-edge.mjs —— 用 Node 拉起一个「固定调试端口」的无头 Edge，供 verify.mjs connect。
 *
 * 为什么不用 puppeteer.launch()：
 *   本机 DSH 沙箱禁止「用管道捕获子进程 stdio」（spawn 返回 EPERM），而 puppeteer.launch()
 *   正是靠管道读 DevTools 的 ws URL。因此独立用 detached + stdio:'ignore' 拉起浏览器，
 *   再用 puppeteer.connect({browserURL}) 连接 —— 这条路径实测可用。
 *
 * 用法：
 *   node tools/web/start-headless-edge.mjs                 # 端口 9333，headless
 *   node tools/web/start-headless-edge.mjs --port 9334 --headful
 *   node tools/web/start-headless-edge.mjs --keep 900000    # 保持 15 分钟（后台作业里用）
 *
 * 临时目录铁律：profile / TEMP 全部落在 .scratch/web 下。
 */
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const SCRATCH = path.join(ROOT, '.scratch', 'web');
const PROFILE = path.join(SCRATCH, 'profile');
const TMP = path.join(SCRATCH, 'tmp');

process.env.TEMP = TMP;
process.env.TMP = TMP;
fs.mkdirSync(TMP, { recursive: true });
fs.mkdirSync(PROFILE, { recursive: true });

const argv = process.argv.slice(2);
const arg = (n, d) => {
  const i = argv.indexOf(`--${n}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
};
const has = (n) => argv.includes(`--${n}`);

const PORT = Number(arg('port', 9333));
const KEEP = Number(arg('keep', 0));
const HEADFUL = has('headful');
const URL_ARG = arg('url', 'about:blank');

const EDGE_CANDIDATES = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
];
const EDGE = EDGE_CANDIDATES.find((p) => fs.existsSync(p));
if (!EDGE) {
  console.error('找不到 msedge.exe');
  process.exit(1);
}

function portOpen(port) {
  return new Promise((resolve) => {
    const s = net.connect({ port, host: '127.0.0.1' });
    s.setTimeout(700);
    s.once('connect', () => {
      s.destroy();
      resolve(true);
    });
    s.once('timeout', () => {
      s.destroy();
      resolve(false);
    });
    s.once('error', () => resolve(false));
  });
}

async function waitDebug(port, ms) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await portOpen(port)) {
      try {
        const res = await fetch(`http://127.0.0.1:${port}/json/version`);
        const j = await res.json();
        if (j.webSocketDebuggerUrl) return j;
      } catch {
        /* 端口刚开但 http 还没就绪 */
      }
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return null;
}

const args = [
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${PROFILE}`,
  '--no-first-run',
  '--no-default-browser-check',
  '--disable-background-networking',
  '--disable-features=Translate,BackForwardCache,MediaRouter',
  '--disable-dev-shm-usage',
  '--disable-extensions',
  '--enable-unsafe-swiftshader',
  '--use-angle=swiftshader',
  '--autoplay-policy=no-user-gesture-required',
  '--window-size=1280,800',
  '--lang=zh-CN',
];
if (!HEADFUL) args.push('--headless=new');
args.push(URL_ARG);

const already = await portOpen(PORT);
if (already) {
  console.log(`ALREADY http://127.0.0.1:${PORT}`);
} else {
  const out = fs.openSync(path.join(SCRATCH, 'edge.log'), 'a');
  const err = fs.openSync(path.join(SCRATCH, 'edge.err.log'), 'a');
  const child = spawn(EDGE, args, {
    detached: true,
    stdio: ['ignore', out, err], // 必须不用 pipe（沙箱 EPERM）
    windowsHide: true,
  });
  child.unref();
  fs.writeFileSync(path.join(SCRATCH, 'edge.pid'), String(child.pid));
  console.log(`PID ${child.pid}`);
  const info = await waitDebug(PORT, 40000);
  if (!info) {
    console.error('FAILED 调试端口未打开（看 .scratch/web/edge.err.log）');
    process.exit(1);
  }
  console.log(`READY http://127.0.0.1:${PORT}`);
  console.log(`BROWSER ${info.Browser}`);
}

if (KEEP > 0) await new Promise((r) => setTimeout(r, KEEP));
