"""
cassets.py — 外部资产解析与导入（PolyHaven CC0 模型/贴图/HDRI）

用法
----
    import cassets as A
    A.model_ids()                        # 已下载模型 id 列表
    objs = A.import_model("WoodenTable_01", col="C_Seating",
                          target_height=0.74, face="-Y")
    A.place(objs, (x, y), rot_z_deg=30)

约定：PolyHaven 模型为真实米制、Z-up。导入后原点归到底面中心，可选按
target_height / target_size 缩放，然后再绕 Z 转向 face。
"""
import os
import glob
import bpy
from mathutils import Vector, Matrix, Euler
import ccore as C
import cprop as P

D2R = C.D2R


def model_ids():
    if not os.path.isdir(P.MODELS):
        return []
    out = []
    for d in sorted(os.listdir(P.MODELS)):
        p = os.path.join(P.MODELS, d)
        if os.path.isdir(p) and glob.glob(os.path.join(p, "*.blend")):
            out.append(d)
    return out


def model_blend(pid):
    d = os.path.join(P.MODELS, pid)
    if not os.path.isdir(d):
        return None
    cands = sorted(glob.glob(os.path.join(d, "*.blend")))
    if not cands:
        return None
    for c in cands:
        if "_1k" in os.path.basename(c):
            return c
    return cands[0]


def _alive(ob):
    try:
        return ob is not None and ob.name in bpy.data.objects
    except Exception:
        return False


def _load_objects(path):
    """从 .blend append 所有对象到当前场景，返回**新链接进场景**的网格对象列表。"""
    before = set(bpy.data.objects.keys())
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
    col = bpy.context.scene.collection
    got = []
    for ob in dst.objects:
        if ob is None:
            continue
        try:
            if ob.name not in col.objects:
                col.objects.link(ob)
            got.append(ob)
        except Exception as e:
            C.log("link failed", getattr(ob, "name", "?"), e)
    C.log("loaded", len(got), "objects from", os.path.basename(path))
    return got


def _purge_nonmesh(objs):
    for ob in list(objs):
        if not _alive(ob):
            continue
        if ob.type != "MESH":
            try:
                bpy.data.objects.remove(ob, do_unlink=True)
            except Exception:
                pass


def import_model(pid, col="C_Helper", target_height=None, target_size=None,
                 face="-Y", name_prefix=None, uv_scale=None, join=True):
    """导入 PolyHaven 模型 → 归一化（原点=底面中心）→ 缩放 → 转向。返回对象列表。"""
    path = model_blend(pid)
    if not path:
        C.log("WARN model missing", pid)
        return []
    loaded = _load_objects(path)
    meshes = [o for o in loaded if _alive(o) and o.type == "MESH"]
    if not meshes:
        C.log("WARN model has no mesh", pid)
        _purge_nonmesh(loaded)
        return []
    _purge_nonmesh(loaded)
    C.ensure_collection(col)
    C.deselect_all()
    for o in meshes:
        try:
            C.link_to(o, col)
        except Exception:
            pass
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    # 清父级 + 烘变换
    try:
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    except Exception:
        pass
    try:
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    except Exception:
        pass
    C.deselect_all()
    # 合并
    ob = None
    if join and len(meshes) > 1:
        ob = C.join(meshes, (name_prefix or pid) + "_M", col)
    elif meshes:
        ob = meshes[0]
    if ob is None:
        return []
    ob.name = name_prefix or pid
    ob.data.name = ob.name + "_mesh"
    # 包围盒归一
    mn, mx = C.world_aabb(ob)
    size = [mx[i] - mn[i] for i in range(3)]
    ctr = [(mn[i] + mx[i]) / 2 for i in range(3)]
    C.set_origin(ob, (ctr[0], ctr[1], mn[2]))
    s = 1.0
    if target_height and size[2] > 1e-6:
        s = target_height / size[2]
    elif target_size:
        cand = [target_size[i] / size[i] for i in range(3) if size[i] > 1e-6 and target_size[i]]
        s = min(cand) if cand else 1.0
    if abs(s - 1.0) > 1e-6:
        C.scale_about(ob, s, pivot=(0, 0, 0))
        mn2, _ = C.world_aabb(ob)
        ob.location.z -= mn2[2]
    if face == "+Y":
        ob.rotation_euler = (0, 0, 180 * D2R)
    elif face == "+X":
        ob.rotation_euler = (0, 0, 90 * D2R)
    elif face == "-X":
        ob.rotation_euler = (0, 0, -90 * D2R)
    if uv_scale:
        C.uv_world(ob, uv_scale)
    C.log("imported", pid, "tris", C.tri_count(ob), "scale", round(s, 4))
    return [ob]


def place(objs, xy, rot_z_deg=None, z=0.0, lift=0.0):
    for ob in objs:
        if not _alive(ob):
            continue
        ob.location.x = xy[0]
        ob.location.y = xy[1]
        ob.location.z = z + lift
        if rot_z_deg is not None:
            ob.rotation_euler = (0, 0, rot_z_deg * D2R)
    return objs


def tri_of(objs):
    return C.tri_count([o for o in objs if _alive(o)])


def report(objs):
    out = []
    for ob in objs:
        if not _alive(ob):
            continue
        mn, mx = C.world_aabb(ob)
        out.append({"name": ob.name, "tris": C.tri_count(ob), "aabb": [mn, mx]})
    return out


# ══════════════════════════════════════════════════════════════════════
# 贴图/HDRI 定位
# ══════════════════════════════════════════════════════════════════════
def tex(key, map_="diff", res=None):
    return P.tex_path(key, map_, res)


def hdri_list():
    if not os.path.isdir(P.HDRI):
        return []
    return sorted([f for f in os.listdir(P.HDRI) if f.lower().endswith((".hdr", ".exr"))])
