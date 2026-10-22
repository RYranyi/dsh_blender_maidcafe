"""
clight.py — C_Light：4 时段 × 6 天气 的 Blender 灯光装置（供 QC 渲染 & 场景清单）

网页端的灯光由 Three.js 按 scene_manifest.json 的 light_rig 重建；
这里的 Blender 灯用于：
  1. 出 4×3 光影质检图（EEVEE）
  2. 生成 .blend 工程里的可视参考（导出 GLB 时不导出灯）

灯组
----
SUN      方向日光（随时段改角度/色温/强度）
SKY      世界环境（HDRI 或纯色，随天气改）
INDOOR   室内灯：3 吊灯 + 3 吧台射灯 + 2 展示柜射灯 + 3 壁灯 + 灯带，
         强度随 indoor 系数变化（清晨微亮 → 夜晚全亮）
FILL     女仆补光（柔和面光，跟随她位置）
"""
import bpy
import math
import os
import sys
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
                else os.path.dirname(os.path.abspath(__file__)))
import ccore as C
import cprop as P
import cmat as MAT

MODULE = "clight"
OWNER = "lead"
TRI_BUDGET = 0
COL = "C_Light"
D2R = C.D2R


# 时段 → HDRI（asset-scout 下载的 PolyHaven CC0 1k .hdr）
HDRI_BY_PHASE = {
    "morning": "kiara_2_sunrise_1k.hdr",
    "noon": "kloppenheim_06_puresky_1k.hdr",
    "dusk": "evening_road_01_puresky_1k.hdr",
    "night": "dikhololo_night_1k.hdr",
}
HDRI_STRENGTH = {"morning": 0.62, "noon": 0.70, "dusk": 0.26, "night": 0.07}
# 环境光染色：黄昏/夜晚把 HDRI 往暖色压，避免夜空蓝把整幅画面拉冷
HDRI_TINT = {
    "morning": ("#EAF2FF", 0.25),
    "noon": ("#FFFFFF", 0.0),
    "dusk": ("#FFC98A", 1.0),
    "night": ("#FFB066", 1.0),
}


def _load_hdri_world():
    """给世界加 Environment Texture（天空盒），返回 image 节点。"""
    w = bpy.context.scene.world
    if w is None:
        w = bpy.data.worlds.new("MaidCafeWorld")
        bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    if bg is None:
        bg = nt.nodes.new("ShaderNodeBackground")
        out = nt.nodes.get("World Output") or nt.nodes.new("ShaderNodeOutputWorld")
        nt.links.new(bg.outputs[0], out.inputs[0])
    env = nt.nodes.get("HDRI_Env")
    if env is None:
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.name = "HDRI_Env"
        env.location = (-420, 260)
    # 环境染色节点：Mix(Multiply) 把 HDRI 往暖色压
    tint = nt.nodes.get("HDRI_Tint")
    if tint is None:
        tint = nt.nodes.new("ShaderNodeMix")
        tint.name = "HDRI_Tint"
        tint.data_type = "RGBA"
        tint.blend_type = "MULTIPLY"
        tint.location = (-160, 260)
        nt.links.new(env.outputs["Color"], tint.inputs[6])   # A
        nt.links.new(tint.outputs[2], bg.inputs[0])          # Result -> Background
    if not bg.inputs[0].is_linked:
        nt.links.new(env.outputs["Color"], bg.inputs[0])
    return w, bg, env


def set_hdri_phase(phase, weather="clear"):
    """按时段切换天空 HDRI；找不到图则退回纯色天空。"""
    w, bg, env = _load_hdri_world()
    fname = HDRI_BY_PHASE.get(phase)
    img = None
    if fname:
        p = os.path.join(P.HDRI, fname)
        if os.path.exists(p):
            img = bpy.data.images.get(fname)
            if img is None:
                try:
                    img = bpy.data.images.load(p, check_existing=True)
                except Exception as e:
                    C.log("HDRI load fail", p, e)
            if img is not None:
                env.image = img
                try:
                    env.projection = "EQUIRECTANGULAR"
                except Exception:
                    pass
    strg = HDRI_STRENGTH.get(phase, 0.8)
    wrig = P.WEATHER_RIG.get(weather, {})
    if img is None:
        # 退回纯色
        for l in list(bg.inputs[0].links):
            w.node_tree.links.remove(l)
        rig = P.LIGHT_RIG.get(phase, {})
        bg.inputs[0].default_value = (*C.hexc(rig.get("sky", "#CFE8FF"))[:3], 1.0)
        strg = rig.get("ambient", 0.7)
    elif img is not None:
        # 环境染色（HDRI * 暖色）
        tint = w.node_tree.nodes.get("HDRI_Tint")
        if tint is not None:
            col_hex, fac = HDRI_TINT.get(phase, ("#FFFFFF", 0.0))
            try:
                tint.inputs[0].default_value = fac
                tint.inputs[7].default_value = C.hexc(col_hex)   # B
            except Exception:
                pass
    bg.inputs[1].default_value = strg * wrig.get("ambient_mult", 1.0)
    return img is not None


def _sun(name="LT_Sun"):
    ld = bpy.data.lights.new(name, "SUN")
    ld.angle = 0.6 * D2R        # 太阳角直径（略软）
    ob = bpy.data.objects.new(name, ld)
    C.ensure_collection(COL).objects.link(ob)
    ob.location = (0, 0, 8)
    return ob


def _point(name, loc, color, power=40.0, radius=0.08, shadow=True):
    ld = bpy.data.lights.new(name, "POINT")
    ld.energy = power
    ld.color = color[:3]
    ld.shadow_soft_size = radius
    ld.use_shadow = shadow
    ob = bpy.data.objects.new(name, ld)
    ob.location = Vector(loc)
    C.ensure_collection(COL).objects.link(ob)
    return ob


def _area(name, loc, look_at, color, power=60.0, size=0.4, shape="DISK"):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.color = color[:3]
    ld.shape = shape
    ld.size = size
    ob = bpy.data.objects.new(name, ld)
    ob.location = Vector(loc)
    d = Vector(look_at) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    C.ensure_collection(COL).objects.link(ob)
    return ob


def _spot(name, loc, look_at, color, power=120.0, angle=38.0, blend=0.35, radius=0.05):
    ld = bpy.data.lights.new(name, "SPOT")
    ld.energy = power
    ld.color = color[:3]
    ld.spot_size = angle * D2R
    ld.spot_blend = blend
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    ob.location = Vector(loc)
    d = Vector(look_at) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    C.ensure_collection(COL).objects.link(ob)
    return ob


# ══════════════════════════════════════════════════════════════════════
def build_lights():
    """建整套灯（只建一次；幂等）。返回分类 dict。"""
    C.wipe_collection(COL)
    C.ensure_collection(COL)
    lights = {"sun": None, "sky": [], "indoor": [], "fill": []}

    # 太阳
    sun = _sun()
    lights["sun"] = sun

    warm = C.hexc(P.C_LAMP_WARM)
    warmer = C.hexc(P.C_LAMP_WARMER)
    cool = C.hexc("#BFD8F2")

    # ── 室内：吊灯（每盏一个 point，位于灯罩内）──────────────
    for p in P.PENDANTS:
        ob = _point(f"LT_Pendant_{p['name']}", (p["x"], p["y"], p["shade_z"] - 0.02),
                    warm, power=150.0, radius=p["r"] * 0.9)
        lights["indoor"].append({"ob": ob, "role": "pendant", "base": 150.0})

    # ── 吧台射灯（spot，朝下打台面）────────────────────────
    for i, s in enumerate(P.BAR_SPOTS):
        ob = _spot(f"LT_BarSpot_{i}", (s["x"], s["y"], s["z"]), (s["x"], 1.50, 0.95),
                   warm, power=175.0, angle=34.0, blend=0.45)
        lights["indoor"].append({"ob": ob, "role": "bar_spot", "base": 175.0})

    # ── 展示柜射灯（2 个，打在柜面上）──────────────────────
    for i, dx in enumerate((-0.35, 0.35)):
        base = P.DISPLAY_SPOT
        loc = (base["x"] + dx * 1.2, base["y"], base["z"])
        ob = _spot(f"LT_DisplaySpot_{i}", loc, (P.DISPLAY["x"][0] + 1.0 + dx, 1.55, 0.80),
                   warm, power=85.0, angle=30.0, blend=0.5)
        lights["indoor"].append({"ob": ob, "role": "display_spot", "base": 85.0})

    # ── 壁灯（3 盏，贴墙暖光）──────────────────────────────
    for i, w in enumerate(P.WALL_LAMPS):
        if w["wall"] == "-X":
            loc = (w["x"] + 0.06, w["y"], w["z"])
        elif w["wall"] == "+X":
            loc = (w["x"] - 0.06, w["y"], w["z"])
        else:
            loc = (w["x"], w["y"] - 0.06, w["z"])
        ob = _point(f"LT_WallLamp_{i}", loc, warmer, power=45.0, radius=0.06)
        lights["indoor"].append({"ob": ob, "role": "wall_lamp", "base": 45.0})

    # ── 天花灯带（4 条 AREA，贴吊顶跌级内侧）───────────────
    rec = 0.55
    zc = P.CEIL_RECESS_Z + 0.06
    w = P.ROOM_X[1] - P.ROOM_X[0]
    d = P.ROOM_Y[1] - P.ROOM_Y[0]
    coves = [
        ("S", (0, P.ROOM_Y[0] + rec + 0.03, zc), (0, 0, 0)),
        ("N", (0, P.ROOM_Y[1] - rec - 0.03, zc), (0, 0, 0)),
    ]
    for tag, loc, _ in coves:
        ld = bpy.data.lights.new(f"LT_Cove_{tag}", "AREA")
        ld.shape = "RECTANGLE"
        ld.size = w - rec * 2
        ld.size_y = 0.06
        ld.energy = 90.0
        ld.color = C.hexc(P.C_LAMP_WARM)[:3]
        ob = bpy.data.objects.new(f"LT_Cove_{tag}", ld)
        ob.location = Vector(loc)
        # 长边沿 X、发光面朝室内（+Z 或 -Z 由旋转决定）：用 rotation_euler 让 -Z 指向房间
        ob.rotation_euler = (0.0, 0.0, 0.0)
        C.ensure_collection(COL).objects.link(ob)
        lights["indoor"].append({"ob": ob, "role": "cove", "base": 90.0})
    for tag in ("W", "E"):
        side = -1 if tag == "W" else 1
        ld = bpy.data.lights.new(f"LT_Cove_{tag}", "AREA")
        ld.shape = "RECTANGLE"
        ld.size = d - rec * 2
        ld.size_y = 0.06
        ld.energy = 90.0
        ld.color = C.hexc(P.C_LAMP_WARM)[:3]
        ob = bpy.data.objects.new(f"LT_Cove_{tag}", ld)
        ob.location = Vector((side * (P.ROOM_X[1] - rec - 0.03), 0, zc))
        # 长边沿 Y：绕 Z 转 90°
        ob.rotation_euler = (0.0, 0.0, math.pi / 2)
        C.ensure_collection(COL).objects.link(ob)
        lights["indoor"].append({"ob": ob, "role": "cove", "base": 90.0})

    # ── 女仆补光（跟随位置的面光）──────────────────────────
    mp = P.MAID_POS
    fill = _area("LT_MaidFill", (mp[0] + 0.75, mp[1] - 1.05, 1.62),
                 (mp[0], mp[1], 1.05), C.hexc("#FFF0DE"), power=42.0, size=0.9)
    lights["fill"].append({"ob": fill, "role": "maid_fill", "base": 42.0})

    # ── 天花板反弹光（向上打，让吊顶不发灰）────────────────
    bounce = _area("LT_Bounce", (0, 0, 1.35), (0, 0, 3.0),
                   C.hexc("#FFE8C8"), power=260.0, size=3.0, shape="RECTANGLE")
    lights["fill"].append({"ob": bounce, "role": "ceiling_bounce", "base": 260.0})

    # ── 世界环境（天空）────────────────────────────────────
    w = bpy.data.worlds.get("MaidCafeWorld") or bpy.data.worlds.new("MaidCafeWorld")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg is None:
        bg = w.node_tree.nodes.new("ShaderNodeBackground")
        out = w.node_tree.nodes.get("World Output") or w.node_tree.nodes.new("ShaderNodeOutputWorld")
        w.node_tree.links.new(bg.outputs[0], out.inputs[0])
    bg.inputs[0].default_value = (*C.hexc("#CFE8FF")[:3], 1.0)
    bg.inputs[1].default_value = 0.75
    lights["world"] = w
    lights["bg"] = bg

    # ── 窗外天光面光（模拟天空漫射从窗射入，让室内有方向感）──────
    wx0, wx1 = P.WIN_X
    sky_area = _area("LT_WindowSky", ((wx0 + wx1) / 2, P.ROOM_Y[0] - 0.45, 1.70),
                     ((wx0 + wx1) / 2, 1.4, 1.15),
                     C.hexc("#DCEBFF"), power=260.0, size=2.6, shape="RECTANGLE")
    lights["sky"].append({"ob": sky_area, "role": "window_sky", "base": 260.0})

    # ── 玻璃不投影（否则日光进不来）──────────────────────────────
    no_shadow = []
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        mats = [m.name for m in ob.data.materials if m]
        if any(n.startswith("MAT_Glass") for n in mats):
            try:
                ob.visible_shadow = False
                no_shadow.append(ob.name)
            except Exception:
                pass
    lights["no_shadow"] = no_shadow

    C.log("lights: sun 1, indoor %d, sky %d, glass-no-shadow %d"
          % (len(lights["indoor"]), len(lights["sky"]), len(no_shadow)))
    return lights


# ══════════════════════════════════════════════════════════════════════
def apply_phase(lights, phase="noon", weather="clear"):
    """按 CONTRACT §LIGHT_RIG 配置灯光。"""
    rig = P.LIGHT_RIG.get(phase)
    wrig = P.WEATHER_RIG.get(weather)
    if not rig or not wrig:
        C.log("WARN unknown phase/weather", phase, weather)
        return
    # 太阳：方向（欧拉角）+ 强度 + 颜色
    sun = lights["sun"]
    sun.rotation_euler = tuple(a * D2R for a in rig["sun_rot"])
    sun.data.energy = rig["sun_energy"] * wrig["sun_mult"]
    sun.data.color = C.hexc(rig["sun_color"])[:3]
    # 天空：优先 HDRI（天空盒），退化到纯色
    set_hdri_phase(phase, weather)

    # ══════════════════════════════════════════════════════════════
    # 室内灯开关逻辑（用户要求）
    #   「只有黄昏到凌晨才开灯，以及多云和下雨天开灯」
    #   → 白天（清晨/正午）晴天/多云=关；黄昏/夜晚=开；
    #     任何时段只要天气是 多云/雨/雷阵雨，也开（阴天室内暗）
    #   开灯时亮度也按「白天不该过曝」原则压低。
    # ══════════════════════════════════════════════════════════════
    # 时段是否属于「需要开灯」的区间：黄昏(17:00起) → 凌晨(6:00前)
    LAMP_PHASES = ("dusk", "night")
    # 这些天气室内偏暗，白天也开灯
    DARK_WEATHERS = ("cloudy", "rain_light", "rain_med", "rain_heavy", "storm")

    need_lamps = (phase in LAMP_PHASES) or (weather in DARK_WEATHERS)

    if need_lamps:
        # 开灯：黄昏/夜晚用完整亮度；白天(阴雨)只开到 45%，避免压掉天光
        if phase in LAMP_PHASES:
            indoor_scale = rig["indoor"]        # 黄昏/夜晚：正常（1.0 / 0.85 等）
            lamp_boost = 1.0
        else:
            indoor_scale = rig["indoor"] * 0.45  # 白天阴雨：只要一点暖光补足
            lamp_boost = 1.0
    else:
        # 关灯：白天晴天 → 室内灯全部归零
        indoor_scale = 0.0
        lamp_boost = 0.0

    for ent in lights["indoor"]:
        ob = ent["ob"]
        ob.data.energy = ent["base"] * indoor_scale
        # 关灯时同时隐藏发光灯泡的面（避免"灯灭了但灯泡还是亮的"）
        try:
            ob.hide_render = (indoor_scale <= 1e-6)
        except Exception:
            pass

    # 灯罩/灯泡等 emissive 网格同步开关（DC_*Bulb*, DS_*SpotBulb*, MAT_Emissive_Bulb）
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        nm = ob.name
        if not any(k in nm for k in ("_Bulb", "Bulb_", "SpotBulb", "Candle_Flame",
                                     "Incense_Tip", "StringLights_Bulb")):
            continue
        try:
            ob.hide_render = (lamp_boost <= 1e-6 and not nm.startswith(("OD_", "RM_")))
        except Exception:
            pass

    for ent in lights["fill"]:
        if ent["role"] == "ceiling_bounce":
            ent["ob"].data.energy = ent["base"] * (0.22 + 0.55 * indoor_scale)
        else:
            ent["ob"].data.energy = ent["base"] * (0.30 + 0.45 * indoor_scale)
    # 窗外天光：白天强、夜晚很弱
    for ent in lights["sky"]:
        day = {"morning": 1.0, "noon": 1.35, "dusk": 0.55, "night": 0.0}.get(phase, 1.0)
        ent["ob"].data.energy = ent["base"] * day * wrig["sun_mult"] ** 0.5
        col = C.hexc(rig["sky"])
        ent["ob"].data.color = col[:3]
    # 对面建筑亮窗：只有黄昏/夜晚才亮
    show_lit = phase in ("dusk", "night")
    for ob in bpy.data.objects:
        if ob.name.startswith(("OD_WindowLit", "OD_LitWindow", "OD_WinLit")):
            try:
                ob.hide_render = not show_lit
            except Exception:
                pass
    # 曝光 / 色彩管理
    try:
        vs = bpy.context.scene.view_settings
        if vs.view_transform == "Standard":
            vs.view_transform = "AgX"
        try:
            vs.look = "AgX - Medium High Contrast"
        except Exception:
            pass
        vs.exposure = rig["exposure"]
    except Exception:
        pass
    scene = bpy.context.scene
    try:
        if wrig["fog"] > 0.001:
            scene.world.mist_settings.use_mist = True
            scene.world.mist_settings.start = 1.0
            scene.world.mist_settings.depth = 6.0 / max(0.005, wrig["fog"])
        else:
            scene.world.mist_settings.use_mist = False
    except Exception:
        pass


def manifest_rig(lights=None):
    """给 scene_manifest.json 用的灯光参数（网页端照此重建）。"""
    no_shadow = (lights or {}).get("no_shadow", [])
    lit_windows = [o.name for o in bpy.data.objects
                   if o.name.startswith(("OD_WindowLit", "OD_LitWindow", "OD_WinLit"))]
    return {"phases": P.LIGHT_RIG, "weather": P.WEATHER_RIG,
            "anchors": {
                "sun_target": [0, 0, 1.2],
                "pendants": [{"pos": [p["x"], p["y"], p["shade_z"]], "r": p["r"]}
                             for p in P.PENDANTS],
                "bar_spots": [[s["x"], s["y"], s["z"]] for s in P.BAR_SPOTS],
                "display_spots": [[P.DISPLAY_SPOT["x"] - 0.35, P.DISPLAY_SPOT["y"],
                                   P.DISPLAY_SPOT["z"]],
                                  [P.DISPLAY_SPOT["x"] + 0.35, P.DISPLAY_SPOT["y"],
                                   P.DISPLAY_SPOT["z"]]],
                "wall_lamps": [[w.get("x", 0), w.get("y", 0), w["z"]] for w in P.WALL_LAMPS],
                "maid_fill": [P.MAID_POS[0] + 0.75, P.MAID_POS[1] - 1.05, 1.62],
                "window_sky": [(P.WIN_X[0] + P.WIN_X[1]) / 2, P.ROOM_Y[0] - 0.45, 1.70],
                "window_sky_target": [(P.WIN_X[0] + P.WIN_X[1]) / 2, 1.4, 1.15],
                "indoor_base": {"pendant": 55.0, "bar_spot": 90.0,
                                "display_spot": 55.0, "wall_lamp": 18.0,
                                "cove": 45.0, "maid_fill": 42.0,
                                "window_sky": 260.0},
                "indoor_scale": {"morning": 0.45, "noon": 0.25, "dusk": 0.95, "night": 1.25},
                "window_sky_day": {"morning": 1.0, "noon": 1.35, "dusk": 0.75, "night": 0.10},
            },
            "no_shadow_objects": no_shadow,
            "lit_window_objects": lit_windows,
            "hdri": {"by_phase": HDRI_BY_PHASE, "strength": HDRI_STRENGTH,
                     "base_url": "assets/hdri/"},
            "window": {"x": list(P.WIN_X), "z": list(P.WIN_Z)},
            "room": {"x": list(P.ROOM_X), "y": list(P.ROOM_Y), "z": [0, P.CEIL_Z]},
            }


def add_render_volume(density=0.0035):
    """给 Blender QC 渲染加体积雾，让日光出现光柱（不导出 GLB）。
    密度要很低，否则整个画面发灰发白。"""
    C.wipe_collection("C_QC")
    C.ensure_collection("C_QC")
    w, d, h = 8.0, 6.0, 3.0
    ob = C.box("QC_Volume", (w, d, h), loc=(0, 0, h / 2), col="C_QC")
    m = bpy.data.materials.new("QC_VolMat")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type not in ("OUTPUT_MATERIAL",):
            pass
    pv = nt.nodes.new("ShaderNodeVolumePrincipled")
    pv.inputs["Density"].default_value = density
    pv.inputs["Color"].default_value = (1.0, 0.96, 0.90, 1.0)
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(pv.outputs["Volume"], out.inputs["Volume"])
    ob.data.materials.append(m)
    sc = bpy.context.scene
    try:
        sc.eevee.use_volumetric_shadows = True
        sc.eevee.volumetric_tile_size = "8"
        sc.eevee.volumetric_samples = 48
        sc.eevee.volumetric_start = 0.5
        sc.eevee.volumetric_end = 18.0
    except Exception:
        pass
    return ob


# ══════════════════════════════════════════════════════════════════════
def build(P_, C_, M_, assets):
    lights = build_lights()
    apply_phase(lights, "noon", "clear")
    return {"objects": [o for o in C.ensure_collection(COL).objects if o.type == "LIGHT"],
            "collections": [COL], "colliders": [], "lights": lights,
            "rig": manifest_rig(lights), "tris": 0,
            "notes": "sun + %d indoor + %d sky + maid fill" % (
                len(lights["indoor"]), len(lights["sky"]))}


if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    M = MAT.palette()
    a = build(P, C, M, {})
    C.log("lights built", len(a["objects"]))
