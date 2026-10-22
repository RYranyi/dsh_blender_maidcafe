#!/usr/bin/env node
/**
 * serve.mjs —— 零依赖静态服务器（只服务 <项目根>）。
 *
 * 用法：
 *   node tools/web/serve.mjs            # 自动选 7800–7899 第一个空闲端口
 *   node tools/web/serve.mjs 8080       # 指定端口
 *   node tools/web/serve.mjs --port 8080 --root <项目根>
 *
 * 输出一行 `READY http://127.0.0.1:<port>`（脚本化验收用）。
 * 安全：只允许 GET/HEAD，路径规范化后必须落在 root 内。
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.glb': 'model/gltf-binary',
  '.gltf': 'model/gltf+json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.mp3': 'audio/mpeg',
  '.ogg': 'audio/ogg',
  '.wav': 'audio/wav',
  '.bin': 'application/octet-stream',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/plain; charset=utf-8',
};

function parseArgs(argv) {
  let port = 0;
  let root = ROOT;
  let verbose = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--port') port = Number(argv[++i]);
    else if (a === '--root') root = path.resolve(argv[++i]);
    else if (a === '--verbose') verbose = true;
    else if (!a.startsWith('--') && /^\d+$/.test(a)) port = Number(a);
  }
  return { port, root, verbose };
}

const args = parseArgs(process.argv.slice(2));

function send(res, code, body, headers = {}) {
  res.writeHead(code, { 'Cache-Control': 'no-store', ...headers });
  res.end(body);
}

const server = http.createServer((req, res) => {
  const t0 = Date.now();
  if (req.method !== 'GET' && req.method !== 'HEAD') return send(res, 405, 'method not allowed');
  let urlPath;
  try {
    urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  } catch {
    return send(res, 400, 'bad url');
  }
  if (urlPath === '/' || urlPath === '') urlPath = '/index.html';
  const target = path.resolve(args.root, '.' + urlPath);
  const rel = path.relative(args.root, target);
  if (rel.startsWith('..') || path.isAbsolute(rel)) return send(res, 403, 'forbidden');

  fs.stat(target, (err, st) => {
    if (err || !st.isFile()) {
      if (args.verbose) console.log(`404 ${urlPath}`);
      return send(res, 404, `not found: ${urlPath}`, { 'Content-Type': 'text/plain; charset=utf-8' });
    }
    const ext = path.extname(target).toLowerCase();
    const headers = {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Content-Length': st.size,
      'Access-Control-Allow-Origin': '*',
    };
    if (req.method === 'HEAD') {
      res.writeHead(200, headers);
      return res.end();
    }
    const stream = fs.createReadStream(target);
    res.writeHead(200, headers);
    stream.pipe(res);
    stream.on('error', () => {
      try {
        res.destroy();
      } catch {}
    });
  });
  if (args.verbose) res.on('finish', () => console.log(`${res.statusCode} ${req.url} ${Date.now() - t0}ms`));
});

function listen(port) {
  return new Promise((resolve, reject) => {
    const onErr = (e) => {
      server.removeListener('listening', onOk);
      reject(e);
    };
    const onOk = () => {
      server.removeListener('error', onErr);
      resolve(server.address().port);
    };
    server.once('error', onErr);
    server.once('listening', onOk);
    server.listen(port, '127.0.0.1');
  });
}

(async () => {
  const start = args.port || 7800;
  const tries = args.port ? [args.port] : Array.from({ length: 100 }, (_, i) => start + i);
  for (const p of tries) {
    try {
      const actual = await listen(p);
      console.log(`READY http://127.0.0.1:${actual}`);
      console.log(`ROOT  ${args.root}`);
      const shutdown = () => server.close(() => process.exit(0));
      process.on('SIGINT', shutdown);
      process.on('SIGTERM', shutdown);
      return;
    } catch (e) {
      if (e && e.code === 'EADDRINUSE') continue;
      console.error('listen failed:', e && e.message);
      process.exit(1);
    }
  }
  console.error('no free port in range');
  process.exit(1);
})();
