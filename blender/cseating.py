"""
cseating.py — C_Seating：5 组圆桌椅 + 蕾丝桌布 + 桌面小物 + 2 张吧台凳

口径（CONTRACT §1.1）
--------------------
  台面上表面精确 = P.TABLE_H (0.74)；桌半径 = P.TABLE_R (0.38)。
  圆桌为**程序化车木 bistro 桌**（lathe 台面 + 车木中柱 + 黑铁底座 + 4 弯脚 + 铜球脚尖），
  而不是导入 round_wooden_table_01：那个模型直径 1.4 m / 高 1.0 m / 8.6k tris，
  要同时缩到「半径 0.38 + 台面 0.74」只能做非等比挤压，车木中柱会被压扁。
  椅子导入 painted_wooden_chair_01（724 tris，做旧白漆木椅），每把补软垫 + 椅背蝴蝶结。
  靠窗桌（window=True）椅子只放在桌子靠室内一侧（+Y 半区），玻璃窗面不被挡住。

对象结构（QC 按桌/椅判干涉，网页也可单独控制）
--------------------------------------------
  TB_01..TB_05            每张桌 1 个对象（台面+中柱+底座+脚，合并）
  TB_0x_Cloth             桌布 1 个对象
  TB_0x_Vase/_Menu/_Sugar 桌面小物各 1 个对象
  CH_0x_n                 每把椅子 1 个对象（导入模型本体）
  CH_0x_n_Deco            该椅的软垫+系带+蝴蝶结（1 个对象）
  CH_Stool_1/2            2 张吧台凳

运行：blender -b -P cseating.py
      MAID_SEAT_ONLY=TB_01,CH_Stool blender -b -P cseating.py   # 只建指定桌/凳
环境变量 MAID_SEAT_OUT 可改预览输出目录。
"""
import bpy
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() \
    else os.getcwd()
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ccore as C
import cprop as P
import cmat as MAT
import cassets as A

MODULE = "cseating"
OWNER = "furn-modeler"
TRI_BUDGET = 70000
COL = "C_Seating"

D2R = C.D2R
PI = C.PI
TAU = C.TAU
Vector = C.Vector
Matrix = C.Matrix

# ── 椅子实测解剖（probe：painted_wooden_chair_01 归一 target_height=0.92 后）──
CH_SEAT_Z = 0.4301          # 座面上表面
CH_SEAT_Y0 = -0.185         # 座面前沿（模型 −Y 为正面）
CH_SEAT_Y1 = 0.150          # 座面后沿
CH_SEAT_YC = (CH_SEAT_Y0 + CH_SEAT_Y1) / 2      # = −0.0175
CH_BACK_Y = 0.225           # ★ 实测修正：原 0.257 让蝴蝶结/系带悬在椅背后 31.7mm
                            #   椅背木板前表面只到 y=0.2123，0.225 让蝴蝶结底面 0.212 贴住板面           # 靠背平面 y（背板在 +Y 侧）
CH_BACK_Z = 0.655           # 系带 / 蝴蝶结高度

# ── 桌布 / 小物基准高度 ──────────────────────────────────────────────
CLOTH_BOT = P.TABLE_H + 0.0005          # 桌布贴桌面（0.7405，与台面留 0.5mm 不共面）
CLOTH_TOP = CLOTH_BOT + 0.0028          # 桌布上表面 0.7433
PROP_Z = CLOTH_TOP - 0.0002             # 小物落点（略微压进桌布，绝不悬空）

# ── 每桌椅子布置角（θ：位置 = 桌心 + R·(sinθ, cosθ)）─────────────────
RING_WIN2 = (-58.0, 58.0)               # 靠窗 2 椅：都在桌子靠室内一侧
RING_WIN3 = (-70.0, 0.0, 70.0)
RING_ANY3 = P.TABLE_RING_ANG            # 非靠窗 3 椅：全环均布 (0,118,242)

_MAT_CACHE = {}


# ══════════════════════════════════════════════════════════════════════
# 基础设施
# ══════════════════════════════════════════════════════════════════════
def _pbr(name, **kw):
    if name not in _MAT_CACHE:
        _MAT_CACHE[name] = MAT.M.pbr(name, **kw)
    return _MAT_CACHE[name]


def _rz(dx, dy, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    return (dx * ca - dy * sa, dx * sa + dy * ca)


def _uv(ob, scale=1.0):
    """世界坐标平铺 UV，并确保该 UV 层是**渲染激活**层。

    坑：多次 join 之后 uv_layers[0].active_render 可能是 False，
    此时 Image Texture 节点取不到 UV → 贴图渲染成纯色（菜单立牌就是这样变灰的）。
    """
    if ob is None or ob.type != "MESH" or not len(ob.data.polygons):
        return ob
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active or (me.uv_layers[0] if len(me.uv_layers) else None)
    if uvl is None:
        return ob
    for u in me.uv_layers:
        u.active_render = (u == uvl)
    uvl.active = True
    Mw = ob.matrix_world
    for poly in me.polygons:
        ax = max(range(3), key=lambda i: abs(poly.normal[i]))
        for li in poly.loop_indices:
            v = Mw @ me.vertices[me.loops[li].vertex_index].co
            if ax == 2:
                u, w = v.x, v.y
            elif ax == 1:
                u, w = v.x, v.z
            else:
                u, w = v.y, v.z
            uvl.data[li].uv = (u / scale, w / scale)
    return ob


def _fix_uv_active(ob):
    """只修 UV 层的渲染激活标志，不动 UV 数值（给菜单这类自带 0..1 UV 的物体）。"""
    if ob is None or ob.type != "MESH":
        return ob
    me = ob.data
    if not me.uv_layers:
        return ob
    uvl = me.uv_layers[0]
    for u in me.uv_layers:
        u.active_render = False
    uvl.active_render = True
    uvl.active = True
    return ob


def _join(objs, name, origin=(0.0, 0.0, 0.0)):
    """合并并把原点归到 origin（局部坐标建模的基准点）。

    注意两个坑：
    1) bpy join 之后物体原点/旋转 = 参与合并的**活动物体**的；
    2) 直接把 location 设成世界坐标会把其余零件整体错位。
    所以先 set_origin 归零，再由 _place() 统一摆位。
    """
    objs = [o for o in objs if o is not None]
    if not objs:
        return None
    if len(objs) == 1:
        ob = objs[0]
        ob.name = name
    else:
        ob = C.join(objs, name, COL)
    bpy.context.view_layer.update()
    # 先把当前 transform 烘进网格（此时物体原点还在活动子物体那），
    # 再把原点挪到基准点 origin
    C.apply_transforms([ob], loc=True, rot=True, scale=True)
    bpy.context.view_layer.update()
    C.set_origin(ob, origin)
    bpy.context.view_layer.update()
    return ob


def _place(ob, loc, rot=(0, 0, 0)):
    """把已烘好 transform 的物体摆到 loc / rot（不再依赖 join 残留的旋转）。"""
    if ob is None:
        return ob
    C.apply_transforms([ob], loc=True, rot=True, scale=True)
    ob.location = loc
    ob.rotation_euler = rot
    bpy.context.view_layer.update()
    return ob


def _true_z(ob):
    """真实世界 min/max z（bound_box 对旋转体会偏大）。"""
    Mw = ob.matrix_world
    zs = [(Mw @ v.co).z for v in ob.data.vertices]
    return (min(zs), max(zs)) if zs else (0.0, 0.0)


def _true_aabb(ob):
    Mw = ob.matrix_world
    pts = [Mw @ v.co for v in ob.data.vertices]
    if not pts:
        return [0, 0, 0], [0, 0, 0]
    mn = [min(p[i] for p in pts) for i in range(3)]
    mx = [max(p[i] for p in pts) for i in range(3)]
    return [round(v, 5) for v in mn], [round(v, 5) for v in mx]


def _print_quad(name, w, h, mat, col, rot=(0, 0, 0), loc=(0, 0, 0)):
    """0..1 正立 UV 的印刷面板：局部法线 −Y；x→u，z→v（不镜像、不倒置）。"""
    ob = C.quads(name,
                 verts=[(-w / 2, 0, -h / 2), (w / 2, 0, -h / 2),
                        (w / 2, 0, h / 2), (-w / 2, 0, h / 2)],
                 faces=[(0, 1, 2, 3)], mat=mat, col=col, shade="flat")
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active or me.uv_layers[0]
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uvl.data[li].uv = ((v.x + w / 2) / w, (v.z + h / 2) / h)
    ob.rotation_euler = rot
    ob.location = loc
    return ob


def _wave_ring(n, r, z, amp_z=0.0, wave_n=9, amp_r=0.0):
    pts = []
    for i in range(n):
        a = TAU * i / n
        k = math.sin(wave_n * a)
        pts.append(((r + amp_r * k) * math.cos(a),
                    (r + amp_r * k) * math.sin(a),
                    z + amp_z * k))
    return pts


# 椅子绕自身原点（脚底中心）的水平包络半径——probe 实测：
#   painted_wooden_chair_01 在 target_height=0.92 下，前后 ±0.30 / 左右 ±0.22
CH_FOOT_RX = 0.235          # x 半宽 + 余量
CH_FOOT_RY = 0.315          # y 半深 + 余量


def _chair_hits_wall(cx, cy, theta_deg):
    """该角度下椅子是否越出房间（留 WALL_GAP 缝）。"""
    th = theta_deg * D2R
    px = cx + P.TABLE_RING_R * math.sin(th)
    py = cy + P.TABLE_RING_R * math.cos(th)
    yaw = -th
    ca, sa = math.cos(yaw), math.sin(yaw)
    # 4 个角点 + 2 个轴向极值
    ex = abs(ca) * CH_FOOT_RX + abs(sa) * CH_FOOT_RY
    ey = abs(sa) * CH_FOOT_RX + abs(ca) * CH_FOOT_RY
    gap = 0.030
    return (px - ex < P.ROOM_X[0] + gap or px + ex > P.ROOM_X[1] - gap or
            py - ey < P.ROOM_Y[0] + gap or py + ey > P.ROOM_Y[1] - gap)


def _fit_ring(cx, cy, angs, step_deg=6.0):
    """把整圈椅子一起绕桌心转，找一个所有椅子都不撞墙的相位。

    返回 (angles, applied_shift_deg)。若整圈都放不下（桌贴墙太紧），
    退回原角度并让 build 报 WARN——不静默挪位。
    """
    cand = []
    for k in range(0, 360, int(step_deg)):
        sh = k if k <= 180 else k - 360
        cand.append(sh)
    cand.sort(key=abs)                    # 优先小角度偏移
    for sh in cand:
        if not any(_chair_hits_wall(cx, cy, a + sh) for a in angs):
            return tuple(a + sh for a in angs), float(sh)
    return tuple(angs), None


# ══════════════════════════════════════════════════════════════════════
# 圆桌（车木中柱 + 圆盘台面 + 黑铁底座弯脚 + 黄铜束环）
# ══════════════════════════════════════════════════════════════════════
def make_table(name, cx, cy, M, col):
    """局部坐标建模 → 合并 → 平移到 (cx,cy)。台面 z 精确 0.74，最低点精确 0。"""
    objs = []
    z_top = P.TABLE_H
    r = P.TABLE_R
    t = 0.038
    z0 = z_top - t
    m_wood = M["wood_table"]
    m_iron = M["black_metal"]
    m_brass = M["brass"]

    # 台面（平底 + 圆边 + 平面）
    prof_top = [
        (0.0, z0), (r - 0.070, z0), (r - 0.030, z0 + 0.004),
        (r - 0.012, z0 + 0.010), (r - 0.002, z0 + 0.019),
        (r, z_top - 0.014), (r - 0.006, z_top - 0.005),
        (r - 0.018, z_top), (0.0, z_top),
    ]
    objs.append(C.lathe(f"{name}_Top", prof_top, segs=48, mat=m_wood, col=col,
                        close_bottom=False, close_top=False, shade="smooth"))

    # 车木中柱
    prof_ped = [
        (0.0, 0.048), (0.132, 0.048), (0.134, 0.062), (0.118, 0.074),
        (0.086, 0.086), (0.064, 0.110), (0.052, 0.156), (0.049, 0.214),
        (0.064, 0.248), (0.064, 0.292), (0.047, 0.328), (0.044, 0.396),
        (0.058, 0.438), (0.058, 0.496), (0.082, 0.532), (0.082, 0.582),
        (0.118, 0.624), (0.132, 0.648), (0.120, 0.672), (0.0, 0.678),
    ]
    objs.append(C.lathe(f"{name}_Pedestal", prof_ped, segs=32, mat=m_wood, col=col,
                        close_bottom=False, close_top=False, shade="smooth"))

    # 黑铁底座毂（底面 z=0）+ 铜箍
    hub_prof = [(0.0, 0.0), (0.168, 0.0), (0.172, 0.010), (0.160, 0.030),
                (0.140, 0.044), (0.126, 0.056), (0.0, 0.056)]
    objs.append(C.lathe(f"{name}_Hub", hub_prof, segs=28, mat=m_iron, col=col,
                        close_bottom=False, close_top=False, shade="smooth"))
    objs.append(C.ring_tube(f"{name}_Collar", R=0.0505, r=0.0065, segs=22,
                            rsegs=6, loc=(0, 0, 0.392), mat=m_brass, col=col))

    # 4 只弯脚：脚尖铜球半径 0.021、球心 z=0.021 → 最低点精确 0
    for i in range(4):
        a = TAU * i / 4 + PI / 4
        ca, sa = math.cos(a), math.sin(a)
        objs.append(C.tube_along(
            f"{name}_Foot{i}",
            [(0.112 * ca, 0.112 * sa, 0.053),
             (0.190 * ca, 0.190 * sa, 0.046),
             (0.262 * ca, 0.262 * sa, 0.032),
             (0.300 * ca, 0.300 * sa, 0.026)],
            radius=0.017, segs=8, mat=m_iron, col=col))
        objs.append(C.sphere(f"{name}_FootTip{i}", r=0.0210, segs=12, rings=7,
                             loc=(0.300 * ca, 0.300 * sa, 0.0210),
                             mat=m_brass, col=col))

    body = _join(objs, name)
    _place(body, (cx, cy, 0.0))
    _uv(body, 0.9)
    return body, z_top


# ══════════════════════════════════════════════════════════════════════
# 椅子（外部模型 + 软垫 + 椅背系带/蝴蝶结）
# ══════════════════════════════════════════════════════════════════════
def make_chair(name, cx, cy, yaw, M, col):
    """返回 [body, deco]；body 正面（模型 −Y）经 yaw 后朝向桌心。"""
    m_cushion = M["gingham"]
    m_ribbon = M["gingham"]

    got = A.import_model("painted_wooden_chair_01", col=col,
                         target_height=P.CHAIR_BACK_H, name_prefix=name)
    if got:
        body = got[0]
        body.location = (cx, cy, 0.0)
        body.rotation_euler = (0, 0, yaw)
        bpy.context.view_layer.update()
        mnz, _ = _true_z(body)
        body.location.z -= mnz                    # 脚底精确 0（误差 <1mm）
    else:                                          # 兜底极简椅
        parts = [C.box(f"{name}_Seat", (0.42, 0.42, 0.035),
                       loc=(0, 0, CH_SEAT_Z - 0.0175), mat=M["wood_oak"], col=col,
                       bevel=0.006)]
        for dx in (-0.17, 0.17):
            for dy in (-0.17, 0.17):
                parts.append(C.box(f"{name}_Leg", (0.035, 0.035, CH_SEAT_Z - 0.02),
                                   loc=(dx, dy, (CH_SEAT_Z - 0.02) / 2),
                                   mat=M["wood_oak"], col=col))
        parts.append(C.box(f"{name}_Back", (0.42, 0.03, 0.46),
                           loc=(0, CH_BACK_Y, 0.68), mat=M["wood_oak"], col=col,
                           bevel=0.006))
        body = _join(parts, name)
        _place(body, (cx, cy, 0.0), (0, 0, yaw))

    # ── 装饰（全部在局部坐标建，最后整体旋转平移到椅子上）──────────
    deco = []
    # 软垫：底 1mm 压进座面（不悬空），尺寸小于座面
    deco.append(C.box(f"{name}_Cushion", (0.362, 0.338, 0.055),
                      loc=(0, CH_SEAT_YC, CH_SEAT_Z - 0.001 + 0.0275),
                      mat=m_cushion, col=col, bevel=0.020, segs=3, shade="smooth"))
    deco.append(C.sphere(f"{name}_Tuft", r=0.011, segs=10, rings=6,
                         scale=(1.0, 1.0, 0.55),
                         loc=(0, CH_SEAT_YC, CH_SEAT_Z + 0.052),
                         mat=m_cushion, col=col))
    # 椅背系带 + 蝴蝶结
    deco.append(C.box(f"{name}_Sash", (0.392, 0.026, 0.042),
                      loc=(0, CH_BACK_Y, CH_BACK_Z), mat=m_ribbon, col=col,
                      bevel=0.007, segs=2, shade="smooth"))
    deco.append(C.box(f"{name}_Knot", (0.048, 0.032, 0.042),
                      loc=(0, CH_BACK_Y + 0.020, CH_BACK_Z), mat=m_ribbon,
                      col=col, bevel=0.012, segs=2, shade="smooth"))
    for s in (-1, 1):
        deco.append(C.box(f"{name}_Loop{s}", (0.092, 0.026, 0.052),
                          loc=(0.058 * s, CH_BACK_Y + 0.024, CH_BACK_Z + 0.003),
                          rot=(0, 0, 24 * D2R * s), mat=m_ribbon, col=col,
                          bevel=0.012, segs=2, shade="smooth"))
    for s in (-1, 1):
        deco.append(C.box(f"{name}_Tail{s}", (0.032, 0.008, 0.115),
                          loc=(0.030 * s, CH_BACK_Y + 0.027, CH_BACK_Z - 0.083),
                          rot=(0, 0, 9 * D2R * s), mat=m_ribbon, col=col,
                          bevel=0.003, segs=1, shade="smooth"))
    decobj = _join(deco, f"{name}_Deco")
    _place(decobj, (cx, cy, 0.0), (0, 0, yaw))
    _uv(decobj, 0.4)          # 装饰件用世界平铺 UV（格子布需要）
    _fix_uv_active(decobj)

    # 把坐垫/系带并进椅子本体：每把椅子仍是**独立的一个对象**（QC 按椅判干涉），
    # 但 min_z 就是脚底 0，不会被判「悬空挂件」。
    body.location = (cx, cy, 0.0)
    body.rotation_euler = (0, 0, yaw)
    bpy.context.view_layer.update()
    merged = C.join([body, decobj], name, COL)   # 活动物体=body → 保留椅子的位姿
    merged.location = (cx, cy, 0.0)
    merged.rotation_euler = (0, 0, yaw)
    bpy.context.view_layer.update()
    mnz, _ = _true_z(merged)
    merged.location.z -= mnz                     # 再次确保脚底精确 0
    bpy.context.view_layer.update()
    # 注意：不要再跑 _uv()！椅子模型自带 UVMap 贴图，重投影会把木纹/做旧漆打乱。
    # join 时两边 UV 层同名（"UVMap"）已自动合并，只需保证渲染激活。
    _fix_uv_active(merged)
    return [merged]


# ══════════════════════════════════════════════════════════════════════
# 蕾丝桌布（平铺盘面 + 波浪垂边），贴在桌面上，不落地
# ══════════════════════════════════════════════════════════════════════
def make_cloth(name, cx, cy, M, col):
    n = 63                              # 7 段/波 × 9 波
    r_cov = P.TABLETOP_LACE_R           # 0.44
    drop = P.TABLETOP_CLOTH_DROP        # 0.10
    m_lace = M["lace"]
    z_b, z_t = CLOTH_BOT, CLOTH_TOP

    disc = C.lathe(f"{name}_Disc",
                   [(0.0, z_b), (r_cov - 0.045, z_b + 0.0004),
                    (r_cov - 0.018, z_b + 0.0026), (r_cov - 0.004, z_t - 0.0010),
                    (r_cov, z_t - 0.0004), (r_cov, z_t), (0.0, z_t)],
                   segs=n, mat=m_lace, col=col,
                   close_bottom=False, close_top=False, shade="smooth")

    zs = [z_t, z_t - drop * 0.26, z_t - drop * 0.58, z_t - drop * 0.82,
          z_t - drop * 0.97, z_t - drop, z_t - drop * 0.94]
    rs = [r_cov, r_cov + 0.002, r_cov + 0.005, r_cov + 0.010,
          r_cov + 0.015, r_cov + 0.014, r_cov + 0.008]
    a_r = [0.0, 0.003, 0.006, 0.009, 0.011, 0.011, 0.008]
    a_z = [0.0, 0.005, 0.010, 0.015, 0.019, 0.020, 0.016]
    secs = [_wave_ring(n, rr, zz, amp_z=az, wave_n=9, amp_r=ar)
            for zz, rr, ar, az in zip(zs, rs, a_r, a_z)]
    skirt = C.loft(f"{name}_Skirt", secs, closed_ring=True, cap=False,
                   mat=m_lace, col=col, shade="smooth")

    ob = _join([disc, skirt], name)
    _place(ob, (cx, cy, 0.0))
    _uv(ob, 0.55)
    return ob


# ══════════════════════════════════════════════════════════════════════
# 桌面小物（局部坐标建 → 平移到落点）
# ══════════════════════════════════════════════════════════════════════
def make_vase(name, x, y, z0, yaw, M, col):
    objs = []
    r, h = P.VASE_R, P.VASE_H
    objs.append(C.lathe(f"{name}_Vase",
                        [(0.0, 0.0), (r * 0.70, 0.0), (r * 0.94, 0.012),
                         (r, 0.052), (r * 0.84, 0.100), (r * 0.55, 0.136),
                         (r * 0.58, h - 0.005), (r * 0.64, h)],
                        segs=22, mat=M["porcelain"], col=col,
                        close_bottom=True, close_top=False, shade="smooth"))
    objs.append(C.cyl(f"{name}_Water", r=r * 0.50, h=0.004, segs=14,
                      loc=(0, 0, 0.118), mat=M["glass"], col=col))
    zt = h - 0.010
    fx, fy = 0.016, 0.012
    tip = (fx, fy, zt + 0.160)
    objs.append(C.tube_along(f"{name}_Stem",
                             [(0, 0, zt), (fx * 0.55, fy * 0.55, zt + 0.085), tip],
                             radius=0.0026, segs=6, mat=M["stem"], col=col))
    for i, a in enumerate((-1.15, 1.15)):
        objs.append(C.sphere(f"{name}_Leaf{i}", r=0.028, segs=10, rings=6,
                             scale=(0.38, 1.0, 0.13), rot=(0, 0, a),
                             loc=(0.024 * math.sin(a), 0.024 * math.cos(a),
                                  zt + 0.070 + 0.014 * i),
                             mat=M["leaf_dark"], col=col))
    for i in range(5):
        a = TAU * i / 5
        objs.append(C.lathe(f"{name}_Petal{i}",
                            [(0.0, 0.0), (0.009, 0.0015), (0.014, 0.006),
                             (0.0, 0.0088)],
                            segs=8, loc=(tip[0] + 0.016 * math.cos(a),
                                         tip[1] + 0.016 * math.sin(a),
                                         tip[2] - 0.005),
                            mat=_pbr("MAT_Plant_Blossom", base="#F7DEE4",
                                     rough=0.55, sss=0.25),
                            col=col, shade="smooth"))
    objs.append(C.sphere(f"{name}_Core", r=0.008, segs=8, rings=5,
                         loc=tip, mat=M["brass"], col=col))
    ob = _join(objs, name)
    _place(ob, (x, y, z0), (0, 0, yaw))
    _uv(ob, 0.25)
    return ob


def make_menu_stand(name, x, y, z0, yaw, M, col, tex):
    """A 字菜单立牌：两块薄板在顶部铰接、底部张开；正面贴 menu_card（文字正立）。"""
    w, h = P.MENU_CARD_W, P.MENU_CARD_H
    tilt = 30 * D2R
    m_paper = M["paper_menu"]
    m_print = _pbr("MAT_Paper_MenuCard", base="#FBF6EC", diff=tex, rough=0.74) \
        if tex else m_paper
    hinge_z = h * math.cos(tilt)          # 局部：底面在 z=0
    objs = []
    for tag, sgn in (("F", -1), ("B", 1)):
        R = Matrix.Rotation(sgn * tilt, 3, "X")
        ctr = Vector((0, 0, hinge_z)) - R @ Vector((0, 0, h / 2))
        objs.append(C.box(f"{name}_Card{tag}", (w, 0.0032, h),
                          loc=tuple(ctr), rot=(sgn * tilt, 0, 0),
                          mat=m_paper, col=col, bevel=0.0015, segs=1))
        if tag == "F" and tex:
            nrm = R @ Vector((0.0, -1.0, 0.0))
            objs.append(_print_quad(f"{name}_Print", w * 0.93, h * 0.93, m_print,
                                    col, rot=(-tilt, 0, 0),
                                    loc=tuple(ctr + nrm * 0.0040)))
    objs.append(C.box(f"{name}_Clamp", (w * 0.94, 0.010, 0.011),
                      loc=(0, 0, hinge_z + 0.004), mat=M["brass"], col=col,
                      bevel=0.003, segs=1, shade="smooth"))
    ob = _join(objs, name)
    _place(ob, (x, y, z0), (0, 0, yaw))
    _fix_uv_active(ob)          # 保留 _print_quad 的 0..1 UV，只修激活标志
    return ob


def make_sugar(name, x, y, z0, M, col):
    r = P.SUGAR_BOWL_R
    objs = [C.lathe(f"{name}_Bowl",
                    [(0.0, 0.0), (r * 0.54, 0.0), (r * 0.70, 0.008),
                     (r * 0.92, 0.030), (r, 0.050), (r * 0.97, 0.055)],
                    segs=22, mat=M["porcelain"], col=col, shade="smooth"),
            C.lathe(f"{name}_Lid",
                    [(0.0, 0.0), (r * 0.99, 0.0), (r * 0.92, 0.010),
                     (r * 0.44, 0.021), (0.0, 0.024)],
                    segs=22, loc=(0, 0, 0.056), mat=M["porcelain"], col=col,
                    close_bottom=False, shade="smooth"),
            C.sphere(f"{name}_Knob", r=0.0095, segs=10, rings=6,
                     loc=(0, 0, 0.086), mat=M["brass"], col=col),
            C.tube_along(f"{name}_Spoon",
                         [(0.050, -0.010, 0.062), (0.036, -0.024, 0.040),
                          (0.020, -0.040, 0.016)],
                         radius=0.0032, segs=5, mat=M["steel"], col=col),
            C.sphere(f"{name}_SpoonBowl", r=0.0115, segs=10, rings=6,
                     scale=(1.0, 1.0, 0.42), rot=(0, 0, 30 * D2R),
                     loc=(0.014, -0.048, 0.011), mat=M["steel"], col=col)]
    ob = _join(objs, name)
    _place(ob, (x, y, z0))
    _uv(ob, 0.2)
    return ob


# ══════════════════════════════════════════════════════════════════════
# 吧台凳（坐面 0.74 + 4 条外八木腿 + 铜脚圈），底端精确落地
# ══════════════════════════════════════════════════════════════════════
def make_stool(name, cx, cy, M, col):
    objs = []
    seat_z = P.BAR_STOOL["seat_z"]
    r = P.BAR_STOOL["r"]
    m_wood = M["wood_dark"]
    m_brass = M["brass"]
    objs.append(C.lathe(f"{name}_Seat",
                        [(0.0, seat_z - 0.062), (r - 0.026, seat_z - 0.062),
                         (r - 0.006, seat_z - 0.048), (r, seat_z - 0.026),
                         (r - 0.006, seat_z - 0.008), (r - 0.024, seat_z),
                         (0.0, seat_z + 0.002)],
                        segs=30, mat=m_wood, col=col,
                        close_bottom=False, close_top=False, shade="smooth"))
    leg_r = 0.0165
    for i in range(4):
        a = TAU * i / 4 + PI / 4
        ca, sa = math.cos(a), math.sin(a)
        objs.append(C.tube_along(
            f"{name}_Leg{i}",
            [(0.098 * ca, 0.098 * sa, seat_z - 0.070),
             (0.150 * ca, 0.150 * sa, 0.380),
             (0.176 * ca, 0.176 * sa, 0.020)],
            radius=leg_r, segs=8, mat=m_wood, col=col))
        # 铜脚套：半球贴地，保证最低点 = 0
        objs.append(C.sphere(f"{name}_LegFoot{i}", r=leg_r, segs=10, rings=6,
                             loc=(0.176 * ca, 0.176 * sa, leg_r),
                             mat=m_brass, col=col))
    objs.append(C.ring_tube(f"{name}_FootRing", R=0.170, r=0.0085, segs=26,
                            rsegs=6, loc=(0, 0, 0.190), mat=m_brass, col=col))
    objs.append(C.ring_tube(f"{name}_SeatRing", R=r - 0.016, r=0.0065, segs=26,
                            rsegs=5, loc=(0, 0, seat_z - 0.060),
                            mat=m_brass, col=col))
    ob = _join(objs, name)
    _place(ob, (cx, cy, 0.0))
    _uv(ob, 0.55)
    return ob


# ══════════════════════════════════════════════════════════════════════
# 主构建
# ══════════════════════════════════════════════════════════════════════
def build(P_, C_, M_, assets, only=None):
    """P_=cprop, C_=ccore, M_=palette, assets=dict。only=[...] 只建指定桌/凳。"""
    C.wipe_collection(COL)
    C.ensure_collection(COL)
    _MAT_CACHE.clear()
    random.seed(20261021)

    only = set(only) if only else None
    objs, colliders, anchors, notes = [], [], {}, []

    def want(key):
        return (only is None) or (key in only) or ("*" in only)

    def upd():
        bpy.context.view_layer.update()

    menu_tex = P.tex_gen_path("menu_card")
    if menu_tex is None:
        notes.append("WARN menu_card.png missing → plain paper card")

    # ── 1. 五组圆桌 ────────────────────────────────────────────────
    chair_log = []
    for tbl in P.TABLES:
        tname = tbl["name"]
        if not want(tname):
            continue
        cx, cy = tbl["x"], tbl["y"]

        tbl_ob, z_top = make_table(tname, cx, cy, M_, COL)
        objs.append(tbl_ob)
        upd()
        mn, mx = _true_aabb(tbl_ob)
        colliders.append({"name": tname, "aabb": [mn, mx], "kind": "solid"})

        objs.append(make_cloth(f"{tname}_Cloth", cx, cy, M_, COL))
        anchors[f"table_{tname[-2:]}_top"] = [cx, cy, round(z_top, 4)]

        # 椅子：先按偏好角度，再自动找一圈不撞墙的相位（墙外留 30mm）
        n = tbl["chairs"]
        if n == 2:
            base = RING_WIN2 if tbl["window"] else (0.0, 180.0)
        elif tbl["window"]:
            base = RING_WIN3
        else:
            base = RING_ANY3
        angs, shifted = _fit_ring(cx, cy, tuple(base[:n]))
        chair_log.append({"t": tname, "base": list(base[:n]),
                          "used": [round(a, 1) for a in angs],
                          "shift": round(shifted, 1)})
        for i, adeg in enumerate(angs):
            th = adeg * D2R
            px = cx + P.TABLE_RING_R * math.sin(th)
            py = cy + P.TABLE_RING_R * math.cos(th)
            cname = f"CH_{tname[-2:]}_{i + 1}"
            ch = make_chair(cname, px, py, -th, M_, COL)
            objs += ch
            upd()
            mn, mx = _true_aabb(ch[0])
            colliders.append({"name": cname, "aabb": [mn, mx], "kind": "soft"})
            anchors[cname] = [round(px, 4), round(py, 4), 0.0]

        # 桌面小物（r ≤ 0.26 内圈）
        objs.append(make_vase(f"{tname}_Vase", cx + 0.010, cy + 0.118, PROP_Z,
                              12 * D2R, M_, COL))
        objs.append(make_menu_stand(f"{tname}_Menu", cx - 0.030, cy - 0.215,
                                    PROP_Z, 0.0, M_, COL, menu_tex))
        objs.append(make_sugar(f"{tname}_Sugar", cx + 0.196, cy + 0.026, PROP_Z,
                               M_, COL))
        upd()

    # ── 2. 吧台凳 2 张 ────────────────────────────────────────────
    if want("CH_Stool"):
        for i, sx in enumerate(P.BAR_STOOL["x"]):
            nm = f"CH_Stool_{i + 1}"
            objs.append(make_stool(nm, sx, P.BAR_STOOL["y"], M_, COL))
            upd()
            mn, mx = _true_aabb(bpy.data.objects[nm])
            colliders.append({"name": nm, "aabb": [mn, mx], "kind": "solid"})
            anchors[nm] = [sx, P.BAR_STOOL["y"], P.BAR_STOOL["seat_z"]]

    upd()

    # ── 3. 统计 + 硬指标自检 ──────────────────────────────────────
    tris = C.tri_count(objs)
    floor_bad, room_bad = [], []
    PROPS = ("Vase", "Menu", "Sugar")
    for ob in objs:
        if ob is None or ob.type != "MESH":
            continue
        nm = ob.name
        mnz, mxz = _true_z(ob)
        # 落地件（桌/椅/凳本体的 min_z 必须 ∈ [−2mm, +2mm]）
        is_floor_part = nm.startswith(("TB_0", "CH_")) and not nm.endswith("_Cloth") \
            and not nm.endswith("_Deco") \
            and not any(nm.endswith(p) for p in PROPS)
        if is_floor_part and not (-0.002 <= mnz <= 0.002):
            floor_bad.append((nm, round(mnz, 5)))
        # 房间边界（1 指宽余量）
        a, b = _true_aabb(ob)
        if a[0] < P.ROOM_X[0] + 0.02 or b[0] > P.ROOM_X[1] - 0.02 or \
                a[1] < P.ROOM_Y[0] + 0.02 or b[1] > P.ROOM_Y[1] - 0.02:
            room_bad.append((nm, [a[0], a[1]], [b[0], b[1]]))

    tops = []
    for tbl in P.TABLES:
        ob = bpy.data.objects.get(tbl["name"])
        if ob:
            tops.append((tbl["name"], round(_true_z(ob)[1], 4)))

    C.log(f"{MODULE}: {len(objs)} objects, {tris} tris (budget {TRI_BUDGET})")
    C.log(f"{MODULE}: table top z = {tops}")
    C.log(f"{MODULE}: cloth top z = {round(CLOTH_TOP, 4)}, props z = {round(PROP_Z, 4)}")
    for cl in chair_log:
        C.log(f"{MODULE}: chairs {cl['t']} base={cl['base']} used={cl['used']} "
              f"shift={cl['shift']}")
    if floor_bad:
        C.log(f"{MODULE}: FAIL floor contact {floor_bad[:12]}")
    else:
        C.log(f"{MODULE}: OK floor contact — all floor parts |min_z| <= 2mm")
    if room_bad:
        C.log(f"{MODULE}: WARN outside room {room_bad[:12]}")
    else:
        C.log(f"{MODULE}: OK room bounds — nothing crosses walls")

    notes.append("5 procedural turned-wood bistro tables, top z=%.2f exact, r=%.2f"
                 % (P.TABLE_H, P.TABLE_R))
    notes.append("13 painted chairs (724 tris each) + gingham cushion + back sash + bow")
    notes.append("lace cloth per table (top z=%.3f), props: vase+flower, A-frame "
                 "menu card (menu_card.png upright), sugar bowl+spoon" % CLOTH_TOP)
    notes.append("2 bar stools at seat_z=%.2f facing +Y" % P.BAR_STOOL["seat_z"])
    notes.append("window-table chairs stay on the room-side arc so the glass wall reads clear")

    return {"objects": [o for o in objs if o], "collections": [COL],
            "colliders": colliders, "anchors": anchors,
            "notes": "; ".join(notes), "tris": tris,
            "table_top_z": tops, "floor_fail": floor_bad, "room_warn": room_bad,
            "chair_rings": chair_log}


# ══════════════════════════════════════════════════════════════════════
def _closeup_menu(outdir, t):
    """菜单贴图近景核对图（低照度固定光，避免白纸过曝）。

    目的：证明 menu_card.png 的文字**正立、未镜像**。
    """
    import bmesh  # noqa: F401  （保持与 ccore 一致的依赖面）
    try:
        # 清掉 selfcheck 加的灯与地面，避免自适应功率继续干扰
        for nm in list(bpy.data.objects.keys()):
            if nm.startswith("QC_") or nm.startswith("T_CU_"):
                ob = bpy.data.objects.get(nm)
                if ob is not None:
                    bpy.data.objects.remove(ob, do_unlink=True)
        C._ensure_world(0.35)
        C._add_area("T_CU_Key", (t["x"] - 0.30, t["y"] - 1.05, 1.12),
                    (t["x"] - 0.030, t["y"] - 0.215, 0.81),
                    power=6.0, size=1.2, color=(1.0, 0.96, 0.90))
        C._add_area("T_CU_Fill", (t["x"] + 0.55, t["y"] - 0.85, 1.05),
                    (t["x"] - 0.030, t["y"] - 0.215, 0.81),
                    power=3.0, size=1.6, color=(0.92, 0.95, 1.0))
        sc = C.setup_engine("eevee", 32, (720, 720))
        try:
            sc.view_settings.view_transform = "Filmic"
        except Exception:
            pass
        cam = C.render_camera("T_CU_Cam", (t["x"] - 0.030, t["y"] - 0.62, 0.90),
                              (t["x"] - 0.030, t["y"] - 0.215, 0.81), 85)
        sc.camera = cam
        p = os.path.join(outdir, f"{MODULE}_menu_closeup.png")
        os.makedirs(outdir, exist_ok=True)
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        C.log("rendered", p)
    except Exception as e:  # pragma: no cover
        C.log("closeup render failed", e)


if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    M = MAT.palette()
    only = os.environ.get("MAID_SEAT_ONLY")
    only = only.split(",") if only else None
    res = build(P, C, M, {}, only=only)
    outdir = os.environ.get("MAID_SEAT_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "renders", "modules"))
    t = P.TABLES[0]
    views = [
        {"name": "persp", "from": (t["x"] + 1.55, t["y"] - 1.85, 1.58),
         "look": (t["x"], t["y"], 0.72), "lens": 40},
        {"name": "table", "from": (t["x"] + 0.34, t["y"] - 0.66, 1.08),
         "look": (t["x"], t["y"], 0.80), "lens": 55},
        {"name": "plan", "from": (0.05, 0.10, 6.60), "look": (0.05, 0.10, 0.0),
         "ortho": 8.9},
    ]
    C.selfcheck(MODULE, res["objects"], outdir=outdir, res=(960, 720), samples=24,
                views=views)
    # 菜单贴图近景单独一张：用固定低照度（selfcheck 的自适应灯会把白纸打过曝），
    # 目的是核对「文字正着读、没镜像、没倒置」。
    _closeup_menu(outdir, t)
