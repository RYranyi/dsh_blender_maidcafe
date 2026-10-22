"""
video_shots.py —— 2 分钟介绍视频的动态镜头渲染（只加相机/调灯光，不改物体）

输出：renders/video/shots/<shot>/####.png
用法：blender -b scene/maid_cafe.blend -P blender/video_shots.py -- --shot <name|all> [--force]
"""
import bpy, sys, os, json, math
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ccore as C
import cprop as P
import clight

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(ROOT, "scene", "maid_cafe.blend")
OUT = os.path.join(ROOT, "renders", "video", "shots")
os.makedirs(OUT, exist_ok=True)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
WANT, FORCE = "all", False
for i, a in enumerate(argv):
    if a == "--shot" and i + 1 < len(argv):
        WANT = argv[i + 1]
    if a == "--force":
        FORCE = True

FPS = 24
RES = (1600, 900)
SAMPLES = 16

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
lights = clight.build_lights()

cam = bpy.data.objects.get("VID_Cam")
if cam is None:
    cd = bpy.data.cameras.new("VID_Cam")
    cam = bpy.data.objects.new("VID_Cam", cd)
    sc.collection.objects.link(cam)
cam.data.clip_start = 0.02
cam.data.clip_end = 300.0
sc.camera = cam

C.setup_engine("eevee", SAMPLES, RES)
sc.render.fps = FPS
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGB"
sc.render.film_transparent = False


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def ease(t):
    return t * t * (3 - 2 * t)


def render_clip(name, phase, weather, n_frames, pose_fn, lens=30):
    outdir = os.path.join(OUT, name)
    os.makedirs(outdir, exist_ok=True)
    done = len([f for f in os.listdir(outdir) if f.endswith(".png")])
    if done >= n_frames and not FORCE:
        C.log("skip (complete):", name, done)
        return 0
    clight.apply_phase(lights, phase, weather)
    cam.data.lens = lens
    for f in range(n_frames):
        t = f / max(1, n_frames - 1)
        pos, tgt = pose_fn(ease(t))
        cam.location = Vector(pos)
        look_at(cam, tgt)
        sc.frame_set(f + 1)
        sc.render.filepath = os.path.join(outdir, "%04d.png" % (f + 1))
        bpy.ops.render.render(write_still=True)
    C.log("clip done:", name, n_frames)
    return n_frames


SHOTS = []


def _push_in():
    def pose(t):
        p0 = (2.05, -2.45, 1.74)
        p1 = (0.35, -1.35, 1.46)
        pos = tuple(a + (b - a) * t for a, b in zip(p0, p1))
        tgt = (-1.10 + 0.28 * t, 0.20, 1.06 - 0.04 * t)
        return pos, tgt
    return pose


def _orbit_room():
    def pose(t):
        ang = math.radians(-52 + 58 * t)
        r = 3.55 - 0.35 * t
        pos = (math.cos(ang) * r + 0.25, math.sin(ang) * r - 0.35, 1.86 - 0.14 * t)
        return pos, (-0.55, 0.55, 1.08)
    return pose


def _bar_dolly():
    def pose(t):
        pos = (-1.10 + 3.45 * t, 0.05, 1.34)
        tgt = (0.30 + 2.25 * t, 1.75, 0.96)
        return pos, tgt
    return pose


def _maid_closeup():
    # 把相机拉远：从 r=2.55 收到 2.05（原 1.80→1.40 太近，女仆占满画面）
    def pose(t):
        ang = math.radians(40 - 46 * t)
        r = 2.55 - 0.28 * t
        cx, cy = -1.85, -0.22
        pos = (cx + math.cos(ang) * r, cy + math.sin(ang) * r, 1.34 + 0.04 * t)
        return pos, (cx + 0.02, cy + 0.02, 1.06)
    return pose


def _display_dolly():
    def pose(t):
        pos = (-0.10 - 1.05 * t, -0.08 - 0.16 * t, 1.27)
        tgt = (-0.58 - 0.52 * t, 0.88, 0.97)
        return pos, tgt
    return pose


def _window_pan():
    def pose(t):
        pos = (1.22 - 2.65 * t, -1.52, 1.58)
        tgt = (1.05 - 3.05 * t, -3.06, 1.42)
        return pos, tgt
    return pose


def _ceiling_rise():
    def pose(t):
        pos = (-2.30 - 1.15 * t, -1.92 + 0.88 * t, 1.02 + 1.08 * t)
        return pos, (-1.55, 0.62, 1.92 + 0.38 * t)
    return pose


SHOTS = [
    ("01_pushin_noon",     "noon",    "clear",    108, _push_in,      26),
    ("02_orbit_noon",      "noon",    "clear",    120, _orbit_room,   24),
    ("03_bar_noon",        "noon",    "clear",    120, _bar_dolly,    30),
    ("04_maid_dusk",       "dusk",    "clear",     96, _maid_closeup, 44),
    ("05_display_noon",    "noon",    "clear",     96, _display_dolly, 34),
    ("06_window_morning",  "morning", "clear",     96, _window_pan,   26),
    ("07_ceiling_dusk",    "dusk",    "clear",     84, _ceiling_rise, 26),
    ("08_light_morning",   "morning", "clear",     60, _orbit_room,   26),
    ("09_light_noon",      "noon",    "clear",     60, _orbit_room,   26),
    ("10_light_dusk",      "dusk",    "clear",     60, _orbit_room,   26),
    ("11_light_night",     "night",   "clear",     60, _orbit_room,   26),
    ("12_rain_noon",       "noon",    "rain_med",  60, _window_pan,   26),
    ("13_storm_night",     "night",   "storm",     60, _window_pan,   28),
]

todo = [s for s in SHOTS if WANT == "all" or WANT in s[0]]
C.log("rendering %d clips" % len(todo))

total = 0
for name, phase, weather, frames, fn, lens in todo:
    total += render_clip(name, phase, weather, frames, fn(), lens)
C.log("ALL DONE, frames:", total)
print("VIDEO_SHOTS_DONE " + json.dumps({"clips": [s[0] for s in todo], "frames": total}))
