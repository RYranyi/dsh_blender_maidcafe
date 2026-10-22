import fs from "node:fs";

const buf = fs.readFileSync(new URL("../scene/maid_cafe.glb", import.meta.url));
const jsonLen = buf.readUInt32LE(12);
const j = JSON.parse(buf.slice(20, 20 + jsonLen).toString("utf8"));
// binary chunk header: 8 bytes (length, type) after JSON chunk
const binStart = 20 + jsonLen + 8;
const NCOMP = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 };
const CSIZE = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 };

function readAccessor(idx, maxItems = 8) {
  const acc = j.accessors[idx];
  const bv = j.bufferViews[acc.bufferView];
  const nc = NCOMP[acc.type];
  const cs = CSIZE[acc.componentType];
  const stride = bv.byteStride || nc * cs;
  const base = binStart + (bv.byteOffset || 0) + (acc.byteOffset || 0);
  const out = [];
  const n = Math.min(maxItems, acc.count);
  for (let i = 0; i < n; i++) {
    const row = [];
    for (let k = 0; k < nc; k++) {
      const off = base + i * stride + k * cs;
      let v;
      if (acc.componentType === 5126) v = buf.readFloatLE(off);
      else if (acc.componentType === 5123) v = buf.readUInt16LE(off) / 65535;
      else if (acc.componentType === 5121) v = buf.readUInt8(off) / 255;
      else v = buf.readUInt32LE(off);
      row.push(v);
    }
    out.push(row);
  }
  return { acc, rows: out };
}

const meshNames = ["Head", "Torso", "HairCap", "FringeMass", "Iris"];
for (const nm of meshNames) {
  const mi = j.meshes.findIndex((m) => m.name === nm);
  if (mi < 0) { console.log(nm, "not found"); continue; }
  for (const p of j.meshes[mi].primitives) {
    const matName = j.materials[p.material]?.name;
    if (p.attributes.COLOR_0 === undefined) { console.log(nm, "mat", matName, "no COLOR_0"); continue; }
    const { acc, rows } = readAccessor(p.attributes.COLOR_0, 5);
    console.log(nm, "mat", matName, "COLOR_0", acc.type, acc.componentType, "count", acc.count);
    for (const r of rows) console.log("   ", r.map((x) => x.toFixed(3)).join(", "));
  }
}
for (const nm of ["M_Skin", "M_Hair", "M_Iris", "M_White", "M_Navy", "M_Sclera"]) {
  const m = j.materials.find((x) => x.name === nm);
  if (!m) continue;
  console.log(nm, JSON.stringify({
    pbr: m.pbrMetallicRoughness,
    ext: m.extensions && Object.keys(m.extensions),
    ds: m.doubleSided,
    alphaMode: m.alphaMode,
  }).slice(0, 500));
}
console.log("extensionsUsed", j.extensionsUsed);
