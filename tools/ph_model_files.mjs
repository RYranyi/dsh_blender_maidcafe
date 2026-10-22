// Inspect PolyHaven files API for models + print gltf keys
const ids = process.argv.slice(2);
for (const id of ids) {
  const r = await fetch(`https://api.polyhaven.com/files/${id}`);
  if (!r.ok) { console.log(`FAIL ${id} ${r.status}`); continue; }
  const j = await r.json();
  const out = [];
  function walk(node, path) {
    if (!node || typeof node !== "object") return;
    if (node.url) { out.push(path + " -> " + node.url.split("?")[0].slice(-60) + " (" + (node.size || 0) + ")"); return; }
    for (const [k, v] of Object.entries(node)) walk(v, path + "/" + k);
  }
  walk(j, id);
  console.log(out.filter(s => /gltf|glb|blend|fbx|obj/i.test(s)).join("\n"));
  console.log("-----");
}
