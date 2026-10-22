// PolyHaven HDRI downloader (1k .hdr).
// usage: node ph_dl_hdri.mjs [--res 1k] [--only sky_night,sky_sunset]
// Reads .scratch/asset-scout/resolved.json -> assets/hdri/<id>_<res>.hdr
// Idempotent (skip > 1KB), failover to the next wishlist id. Records
// .scratch/asset-scout/hdris_downloaded.json
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const OUT = path.join(ROOT, "assets/hdri");
const SCRATCH = path.join(ROOT, ".scratch/asset-scout");
fs.mkdirSync(OUT, { recursive: true });

const args = process.argv.slice(2);
const RES = args.includes("--res") ? args[args.indexOf("--res") + 1] : "1k";
const onlyArg = args.includes("--only") ? args[args.indexOf("--only") + 1] : null;
const only = onlyArg ? new Set(onlyArg.split(",")) : null;

const resolved = JSON.parse(fs.readFileSync(path.join(SCRATCH, "resolved.json"), "utf8"));
const wish = JSON.parse(fs.readFileSync(path.join(ROOT, "tools/ph_wishlist.json"), "utf8")).hdris;
const groups = wish.filter((g) => !only || only.has(g.key));

const log = [];
const record = [];
const already = (p) => fs.existsSync(p) && fs.statSync(p).size > 1024;

async function fetchBuf(url, tries = 3) {
  let last = "";
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url);
      if (!r.ok) { last = `HTTP ${r.status}`; if (r.status === 403 || r.status === 404) break; }
      else return Buffer.from(await r.arrayBuffer());
    } catch (e) { last = e.message; }
    await new Promise((res) => setTimeout(res, 500 * (i + 1)));
  }
  throw new Error(last || "unknown");
}

for (const grp of groups) {
  let done = null;
  for (const id of grp.ids) {
    let files;
    try {
      const r = await fetch(`https://api.polyhaven.com/files/${id}`);
      if (!r.ok) { log.push(`FILESFAIL ${id} ${r.status}`); continue; }
      files = await r.json();
    } catch (e) { log.push(`FILESERR ${id} ${e.message}`); continue; }

    const root = files.hdri;
    if (!root) { log.push(`NOHDRI ${id}`); continue; }
    const resKey = root[RES] ? RES : root["1k"] ? "1k" : root["2k"] ? "2k" : root["4k"] ? "4k" : Object.keys(root)[0];
    const pick = root[resKey] && (root[resKey].hdr || root[resKey].exr);
    if (!pick || !pick.url) { log.push(`NOPICK ${id} ${RES}`); continue; }

    const dest = path.join(OUT, `${id}_${resKey}.hdr`);
    if (!already(dest)) {
      try {
        const buf = await fetchBuf(pick.url);
        fs.writeFileSync(dest, buf);
        log.push(`OK   ${path.basename(dest)} ${(buf.length / 1048576).toFixed(2)}MB`);
      } catch (e) { log.push(`DLFAIL ${id} ${e.message}`); continue; }
    } else log.push(`SKIP ${path.basename(dest)}`);

    done = {
      key: grp.key, role: grp.role, id, res: resKey,
      file: path.relative(ROOT, dest).replace(/\\/g, "/"),
      bytes: fs.statSync(dest).size,
      license: "CC0 (PolyHaven)",
    };
    break;
  }
  if (done) record.push(done);
  else log.push(`GROUPFAIL ${grp.key}`);
}

const byId = Object.fromEntries(resolved.hdris.map((h) => [h.id, h]));
for (const r of record) {
  const m = byId[r.id] || {};
  r.name = m.name || r.id;
  r.authors = m.authors || [];
  r.categories = m.categories || [];
  r.sourceUrl = `https://polyhaven.com/a/${r.id}`;
}

const recPath = path.join(SCRATCH, "hdris_downloaded.json");
const prev = fs.existsSync(recPath) ? JSON.parse(fs.readFileSync(recPath, "utf8")) : [];
const byKey = Object.fromEntries(prev.map((p) => [p.key, p]));
for (const r of record) byKey[r.key] = r;
fs.writeFileSync(recPath, JSON.stringify(Object.values(byKey), null, 1));

console.log(log.join("\n"));
console.log(`\ngroups=${groups.length} done=${record.length}`);
