"""
cbuild.py — 总装配：调用各模块 → 存 .blend → 导出 GLB → 生成 scene_manifest.json

用法
----
    blender -b -P cbuild.py                      # 全量构建 + 导出 + 出 4 时段预览
    MAID_CAFE_MODE=build blender -b -P cbuild.py # 只构建不渲染
    MAID_CAFE_RENDER=1 ...                        # 构建后出 12 张光影图

模块
----
croom  C_Room     建筑壳
cbar   C_Bar      L 台设备
cdisplay C_Display 展示柜（furn-modeler）
cseating C_Seating 桌椅（furn-modeler）
cdecor C_Decor    装饰（decor-modeler）
coutdoor C_Outdoor 室外（decor-modeler）
cmaid  C_Maid     女仆（lead）
clight C_Light    灯光（lead，不导出 GLB）
"""
import bpy
import os
import sys
import json
import time
import importlib

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ccore as C
import cprop as P
import cmat as MAT
import cassets as A
import croom
import cbar
try:
    import cdisplay
except Exception as e:
    cdisplay = None
    print("[CBUILD] cdisplay unavailable:", e)
try:
    import cseating
except Exception as e:
    cseating = None
    print("[CBUILD] cseating unavailable:", e)
try:
    import cdecor
except Exception as e:
    cdecor = None
    print("[CBUILD] cdecor unavailable:", e)
try:
    import coutdoor
except Exception as e:
    coutdoor = None
    print("[CBUILD] coutdoor unavailable:", e)
import cmaid
import clight

EXPORT_COLS = ["C_Room", "C_Bar", "C_Display", "C_Seating", "C_Decor",
               "C_Outdoor", "C_Maid"]
OUT_BLEND = os.path.join(P.SCENE_DIR, "maid_cafe.blend")
OUT_GLB = os.path.join(P.SCENE_DIR, "maid_cafe.glb")
OUT_MAN = os.path.join(P.SCENE_DIR, "scene_manifest.json")


# ══════════════════════════════════════════════════════════════════════
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.render.fps = 30
    # 移除默认集合并建工作集合
    for cn in P.COLS:
        C.ensure_collection(cn)
    return sc


def _call(mod, name, *args, **kw):
    """安全调用模块 build；失败不中断整个构建，记录错误。"""
    if mod is None:
        return {"error": "module missing", "objects": [], "colliders": [],
                "collections": [], "tris": 0, "module": name}
    fn = getattr(mod, "build", None)
    if fn is None:
        return {"error": "no build()", "objects": [], "colliders": [],
                "collections": [], "tris": 0, "module": name}
    t0 = time.time()
    try:
        res = fn(*args, **kw)
        res["module"] = name
        res["ms"] = int((time.time() - t0) * 1000)
        return res
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": repr(e), "objects": [], "colliders": [],
                "collections": [], "tris": 0, "module": name}


def build_all(render_preview=False):
    reset_scene()
    M = MAT.palette()
    assets = {"tex": P.tex_path, "model": P.model_dir, "import": A.import_model}
    results = {}
    order = [
        ("croom", croom, "C_Room"),
        ("cbar", cbar, "C_Bar"),
        ("cdisplay", cdisplay, "C_Display"),
        ("cseating", cseating, "C_Seating"),
        ("cdecor", cdecor, "C_Decor"),
        ("coutdoor", coutdoor, "C_Outdoor"),
        ("cmaid", cmaid, "C_Maid"),
    ]
    for name, mod, col in order:
        C.log("=== build %s ===" % name)
        results[name] = _call(mod, name, P, C, M, assets)

    C.log("=== lights ===")
    lres = _call(clight, "clight", P, C, M, assets)
    results["clight"] = lres

    # 外部模型材质统一
    try:
        harmonize_materials(M)
    except Exception:
        import traceback
        traceback.print_exc()

    # 越过墙面的陈设整体收进室内
    try:
        fit_inside_room()
    except Exception:
        import traceback
        traceback.print_exc()

    # 关键：让 matrix_world 刷新，否则 colliders / AABB 会是零变换的错值
    bpy.context.view_layer.update()

    # 统计
    stats = C.stats(P.COLS)
    total = 0
    for cn, s in stats.items():
        total += s["tris"]
        C.log("STAT %-12s %6d tris  %4d objs" % (cn, s["tris"], s["objects"]))
    C.log("TOTAL %d tris" % total)

    manifest = compose_manifest(results, stats, total)
    with open(OUT_MAN, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    C.log("manifest ->", OUT_MAN, os.path.getsize(OUT_MAN), "bytes")

    # 构建失败保护：任一模块报错 → 存为 partial，不覆盖主文件
    errors = manifest.get("errors") or {}
    if errors:
        partial = OUT_BLEND.replace(".blend", ".partial.blend")
        C.log("WARN build has module errors:", list(errors.keys()), "-> saving", partial)
        C.save_blend(partial)
    else:
        C.save_blend(OUT_BLEND)
    return results, manifest, stats, total


# ══════════════════════════════════════════════════════════════════════
# 材质统一（外部 PolyHaven 模型的材质按前缀替换成项目统一材质）
# ══════════════════════════════════════════════════════════════════════
RETINT = {
    # PolyHaven 材质名前缀 → 目标项目材质名
    "painted_wooden_chair_01": "MAT_Chair_Paint",
    "painted_wooden_chair_02": "MAT_Chair_Paint",
    "round_wooden_table_01": "MAT_Table_Wood",
    "wooden_bookshelf_worn": "MAT_Wood_Dark",
    "steel_frame_shelves_01": "MAT_Wood_Shelf",
    "hanging_picture_frame": "MAT_Wood_Dark",
    "fancy_picture_frame": "MAT_Wood_Dark",
    "standing_chalkboard_01": "MAT_Wood_Dark",
    # 两款 PolyHaven 蛋糕：自带 mask 贴图在 WEBP 导出时会失败 → 换简化材质
    "carrot_cake": "MAT_Cake_Carrot",
    "strawberry_chocolate_cake": "MAT_Cake_Strawberry",
}


def harmonize_materials(mats):
    """把外部模型材质替换为项目统一材质，保证色调一致。"""
    n = 0
    cache = {}
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        me = ob.data
        for i, m in enumerate(list(me.materials)):
            if not m:
                continue
            base = m.name.split(".")[0]
            for pref, target in RETINT.items():
                if base.startswith(pref):
                    tm = cache.get(target)
                    if tm is None:
                        tm = mats.get(_key_of(target)) or bpy.data.materials.get(target)
                        cache[target] = tm
                    if tm is not None:
                        me.materials[i] = tm
                        n += 1
                    break
    C.log("harmonize: %d material slots retinted" % n)
    return n


def _key_of(matname):
    """MAT_Chair_Paint → chair_paint（palette 字典键）。"""
    s = matname
    if s.startswith("MAT_"):
        s = s[4:]
    return s.lower()


# ══════════════════════════════════════════════════════════════════════
# 收进房间：把越出墙面的陈设整体平移回室内（按名称前缀分组，避免拆散椅子/桌布）
# ══════════════════════════════════════════════════════════════════════
def _group_key(name):
    """把同一件家具的零件归到一组，保证 fit_inside_room 整组平移、不拆散桌布/坐垫。

    注意：`TB_01_Cloth` 必须归到 `TB_01`（不是 `TB_01_Cloth`），否则桌布与桌子会被
    分别施加不同位移而滑离桌面（decor-modeler 报过这个潜在 bug）。
    """
    parts = name.split("_")
    if name.startswith("CH_Stool"):
        return "_".join(parts[:3])      # 每张吧凳独立
    if name.startswith("TB_"):
        return "_".join(parts[:2])      # TB_01 + TB_01_Cloth/Menu/Sugar/Vase 同组
    if name.startswith("CH_"):
        return "_".join(parts[:3])      # CH_01_1
    if name.startswith(("DS_", "DC_", "OD_")):
        return "_".join(parts[:2])
    return name


def fit_inside_room(pad=0.01):
    x0, x1 = P.ROOM_X
    y0, y1 = P.ROOM_Y
    groups = {}
    for cn in ("C_Bar", "C_Display", "C_Seating", "C_Decor"):
        col = bpy.data.collections.get(cn)
        if not col:
            continue
        for ob in col.all_objects:
            if ob.type != "MESH":
                continue
            groups.setdefault(_group_key(ob.name), []).append(ob)
    moved = []
    for key, obs in groups.items():
        mn, mx = C.world_aabb(obs)
        if mn[0] > 1e8:
            continue
        dx = dy = 0.0
        if mn[0] < x0 + pad:
            dx = (x0 + pad) - mn[0]
        elif mx[0] > x1 - pad:
            dx = (x1 - pad) - mx[0]
        if mn[1] < y0 + pad:
            dy = (y0 + pad) - mn[1]
        elif mx[1] > y1 - pad:
            dy = (y1 - pad) - mx[1]
        # 只处理轻微越界（<=0.25m），大范围越界说明是设计问题，交给 QC 报
        if (abs(dx) > 1e-4 and abs(dx) <= 0.25) or (abs(dy) > 1e-4 and abs(dy) <= 0.25):
            for ob in obs:
                ob.location.x += dx
                ob.location.y += dy
            moved.append({"group": key, "dx": round(dx, 4), "dy": round(dy, 4),
                          "n": len(obs)})
    if moved:
        C.log("fit_inside_room: moved %d groups" % len(moved))
        for m in moved[:12]:
            C.log("   ", m)
    return moved


# ══════════════════════════════════════════════════════════════════════
def compose_manifest(results, stats, total):
    colliders = []
    anchors = {}
    notes = {}
    errors = {}
    for name, r in results.items():
        if r.get("error"):
            errors[name] = r["error"]
        for c in r.get("colliders", []) or []:
            colliders.append(c)
        for k, v in (r.get("anchors", {}) or {}).items():
            anchors[k] = v
        if r.get("notes"):
            notes[name] = r["notes"]
    rig = results.get("clight", {}).get("rig") or clight.manifest_rig()
    # 补充网页需要的锚点（若模块未提供，用 cprop 兜底）
    anchors.setdefault("cam_default", {"pos": [1.85, -2.55, 1.55],
                                       "target": [-1.20, 0.50, 1.05]})
    anchors.setdefault("maid_pos", [P.MAID_POS[0], P.MAID_POS[1], 0.0])
    anchors.setdefault("maid_rot_z_deg", P.MAID_ROT_Z)
    anchors.setdefault("tray_top_z", P.TRAY_Z)
    anchors.setdefault("tables", [{"name": t["name"], "x": t["x"], "y": t["y"]}
                                 for t in P.TABLES])
    anchors.setdefault("window", {"x": list(P.WIN_X), "z": list(P.WIN_Z)})
    anchors.setdefault("door", {"x": list(P.DOOR_X), "z": list(P.DOOR_Z)})
    anchors.setdefault("bar", {"main": P.BAR_MAIN, "top_z": P.BAR_TOP_Z})
    anchors.setdefault("display", P.DISPLAY)
    anchors.setdefault("street", {"sidewalk_y": list(P.SIDEWALK["y"]),
                                  "road_y": list(P.ROAD["y"]),
                                  "bldg_y": list(P.BLDG_FAR["y"])})
    mat_names = sorted([m.name for m in bpy.data.materials if m.users > 0])
    return {
        "version": "1.0.0",
        "generated_by": "cbuild.py",
        "room": {"x": list(P.ROOM_X), "y": list(P.ROOM_Y),
                 "z": [0.0, P.CEIL_Z], "wall_t": P.WALL_T,
                 "wainscot_z": P.WAINSCOT_Z},
        "anchors": anchors,
        "colliders": colliders,
        "light_rig": rig,
        "fx_nodes": {
            "window_glass_material": "MAT_Glass_Clear",
            "steam_node": "MD_Steam_0",
            "steam_nodes": ["MD_Steam_0", "MD_Steam_1", "MD_Steam_2"],
            "lamp_materials": ["MAT_Emissive_Shade", "MAT_Emissive_Bulb", "MAT_Emissive_LED"],
            "emissive_materials": ["MAT_Emissive_Shade", "MAT_Emissive_Bulb", "MAT_Emissive_LED"],
            "window_lit_material": "MAT_Window_Lit",
            "puddle_material": "MAT_Puddle",
            "rain_surface_y": P.SIDEWALK["y"][0],
        },
        "material_names": mat_names,
        "counts": {"tris": total,
                   "objects": sum(s["objects"] for s in stats.values()),
                   "per_collection": stats},
        "modules": {k: {"tris": v.get("tris", 0), "ms": v.get("ms"),
                        "error": v.get("error")}
                    for k, v in results.items()},
        "notes": notes,
        "errors": errors,
    }


# ══════════════════════════════════════════════════════════════════════
def validate_glb(path):
    """解析 GLB 的 JSON 头，检查 texture/image/material 引用完整性。

    返回 issue 列表（空 = 合规）。典型问题：WEBP 转换失败的图片会留下
    `textures[i] = {"extensions":{},"sampler":0}` 这种没有 source 的空槽，
    浏览器 GLTFLoader 会整包 throw。
    """
    import struct
    issues = []
    try:
        with open(path, "rb") as f:
            magic, ver, length = struct.unpack("<III", f.read(12))
            if magic != 0x46546C67:
                return ["bad magic (not GLB)"]
            jlen, jtype = struct.unpack("<II", f.read(8))
            js = json.loads(f.read(jlen).decode("utf-8"))
    except Exception as e:
        return ["parse failed: %r" % (e,)]
    imgs = js.get("images") or []
    for i, im in enumerate(imgs):
        if "bufferView" not in im and "uri" not in im:
            issues.append("images[%d] has neither bufferView nor uri" % i)
    texs = js.get("textures") or []
    for i, tx in enumerate(texs):
        src = tx.get("source")
        if src is None:
            ext = (tx.get("extensions") or {})
            for k, v in ext.items():
                if isinstance(v, dict) and v.get("source") is not None:
                    src = v["source"]
                    break
        if src is None:
            issues.append("textures[%d] has no source (%s)" % (i, json.dumps(tx)[:80]))
        elif isinstance(src, int) and src >= len(imgs):
            issues.append("textures[%d].source=%d out of range (images=%d)"
                          % (i, src, len(imgs)))
    mats = js.get("materials") or []
    for mi, m in enumerate(mats):
        pbr = m.get("pbrMetallicRoughness") or {}
        for key in ("baseColorTexture", "metallicRoughnessTexture"):
            ref = pbr.get(key)
            if isinstance(ref, dict):
                ti = ref.get("index")
                if isinstance(ti, int) and ti >= len(texs):
                    issues.append("materials[%s].%s.index=%d out of range"
                                  % (m.get("name"), key, ti))
        for key in ("normalTexture", "occlusionTexture", "emissiveTexture"):
            ref = m.get(key)
            if isinstance(ref, dict):
                ti = ref.get("index")
                if isinstance(ti, int) and ti >= len(texs):
                    issues.append("materials[%s].%s.index=%d out of range"
                                  % (m.get("name"), key, ti))
    return issues


def _do_export(kwargs):
    import re as _re
    kw = dict(kwargs)
    for _attempt in range(8):
        try:
            bpy.ops.export_scene.gltf(**kw)
            return
        except TypeError as e:
            m = _re.search(r"""['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]""", str(e))
            if m and m.group(1) in kw:
                C.log("export: dropping unsupported kwarg", m.group(1))
                kw.pop(m.group(1))
                continue
            raise


def export_glb():
    """导出 GLB：只选导出集合、apply modifiers、内嵌贴图；带结构自检 + 回退。"""
    C.deselect_all()
    n = 0
    for cn in EXPORT_COLS:
        col = bpy.data.collections.get(cn)
        if not col:
            C.log("WARN export collection missing", cn)
            continue
        for ob in col.all_objects:
            if ob.type == "MESH":
                ob.select_set(True)
                n += 1
    if not n:
        C.log("ERROR nothing to export")
        return None
    C.log("export: %d mesh objects selected" % n)
    base = dict(
        filepath=OUT_GLB,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
        export_extras=True,
        export_keep_originals=False,
    )
    # 先试 WEBP（体积小 ~4x），失败/不合规回退 AUTO
    for fmt, quality in (("WEBP", 78), ("AUTO", None)):
        kw = dict(base)
        kw["export_image_format"] = fmt
        if quality:
            kw["export_image_quality"] = quality
        C.log("export attempt format=%s" % fmt)
        _do_export(kw)
        if not os.path.exists(OUT_GLB):
            C.log("ERROR GLB not written (%s)" % fmt)
            continue
        issues = validate_glb(OUT_GLB)
        if not issues:
            sz = os.path.getsize(OUT_GLB)
            C.log("GLB OK (%s) -> %s  %d bytes  %.2f MB" % (fmt, OUT_GLB, sz, sz / 1048576.0))
            C.deselect_all()
            return OUT_GLB
        C.log("GLB validation FAILED (%s): %d issues" % (fmt, len(issues)))
        for s in issues[:8]:
            C.log("   ", s)
    C.log("ERROR: all export formats produced invalid GLB")
    C.deselect_all()
    return OUT_GLB if os.path.exists(OUT_GLB) else None


# ══════════════════════════════════════════════════════════════════════
def render_light_matrix(outdir=None, res=(1280, 720), samples=32):
    """4 时段 × 3 天气 光影图（晴/多云/雨）。"""
    outdir = outdir or os.path.join(P.RENDERS, "light")
    os.makedirs(outdir, exist_ok=True)
    lights = clight.build_lights()
    sc = bpy.context.scene
    C.setup_engine("eevee", samples, res)
    cam = C.render_camera("QC_LightCam", (1.85, -2.55, 1.62), (-1.20, 0.50, 1.05), lens=24)
    sc.camera = cam
    paths = []
    combos = [("morning", "clear"), ("noon", "clear"), ("dusk", "clear"),
              ("night", "clear"), ("noon", "cloudy"), ("night", "rain_med")]
    for phase, weather in combos:
        clight.apply_phase(lights, phase, weather)
        p = os.path.join(outdir, f"{phase}_{weather}.png")
        sc.render.filepath = p
        try:
            bpy.ops.render.render(write_still=True)
            paths.append(p)
            C.log("light render", p)
        except Exception as e:
            C.log("render fail", p, e)
    return paths


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    mode = os.environ.get("MAID_CAFE_MODE", "all").lower()
    do_render = os.environ.get("MAID_CAFE_RENDER", "0") == "1"
    force = os.environ.get("MAID_CAFE_FORCE", "0") == "1"
    t0 = time.time()
    results, manifest, stats, total = build_all()
    C.log("build done in %.1fs" % (time.time() - t0))
    errors = manifest.get("errors") or {}
    if mode in ("all", "export"):
        if errors and not force:
            C.log("SKIP GLB export: module errors", list(errors.keys()),
                  "(set MAID_CAFE_FORCE=1 to override)")
        else:
            export_glb()
    if do_render:
        render_light_matrix(res=(1280, 720), samples=24)
    # 汇总
    summary = {
        "tris": total,
        "per_collection": stats,
        "errors": manifest.get("errors", {}),
        "modules": manifest.get("modules", {}),
        "blend": OUT_BLEND,
        "glb": OUT_GLB if os.path.exists(OUT_GLB) else None,
        "glb_mb": round(os.path.getsize(OUT_GLB) / 1048576.0, 2) if os.path.exists(OUT_GLB) else None,
        "manifest": OUT_MAN,
        "seconds": round(time.time() - t0, 1),
    }
    print("CBUILD_SUMMARY " + json.dumps(summary, ensure_ascii=False))
