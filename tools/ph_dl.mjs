// Download PolyHaven 1k JPG textures for a list of ids
// usage: node ph_dl.mjs <outdir> id1 id2 ...
// strategy: try files API, pick 1k jpg for diff/rough/nor_gl/arm(optional)
import fs from "node:fs";
import path from "node:path";

const [,, outdir, ...ids] = process.argv;
fs.mkdirSync(outdir, { recursive: true });

const MAPS = [
  ["Map", ["diff", "rough", "nor_gl", "arm", "disp", "ao"]],
];

for (const id of ids) {
  try {
    const r = await fetch(`https://api.polyhaven.com/files/${id}`);
    if (!r.ok) { console.log(`FAIL ${id} HTTP ${r.status}`); continue; }
    const j = await r.json();
    const got = [];
    for (const [key, val] of Object.entries(j)) {
      if (!key.startsWith("Diffuse") && !key.startsWith("Rough") && !key.startsWith("nor_gl") && !key.startsWith("arm") && !key.startsWith("Displacement") && !key.startsWith("AO")) {
        // some assets nest differently; we inspect below
      }
      const walk = (node, name) => {
        if (!node || typeof node !== "object") return;
        if (node["1k"]) {
          const v = node["1k"];
          if (v && v.url && v.url.endsWith(".jpg")) {
            const tag = name.toLowerCase()
              .replace("diffuse", "diff").replace("roughness", "rough")
              .replace("normal", "nor_gl").replace("arm", "arm")
              .replace("displacement", "disp").replace("ao", "ao");
            got.push([tag, v.url]);
          } else if (v && v.url) {
            // hdri or other
          }
        } else if (node.url && node.url.endsWith(".jpg")) {
          got.push([name.toLowerCase(), node.url]);
        }
        for (const [k, v] of Object.entries(node)) {
          if (typeof v === "object" && k !== "1k") walk(v, k);
        }
      };
      walk(val, key);
    }
    if (!got.length) console.log(`EMPTY ${id}`);
    for (const [tag, url] of got) {
      const ext = path.extname(new URL(url).pathname) || ".jpg";
      const dest = path.join(outdir, `${id}_${tag}_1k${ext}`);
      if (fs.existsSync(dest) && fs.statSync(dest).size > 1000) { console.log(`SKIP ${dest}`); continue; }
      const rr = await fetch(url);
      if (!rr.ok) { console.log(`DLFAIL ${url} ${rr.status}`); continue; }
      const buf = Buffer.from(await rr.arrayBuffer());
      fs.writeFileSync(dest, buf);
      console.log(`OK ${path.basename(dest)} ${buf.length}`);
    }
  } catch (e) {
    console.log(`ERR ${id} ${e.message}`);
  }
}
