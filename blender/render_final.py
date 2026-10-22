"""Final hero renders: 4 time phases + weather, 1600x900, AgX, subtle volumetrics.

用法：
    blender -b -P render_final.py                # 出全部 9 张
    MAID_ONLY_SHOT=hero_noon blender -b -P ...   # 只出某一张（环境变量）
"""
import bpy, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ccore as C, cprop as P, clight

bpy.ops.wm.open_mainfile(filepath=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scene", "maid_cafe.blend"))
sc = bpy.context.scene
lights = clight.build_lights()
vol = clight.add_render_volume(0.0014)
C.setup_engine("eevee", 48, (1600, 900))
outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "renders", "final")
os.makedirs(outdir, exist_ok=True)
ONLY = os.environ.get("MAID_ONLY_SHOT", "")

CAM = dict(frm=(1.85, -2.55, 1.55), look=(-1.20, 0.50, 1.05), lens=24)
WIN = dict(frm=(2.20, 0.20, 1.55), look=(-1.90, -3.05, 1.25), lens=26, novol=True)
MAID = dict(frm=(0.1, -2.15, 1.42), look=(-1.7, 0.3, 0.92), lens=42)

# (名字, 时段, 天气, 机位, 曝光补偿)——朝窗的机位要压曝光，否则室外过曝成白片
shots = [
    ("hero_morning", "morning", "clear", CAM, None),
    ("hero_noon", "noon", "clear", CAM, None),
    ("hero_dusk", "dusk", "clear", CAM, None),
    ("hero_night", "night", "clear", CAM, None),
    ("hero_window_noon", "noon", "clear", WIN, -0.95),
    ("hero_window_night", "night", "clear", WIN, None),
    ("hero_maid", "dusk", "clear", MAID, None),
    ("hero_rain_noon", "noon", "rain_med", WIN, -0.75),
    ("hero_storm_night", "night", "storm", WIN, 0.10),
]
paths = []
for name, phase, weather, v, expo in shots:
    if ONLY and name != ONLY:
        continue
    clight.apply_phase(lights, phase, weather)
    base_expo = P.LIGHT_RIG.get(phase, {}).get("exposure", 0.0)
    sc.view_settings.exposure = base_expo if expo is None else base_expo + expo
    cam = bpy.data.objects.get("QC_FinalCam") or C.render_camera("QC_FinalCam", v["frm"], v["look"], lens=v["lens"])
    cam.location = v["frm"]
    cam.rotation_euler = (C.Vector(v["look"]) - C.Vector(v["frm"])).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = v["lens"]
    sc.camera = cam
    # 朝窗机位关掉体积雾：穿过 4m 雾看亮窗会整片泛白，把街景糊掉
    if vol is not None:
        vol.hide_render = bool(v.get("novol"))
    p = os.path.join(outdir, name + ".png")
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    paths.append(p)
    print("SHOT", name, "expo", round(sc.view_settings.exposure, 2))
print("FINAL_RENDERS " + json.dumps(paths))
