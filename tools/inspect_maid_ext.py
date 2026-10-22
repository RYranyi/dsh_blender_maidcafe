import json
import struct

P = r"E:\dsh\maid_cafe\scene\maid_cafe.glb"
with open(P, "rb") as f:
    magic, ver, length = struct.unpack("<III", f.read(12))
    jlen, jtype = struct.unpack("<II", f.read(8))
    js = json.loads(f.read(jlen).decode("utf-8"))

want = ["M_Hair", "M_Skin", "M_White", "M_Satin", "M_Iris", "M_Navy", "M_Sclera"]
for m in js.get("materials", []):
    if m.get("name") in want:
        print("==", m["name"])
        print(json.dumps({k: v for k, v in m.items() if k != "name"}, ensure_ascii=False, indent=1))
