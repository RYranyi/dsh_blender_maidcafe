// Quick probe: PolyHaven asset search + file listing via Node fetch
const q = process.argv[2] || "wood";
const url = `https://api.polyhaven.com/assets?t=textures&c=wood`;
const r = await fetch(url);
console.log("STATUS", r.status);
const j = await r.json();
const ids = Object.keys(j);
console.log("COUNT", ids.length);
console.log(ids.slice(0, 40).join("\n"));
