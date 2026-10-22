// Network reachability probe for asset sources
const urls = [
  "https://cdn.jsdelivr.net/npm/three@0.160.0/package.json",
  "https://unpkg.com/three@0.160.0/package.json",
  "https://registry.npmjs.org/three",
  "https://api.polyhaven.com/assets?t=models&c=furniture",
  "https://api.polyhaven.com/files/herringbone_parquet",
  "https://pixabay.com/api/",
  "https://freesound.org/apiv2/",
  "https://opengameart.org/",
  "https://kenney.nl/",
  "https://github.com/",
  "https://raw.githubusercontent.com/mrdoob/three.js/dev/package.json",
  "https://ambientcg.com/api/v2/full_json",
];
for (const u of urls) {
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 15000);
    const r = await fetch(u, { signal: ctl.signal, headers: { "User-Agent": "Mozilla/5.0 dsh-agent" } });
    clearTimeout(t);
    const txt = await r.text();
    console.log(`${r.status} ${u} len=${txt.length}`);
  } catch (e) {
    console.log(`ERR ${u} :: ${e.message}`);
  }
}
