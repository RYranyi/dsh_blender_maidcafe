"""
cdisplay.py — C_Display：玻璃冷藏甜品展示柜（+ 内部 9 件甜品 / 3 层玻璃层板 / LED / 射灯 / 价格立牌）

坐标与尺寸全部来自 cprop.P（DISPLAY / DISPLAY_SHELVES / DISPLAY_GLASS_Z ...），
面朝 −Y（顾客方向）。原点规范：落地物原点=底面中心；甜品原点=盘底中心。

外部模型：strawberry_chocolate_cake / carrot_cake。
  ⚠ 实测坑：`carrot_cake` 原始网格含大量退化面，Blender 的 Decimate(COLLAPSE) 作用在它身上
    会【增加】三角面（13790 → 24624）。因此本模块的减面走 `_reduce_to_target()`：
    先 bmesh 合并重复点（merge by distance），再做「安全 decimate」（减面后若变多就回滚），
    直到达标或没有可用手段为止。

顶罩方案：采用「不锈钢顶盖」（而不是 DISPLAY_GLASS_Z 1.36–1.62 的玻璃顶罩）——
  理由：① 保证整体高度严格 = P.DISPLAY["z"][1] = 1.36，不越契约给的柜体包络；
        ② 玻璃顶罩会在柜顶形成空玻璃箱，视觉上是空的、还多一层透射面；
        ③ 不锈钢顶盖正好把顶部 LED 线槽与 2 只射灯罩收进去（外观更接近日式喫茶店的冷藏柜）。

玻璃：用 M["glass_case"]（alpha 混合，EEVEE / three.js 都真透明），并关闭投影
  （ob.visible_shadow=False），否则柜内会被玻璃阴影压成死黑。
"""
import bpy
import bmesh
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
                else os.getcwd())
import ccore as C
import cprop as P
import cmat as MAT
import cassets as A
from mathutils import Vector, Matrix, Euler

MODULE = "cdisplay"
OWNER = "furn-modeler"
TRI_BUDGET = 40000
COL = "C_Display"

D2R = C.D2R
PI = C.PI

_M = None      # 调色板 dict（build 时注入）
_X = {}        # 本模块自建材质
_STATS = {}    # 减面报告（写进 notes，供 QC 核对）


# ══════════════════════════════════════════════════════════════════════
# 网格工具（减面 / 度量）
# ══════════════════════════════════════════════════════════════════════
def _tris(ob):
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def _merge_doubles(ob, dist):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    before = len(bm.faces)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=dist)
    bmesh.ops.dissolve_degenerate(bm, dist=dist * 0.5, edges=list(bm.edges))
    bm.to_mesh(me)
    bm.free()
    me.update()
    return before, _tris(ob)


def _decimate_safe(ob, ratio):
    """安全 decimate：减面后三角面反而变多（退化网格的已知现象）就回滚。"""
    before = _tris(ob)
    backup = ob.data.copy()
    C.decimate(ob, ratio)
    after = _tris(ob)
    if after >= before:
        old = ob.data
        ob.data = backup
        try:
            bpy.data.meshes.remove(old)
        except Exception:
            pass
        return before, False
    bpy.data.meshes.remove(backup)
    return after, True


def _reduce_to_target(ob, target, tag=""):
    """合并重复点 → 安全 decimate，直到 tris ≤ target（尽力而为）。返回最终 tris。"""
    t0 = _tris(ob)
    # 1) merge by distance 逐级加大（先温和，避免吃掉 2~3mm 的蛋糕装饰细节）
    for d in (0.0008, 0.0015, 0.0025, 0.004):
        if _tris(ob) <= target:
            break
        _merge_doubles(ob, d)
    # 2) 安全 decimate 逐级
    for r in (0.55, 0.40, 0.30, 0.22):
        if _tris(ob) <= target:
            break
        _decimate_safe(ob, r)
    t1 = _tris(ob)
    _STATS[tag or ob.name] = {"from": t0, "to": t1, "target": target}
    C.log(f"reduce {tag or ob.name}: {t0} → {t1} tris (target {target})")
    return t1


def _vbox(ob):
    """顶点级世界 AABB（不依赖 bound_box 缓存，可靠的 min_z 判据）。"""
    bpy.context.view_layer.update()
    mn = [1e9, 1e9, 1e9]
    mx = [-1e9, -1e9, -1e9]
    for v in ob.data.vertices:
        p = ob.matrix_world @ v.co
        for i in range(3):
            if p[i] < mn[i]:
                mn[i] = p[i]
            if p[i] > mx[i]:
                mx[i] = p[i]
    return mn, mx


def _fit_import(pid, name, x, y, z, dia, target=None, height_fix=None):
    """导入外部模型 → 减面到 target → 归一化（底面中心在原点）→ 缩到 dia → 摆到 (x,y,z)。"""
    got = A.import_model(pid, col=COL, name_prefix=name)
    if not got:
        C.log("WARN import failed", pid)
        return []
    ob = got[0]
    ob.name = name
    ob.data.name = name + "_mesh"
    if target:
        _reduce_to_target(ob, target, tag=name)
    C.apply_transforms([ob])
    me = ob.data
    vs = [v.co for v in me.vertices]
    mn = [min(v[i] for v in vs) for i in range(3)]
    mx = [max(v[i] for v in vs) for i in range(3)]
    size = [max(mx[i] - mn[i], 1e-6) for i in range(3)]
    s = dia / max(size[0], size[1]) if dia else 1.0
    sz = height_fix / size[2] if height_fix else s
    me.transform(Matrix.Translation(Vector((-(mn[0] + mx[0]) / 2,
                                           -(mn[1] + mx[1]) / 2, -mn[2]))))
    me.transform(Matrix.Diagonal(Vector((s, s, sz))).to_4x4())
    ob.location = (x, y, z)
    ob.rotation_euler = (0, 0, 0)
    return [ob]


# ══════════════════════════════════════════════════════════════════════
# 材质
# ══════════════════════════════════════════════════════════════════════
def _mats():
    """本模块专属材质（全局复用，幂等）。"""
    global _X
    if _X:
        return _X
    _X = {
        # 甜品主色：饱和度抬高，隔着玻璃也要能一眼分辨
        "strawberry": MAT.M.pbr("MAT_Strawberry", base="#C8202F", rough=0.32,
                                coat=0.3, coat_rough=0.15),
        "chocolate": MAT.M.pbr("MAT_Cake_Chocolate", base="#3D2015", rough=0.30,
                               coat=0.35, coat_rough=0.16),
        "sponge": MAT.M.pbr("MAT_Cake_Sponge", base="#E3BD7C", rough=0.76),
        "cream": MAT.M.pbr("MAT_Cake_Cream", base="#FFF7E8", rough=0.44,
                           sss=0.2, sss_radius=(0.9, 0.5, 0.35)),
        "matcha": MAT.M.pbr("MAT_Cake_Matcha", base="#6E8437", rough=0.60),
        "matcha_deep": MAT.M.pbr("MAT_Cake_Matcha_Deep", base="#43552a", rough=0.64),
        "custard": MAT.M.pbr("MAT_Cake_Custard", base="#F3CE72", rough=0.28,
                             sss=0.3, sss_radius=(1.0, 0.6, 0.3)),
        "caramel": MAT.M.pbr("MAT_Cake_Caramel", base="#8E4310", rough=0.10,
                             coat=0.75, coat_rough=0.04),
        "macaron_pink": MAT.M.pbr("MAT_Cake_Macaron_Pink", base="#E8879E", rough=0.52),
        "macaron_pist": MAT.M.pbr("MAT_Cake_Macaron_Pistachio", base="#A8C068", rough=0.52),
        "macaron_cream": MAT.M.pbr("MAT_Cake_Macaron_Filling", base="#FFEFD2", rough=0.48),
        "tartshell": MAT.M.pbr("MAT_Cake_Tart_Shell", base="#BC8143", rough=0.64),
        "glaze": MAT.M.pbr("MAT_Cake_Glaze", base="#B01526", rough=0.08,
                           coat=0.85, coat_rough=0.03),
        "icing": MAT.M.pbr("MAT_Cake_Icing", base="#F6C6D2", rough=0.32),
        "board": MAT.M.pbr("MAT_Wood_CakeBoard", base="#E7D9BD", rough=0.7),
        "back": MAT.M.pbr("MAT_Case_Back", base="#E8DCC8", rough=0.70,
                          uv_scale=1.0, procedural="noise"),
    }
    return _X


def _mat_glass():
    """展示柜玻璃：优先 glass_case（alpha 混合），退化到 glass。"""
    return (_M.get("glass_case") or _M.get("glass"))


# ══════════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════════
def _no_shadow(ob):
    """玻璃不投影（否则柜内死黑）。"""
    for attr, val in (("visible_shadow", False), ("visible_glossy", False)):
        try:
            setattr(ob, attr, val)
        except Exception:
            pass
    return ob


def _plate(name, cx, cy, z, r, mat, segs=20):
    """白瓷小盘：原点=盘底中心。"""
    prof = [(0.0, 0.0), (r * 0.55, 0.0), (r * 0.72, 0.0025),
            (r * 0.93, 0.0075), (r, 0.0105), (r * 0.955, 0.0125)]
    return C.lathe(name, prof, segs=segs, loc=(cx, cy, z), mat=mat,
                   col=COL, close_top=True, shade="smooth")


def _cream_rosette(name, cx, cy, z, r, h, mat, tier=4):
    """奶油裱花（lathe 锥形分层收径 = 挤花嘴绕圈堆高的外观）。"""
    prof = [(0.0, 0.0), (r, 0.0), (r * 1.02, h * 0.10)]
    for i in range(tier):
        t = i / float(tier)
        prof.append((r * (1.0 - 0.72 * (t + 0.30)), h * (0.10 + 0.78 * (t + 0.25))))
    prof.append((0.0, h * 0.98))
    prof = [(max(0.0, pr), pz) for pr, pz in prof]
    return C.lathe(name, prof, segs=16, loc=(cx, cy, z), mat=mat, col=COL,
                   close_top=True, shade="smooth")


def _cream_helix(name, cx, cy, z, r, h, mat, turns=2.4, pts=9, rad=0.006):
    """真·锥形螺旋挤花：沿螺旋线扫管。"""
    pl = []
    for i in range(pts):
        t = i / float(pts - 1)
        a = turns * math.tau * t
        rr = r * (1.0 - 0.62 * t)
        pl.append((cx + rr * math.cos(a), cy + rr * math.sin(a), z + h * t))
    return C.tube_along(name, pl, radius=rad, segs=6, mat=mat, col=COL)


def _strawberry(name, cx, cy, z, r, mat, segs=12, rings=8):
    """草莓：小球（略拉高）+ 锥形尖。"""
    o = C.sphere(name + "_Body", r=r, segs=segs, rings=rings,
                 loc=(cx, cy, z + r * 1.06), mat=mat, col=COL,
                 scale=(1.0, 1.0, 1.18))
    tip = C.cyl(name + "_Tip", r=r * 0.44, h=r * 0.62, r2=0.004, segs=8,
                loc=(cx, cy, z + r * 1.06 + r * 1.02), mat=mat, col=COL)
    return [o, tip]


def _choc_shard(name, cx, cy, z, mat, w=0.028, h=0.052, curl=0.10):
    """薄弯巧克力片：4 段矩形截面 loft（有厚度，双面可导出）。"""
    secs = []
    n = 4
    for i in range(n):
        t = i / float(n - 1)
        px = cx + curl * (t - 0.5) * 0.9
        pz = z + h * t
        ang = t * 1.05
        dx = math.sin(ang) * w * 0.5
        dy = math.cos(ang) * 0.0016
        secs.append([(px - dx, cy - 0.0016 - dy, pz),
                     (px + dx, cy - 0.0016 + dy, pz),
                     (px + dx, cy + 0.0016 + dy, pz),
                     (px - dx, cy + 0.0016 - dy, pz)])
    return C.loft(name, secs, closed_ring=True, cap=True, mat=mat, col=COL,
                  shade="smooth")


# ══════════════════════════════════════════════════════════════════════
# 甜品（每件 = 盘 + 主体 + 装饰）
# ══════════════════════════════════════════════════════════════════════
def _dessert_strawberry_cake(idx, cx, cy, z):
    """外模：草莓巧克力蛋糕（27k → 减到 6000）。"""
    objs = [_plate(f"DS_Plate_{idx:02d}", cx, cy, z, 0.135, _M["porcelain"], segs=22)]
    objs += _fit_import("strawberry_chocolate_cake", f"DS_Cake_Strawberry_{idx:02d}",
                        cx, cy, z + 0.0125, dia=0.235, target=6000)
    for k, a in enumerate((0.55, 2.30, 4.05)):
        rr = 0.108
        objs += _strawberry(f"DS_GarnishBerry_{idx:02d}_{k}",
                            cx + rr * math.cos(a), cy + rr * math.sin(a),
                            z + 0.0125, 0.0135, _X["strawberry"], segs=10, rings=6)
    objs.append(_choc_shard(f"DS_GarnishChoc_{idx:02d}", cx + 0.10, cy - 0.03,
                            z + 0.014, _X["chocolate"]))
    return objs


def _dessert_carrot_cake(idx, cx, cy, z):
    """外模：胡萝卜蛋糕（13.8k 退化网格 → 合并+安全减面到 5000）。"""
    objs = [_plate(f"DS_Plate_{idx:02d}", cx, cy, z, 0.128, _M["porcelain"], segs=22)]
    objs += _fit_import("carrot_cake", f"DS_Cake_Carrot_{idx:02d}",
                        cx, cy, z + 0.0125, dia=0.215, target=5000)
    for k in range(3):
        a = 0.4 + k * 2.1
        objs.append(_cream_rosette(f"DS_GarnishCream_{idx:02d}_{k}",
                                   cx + 0.058 * math.cos(a), cy + 0.058 * math.sin(a),
                                   z + 0.0125 + 0.082, 0.016, 0.030, _X["cream"], tier=2))
    return objs


def _dessert_matcha_roll(idx, cx, cy, z, flip=False):
    """抹茶卷：横躺圆柱卷 + 两端螺旋奶油 + 顶部奶油与抹茶粉。"""
    objs = [_plate(f"DS_Plate_{idx:02d}", cx, cy, z, 0.142, _M["porcelain"], segs=22)]
    L = 0.20
    r = 0.045
    zc = z + 0.0125 + r
    body = C.cyl(f"DS_Cake_MatchaRoll_{idx:02d}", r=r, h=L, segs=18,
                 rot=(0, PI / 2, 0 if not flip else PI),
                 loc=(cx, cy, zc), mat=_X["matcha"], col=COL, bevel=0.004, bsegs=1)
    C.shade_smooth(body)
    objs.append(body)
    for s in (-1, 1):
        tag = "L" if s < 0 else "R"
        objs.append(C.cyl(f"DS_Cake_MatchaCream_{idx:02d}_{tag}",
                          r=r * 0.62, h=0.006, segs=14, rot=(0, PI / 2, 0),
                          loc=(cx + s * (L / 2 + 0.002), cy, zc),
                          mat=_X["cream"], col=COL))
        objs.append(C.cyl(f"DS_Cake_MatchaSwirl_{idx:02d}_{tag}",
                          r=r * 0.26, h=0.009, segs=10, rot=(0, PI / 2, 0),
                          loc=(cx + s * (L / 2 + 0.005), cy, zc),
                          mat=_X["matcha_deep"], col=COL))
    objs.append(_cream_rosette(f"DS_GarnishCream_{idx:02d}", cx - 0.04, cy,
                               z + 0.0125 + 2 * r - 0.004, 0.020, 0.034,
                               _X["cream"], tier=3))
    objs.append(C.box(f"DS_GarnishDust_{idx:02d}", (0.05, 0.012, 0.004),
                      loc=(cx + 0.06, cy + 0.006, z + 0.0125 + 2 * r + 0.002),
                      mat=_X["matcha_deep"], col=COL, bevel=0.001))
    return objs


def _dessert_pudding(idx, cx, cy, z, dark=False):
    """布丁：焦糖圆台 + 半球顶 + 焦糖淋面 + 垂流。"""
    m_body = _X["caramel"] if dark else _X["custard"]
    m_top = _X["custard"] if dark else _X["caramel"]
    objs = [_plate(f"DS_Plate_{idx:02d}", cx, cy, z, 0.115, _M["porcelain"], segs=22)]
    r = 0.052
    zb = z + 0.0125
    objs.append(C.lathe(f"DS_Cake_Pudding_{idx:02d}",
                        [(0.0, 0.0), (r * 0.94, 0.0), (r, 0.006), (r * 1.02, 0.020),
                         (r * 1.05, 0.032), (r * 0.92, 0.048), (r * 0.72, 0.060),
                         (r * 0.40, 0.068), (0.0, 0.070)],
                        segs=20, loc=(cx, cy, zb), mat=m_body, col=COL,
                        close_bottom=True, close_top=True, shade="smooth"))
    objs.append(C.lathe(f"DS_GarnishCaramel_{idx:02d}",
                        [(0.0, 0.0), (r * 0.88, 0.0), (r * 0.9, 0.004), (0.0, 0.006)],
                        segs=20, loc=(cx, cy, zb + 0.066), mat=m_top, col=COL,
                        shade="smooth"))
    for k, a in enumerate((0.2, 1.6, 3.0, 4.6)):
        objs.append(C.cyl(f"DS_GarnishDrip_{idx:02d}_{k}", r=0.007, h=0.020,
                          segs=8, loc=(cx + r * 0.80 * math.cos(a),
                                       cy + r * 0.80 * math.sin(a), zb + 0.052),
                          mat=m_top, col=COL))
    objs.append(_cream_rosette(f"DS_GarnishCream_{idx:02d}", cx, cy,
                               zb + 0.068, 0.017, 0.030, _X["cream"], tier=2))
    return objs


def _dessert_macaron(idx, cx, cy, z, cols=None):
    """马卡龙塔：3 层小圆饼叠塔（每层 = 上下壳 + 夹心 + 裙边）。"""
    objs = [_plate(f"DS_Plate_{idx:02d}", cx, cy, z, 0.105, _M["porcelain"], segs=22)]
    cols = cols or ["macaron_pink", "macaron_pist", "macaron_pink"]
    rr = 0.044
    zc = z + 0.0125
    for i, key in enumerate(cols):
        m = _X[key]
        r_i = rr * (1.0 - 0.10 * i)
        objs.append(C.cyl(f"DS_Macaron_{idx:02d}_{i}_A", r=r_i, h=0.011, r2=r_i * 0.94,
                          segs=16, loc=(cx, cy, zc + 0.0055), mat=m, col=COL))
        objs.append(C.cyl(f"DS_Macaron_{idx:02d}_{i}_F", r=r_i * 0.93, h=0.009,
                          segs=16, loc=(cx, cy, zc + 0.0155),
                          mat=_X["macaron_cream"], col=COL))
        objs.append(C.cyl(f"DS_Macaron_{idx:02d}_{i}_B", r=r_i, h=0.012, r2=r_i * 0.97,
                          segs=16, loc=(cx, cy, zc + 0.026), mat=m, col=COL))
        objs.append(C.cyl(f"DS_Macaron_{idx:02d}_{i}_R", r=r_i * 0.99, h=0.004,
                          segs=16, loc=(cx, cy, zc + 0.0105), mat=m, col=COL))
        zc += 0.032
    objs += _strawberry(f"DS_GarnishBerry_{idx:02d}", cx, cy, zc - 0.001,
                        0.012, _X["strawberry"], segs=10, rings=6)
    objs.append(_choc_shard(f"DS_GarnishChoc_{idx:02d}", cx + 0.042, cy - 0.018,
                            z + 0.0145, _X["chocolate"], w=0.018, h=0.030, curl=0.06))
    return objs


def _dessert_tart(idx, cx, cy, z):
    """水果挞：挞壳 + 卡士达 + 镜面果胶 + 5 颗草莓。"""
    objs = [_plate(f"DS_Plate_{idx:02d}", cx, cy, z, 0.125, _M["porcelain"], segs=22)]
    zb = z + 0.0125
    rt = 0.077
    objs.append(C.lathe(f"DS_Cake_TartShell_{idx:02d}",
                        [(0.0, 0.0), (rt * 0.86, 0.0), (rt * 0.95, 0.006),
                         (rt, 0.020), (rt * 1.04, 0.034), (rt * 0.99, 0.036),
                         (rt * 0.80, 0.030)],
                        segs=22, loc=(cx, cy, zb), mat=_X["tartshell"], col=COL,
                        close_bottom=True, close_top=True, shade="smooth"))
    objs.append(C.cyl(f"DS_Cake_TartCustard_{idx:02d}", r=rt * 0.88, h=0.016, segs=20,
                      loc=(cx, cy, zb + 0.024), mat=_X["custard"], col=COL,
                      bevel=0.003, bsegs=1))
    objs.append(C.cyl(f"DS_Cake_TartGlaze_{idx:02d}", r=rt * 0.84, h=0.003, segs=20,
                      loc=(cx, cy, zb + 0.033), mat=_X["glaze"], col=COL))
    for k in range(5):
        a = k * math.tau / 5 + 0.3
        rr = rt * 0.52 if k else 0.0
        objs += _strawberry(f"DS_GarnishBerry_{idx:02d}_{k}",
                            cx + rr * math.cos(a), cy + rr * math.sin(a),
                            zb + (0.035 if k == 0 else 0.033), 0.0155,
                            _X["strawberry"], segs=10, rings=6)
    return objs


# ══════════════════════════════════════════════════════════════════════
# 柜体
# ══════════════════════════════════════════════════════════════════════
def _base(D, X0, X1, Y0, Y1):
    """底座（0 → 0.30）：木纹柜体 + 不锈钢踢脚 + 正面通风格栅 + 黄铜压边。"""
    m_wood = _M["wood_counter"]
    m_steel = _M["steel_brushed"]
    m_brass = _M["brass"]
    m_black = _M["black_metal"]
    m_grille = _M["grille"]
    objs = []
    base_h = 0.30
    kick_h = 0.08
    inset = 0.035

    objs.append(C.box("DS_BaseKick", (X1 - X0 - inset * 2, Y1 - Y0 - inset * 2, kick_h),
                      loc=((X0 + X1) / 2, (Y0 + Y1) / 2, kick_h / 2),
                      mat=m_steel, col=COL, bevel=0.004, segs=1))
    body = C.box("DS_BaseBody", (X1 - X0, Y1 - Y0, base_h - kick_h),
                 loc=((X0 + X1) / 2, (Y0 + Y1) / 2, kick_h + (base_h - kick_h) / 2),
                 mat=m_wood, col=COL, bevel=0.006, segs=2)
    C.uv_world(body, 1.0)
    objs.append(body)
    objs.append(C.box("DS_BaseBand", (X1 - X0 + 0.008, Y1 - Y0 + 0.008, 0.014),
                      loc=((X0 + X1) / 2, (Y0 + Y1) / 2, base_h - 0.007),
                      mat=m_brass, col=COL, bevel=0.002, segs=1))
    objs.append(C.box("DS_BaseDeck", (X1 - X0 - 0.05, Y1 - Y0 - 0.05, 0.012),
                      loc=((X0 + X1) / 2, (Y0 + Y1) / 2, base_h + 0.006),
                      mat=m_steel, col=COL, bevel=0.003, segs=1))

    # 正面通风格栅（细横条）：凹槽 + 细条，覆盖 z 0.10..0.245。
    # 价格立牌立在底座台面（z=0.30）之上，两者 z 区间不重叠，卡片不会被铝条切碎。
    gz0, gz1 = 0.100, 0.245
    objs.append(C.box("DS_VentRecess", (X1 - X0 - 0.26, 0.012, gz1 - gz0),
                      loc=((X0 + X1) / 2, Y0 + 0.004, (gz0 + gz1) / 2),
                      mat=m_black, col=COL))
    n = 11
    for i in range(n):
        zz = gz0 + 0.007 + i * ((gz1 - gz0 - 0.014) / (n - 1))
        objs.append(C.box(f"DS_VentSlat_{i:02d}", (X1 - X0 - 0.28, 0.010, 0.0050),
                          loc=((X0 + X1) / 2, Y0 - 0.001, zz),
                          mat=m_grille, col=COL, bevel=0.001, segs=1))
    for i, zz in enumerate((gz0 - 0.006, gz1 + 0.006)):
        objs.append(C.box(f"DS_VentFrame_{i}", (X1 - X0 - 0.24, 0.016, 0.008),
                          loc=((X0 + X1) / 2, Y0 - 0.002, zz),
                          mat=m_steel, col=COL))
    for sx in (X0 + inset / 2, X1 - inset / 2):
        for sy in (Y0 + inset / 2, Y1 - inset / 2):
            objs.append(C.box("DS_FootGuard", (0.020, 0.020, kick_h - 0.012),
                              loc=(sx, sy, (kick_h - 0.012) / 2 + 0.004),
                              mat=m_brass, col=COL, bevel=0.003, segs=2))
    return objs


def _vitrine(D, X0, X1, Y0, Y1):
    """玻璃腔（0.30 → 1.36）：4 根立柱 + 三面玻璃 + 顶部玻璃 + 背板 + 不锈钢顶盖。"""
    m_glass = _mat_glass()
    m_steel = _M["steel"]
    m_brass = _M["brass"]
    m_back = _X["back"]
    objs = []
    zb = 0.30
    zt = D["z"][1]
    post = 0.036

    for i, (px, py) in enumerate([(X0 + post / 2, Y0 + post / 2),
                                  (X1 - post / 2, Y0 + post / 2),
                                  (X0 + post / 2, Y1 - post / 2),
                                  (X1 - post / 2, Y1 - post / 2)]):
        objs.append(C.box(f"DS_Post_{i}", (post, post, zt - zb),
                          loc=(px, py, (zb + zt) / 2), mat=m_steel, col=COL,
                          bevel=0.012, segs=3, shade="auto"))
        for k, zz in enumerate((zb + 0.02, zt - 0.03)):
            objs.append(C.box(f"DS_PostRing_{i}_{k}", (post + 0.006, post + 0.006, 0.014),
                              loc=(px, py, zz), mat=m_brass, col=COL,
                              bevel=0.002, segs=1))

    gx0, gx1 = X0 + post, X1 - post
    gy0, gy1 = Y0 + post, Y1 - post
    t = 0.008
    zt_glass = zt - 0.028
    for side, (cx, cy, sx, sy) in {
        "Front": ((gx0 + gx1) / 2, Y0 + 0.010, gx1 - gx0, t),
        "Left": (X0 + 0.010, (gy0 + gy1) / 2, t, gy1 - gy0),
        "Right": (X1 - 0.010, (gy0 + gy1) / 2, t, gy1 - gy0),
    }.items():
        g = C.box(f"DS_Glass_{side}", (sx, sy, zt_glass - zb),
                  loc=(cx, cy, (zb + zt_glass) / 2), mat=m_glass, col=COL)
        objs.append(_no_shadow(g))
    objs.append(_no_shadow(C.box("DS_Glass_Top", (gx1 - gx0, gy1 - gy0, t),
                                 loc=((gx0 + gx1) / 2, (gy0 + gy1) / 2, zt - 0.022),
                                 mat=m_glass, col=COL)))

    # 背板（浅暖色面板，不用纯白 —— 否则柜内过曝、甜品颜色被冲掉）
    objs.append(C.box("DS_BackPanel", (gx1 - gx0 - 0.004, 0.014, zt - zb - 0.004),
                      loc=((gx0 + gx1) / 2, Y1 - 0.020, (zb + zt) / 2),
                      mat=m_back, col=COL, bevel=0.002, segs=1))
    for i, fx in enumerate((0.30, 0.62, 0.94)):
        objs.append(C.box(f"DS_BackStrip_{i}", (0.006, 0.004, zt - zb - 0.02),
                          loc=(gx0 + (gx1 - gx0) * fx, Y1 - 0.026, (zb + zt) / 2),
                          mat=m_steel, col=COL))

    # 顶盖：不锈钢（含 10mm 出檐）+ 黄铜边条 —— 取代玻璃顶罩
    cap_h = 0.026
    objs.append(C.box("DS_TopCap", (X1 - X0 + 0.020, Y1 - Y0 + 0.020, cap_h),
                      loc=((X0 + X1) / 2, (Y0 + Y1) / 2, zt - cap_h / 2),
                      mat=_M["steel_brushed"], col=COL, bevel=0.006, segs=2))
    objs.append(C.box("DS_TopCapTrim", (X1 - X0 + 0.026, Y1 - Y0 + 0.026, 0.007),
                      loc=((X0 + X1) / 2, (Y0 + Y1) / 2, zt - cap_h - 0.0035),
                      mat=m_brass, col=COL, bevel=0.002, segs=1))
    objs.append(C.box("DS_TopCapLip", (X1 - X0 + 0.004, 0.010, 0.014),
                      loc=((X0 + X1) / 2, Y0 - 0.002, zt - cap_h - 0.016),
                      mat=m_steel, col=COL, bevel=0.003, segs=2))

    # 前门：上下铝轨 + 竖梃 + 黄铜拉手
    objs.append(C.box("DS_DoorTrackBot", (gx1 - gx0, 0.020, 0.026),
                      loc=((gx0 + gx1) / 2, Y0 + 0.012, zb + 0.013),
                      mat=m_steel, col=COL, bevel=0.003, segs=1))
    objs.append(C.box("DS_DoorTrackTop", (gx1 - gx0, 0.020, 0.018),
                      loc=((gx0 + gx1) / 2, Y0 + 0.012, zt_glass - 0.010),
                      mat=m_steel, col=COL, bevel=0.003, segs=1))
    mx = (gx0 + gx1) / 2
    objs.append(C.box("DS_DoorStile", (0.012, 0.014, zt_glass - zb - 0.06),
                      loc=(mx, Y0 + 0.017, (zb + zt_glass) / 2),
                      mat=m_steel, col=COL))
    for k, dx in enumerate((-0.16, 0.16)):
        objs.append(C.cyl(f"DS_DoorPull_{k}", r=0.008, h=0.075, segs=12,
                          rot=(0, PI / 2, 0), loc=(mx + dx, Y0 - 0.004, 0.80),
                          mat=m_brass, col=COL, bevel=0.002, bsegs=2))
        for s in (-1, 1):
            objs.append(C.cyl(f"DS_DoorPullStem_{k}{s}", r=0.005, h=0.012, segs=8,
                              rot=(PI / 2, 0, 0),
                              loc=(mx + dx, Y0 + 0.002, 0.80 + s * 0.030),
                              mat=m_brass, col=COL))
    return objs


def _shelves(D, X0, X1, Y0, Y1):
    """3 层玻璃层板（P.DISPLAY_SHELVES）+ 前缘黄铜挡条 + 板下 LED 灯带。"""
    m_glass = _mat_glass()
    m_brass = _M["brass"]
    m_led = _M["led"]
    objs = []
    gx0, gx1 = X0 + 0.040, X1 - 0.040
    gy0, gy1 = Y0 + 0.045, Y1 - 0.040
    for i, sz in enumerate(P.DISPLAY_SHELVES):
        objs.append(_no_shadow(C.box(f"DS_Shelf_{i}", (gx1 - gx0, gy1 - gy0, 0.012),
                                     loc=((gx0 + gx1) / 2, (gy0 + gy1) / 2, sz - 0.006),
                                     mat=m_glass, col=COL)))
        objs.append(C.cyl(f"DS_ShelfRail_{i}", r=0.0045, h=gx1 - gx0 - 0.02, segs=10,
                          rot=(0, PI / 2, 0),
                          loc=((gx0 + gx1) / 2, gy0 + 0.012, sz + 0.017),
                          mat=m_brass, col=COL))
        for s in (-1, 1):
            objs.append(C.box(f"DS_ShelfRailPost_{i}{s}", (0.008, 0.012, 0.022),
                              loc=((gx0 + gx1) / 2 + s * (gx1 - gx0) / 2 - s * 0.012,
                                   gy0 + 0.012, sz + 0.009),
                              mat=m_brass, col=COL, bevel=0.002, segs=1))
        # 板下 LED 灯带：**不做**。第一版在每层板下放了 2 根发光条，结果在正视角上
        # 变成横穿甜品前面的两条刺眼白杠（既挡视线又把柜内冲白）。柜内照明改由
        # 柜顶 2 条 LED 灯带 + 2 只黄铜射灯负责（见 _ceiling_light），层板只保留
        # 前缘黄铜挡条与背板支撑。
        for s in (-1, 1):
            objs.append(C.box(f"DS_ShelfBracket_{i}{s}", (0.030, 0.018, 0.014),
                              loc=((gx0 + gx1) / 2 + s * (gx1 - gx0) * 0.36,
                                   Y1 - 0.030, sz - 0.014),
                              mat=m_brass, col=COL))
    return objs


def _ceiling_light(D, X0, X1, Y0, Y1):
    """柜内顶：2 条 LED 灯带 + 2 只黄铜射灯罩（内芯 bulb）。"""
    m_led = _M["led"]
    m_brass = _M["brass"]
    m_bulb = _M["bulb"]
    objs = []
    zt = D["z"][1]
    z_ceiling = zt - 0.026 - 0.008
    for k, yy in enumerate((Y0 + 0.12, Y1 - 0.12)):
        objs.append(C.box(f"DS_LEDStrip_{k}", (X1 - X0 - 0.14, 0.016, 0.010),
                          loc=((X0 + X1) / 2, yy, z_ceiling),
                          mat=m_led, col=COL, bevel=0.001, segs=1))
    for k, xx in enumerate((X0 + 0.42, X1 - 0.42)):
        yy = (Y0 + Y1) / 2
        shade_h = 0.052
        z0 = z_ceiling - shade_h
        objs.append(C.lathe(f"DS_SpotShade_{k}",
                            [(0.0, 0.0), (0.052, 0.0), (0.055, 0.004),
                             (0.040, 0.026), (0.021, 0.046), (0.020, shade_h)],
                            segs=20, loc=(xx, yy, z0), mat=m_brass, col=COL,
                            close_bottom=False, close_top=True, shade="smooth"))
        objs.append(C.sphere(f"DS_SpotBulb_{k}", r=0.017, segs=12, rings=8,
                             loc=(xx, yy, z0 + 0.012), mat=m_bulb, col=COL))
        objs.append(C.cyl(f"DS_SpotCollar_{k}", r=0.021, h=0.010, segs=16,
                          loc=(xx, yy, z_ceiling - 0.004), mat=m_brass, col=COL))
    return objs


def _price_tags(D, X0, X1, Y0, Y1):
    """柜前下沿价格立牌：薄卡片（纸 M["paper"]），正面贴 menu_card.png（uv 0..1）。

    摆在底座台面（z=0.30）上的黄铜小托板上、后仰 13°，卡片整体落在前玻璃**外侧**，
    因此既不与通风格栅重叠、也不与玻璃干涉（第一版贴在格栅上，字都被铝条切碎）。
    """
    m_paper = _M["paper"]
    m_brass = _M["brass"]
    tex = P.tex_gen_path("menu_card")
    m_tex = MAT.M.pbr("MAT_Paper_MenuCard", base="#FBF6EC", diff=tex, rough=0.72,
                      uv_scale=1.0)
    objs = []
    w, h, t = 0.100, 0.138, 0.0035
    shelf_z = 0.30                       # 底座上表面
    tilt = -11 * D2R                     # 顶边向后（+Y）倾，靠向玻璃
    base_y = Y0 - 0.026                  # 卡片底边所在 y（在前玻璃之外）
    # 顶边 y 必须停在前玻璃前表面（Y0+0.006）之外，避免卡片穿玻璃。
    # 注意：这里【不能】用 assert —— 集成期任何断言失败都会让整个场景少掉 C_Display。
    # 改成「自动夹紧 + 必要时减小倾角」，任何情况下都能建出合法的立牌。
    y_front_glass = Y0 + 0.006
    y_head = base_y + h * math.sin(-tilt)
    if y_head > y_front_glass - 0.002:
        # 先减小倾角（最多退到 -4°），还不够再把整块卡片往 −Y 推
        need = y_head - (y_front_glass - 0.002)
        max_reduce = math.sin(-tilt) - math.sin(-4 * D2R)
        if max_reduce * h >= need:
            tilt = -math.asin(min(1.0, (h * math.sin(-tilt) - need) / h))
        else:
            tilt = -4 * D2R
            base_y -= need - max_reduce * h
        C.log(f"price tags: clamped tilt={tilt / D2R:.1f}deg base_y={base_y:.4f} "
              f"(glass front y={y_front_glass:.4f})")
    y_head = base_y + h * math.sin(-tilt)
    if y_head > y_front_glass - 0.001:        # 极端兜底：整块往 −Y 平移
        base_y -= (y_head - (y_front_glass - 0.001))
    for i, fx in enumerate((0.16, 0.50, 0.84)):
        cx = X0 + (X1 - X0) * fx
        card = C.box(f"DS_PriceTag_{i}", (w, t, h), loc=(0, 0, 0),
                     mat=m_paper, col=COL, bevel=0.0012, segs=1)
        me = card.data
        if not me.uv_layers:
            me.uv_layers.new(name="UVMap")
        uvl = me.uv_layers.active
        slot = C.mat_add(card, m_tex)      # slot 1 = 菜单贴图
        for poly in me.polygons:
            if poly.normal.y < -0.9:        # 正面（朝 −Y，顾客方向）
                poly.material_index = slot
                for li in poly.loop_indices:
                    v = me.vertices[me.loops[li].vertex_index].co
                    uvl.data[li].uv = ((v.x + w / 2) / w, (v.z + h / 2) / h)
        # 底边落在托板上，顶边向后倾
        zc = shelf_z + (h / 2) * math.cos(-tilt) + 0.004
        yc = base_y + (h / 2) * math.sin(-tilt)
        card.location = (cx, yc, zc)
        card.rotation_euler = (tilt, 0, 0)
        objs.append(card)
        # 黄铜托板（伸出底座前沿 32mm，托住卡片底边）
        objs.append(C.box(f"DS_PriceTagShelf_{i}", (w + 0.016, 0.048, 0.006),
                          loc=(cx, Y0 - 0.024, shelf_z - 0.003),
                          mat=m_brass, col=COL, bevel=0.002, segs=2))
        # 卡片底边压条（防止卡片在托板上滑动）
        objs.append(C.box(f"DS_PriceTagLip_{i}", (w + 0.008, 0.006, 0.012),
                          loc=(cx, base_y - 0.005, shelf_z + 0.006),
                          mat=m_brass, col=COL, bevel=0.001, segs=1))
    return objs


# ══════════════════════════════════════════════════════════════════════
# 主构建
# ══════════════════════════════════════════════════════════════════════
def build(P_, C_, M_, assets=None):
    """构建 C_Display。P_/C_/M_ 为 cprop/ccore/cmat 调色板（入参）。"""
    global _M, _X, _STATS
    _M = M_
    _X = {}
    _STATS = {}
    _mats()
    D = P_.DISPLAY
    X0, X1 = D["x"]
    Y0, Y1 = D["y"]

    C_.wipe_collection(COL)
    C_.ensure_collection(COL)

    objs = []
    objs += _base(D, X0, X1, Y0, Y1)
    objs += _vitrine(D, X0, X1, Y0, Y1)
    objs += _shelves(D, X0, X1, Y0, Y1)
    objs += _ceiling_light(D, X0, X1, Y0, Y1)
    objs += _price_tags(D, X0, X1, Y0, Y1)

    # ── 甜品布置：3 层 × 3 件 = 9 件（每件下有白瓷小盘）────────────
    shelf_x = (X0 + 0.36, (X0 + X1) / 2, X1 - 0.36)
    cy = (Y0 + Y1) / 2 + 0.01

    s0 = P_.DISPLAY_SHELVES[0]
    objs += _dessert_strawberry_cake(0, shelf_x[0], cy, s0)
    objs += _dessert_carrot_cake(1, shelf_x[1], cy, s0)
    objs += _dessert_matcha_roll(2, shelf_x[2], cy, s0)

    s1 = P_.DISPLAY_SHELVES[1]
    objs += _dessert_pudding(3, shelf_x[0], cy, s1)
    objs += _dessert_macaron(4, shelf_x[1], cy, s1)
    objs += _dessert_tart(5, shelf_x[2], cy, s1)

    s2 = P_.DISPLAY_SHELVES[2]
    objs += _dessert_matcha_roll(6, shelf_x[0], cy, s2, flip=True)
    objs += _dessert_tart(7, shelf_x[1], cy + 0.005, s2)
    objs += _dessert_pudding(8, shelf_x[2], cy, s2, dark=True)

    objs = [o for o in objs if o is not None]

    # ── 落地检查 ────────────────────────────────────────────────────
    all_mn = [1e9] * 3
    all_mx = [-1e9] * 3
    for ob in objs:
        mn, mx = _vbox(ob)
        for i in range(3):
            all_mn[i] = min(all_mn[i], mn[i])
            all_mx[i] = max(all_mx[i], mx[i])
    dz = 0.0 - all_mn[2]
    C.log(f"{MODULE}: min_z={all_mn[2]:.5f} → snap dz={dz:+.5f}")
    if abs(dz) > 1e-6:
        for ob in objs:
            ob.location.z += dz
        all_mn[2] = 0.0
        all_mx[2] += dz

    tris = C.tri_count(objs)
    C.log(f"{MODULE}: {len(objs)} objects, {tris} tris (budget {TRI_BUDGET}), "
          f"aabb={[round(v, 3) for v in all_mn]}..{[round(v, 3) for v in all_mx]}")
    if tris > TRI_BUDGET:
        C.log(f"{MODULE}: WARN over budget by {tris - TRI_BUDGET}")

    colliders = [{
        "name": "DS_DisplayCabinet",
        "aabb": [[round(v, 4) for v in all_mn], [round(v, 4) for v in all_mx]],
        "kind": "solid",
    }]
    return {
        "objects": objs,
        "collections": [COL],
        "colliders": colliders,
        "anchors": {"display_front": [X0, Y0, 0.0],
                    "display_center": [(X0 + X1) / 2, (Y0 + Y1) / 2, 0.0],
                    "shelf_z": list(P_.DISPLAY_SHELVES)},
        "notes": ("glass refrigerated display cabinet (base + 4 posts + 3 glass sides + "
                  "glass top), 3 glass shelves w/ brass rails, 9 desserts on porcelain "
                  "plates, interior LED strips + 2 brass spot shades, stainless top cap "
                  "(instead of glass hood 1.36-1.62), 3 price tags with menu_card.png; "
                  "carrot_cake decimation guarded (raw mesh degenerates; explode-guard)."),
        "tris": tris,
        "reduce_stats": _STATS,
    }


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _pal = MAT.palette()
    res = build(P, C, _pal, {})
    C.log("built", res["tris"], "tris", res.get("reduce_stats"))
    # 自检机位按 P.DISPLAY 动态推导，柜子被移动后不用手改坐标
    X0, X1 = P.DISPLAY["x"]
    Y0, Y1 = P.DISPLAY["y"]
    cx = (X0 + X1) / 2.0
    cy = (Y0 + Y1) / 2.0
    C.selfcheck(MODULE, res["objects"], outdir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "renders", "modules"),
                res=(960, 720), samples=32,
                views=[
                    # 机位按 P.DISPLAY 动态算：Lead 调柜子位置后自检图自动跟上，
                    # 不会像上一版那样还对着旧坐标拍空景。
                    {"name": "persp",
                     "from": (cx + 0.72, cy - 1.24, 1.62), "look": (cx, cy, 0.92),
                     "lens": 32},
                    {"name": "front",
                     "from": (cx, cy - 1.30, 1.18), "look": (cx, cy, 0.86),
                     "lens": 34},
                    {"name": "detail",
                     "from": (X0 - 0.02, cy - 0.85, 1.02), "look": (X0 + 0.18, cy, 0.60),
                     "lens": 46},
                    {"name": "top",
                     "from": (cx, cy - 0.75, 2.62), "look": (cx, cy, 0.88),
                     "lens": 42},
                ])
