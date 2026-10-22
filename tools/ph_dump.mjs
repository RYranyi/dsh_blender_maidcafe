// Dump the top-level structure of a PolyHaven files entry
const id = process.argv[2];
const r = await fetch(`https://api.polyhaven.com/files/${id}`);
const j = await r.json();
console.log(JSON.stringify(j, null, 1).slice(0, 4000));
