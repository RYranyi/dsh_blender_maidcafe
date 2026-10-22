import json
import struct

P = r"E:\dsh\maid_cafe\scene\maid_cafe.glb"
with open(P, "rb") as f:
    f.read(12)
    jlen, jtype = struct.unpack("<II", f.read(8))
    js = json.loads(f.read(jlen).decode("utf-8"))

want = ["M_Hair", "M_Skin", "M_White", "M_Satin", "M_Navy", "M_Iris", "M_Sclera"]
print("%-10s %-8s %-8s %-10s %-9s %s" % ("material", "sheen", "aniso", "clearcoat", "spec", "rough"))
for m in js.get("materials", []):
    n = m.get("name")
    if n not in want:
        continue
    ext = m.get("extensions", {})
    sh = ext.get("KHR_materials_sheen", {})
    an = ext.get("KHR_materials_anisotropy", {})
    cc = ext.get("KHR_materials_clearcoat", {})
    sp = ext.get("KHR_materials_specular", {})
    rough = (m.get("pbrMetallicRoughness") or {}).get("roughnessFactor")
    print(
        "%-10s %-8s %-8s %-10s %-9s %s"
        % (
            n,
            json.dumps(sh.get("sheenColorFactor")) if sh else "-",
            an.get("anisotropyStrength", "-") if an else "-",
            cc.get("clearcoatFactor", "0(implicit)") if cc else "-",
            sp.get("specularFactor", "-") if sp else "-",
            round(rough, 3) if rough is not None else "-",
        )
    )
print("\nextensionsUsed:", [e for e in js.get("extensionsUsed", []) if "sheen" in e or "anisotropy" in e])
print("total materials:", len(js.get("materials", [])))
