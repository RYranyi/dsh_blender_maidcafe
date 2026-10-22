// PolyHaven model downloader (1k .blend + its packed textures).
// usage: node ph_dl_model.mjs [--only table_a,chair_a] [--res 1k]
// Reads .scratch/asset-scout/resolved.json. Writes
//   assets/models/<id>/<id>_<res>.blend
//   assets/models/<id>/textures/<name>.{jpg,exr,png}
// Idempotent (skip > 1KB). Failover to the next wishlist id when a model 404s.
// Records .scratch/asset-scout/models_downloaded.json
import fs from "node:fs";
import path from "node:path";

const ROOT = "E:/dsh/maid_cafe";
const MODELS = path.join(ROOT, "assets/models");
const SCRATCH = path.join(ROOT, ".scratch/asset-scout");
fs.mkdirSync(MODELS, { recursive: true });
fs.mkdirSync(SCRATCH, { recursive: true });

const args = process.argv.slice(2);
const onlyArg = args.includes("--only") ? args[args.indexOf("--only") + 1] : null;
const only = onlyArg ? new Set(onlyArg.split(",")) : null;
const RES = args.includes("--res") ? args[args.indexOf("--res") + 1] : "1k";
const withTextures = !args.includes("--no-textures");

const resolved = JSON.parse(fs.readFileSync(path.join(SCRATCH, "resolved.json"), "utf8"));
const wish = JSON.parse(fs.readFileSync(path.join(ROOT, "tools/ph_wishlist.json"), "utf8"));
const groups = wish.models.filter((g) => !only || only.has(g.key));

const log = [];
const record = [];

function already(p) { return fs.existsSync(p) && fs.statSync(p).size > 1024; }

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

    const blendNode = files.blend && files.blend[RES] && files.blend[RES].blend;
    if (!blendNode || !blendNode.url) { log.push(`NOBLEND ${id} ${RES}`); continue; }

    const dir = path.join(MODELS, id);
    const texDir = path.join(dir, "textures");
    fs.mkdirSync(texDir, { recursive: true });

    const blendDest = path.join(dir, `${id}_${RES}.blend`);
    let okBlend = already(blendDest);
    if (!okBlend) {
      try {
        const buf = await fetchBuf(blendNode.url);
        fs.writeFileSync(blendDest, buf);
        log.push(`OK   ${id}/${path.basename(blendDest)} ${buf.length}`);
        okBlend = true;
      } catch (e) { log.push(`DLFAIL ${id} blend ${e.message}`); }
    } else log.push(`SKIP ${id}/${path.basename(blendDest)}`);

    let texOk = 0, texFail = 0;
    if (withTextures && blendNode.include) {
      for (const [rel, ent] of Object.entries(blendNode.include)) {
        if (!ent || !ent.url) continue;
        const name = path.basename(rel);
        const dest = path.join(texDir, name);
        if (already(dest)) { texOk++; continue; }
        try {
          const buf = await fetchBuf(ent.url);
          fs.writeFileSync(dest, buf);
          texOk++;
        } catch (e) { texFail++; log.push(`TEXFAIL ${id}/${name} ${e.message}`); }
      }
    }

    if (okBlend) {
      done = {
        key: grp.key, role: grp.role, id, res: RES,
        blend: path.relative(ROOT, blendDest).replace(/\\/g, "/"),
        blendBytes: fs.statSync(blendDest).size,
        textures: texOk, textureFailures: texFail,
        texDir: path.relative(ROOT, texDir).replace(/\\/g, "/"),
      };
      log.push(`GROUP ${grp.key} -> ${id}  tex=${texOk} fail=${texFail}`);
      break;
    }
    log.push(`RETRY-ALT ${id} blend failed`);
  }
  if (done) record.push(done);
  else log.push(`GROUPFAIL ${grp.key}`);
}

const byId = Object.fromEntries(resolved.models.map((m) => [m.id, m]));
for (const r of record) {
  const m = byId[r.id] || {};
  r.name = m.name || r.id;
  r.authors = m.authors || [];
  r.categories = m.categories || [];
  r.downloads = m.downloads || 0;
  r.license = "CC0 (PolyHaven)";
  r.sourceUrl = `https://polyhaven.com/a/${r.id}`;
}

// merge with any earlier run so partial runs accumulate
const recPath = path.join(SCRATCH, "models_downloaded.json");
const prev = fs.existsSync(recPath) ? JSON.parse(fs.readFileSync(recPath, "utf8")) : [];
const byKey = Object.fromEntries(prev.map((p) => [p.key, p]));
for (const r of record) byKey[r.key] = r;
fs.writeFileSync(recPath, JSON.stringify(Object.values(byKey), null, 1));

console.log(log.join("\n"));
console.log(`\ngroups=${groups.length} done=${record.length}`);
