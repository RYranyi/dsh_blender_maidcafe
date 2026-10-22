"""
render_lv_anim.py —— 3 分钟光影片 · 真 3D 动画渲染

30 段 × 6s × 24fps = 4,320 帧（1600×900 / EEVEE / 32-48 spp）

和上一版（静帧 + ffmpeg 数字推拉）的区别：
  · 相机是真的在 Blender 里走：推 / 拉 / 横移 / 环绕 / 升降 / 俯仰
  · 雨丝是真的在落（雨网格逐帧位移）
  · 雷阵雨有真的闪电（周期性提升曝光 + 灯罩发光）
  · 每帧都重新算光影 → 有视差、有运动

用法：
  ONLY_FROM=1 ONLY_TO=6 blender -b -P render_lv_anim.py
  （不传则跑全部 30 段）
"""
import bpy
import sys
import os
import math
import random
from mathutils import Vector

ROOT = None
for start in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
    p = start
    for _ in range(6):
        if os.path.isfile(os.path.join(p, "scene", "maid_cafe.blend")):
            ROOT = p
            break
        p = os.path.dirname(p)
    if ROOT:
        break
if ROOT is None:
    raise RuntimeError("找不到项目根")
sys.path.insert(0, os.path.join(ROOT, "blender"))
import ccore as C
import clight

BLEND = os.path.join(ROOT, "scene", "maid_cafe.blend")
OUT = os.path.join(ROOT, "renders", "lv_anim")
os.makedirs(OUT, exist_ok=True)

W, H = 1600, 900
FPS = 24
SEG_S = 6.0
NF = int(SEG_S * FPS)          # 每段 144 帧

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
lights = clight.build_lights()
bpy.context.view_layer.update()

cam = bpy.data.objects.get("LVA_Cam")
if cam is None:
    cd = bpy.data.cameras.new("LVA_Cam")
    cam = bpy.data.objects.new("LVA_Cam", cd)
    sc.collection.objects.link(cam)
cam.data.clip_start = 0.02
cam.data.clip_end = 400.0
sc.camera = cam

F = (W, H)


def smooth(t):
    return t * t * (3 - 2 * t)


def lerp3(a, b, t):
    return Vector((a[0] + (b[0] - a[0]) * t,
                   a[1] + (b[1] - a[1]) * t,
                   a[2] + (b[2] - a[2]) * t))


# ══════════════════════════════════════════════════════════════
# 30 段：每段有真实的相机起止位置 + 朝向 + 焦距变化
# (id, kind, phase, weather, rainlv, lens0, lens1, pos0, pos1, look0, look1)
# ══════════════════════════════════════════════════════════════
SHOTS = [
    # ── A 制作过程 ──
    ("01_wire", "wire", "noon", "clear", 0, 24, 20,
     (3.30, -2.70, 1.85), (1.60, -1.70, 1.55),
     (-1.60, 0.60, 1.05), (-1.30, 0.75, 1.00)),
    ("02_clay", "clay", "noon", "clear", 0, 20, 25,
     (1.40, -1.40, 1.62), (3.20, -2.50, 1.78),
     (-1.40, 0.70, 1.00), (-1.20, 0.60, 1.05)),
    ("03_clay_bar", "clay", "noon", "clear", 0, 30, 26,
     (-0.30, -0.90, 1.35), (1.90, -0.20, 1.45),
     (2.30, 1.70, 0.95), (2.20, 1.75, 1.00)),
    ("04_clay_disp", "clay", "noon", "clear", 0, 24, 32,
     (0.60, -1.60, 1.30), (-0.60, -0.55, 1.20),
     (-1.00, 0.85, 0.90), (-0.95, 0.85, 0.75)),
    ("05_clay_maid", "clay", "noon", "clear", 0, 30, 34,
     (-0.20, -2.20, 1.35), (-1.20, -1.85, 1.30),
     (-1.75, -0.20, 0.95), (-1.80, -0.15, 0.90)),
    ("06_final_wide", "final", "noon", "clear", 0, 26, 21,
     (1.20, -1.55, 1.62), (2.90, -2.45, 1.74),
     (-1.40, 0.70, 1.00), (-1.20, 0.55, 1.05)),

    # ── B 四个时段 ──
    ("07_morning_wide", "final", "morning", "clear", 0, 22, 24,
     (2.90, -2.45, 1.40), (2.95, -2.40, 2.05),
     (-1.30, 0.60, 1.00), (-1.20, 0.50, 1.35)),
    ("08_morning_win", "final", "morning", "clear", 0, 24, 20,
     (-0.10, -0.60, 1.70), (-1.30, -1.55, 1.60),
     (-2.60, -3.00, 1.55), (-2.70, -3.00, 1.45)),
    ("09_noon_wide", "final", "noon", "clear", 0, 23, 26,
     (2.10, -2.60, 1.66), (3.05, -1.90, 1.70),
     (-1.35, 0.55, 1.00), (-1.20, 0.80, 1.05)),
    ("10_noon_win", "final", "noon", "clear", 0, 26, 22,
     (0.60, -1.35, 1.85), (0.70, -1.20, 1.15),
     (-2.40, -3.00, 1.70), (-2.20, -2.95, 0.95)),
    ("11_dusk_wide", "final", "dusk", "clear", 0, 24, 22,
     (3.05, -1.60, 1.62), (2.30, -2.70, 1.72),
     (-1.20, 0.80, 1.05), (-1.40, 0.50, 1.00)),
    ("12_dusk_lamp", "final", "dusk", "clear", 0, 26, 24,
     (-0.40, -0.30, 1.35), (-0.90, -0.10, 2.05),
     (-2.20, 0.70, 2.05), (-2.00, 0.60, 2.00)),
    ("13_night_wide", "final", "night", "clear", 0, 22, 25,
     (0.30, -1.20, 1.60), (2.10, -2.30, 1.70),
     (2.30, 1.60, 1.00), (2.20, 1.60, 1.05)),
    ("14_night_detail", "final", "night", "clear", 0, 24, 32,
     (0.80, -1.40, 1.30), (-0.40, -0.60, 1.20),
     (-1.00, 0.85, 0.90), (-0.95, 0.85, 0.78)),

    # ── C 六种天气 ──
    ("15_clear_win", "final", "noon", "clear", 0, 24, 20,
     (1.60, -0.60, 1.62), (0.55, -1.30, 1.55),
     (-2.20, -3.00, 1.45), (-2.45, -3.00, 1.40)),
    ("16_clear_bar", "final", "noon", "clear", 0, 26, 30,
     (-0.20, -0.40, 1.32), (1.10, 0.30, 1.34),
     (2.20, 1.75, 0.95), (2.35, 1.70, 0.98)),
    ("17_cloudy_win", "final", "noon", "cloudy", 0, 20, 24,
     (0.30, -1.05, 1.55), (1.75, -0.60, 1.62),
     (-2.50, -3.00, 1.40), (-2.15, -3.00, 1.45)),
    ("18_cloudy_wide", "final", "noon", "cloudy", 0, 22, 24,
     (2.95, -2.40, 1.42), (2.90, -2.45, 2.00),
     (-1.30, 0.60, 1.00), (-1.20, 0.55, 1.30)),
    ("19_rainlight_win", "final", "noon", "rain_light", 1, 24, 20,
     (1.50, -0.70, 1.60), (0.60, -1.30, 1.55),
     (-2.20, -3.00, 1.45), (-2.45, -3.00, 1.40)),
    ("20_rainmed_win", "final", "noon", "rain_med", 2, 22, 24,
     (1.85, -0.45, 1.58), (0.70, -1.25, 1.56),
     (-2.10, -3.00, 1.42), (-2.40, -3.00, 1.42)),
    ("21_rainheavy_win", "final", "noon", "rain_heavy", 3, 24, 20,
     (1.00, -1.00, 1.50), (0.85, -1.10, 1.78),
     (-2.30, -3.00, 1.35), (-2.30, -3.00, 1.60)),
    ("22_storm_win", "final", "night", "storm", 3, 20, 24,
     (0.55, -1.30, 1.52), (1.55, -0.65, 1.60),
     (-2.45, -3.00, 1.38), (-2.15, -3.00, 1.45)),
    ("23_rain_wide", "final", "dusk", "rain_med", 2, 24, 22,
     (3.00, -1.70, 1.62), (2.25, -2.65, 1.70),
     (-1.20, 0.80, 1.05), (-1.40, 0.55, 1.00)),
    ("24_storm_wide", "final", "night", "storm", 3, 22, 25,
     (2.85, -2.35, 2.00), (2.85, -2.40, 1.40),
     (-1.25, 0.60, 1.25), (-1.30, 0.60, 0.95)),

    # ── D 收尾 ──
    ("25_top_stats", "final", "noon", "clear", 0, 24, 22,
     (0.10, 0.10, 7.60), (-0.10, 0.20, 6.90),
     (0.10, 0.10, 0.00), (-0.10, 0.20, 0.00)),
    ("26_shelf", "final", "dusk", "clear", 0, 26, 32,
     (-1.55, 0.55, 1.45), (-2.10, 1.25, 1.30),
     (-3.05, 2.90, 1.25), (-3.20, 2.90, 1.10)),
    ("27_maid_dusk", "final", "dusk", "clear", 0, 30, 34,
     (-0.30, -2.10, 1.38), (-1.05, -1.80, 1.30),
     (-1.72, -0.20, 0.95), (-1.80, -0.15, 0.90)),
    ("28_bar_noon", "final", "noon", "clear", 0, 30, 26,
     (1.90, 0.40, 1.40), (-0.20, -0.30, 1.36),
     (2.20, 1.72, 1.00), (2.30, 1.72, 0.96)),
    ("29_window_dusk", "final", "dusk", "clear", 0, 24, 20,
     (-0.25, -0.75, 1.68), (-1.35, -1.60, 1.60),
     (-2.60, -3.00, 1.50), (-2.70, -3.00, 1.45)),
    ("30_end_hero", "final", "dusk", "clear", 0, 24, 20,
     (1.40, -1.90, 1.62), (2.70, -2.50, 1.72),
     (-1.50, 0.85, 0.95), (-1.30, 0.70, 1.02)),
]

# ── 天花板（俯视用）──────────────────────────────────────────
CEIL = [o for o in bpy.data.objects
        if o.type == "MESH" and any(k in (o.name or "").lower()
                                    for k in ("ceil", "roof"))]

# ── 线框材质 ────────────────────────────────────────────────
WIRE_MAT = None


def get_wire_mat():
    global WIRE_MAT
    if WIRE_MAT is not None:
        return WIRE_MAT
    m = bpy.data.materials.new("LVA_Wire")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.92, 0.76, 1)
    wf = nt.nodes.new("ShaderNodeWireframe")
    wf.use_pixel_size = True
    wf.inputs["Size"].default_value = 1.0
    nt.links.new(wf.outputs["Fac"], em.inputs["Strength"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    WIRE_MAT = m
    return m


# ── 雨丝（两层，可逐帧下落）─────────────────────────────────
RAIN_OB = None


def build_rain(count, length, alpha, wind, bright):
    global RAIN_OB
    mat = bpy.data.materials.get("LVA_Rain")
    if mat is None:
        mat = bpy.data.materials.new("LVA_Rain")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (0.72, 0.80, 0.92, 1.0)
        em.inputs["Strength"].default_value = 1.4 * bright
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs["Fac"].default_value = alpha
        nt.links.new(em.outputs["Emission"], mix.inputs[1])
        nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        mat.blend_method = "BLEND"
        mat.use_backface_culling = False

    verts, faces = [], []
    random.seed(20261022)
    for layer in range(2):                     # 两层，补偿下落
        for _ in range(count):
            x = random.uniform(-7.5, 7.5)
            y = random.uniform(-9.0, -3.15)
            z = random.uniform(-0.5, 7.5) + layer * 8.0
            w = random.uniform(0.006, 0.013)
            h = length * random.uniform(0.7, 1.4)
            dx = wind * h
            i = len(verts)
            verts += [(x - w, y, z), (x + w, y, z),
                      (x + w + dx, y, z + h), (x - w + dx, y, z + h)]
            faces.append((i, i + 1, i + 2, i + 3))
    me = bpy.data.meshes.new("LVA_RainMesh")
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new("LVA_RainObj", me)
    ob.data.materials.append(mat)
    sc.collection.objects.link(ob)
    RAIN_OB = ob
    return ob


def clear_rain():
    global RAIN_OB
    if RAIN_OB is not None:
        try:
            bpy.data.objects.remove(RAIN_OB, do_unlink=True)
        except Exception:
            pass
        RAIN_OB = None


# ── 引擎设置 ────────────────────────────────────────────────
SAMPLES_FINAL = 32


def set_engine(kind):
    if kind == "wire":
        sc.render.engine = "BLENDER_EEVEE"
        sc.eevee.taa_render_samples = 8
    elif kind == "clay":
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.studio_light = "Default"
        sh.color_type = "SINGLE"
        sh.single_color = (0.84, 0.84, 0.86)
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        try:
            sh.type = "SOLID"
        except Exception:
            pass
    else:
        sc.render.engine = "BLENDER_EEVEE"
        sc.eevee.taa_render_samples = SAMPLES_FINAL
    sc.render.film_transparent = False
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"


FROM = int(os.environ.get("ONLY_FROM", "0"))
TO = int(os.environ.get("ONLY_TO", "999"))
ONLY = os.environ.get("ONLY_SHOT", "")

BIG_ASSETS = None
total = 0
for idx, (sid, kind, phase, weather, rainlv, l0, l1, p0, p1, k0, k1) in enumerate(SHOTS):
    if idx < FROM or idx >= TO:
        continue
    if ONLY and sid != ONLY:
        continue
    d = os.path.join(OUT, sid)
    os.makedirs(d, exist_ok=True)
    # 已完成就跳过
    have = len([f for f in os.listdir(d) if f.endswith(".png")])
    if have >= NF:
        C.log("skip (done)", sid)
        continue

    set_engine(kind)
    clear_rain()
    for ob in CEIL:
        ob.hide_render = (sid == "25_top_stats")

    saved = None
    if kind == "wire":
        wm = get_wire_mat()
        saved = {}
        for ob in bpy.data.objects:
            if ob.type != "MESH" or ob.hide_render:
                continue
            saved[ob.name] = [s.material for s in ob.material_slots]
            if not ob.material_slots:
                ob.data.materials.append(wm)
            else:
                for s in ob.material_slots:
                    s.material = wm
    elif kind == "final":
        clight.apply_phase(lights, phase, weather)
        if rainlv > 0:
            if rainlv >= 3:
                build_rain(1500, 0.38, 0.34, 0.14, 1.15)
            elif rainlv == 2:
                build_rain(1100, 0.32, 0.30, 0.12, 1.0)
            else:
                build_rain(650, 0.26, 0.24, 0.08, 0.9)

    base_exp = sc.view_settings.exposure
    for f in range(NF):
        t = f / max(NF - 1, 1)
        e = smooth(t)
        cam.location = lerp3(p0, p1, e)
        tgt = lerp3(k0, k1, e)
        cam.data.lens = l0 + (l1 - l0) * e
        dvec = tgt - cam.location
        cam.rotation_euler = dvec.to_track_quat("-Z", "Y").to_euler()

        # 雨：逐帧下落（两层循环，落差 8m 覆盖全部）
        if RAIN_OB is not None:
            RAIN_OB.location.z = -((f / FPS) * 3.2) % 8.0

        # 雷阵雨：周期性闪电
        if weather == "storm" and kind == "final":
            cyc = (f / FPS) % 2.6
            flash = max(0.0, 1.0 - cyc / 0.22) if cyc < 0.22 else 0.0
            sc.view_settings.exposure = base_exp + flash * 1.6
        else:
            sc.view_settings.exposure = base_exp

        sc.render.filepath = os.path.join(d, "%04d" % (f + 1))
        bpy.ops.render.render(write_still=True)
        total += 1
        if f % 24 == 0:
            C.log("frame", sid, "%d/%d" % (f + 1, NF))

    sc.view_settings.exposure = base_exp
    clear_rain()
    if saved is not None:
        for ob in bpy.data.objects:
            if ob.name in saved:
                for s, m in zip(ob.material_slots, saved[ob.name]):
                    try:
                        s.material = m
                    except Exception:
                        pass
    for ob in CEIL:
        ob.hide_render = False
    C.log("SHOT DONE", sid)

print("LV_ANIM_DONE frames=%d" % total)
