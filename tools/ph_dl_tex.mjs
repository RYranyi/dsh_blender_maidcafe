// PolyHaven texture downloader for the maid-cafe asset set.
// usage: node ph_dl_tex.mjs [--res-override 1k] [--rerun]
// Reads .scratch/asset-scout/resolved.json (produced by ph_scout_manifest.mjs).
// Writes assets/tex/<id>_<map>_<res>.jpg where map ∈ diff|nor_gl|arm|rough|disp
// Idempotent: skips any existing file > 1KB. Fails over to the next id in the
// wishlist group on 403/404, and retries each URL up to 3 times.
// Records everything in .scratch/asset-scout/tex_downloaded.json
import fs from "node:fs";
import path from "node:path";

const ROOT = "E:/dsh/maid_cafe";
const OUT = path.join(ROOT, "assets/tex");
const SCRATCH = path.join(ROOT, ".scratch/asset-scout");
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(SCRATCH, { recursive: true });

const resolved = JSON.parse(fs.readFileSync(path.join(SCRATCH, "resolved.json"), "utf8"));
const groups = JSON.parse(fs.readFileSync(path.join(ROOT, "tools/ph_wishlist.json"), "utf8")).textures;

// PolyHaven files API map key -> our short map token
const MAP_KEYS = [
  ["Diffuse", "diff"],
  ["nor_gl", "nor_gl"],
  ["arm", "arm"],
  ["Rough", "rough"],
  ["Displacement", "disp"],
];

const log = [];
const record = [];

function walkEntries(node, acc) {
  if (!node || typeof node !== "object") return;
  if (node.url) { acc.push(node); return; }
  for (const v of Object.values(node)) walkEntries(v, acc);
}

async function fetchBuf(url, tries = 3) {
  let last = "";
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url);
      if (!r.ok) { last = `HTTP ${r.status}`; if (r.status === 403 || r.status === 404) break; }
      else return Buffer.from(await r.arrayBuffer());
    } catch (e) { last = e.message; }
    await new Promise((res) => setTimeout(res, 400 * (i + 1)));
  }
  throw new Error(last || "unknown");
}

function already(p) { return fs.existsSync(p) && fs.statSync(p).size > 1024; }

for (const want of groups) {
  const candidates = [want.ids[0], ...want.ids.slice(1)]; // wishlist order == failover order
  let groupDone = null;
  for (const id of candidates) {
    let files;
    try {
      const r = await fetch(`https://api.polyhaven.com/files/${id}`);
      if (!r.ok) { log.push(`FILESFAIL ${id} ${r.status}`); continue; }
      files = await r.json();
    } catch (e) { log.push(`FILESERR ${id} ${e.message}`); continue; }

    const res = want.res || "1k";
    const picks = [];
    for (const [apiKey, token] of MAP_KEYS) {
      const node = files[apiKey];
      if (!node) continue;
      // shape: files[apiKey][res][format] -> {url,size,md5}; jpg is the delivery format we name for
      const resKey = node[res] ? res : node["1k"] ? "1k" : node["2k"] ? "2k" : node["4k"] ? "4k" : null;
      if (!resKey) continue;
      const fmt = node[resKey];
      const picked = fmt && (fmt.jpg || fmt.png || fmt.exr);
      if (!picked || !picked.url) continue;
      picks.push({ token, url: picked.url, res: resKey, size: picked.size || 0 });
    }
    if (!picks.length) { log.push(`NOPICK ${id}`); continue; }

    let got = 0, fail = 0;
    for (const p of picks) {
      const ext = path.extname(new URL(p.url).pathname) || ".jpg";
      const dest = path.join(OUT, `${id}_${p.token}_${p.res}${ext}`);
      if (already(dest)) { got++; continue; }
      try {
        const buf = await fetchBuf(p.url);
        fs.writeFileSync(dest, buf);
        got++;
        log.push(`OK   ${path.basename(dest)} ${buf.length}`);
      } catch (e) { fail++; log.push(`DLFAIL ${id}/${p.token} ${e.message}`); }
    }
    if (got) {
      groupDone = { key: want.key, role: want.role, id, maps: picks.map((p) => `${id}_${p.token}_${p.res}`), got, fail };
      break; // this id worked for the group
    }
    log.push(`RETRY-ALT ${id} produced nothing, trying next candidate`);
  }
  if (groupDone) record.push(groupDone);
  else log.push(`GROUPFAIL ${want.key}`);
}

// Enrich the record with author/license info from resolved.json
const byId = Object.fromEntries(resolved.textures.map((t) => [t.id, t]));
for (const r of record) {
  const meta = byId[r.id] || {};
  r.name = meta.name || r.id;
  r.authors = meta.authors || [];
  r.categories = meta.categories || [];
  r.license = "CC0 (PolyHaven)";
}

fs.writeFileSync(path.join(SCRATCH, "tex_downloaded.json"), JSON.stringify(record, null, 1));
console.log(log.join("\n"));
console.log(`\ngroups=${groups.length} done=${record.length}`);
