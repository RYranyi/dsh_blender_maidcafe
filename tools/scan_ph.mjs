// Scan PolyHaven (all textures) and ambientCG for keywords, write a candidate report.
import fs from "node:fs";
const out = {};
const r = await fetch("https://api.polyhaven.com/assets?t=textures");
const all = await r.json();
const names = Object.keys(all);
out.polyhaven_total = names.length;
const cats = {};
for (const [id, v] of Object.entries(all)) {
  const c = (v.categories || []).join("/");
  cats[c] = (cats[c] || 0) + 1;
}
out.polyhaven_categories = cats;
const kws = ["marble", "granite", "stone", "metal", "steel", "brass", "copper", "glass", "ceramic", "tile", "plaster", "stucco", "paint", "fabric", "linen", "lace", "leather", "wood", "parquet", "concrete", "asphalt", "paving", "brick", "roof", "grass", "paper"];
out.matches = {};
for (const k of kws) out.matches[k] = names.filter(n => n.includes(k));
// HDRI list
const h = await (await fetch("https://api.polyhaven.com/assets?t=hdris")).json();
out.hdri = Object.keys(h).filter(n => /sky|sun|city|street|studio|outdoor|kloppenheim|autumn|night|interior|room|park/i.test(n)).slice(0, 120);
// models: furniture category
const m = await (await fetch("https://api.polyhaven.com/assets?t=models")).json();
out.models = Object.keys(m);
fs.writeFileSync(new URL("./scan_polyhaven.json", import.meta.url), JSON.stringify(out, null, 1));
console.log("total textures", out.polyhaven_total, "models", out.models.length, "hdris-sample", out.hdri.length);
for (const k of ["marble", "metal", "glass", "ceramic", "lace", "leather"]) console.log(k, "->", out.matches[k].slice(0, 25).join(", "));
console.log("MODELS:", out.models.join(", "));
console.log("HDRI:", out.hdri.join(", "));
