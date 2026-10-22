// Model/HDRI downloader for PolyHaven: walks file tree, picks gltf(1k/2k) for models, hdr for HDRIs
import fs from "node:fs";
import path from "node:path";

const [,, kind, outdir, ...ids] = process.argv; // kind: model | hdri
fs.mkdirSync(outdir, { recursive: true });

function collect(node, pathStr, acc) {
  if (!node || typeof node !== "object") return;
  if (node.url) { acc.push({ path: pathStr, url: node.url, size: node.size || 0 }); return; }
  for (const [k, v] of Object.entries(node)) collect(v, pathStr ? pathStr + "/" + k : k, acc);
}

for (const id of ids) {
  const r = await fetch(`https://api.polyhaven.com/files/${id}`);
  if (!r.ok) { console.log(`FAIL ${id} ${r.status}`); continue; }
  const j = await r.json();
  const acc = [];
  collect(j, "", acc);
  let picks;
  if (kind === "model") {
    const gl = acc.filter(a => /gltf/i.test(a.path) && /gltf|glb/i.test(a.url));
    // prefer 1k, then 2k
    picks = gl.filter(a => /\/1k\//.test(a.url)).length ? gl.filter(a => /\/1k\//.test(a.url))
      : gl.filter(a => /\/2k\//.test(a.url)).length ? gl.filter(a => /\/2k\//.test(a.url)) : gl;
  } else {
    const h = acc.filter(a => /\.hdr$/i.test(a.url));
    picks = h.filter(a => /\/1k\//.test(a.url));
    if (!picks.length) picks = h.filter(a => /\/2k\//.test(a.url));
    if (!picks.length) picks = h;
  }
  if (!picks.length) { console.log(`NOPICK ${id} :: ${acc.map(a => a.path).slice(0, 10).join(" | ")}`); continue; }
  for (const p of picks.slice(0, 6)) {
    const base = path.basename(new URL(p.url).pathname);
    const dest = path.join(outdir, base);
    if (fs.existsSync(dest) && fs.statSync(dest).size > 1000) { console.log(`SKIP ${base}`); continue; }
    const rr = await fetch(p.url);
    if (!rr.ok) { console.log(`DLFAIL ${base} ${rr.status}`); continue; }
    fs.writeFileSync(dest, Buffer.from(await rr.arrayBuffer()));
    console.log(`OK ${base} ${fs.statSync(dest).size}`);
  }
}
