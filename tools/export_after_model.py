"""
export_after_model.py —— 从当前 blend 重新导出 GLB + manifest

（替代 export_only.py：无头包装会改写 __file__，所以这里用「向上找 scene/maid_cafe.blend」
  的方式定位项目根，最稳。）
"""
import bpy
import sys
import os
import json
import re
import struct

# ── 定位项目根：从 cwd 和 __file__ 逐级向上找 scene/maid_cafe.blend ──
CANDIDATES = []
for start in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
    p = start
    for _ in range(6):
        CANDIDATES.append(p)
        p = os.path.dirname(p)
ROOT = None
for c in CANDIDATES:
    if os.path.isfile(os.path.join(c, "scene", "maid_cafe.blend")):
        ROOT = c
        break
if ROOT is None:
    raise RuntimeError("找不到项目根（scene/maid_cafe.blend）")

sys.path.insert(0, os.path.join(ROOT, "blender"))
import ccore as C
import clight

BLEND = os.path.join(ROOT, "scene", "maid_cafe.blend")
GLB = os.path.join(ROOT, "scene", "maid_cafe.glb")
MANIFEST = os.path.join(ROOT, "scene", "scene_manifest.json")
print("[ROOT]", ROOT)

bpy.ops.wm.open_mainfile(filepath=BLEND)
bpy.context.view_layer.update()

COLS = ["C_Room", "C_Bar", "C_Display", "C_Seating",
        "C_Decor", "C_Outdoor", "C_Maid", "C_Helper"]

stats = {}
total_tris = 0
total_objs = 0
for cn in COLS:
    col = bpy.data.collections.get(cn)
    if not col:
        continue
    obs = [o for o in col.all_objects if o.type == "MESH"]
    t = C.tri_count(obs)
    stats[cn] = {"tris": t, "objects": len(obs)}
    total_tris += t
    total_objs += len(obs)

C.deselect_all()
n = 0
for cn in COLS:
    col = bpy.data.collections.get(cn)
    if not col:
        continue
    for ob in col.all_objects:
        if ob.type == "MESH":
            ob.select_set(True)
            n += 1
C.log("export objects:", n, "tris:", total_tris)


def validate(path):
    with open(path, "rb") as f:
        f.read(12)
        jlen, _ = struct.unpack("<II", f.read(8))
        js = json.loads(f.read(jlen).decode("utf-8"))
    issues = []
    imgs = js.get("images") or []
    for i, im in enumerate(imgs):
        if "bufferView" not in im and "uri" not in im:
            issues.append("img%d" % i)
    texs = js.get("textures") or []
    for i, tx in enumerate(texs):
        src = tx.get("source")
        if src is None:
            for v in (tx.get("extensions") or {}).values():
                if isinstance(v, dict) and v.get("source") is not None:
                    src = v["source"]
        if src is None or (isinstance(src, int) and src >= len(imgs)):
            issues.append("tex%d" % i)
    return issues, js


base = dict(filepath=GLB, export_format="GLB", use_selection=True,
            export_apply=True, export_yup=True, export_texcoords=True,
            export_normals=True, export_materials="EXPORT",
            export_cameras=False, export_lights=False, export_extras=True,
            export_keep_originals=False)

ok = False
for fmt, q in (("WEBP", 78), ("AUTO", None)):
    kw = dict(base)
    kw["export_image_format"] = fmt
    if q:
        kw["export_image_quality"] = q
    for _ in range(8):
        try:
            bpy.ops.export_scene.gltf(**kw)
            break
        except TypeError as e:
            m = re.search(r"""['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]""", str(e))
            if m and m.group(1) in kw:
                kw.pop(m.group(1))
                continue
            raise
    issues, js = validate(GLB)
    if not issues:
        C.log("GLB OK (%s) %.2f MB meshes=%d"
              % (fmt, os.path.getsize(GLB) / 1048576.0, len(js.get("meshes", []))))
        ok = True
        break
    C.log("GLB invalid:", issues[:4])
if not ok:
    raise RuntimeError("GLB 校验失败")

lights = clight.build_lights()
old = {}
if os.path.exists(MANIFEST):
    try:
        old = json.load(open(MANIFEST, encoding="utf-8"))
    except Exception:
        old = {}
man = dict(old)
man["version"] = "shelf-v2"
man["counts"] = {"tris": total_tris, "objects": total_objs, "per_collection": stats}
man["light_rig"] = clight.manifest_rig()
json.dump(man, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 书架装饰清单，供网页/文档引用
shelf = []
for o in bpy.data.objects:
    if o.type == "MESH" and (o.name or "").startswith("DC_Shf_"):
        mn, mx = C.world_aabb(o)
        shelf.append({"name": o.name, "tris": C.tri_count([o]),
                      "aabb": [[round(v, 4) for v in mn], [round(v, 4) for v in mx]]})
man["shelf_decor"] = shelf
json.dump(man, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("EXPORT_MODEL_DONE " + json.dumps({
    "tris": total_tris, "objects": total_objs,
    "glb_mb": round(os.path.getsize(GLB) / 1048576.0, 2),
    "shelf_decor": len(shelf), "stats": stats}, ensure_ascii=False))
