// Probe audio source reachability + inspect PolyHaven model file tree + asset metadata
const audio = [
  "https://opengameart.org/sites/default/files/audio_preview/rain.mp3",
  "https://incompetech.com/music/royalty-free/mp3-royaltyfree/",
  "https://archive.org/advancedsearch.php?q=jazz&fl%5B%5D=identifier&rows=1&output=json",
  "https://freepd.com/",
  "https://cdn.pixabay.com/audio/2022/03/15/audio_c8c8a73467.mp3",
  "https://opengameart.org/sites/default/files/",
  "https://files.freemusicarchive.org/",
  "https://www.soundjay.com/",
  "https://freesound.org/data/previews/",
];
for (const u of audio) {
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 12000);
    const r = await fetch(u, { signal: ctl.signal, headers: { "User-Agent": "Mozilla/5.0" }, method: "GET" });
    clearTimeout(t);
    console.log(`${r.status} ${u} ct=${r.headers.get("content-type")} len=${r.headers.get("content-length")}`);
  } catch (e) { console.log(`ERR ${u} :: ${e.message}`); }
}
// model file tree
const r = await fetch("https://api.polyhaven.com/files/WoodenTable_01");
const j = await r.json();
console.log("MODEL_TREE", JSON.stringify(j, null, 1).slice(0, 2500));
// asset metadata incl polycount
const a = await (await fetch("https://api.polyhaven.com/info/WoodenTable_01")).json();
console.log("INFO", JSON.stringify(a).slice(0, 1200));
