// 探测音频素材源可达性（Node fetch 走系统 TLS，比 PowerShell 靠谱）
// 用法: node probe_sources.mjs
const targets = [
  // 素材站
  'https://opengameart.org/',
  'https://opengameart.org/art-search-advanced?keys=rain&field_art_type_tid%5B%5D=13&field_art_licenses_tid%5B%5D=4',
  'https://freepd.com/',
  'https://freepd.com/upbeat.php',
  'https://soundjay.com/',
  // 镜像 / CDN / 代码仓
  'https://raw.githubusercontent.com/',
  'https://github.com/',
  'https://upload.wikimedia.org/',
  'https://commons.wikimedia.org/',
  'https://archive.org/',
  'https://cdn.jsdelivr.net/',
  'https://unpkg.com/',
  'https://registry.npmjs.org/',
  // 已知不可达的对照
  'https://pixabay.com/api/',
  'https://freesound.org/apiv2/',
  'https://api.polyhaven.com/',
];

for (const url of targets) {
  const t0 = Date.now();
  try {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 20000);
    const res = await fetch(url, {
      method: 'GET',
      signal: ctl.signal,
      redirect: 'follow',
      headers: { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) maid-cafe-audio/1.0' },
    });
    clearTimeout(timer);
    const ct = res.headers.get('content-type') || '';
    const len = res.headers.get('content-length') || '?';
    console.log(`OK   ${res.status}  ${String(Date.now() - t0).padStart(6)}ms  ${ct.slice(0, 40).padEnd(42)} ${url}`);
    // 读完丢弃，避免半连接
    try { await res.arrayBuffer(); } catch {}
  } catch (e) {
    console.log(`FAIL ${String(e.name)} ${String(Date.now() - t0).padStart(6)}ms  ${url}  :: ${String(e.message).slice(0, 90)}`);
  }
}
