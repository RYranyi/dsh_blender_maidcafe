// Resolve the asset-scout wishlist against the live PolyHaven API.
// usage: node ph_scout_manifest.mjs
// Writes <项目根>/.scratch/asset-scout/resolved.json
//   { textures:[{key,role,res,id,name,authors,categories,downloads,max_resolution}], models:[...], hdris:[...], missing:[...] }
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const SCRATCH = path.join(ROOT, ".scratch/asset-scout");
fs.mkdirSync(SCRATCH, { recursive: true });
const wish = JSON.parse(fs.readFileSync(path.join(ROOT, "tools/ph_wishlist.json"), "utf8"));

const TABLES = { textures: "textures", models: "models", hdris: "hdris" };
const meta = {};
for (const [k, t] of Object.entries(TABLES)) {
  const r = await fetch(`https://api.polyhaven.com/assets?t=${t}`);
  if (!r.ok) { console.log(`METAFAIL ${t} ${r.status}`); process.exit(1); }
  meta[k] = await r.json();
  console.log(`meta ${t}: ${Object.keys(meta[k]).length} assets`);
}

const out = { generated: new Date().toISOString(), textures: [], models: [], hdris: [], missing: [] };
for (const kind of ["textures", "models", "hdris"]) {
  for (const grp of wish[kind]) {
    const hit = (grp.ids || []).find((id) => meta[kind][id]);
    if (!hit) {
      out.missing.push({ kind, key: grp.key, tried: grp.ids });
      console.log(`MISS ${kind}/${grp.key} tried=${(grp.ids || []).join(",")}`);
      continue;
    }
    const m = meta[kind][hit] || {};
    const authorsArr = typeof m.authors === "object" && !Array.isArray(m.authors) ? Object.keys(m.authors) : (m.authors || []);
    out[kind].push({
      key: grp.key,
      role: grp.role || "",
      res: grp.res || "1k",
      id: hit,
      name: m.name || hit,
      authors: authorsArr,
      categories: m.categories || [],
      downloads: m.downloads || 0,
      max_resolution: m.max_resolution || null,
      // keep the full fallback list so the downloader can fail over on 403/404
      ids: grp.ids,
    });
    console.log(`OK   ${kind}/${grp.key} -> ${hit}  [${m.name}] by ${authorsArr.join("+")}`);
  }
}
fs.writeFileSync(path.join(SCRATCH, "resolved.json"), JSON.stringify(out, null, 1));
console.log(`\nresolved: textures=${out.textures.length} models=${out.models.length} hdris=${out.hdris.length} missing=${out.missing.length}`);
