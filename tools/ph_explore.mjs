// PolyHaven asset explorer: list ids per category, filter by keyword
const cats = ["wood", "marble", "fabric", "concrete", "tiles", "bricks", "ground", "plaster", "paving"];
const kw = (process.argv[2] || "").toLowerCase();
for (const c of cats) {
  try {
    const r = await fetch(`https://api.polyhaven.com/assets?t=textures&c=${c}`);
    if (!r.ok) { console.log(`# ${c} HTTP ${r.status}`); continue; }
    const j = await r.json();
    const ids = Object.keys(j).filter(id => !kw || id.includes(kw));
    console.log(`# ${c} (${Object.keys(j).length}) -> ${ids.join(", ")}`);
  } catch (e) { console.log(`# ${c} FAIL ${e.message}`); }
}
