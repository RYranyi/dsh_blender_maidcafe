"""
cdecor.py — C_Decor：墙面/天花装饰与陈设

内容
----
1. 吊灯 ×3（吊线 + 灯罩 + 发光灯泡 + 吸顶盘）
2. 天花灯带 ×4（吊顶跌级内沿的暖光条）
3. 壁灯 ×3（墙座 + 支臂 + 灯罩 + 发光芯）
4. 黑板菜单（木框 + 板面贴 menu_blackboard，文字正立）+ 粉笔槽
5. 相框 ×2（右墙，贴 picture_art_01/02）
6. 门帘（4 片，中间 2 片贴 noren_welcome）+ 横杆 + 吊环
7. 风铃（玻璃罩 + 短册）
8. 书架（外模 wooden_bookshelf_worn）+ 书 + 立盘 + 小摆件
9. 窗帘 ×2（波浪截面 loft）
10. 吧台射灯 ×3 + 展示柜射灯 ×2（灯体，光由 clight 提供）
11. 盆栽（calathea 减面 + 陶盆；窗台小盆栽）
12. 伞架 + 2 把伞
13. 门边营业牌（sign_cafe）
"""
import bpy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
                else r"E:\dsh\maid_cafe\blender")
import ccore as C
import cprop as P
import cmat as MAT
from mathutils import Vector
import cassets as A

MODULE = "cdecor"
OWNER = "lead"
TRI_BUDGET = 60000
COL = "C_Decor"
D2R = C.D2R
PI = C.PI


# ══════════════════════════════════════════════════════════════════════
def _uv01(ob, flip_u=False, flip_v=False):
    """把平面/薄板的 UV 归一到 0..1（文字贴图必须正着）。"""
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active
    base = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    n = len(me.loops)
    for i in range(n):
        u, v = base[i % 4]
        if flip_u:
            u = 1.0 - u
        if flip_v:
            v = 1.0 - v
        uvl.data[i].uv = (u, v)
    return ob


def _tex_plane(name, w, h, loc, toward, tex_path, col, rough=0.8, lift=0.0,
               flip_u=False, flip_v=False, emissive=0.0):
    """贴图的薄平面（文字/画面）。toward 指定朝内方向。"""
    mat = MAT.M.pbr("MAT_Decor_" + name, diff=tex_path, rough=rough,
                    uv_scale=1.0)
    if emissive:
        MAT.set_in(MAT._bsdf_of(mat), "emission_color", C.hexc("#FFFFFF"))
        MAT.set_in(MAT._bsdf_of(mat), "emission_strength", emissive)
    ob = C.plane(name, sx=w, sy=h, loc=loc, toward=toward, mat=mat, col=col)
    _uv01(ob, flip_u=flip_u, flip_v=flip_v)
    return ob


# ══════════════════════════════════════════════════════════════════════
def _pendants(M_, col):
    objs = []
    m_brass = M_["brass"]
    m_shade = M_["shade"]
    m_bulb = M_["bulb"]
    for p in P.PENDANTS:
        x, y = p["x"], p["y"]
        z_shade = p["shade_z"]
        z_ceil = P.CEIL_RECESS_Z
        # 中央吊顶板（RM_CeilCenter）在 z_ceil-0.04 … z_ceil，底面 = z_ceil-0.04。
        # 吸顶盘/吊线必须止于该底面，否则会插进吊顶板（曾实测吊线穿入 20mm）。
        # 实测 RM_CeilCenter z=[2.82,2.86]，其底面就是 2.82；
        # 不能用 z_ceil-0.04（=2.96，会算到吊顶板内部，导致吊线穿 20mm）。
        ceil_bottom = 2.82
        r = p["r"]
        # 吸顶盘（顶面离吊顶底面留 0.5mm，避免顶点采样落进吊顶板）
        canopy_h = 0.025
        canopy_bot = ceil_bottom - 0.0005 - canopy_h
        objs.append(C.cyl(f"DC_PendantCanopy_{p['name']}", r=0.055, h=canopy_h, segs=20,
                          loc=(x, y, canopy_bot + canopy_h / 2.0),
                          mat=m_brass, col=col, bevel=0.004, bsegs=1))
        # 吊线（上端从吸顶盘底面起，下端接入灯罩顶）
        wire_top = canopy_bot + 0.004
        wire_bot = z_shade + 0.235
        objs.append(C.cyl(f"DC_PendantWire_{p['name']}", r=0.0045,
                          h=max(0.02, wire_top - wire_bot),
                          segs=8, loc=(x, y, (wire_top + wire_bot) / 2),
                          mat=M_["black_metal"], col=col))
        # 灯罩（浅碗/伞形，开口向下：从罩口边缘收到顶部的小口）
        shade = C.lathe(f"DC_PendantShade_{p['name']}",
                        [(r, 0.0), (r * 0.985, 0.016), (r * 0.90, 0.055),
                         (r * 0.74, 0.105), (r * 0.50, 0.150), (r * 0.26, 0.178),
                         (0.0, 0.186)],
                        segs=40, loc=(x, y, z_shade), mat=m_shade, col=col,
                        close_bottom=False, close_top=False)
        C.shade_auto(shade, 30 * D2R)
        objs.append(shade)
        # 罩内灯泡（露在罩口下方一点）
        objs.append(C.sphere(f"DC_PendantBulb_{p['name']}", r=r * 0.26, segs=18, rings=12,
                             loc=(x, y, z_shade + 0.045), mat=m_bulb, col=col))
        # 罩口金属圈
        objs.append(C.ring_tube(f"DC_PendantRim_{p['name']}", R=r * 0.99, r=0.007,
                                segs=40, rsegs=6, loc=(x, y, z_shade + 0.004),
                                mat=m_brass, col=col))
        # 罩顶装饰帽 + 吊线接头
        objs.append(C.lathe(f"DC_PendantCap_{p['name']}",
                            [(0.0, 0.0), (r * 0.20, 0.0), (r * 0.16, 0.03), (0.0, 0.04)],
                            segs=20, loc=(x, y, z_shade + 0.186), mat=m_brass, col=col))
        objs.append(C.cyl(f"DC_PendantNeck_{p['name']}", r=0.012, h=0.045, segs=10,
                          loc=(x, y, z_shade + 0.215), mat=m_brass, col=col))
    return objs


def _cove(M_, col):
    objs = []
    m_led = M_["led"]
    rec = 0.55
    z = P.CEIL_RECESS_Z + 0.02
    x0, x1 = P.ROOM_X
    y0, y1 = P.ROOM_Y
    # 跌级外圈内沿（croom 的 RM_CeilRim* 边界）：
    #   前/后沿 = y0+rec / y1-rec，左/右沿 = x0+rec / x1-rec
    # 灯带条宽 0.05，若直接贴边会嵌进跌级板 5mm（实测 DC_Cove_N/S↔RM_CeilRimN/S 5mm）。
    # 这里让灯带整条退到跌级内沿以内、留 1.5mm 装配间隙，视觉上仍藏在灯槽里。
    clear = 0.0015
    hw = 0.025                      # 灯带半宽（0.05/2）
    y_in_s = y0 + rec               # 南侧跌级内沿
    y_in_n = y1 - rec               # 北侧跌级内沿
    x_in_w = x0 + rec               # 西侧跌级内沿
    x_in_e = x1 - rec               # 东侧跌级内沿
    # 4 条：沿 X 两条（前后），沿 Y 两条（左右）
    objs.append(C.box("DC_Cove_S", (x1 - x0 - rec * 2, 0.05, 0.02),
                      loc=(0, y_in_s + clear + hw, z), mat=m_led, col=col))
    objs.append(C.box("DC_Cove_N", (x1 - x0 - rec * 2, 0.05, 0.02),
                      loc=(0, y_in_n - clear - hw, z), mat=m_led, col=col))
    objs.append(C.box("DC_Cove_W", (0.05, y1 - y0 - rec * 2, 0.02),
                      loc=(x_in_w + clear + hw, 0, z), mat=m_led, col=col))
    objs.append(C.box("DC_Cove_E", (0.05, y1 - y0 - rec * 2, 0.02),
                      loc=(x_in_e - clear - hw, 0, z), mat=m_led, col=col))
    return objs


def _wall_lamps(M_, col):
    objs = []
    m_brass = M_["brass"]
    m_shade = M_["shade"]
    m_bulb = M_["bulb"]
    for i, w in enumerate(P.WALL_LAMPS):
        wall = w["wall"]
        axis = w.get("face", "+X")          # 朝室内方向
        # 统一算出：墙座中心 base、向外(室内)单位向量 outv、以及「墙座前表面」根点 root
        if wall == "-X":
            base = Vector((P.ROOM_X[0] + 0.022, w["y"], w["z"]))
            outv = Vector((1.0, 0.0, 0.0))
            base_rot = (0.0, PI / 2, 0.0)
        elif wall == "+X":
            base = Vector((P.ROOM_X[1] - 0.022, w["y"], w["z"]))
            outv = Vector((-1.0, 0.0, 0.0))
            base_rot = (0.0, PI / 2, 0.0)
        elif wall == "-Y":
            base = Vector((w.get("x", 0.0), P.ROOM_Y[0] + 0.022, w["z"]))
            outv = Vector((0.0, 1.0, 0.0))
            base_rot = (PI / 2, 0.0, 0.0)
        else:  # +Y
            base = Vector((w.get("x", 0.0), P.ROOM_Y[1] - 0.022, w["z"]))
            outv = Vector((0.0, -1.0, 0.0))
            base_rot = (PI / 2, 0.0, 0.0)

        # 墙座（厚度 0.02，中心贴墙内表面 → 前表面 = base + outv*0.01）
        objs.append(C.cyl(f"DC_WallLampBase_{i}", r=0.05, h=0.02, segs=20,
                          rot=base_rot, loc=tuple(base),
                          mat=m_brass, col=col))
        # 支臂：从**墙座前表面**起，而不是从墙座中心起
        # （从中心起会让根部穿透墙座 10mm —— qc 报的 DC_WallLampArm↔Base 10mm）
        root = base + outv * 0.012
        mid = base + outv * 0.11 + Vector((0.0, 0.0, 0.07))
        tip = base + outv * 0.20 + Vector((0.0, 0.0, 0.10))
        objs.append(C.tube_along(f"DC_WallLampArm_{i}",
                                 [tuple(root), tuple(mid), tuple(tip)],
                                 radius=0.010, segs=8, mat=m_brass, col=col))
        # 灯罩（开口朝上的小碗）
        shade = C.lathe(f"DC_WallLampShade_{i}",
                        [(0.035, 0.0), (0.070, 0.035), (0.085, 0.09),
                         (0.075, 0.10), (0.030, 0.055), (0.0, 0.05)],
                        segs=24, loc=(tip[0], tip[1], tip[2]), mat=m_shade, col=col,
                        close_bottom=True)
        C.shade_auto(shade, 30 * D2R)
        objs.append(shade)
        objs.append(C.sphere(f"DC_WallLampBulb_{i}", r=0.028, segs=14, rings=10,
                             loc=(tip[0], tip[1], tip[2] + 0.055), mat=m_bulb, col=col))
    return objs


def _chalkboard(M_, col):
    objs = []
    cb = P.CHALKBOARD
    y0, y1 = cb["y"]
    z0, z1 = cb["z"]
    x_face = P.ROOM_X[0] + 0.032
    fw = cb["frame"]
    # 外框（4 条）
    objs.append(C.box("DC_ChalkFrame_T", (0.064, (y1 - y0) + fw * 2, fw),
                      loc=(x_face, (y0 + y1) / 2, z1 + fw / 2), mat=M_["wood_dark"],
                      col=col, bevel=0.004, segs=1))
    objs.append(C.box("DC_ChalkFrame_B", (0.064, (y1 - y0) + fw * 2, fw),
                      loc=(x_face, (y0 + y1) / 2, z0 - fw / 2), mat=M_["wood_dark"],
                      col=col, bevel=0.004, segs=1))
    objs.append(C.box("DC_ChalkFrame_L", (0.064, fw, (z1 - z0)),
                      loc=(x_face, y0 - fw / 2, (z0 + z1) / 2), mat=M_["wood_dark"],
                      col=col, bevel=0.004, segs=1))
    objs.append(C.box("DC_ChalkFrame_R", (0.064, fw, (z1 - z0)),
                      loc=(x_face, y1 + fw / 2, (z0 + z1) / 2), mat=M_["wood_dark"],
                      col=col, bevel=0.004, segs=1))
    # 背板（chalk 材质）
    board = C.box("DC_ChalkBoard", (0.02, (y1 - y0), (z1 - z0)),
                  loc=(x_face + 0.015, (y0 + y1) / 2, (z0 + z1) / 2),
                  mat=M_["chalk"], col=col)
    objs.append(board)
    # 贴图面（朝 +X 室内），比例按 1200x1600 → 3:4
    tex = P.tex_gen_path("menu_blackboard.png") or P.tex_gen_path("menu_blackboard")
    if tex:
        h = (z1 - z0) * 0.94
        w = h * 1200.0 / 1600.0
        if w > (y1 - y0) * 0.94:
            w = (y1 - y0) * 0.94
            h = w * 1600.0 / 1200.0
        objs.append(_tex_plane("DC_ChalkTex", w, h,
                               (x_face + 0.028, (y0 + y1) / 2, (z0 + z1) / 2),
                               "+X", tex, col, rough=0.9, emissive=0.06,
                               flip_u=True, flip_v=False))
    # 粉笔槽 + 粉笔
    objs.append(C.box("DC_ChalkTray", (0.07, (y1 - y0) + 0.06, 0.025),
                      loc=(x_face + 0.02, (y0 + y1) / 2, z0 - fw - 0.012),
                      mat=M_["wood_dark"], col=col, bevel=0.003, segs=1))
    for i, (dy, hx) in enumerate([(-0.25, "#FFF9EC"), (0.02, "#F3C6D2"), (0.28, "#FFF9EC")]):
        objs.append(C.cyl(f"DC_Chalk_{i}", r=0.006, h=0.065, segs=8,
                          rot=(0, PI / 2, 0.35),
                          loc=(x_face + 0.03, (y0 + y1) / 2 + dy, z0 - fw + 0.006),
                          mat=MAT.M.pbr(f"MAT_ChalkStick_{i}", base=hx, rough=0.95),
                          col=col))
    return objs


def _frames(M_, col):
    objs = []
    x_face = P.ROOM_X[1] - 0.03
    arts = ["picture_art_01.png", "picture_art_02.png", "picture_art_03.png"]
    for i, fr in enumerate(P.FRAMES_RIGHT):
        y0, y1 = fr["y"]
        z0, z1 = fr["z"]
        w = (y1 - y0)
        h = (z1 - z0)
        # 外框
        fw = 0.035
        objs.append(C.box(f"DC_Frame_{i}_T", (0.04, w, fw),
                          loc=(x_face, (y0 + y1) / 2, z1 - fw / 2),
                          mat=M_["wood_dark"], col=col, bevel=0.003, segs=1))
        objs.append(C.box(f"DC_Frame_{i}_B", (0.04, w, fw),
                          loc=(x_face, (y0 + y1) / 2, z0 + fw / 2),
                          mat=M_["wood_dark"], col=col, bevel=0.003, segs=1))
        objs.append(C.box(f"DC_Frame_{i}_L", (0.04, fw, h - fw * 2),
                          loc=(x_face, y0 + fw / 2, (z0 + z1) / 2),
                          mat=M_["wood_dark"], col=col, bevel=0.003, segs=1))
        objs.append(C.box(f"DC_Frame_{i}_R", (0.04, fw, h - fw * 2),
                          loc=(x_face, y1 - fw / 2, (z0 + z1) / 2),
                          mat=M_["wood_dark"], col=col, bevel=0.003, segs=1))
        # 白卡纸内衬
        objs.append(C.box(f"DC_Frame_{i}_Mat", (0.02, w - fw * 2, h - fw * 2),
                          loc=(x_face - 0.005, (y0 + y1) / 2, (z0 + z1) / 2),
                          mat=M_["paper"], col=col))
        tex = P.tex_gen_path(arts[i % len(arts)])
        if tex:
            pw = (w - fw * 2) * 0.80
            ph = pw * 0.78
            objs.append(_tex_plane(f"DC_Frame_{i}_Art", pw, ph,
                                   (x_face - 0.018, (y0 + y1) / 2, (z0 + z1) / 2),
                                   "-X", tex, col, rough=0.8))
    return objs


def _noren(M_, col):
    objs = []
    n = P.NOREN
    x0, x1 = n["x"]
    z_top, z_bot = n["z_top"], n["z_bot"]
    y = P.ROOM_Y[0] + 0.055
    # 横杆
    objs.append(C.cyl("DC_NorenRod", r=0.012, h=(x1 - x0) + 0.10, segs=12,
                      rot=(0, PI / 2, 0),
                      loc=((x0 + x1) / 2, y, z_top + 0.03), mat=M_["brass"], col=col))
    for i, xx in enumerate((x0 - 0.02, x1 + 0.02)):
        objs.append(C.cyl(f"DC_NorenBracket_{i}", r=0.010, h=0.10, segs=8,
                          rot=(PI / 2, 0, 0), loc=(xx, y - 0.05, z_top + 0.03),
                          mat=M_["brass"], col=col))
    # 门帘布片：中间 2 片合并成一幅贴图，两侧各 1 片纯色
    total_w = x1 - x0
    side_w = total_w * 0.22
    mid_w = total_w - side_w * 2 - 0.03
    h = z_top - z_bot
    cloth_mat = M_["noren"]
    tex = P.tex_gen_path("noren_welcome.png") or P.tex_gen_path("noren_welcome")
    # 纯色侧片
    for i, cx in enumerate((x0 + side_w / 2, x1 - side_w / 2)):
        ob = C.box(f"DC_NorenSide_{i}", (side_w - 0.012, 0.010, h),
                   loc=(cx, y + 0.02, (z_top + z_bot) / 2), mat=cloth_mat, col=col)
        objs.append(ob)
    # 中间主片（贴图）
    if tex:
        main = _tex_plane("DC_NorenMain", mid_w, h,
                          ((x0 + x1) / 2, y + 0.015, (z_top + z_bot) / 2),
                          "-Y", tex, col, rough=0.88, flip_v=False)
        objs.append(main)
        # 背面补一层布（避免看穿）
        objs.append(C.box("DC_NorenBack", (mid_w, 0.008, h),
                          loc=((x0 + x1) / 2, y + 0.03, (z_top + z_bot) / 2),
                          mat=cloth_mat, col=col))
    else:
        objs.append(C.box("DC_NorenMain", (mid_w, 0.010, h),
                          loc=((x0 + x1) / 2, y + 0.02, (z_top + z_bot) / 2),
                          mat=cloth_mat, col=col))
    # 吊环
    for i in range(5):
        xx = x0 + (total_w) * i / 4
        objs.append(C.ring_tube(f"DC_NorenRing_{i}", R=0.018, r=0.0035, segs=12, rsegs=4,
                                loc=(xx, y, z_top + 0.01), rot=(PI / 2, 0, 0),
                                mat=M_["brass"], col=col))
    return objs


def _chime(M_, col):
    objs = []
    w = P.WIND_CHIME
    x, y, z = w["x"], w["y"], w["z"]
    # 挂杆
    objs.append(C.box("DC_ChimeBar", (0.30, 0.03, 0.03),
                      loc=(x - 0.10, y, z + 0.03), mat=M_["wood_dark"], col=col))
    # 吊线
    objs.append(C.cyl("DC_ChimeWire", r=0.0018, h=0.20, segs=6,
                      loc=(x, y, z - 0.07), mat=M_["black_metal"], col=col))
    # 玻璃铃（倒扣碗）
    glass = M_["glass"]
    bell = C.lathe("DC_ChimeBell",
                   [(0.0, 0.0), (0.035, -0.005), (0.052, -0.03), (0.056, -0.065),
                    (0.050, -0.085), (0.0, -0.088)],
                   segs=24, loc=(x, y, z - 0.18), mat=glass, col=col,
                   close_bottom=True)
    C.shade_auto(bell, 30 * D2R)
    objs.append(bell)
    # 铃舌
    objs.append(C.sphere("DC_ChimeClapper", r=0.012, segs=12, rings=8,
                         loc=(x, y, z - 0.24), mat=M_["brass"], col=col))
    # 短册（纸片）
    paper = MAT.M.pbr("MAT_ChimePaper", base="#FFFCF2", rough=0.9)
    objs.append(C.box("DC_ChimePaper", (0.045, 0.003, 0.13),
                      loc=(x, y, z - 0.33), mat=paper, col=col))
    return objs


def _bookshelf(M_, col):
    objs = []
    bs = P.BOOKSHELF
    x0, x1 = bs["x"]
    y0, y1 = bs["y"]
    z0, z1 = bs["z"]
    shelves = bs["shelves"]
    # 侧板 / 顶底板 / 背板
    m_wood = M_["wood_oak"]
    m_dark = M_["wood_dark"]
    objs.append(C.box("DC_ShelfSide_L", (0.03, y1 - y0, z1),
                      loc=(x0 + 0.015, (y0 + y1) / 2, z1 / 2), mat=m_wood, col=col,
                      bevel=0.004, segs=1))
    objs.append(C.box("DC_ShelfSide_R", (0.03, y1 - y0, z1),
                      loc=(x1 - 0.015, (y0 + y1) / 2, z1 / 2), mat=m_wood, col=col,
                      bevel=0.004, segs=1))
    # 背板：底边从踢脚板上沿(0.08)起，避免与 DC_ShelfPlinth 整体重叠（原 1970mm 假阳性）
    objs.append(C.box("DC_ShelfBack", (x1 - x0, 0.02, z1 - 0.08),
                      loc=((x0 + x1) / 2, y1 - 0.01, 0.08 + (z1 - 0.08) / 2),
                      mat=m_dark, col=col))
    objs.append(C.box("DC_ShelfTop", (x1 - x0, y1 - y0, 0.03),
                      loc=((x0 + x1) / 2, (y0 + y1) / 2, z1 - 0.015), mat=m_wood, col=col,
                      bevel=0.004, segs=1))
    objs.append(C.box("DC_ShelfPlinth", (x1 - x0, y1 - y0, 0.08),
                      loc=((x0 + x1) / 2, (y0 + y1) / 2, 0.04), mat=m_dark, col=col))
    # 层板
    zs = [0.08 + (z1 - 0.10) * i / shelves for i in range(shelves)] + [z1 - 0.03]
    for i, z in enumerate(zs):
        objs.append(C.box(f"DC_ShelfBoard_{i}", (x1 - x0 - 0.06, y1 - y0 - 0.03, 0.022),
                          loc=((x0 + x1) / 2, (y0 + y1) / 2 - 0.01, z),
                          mat=m_wood, col=col, bevel=0.003, segs=1))
    # 书（每层 8–12 本，不同高度/厚度/颜色）
    import random
    rnd = random.Random(20261021)
    book_colors = ["#7A3B2E", "#3E5B72", "#8A7A4E", "#5B6B4A", "#8C4A5A",
                   "#4A4A5C", "#B08A5A", "#6B4E7A"]
    book_mats = [MAT.M.pbr(f"MAT_Book_{i}", base=c, rough=0.72)
                 for i, c in enumerate(book_colors)]
    for si, z in enumerate(zs[:-1]):
        x = x0 + 0.06
        while x < x1 - 0.09:
            bw = rnd.uniform(0.018, 0.042)
            bh = rnd.uniform(0.16, 0.26)
            bd = rnd.uniform(0.13, 0.19)
            if x + bw > x1 - 0.06:
                break
            objs.append(C.box(f"DC_Book_{si}_{len(objs)}", (bw, bd, bh),
                              loc=(x + bw / 2, (y0 + y1) / 2 - 0.02, z + 0.011 + bh / 2),
                              mat=book_mats[rnd.randrange(len(book_mats))], col=col))
            x += bw + 0.004
    # 装饰立盘 ×2
    # 盘绕 X 转 90° 后竖直立起，半径 0.12 展开在 Z 向 → 盘底 = 中心 z − 0.12。
    # 旧版中心取 zs[-2]+0.02，盘底落到 zs[-2]−0.10，直接插进下方层板
    # （实测 DC_DecoPlate_0/1 ↔ DC_ShelfBoard_4 8.75mm）。
    # 修法：盘底坐在该层板上表面（板厚 0.022，顶面 = z + 0.011）+ 2mm 装配间隙。
    board_top = zs[-2] + 0.011
    plate_r = 0.12
    for i, (yy, zz) in enumerate([(y0 + 0.12, board_top + plate_r + 0.002),
                                  (y1 - 0.12, board_top + plate_r + 0.002)]):
        plate = C.lathe(f"DC_DecoPlate_{i}",
                        [(0.0, 0.0), (0.10, 0.004), (0.12, 0.02), (0.10, 0.032)],
                        segs=28, rot=(PI / 2, 0, 0),
                        loc=((x0 + x1) / 2 + (i * 2 - 1) * 0.16, yy, zz), mat=M_["porcelain"], col=col)
        objs.append(plate)
    # 小摆件（黄铜花瓶）
    objs.append(C.lathe("DC_ShelfVase",
                        [(0.0, 0.0), (0.035, 0.0), (0.045, 0.05), (0.028, 0.12),
                         (0.034, 0.16), (0.030, 0.17)],
                        segs=20, loc=((x0 + x1) / 2, y0 + 0.14, zs[1] + 0.011),
                        mat=M_["brass"], col=col))
    return objs


def _curtains(M_, col):
    objs = []
    fx0, fx1 = P.WIN_X
    fz1 = P.WIN_Z[1]
    m = M_["curtain"]
    # 每侧一片：波浪截面沿 y 方向（贴窗内侧 y≈-2.86）
    # 注意：旧版左帘 cx = WIN_X[0]-0.18 = -3.88、宽 0.36 → x 范围 -4.06…-3.70，
    # 伸进左墙 60mm，正好扫过 RM_ChairRail_W 腰线（实测顶点穿透 5.63mm）。
    # 修法：把帘片的 x 起点卡在腰线外表面（-3.972）之内，不靠抬高下摆绕开
    #      （腰线 z=0.82 在帘子高度区间内，抬高下摆无效）。
    rail_face = P.ROOM_X[0] + 0.028          # -3.972 = 腰线凸出墙面的外表面
    # 左片原 cx=fx0-0.18、w=0.36 → 左缘贴到左墙(-3.99)，与墙裙/腰线在 z0.93-0.97 相穿。
    # 收进 40mm 让窗帘离开左墙 25mm 以上。
    for side, (cx) in enumerate((fx0 - 0.14, fx1 + 0.18)):
        w = 0.36
        if side == 0:
            cx = rail_face + w / 2.0         # -3.792 → x 范围 -3.972…-3.612
        z_top = fz1 + 0.10
        z_bot = 0.30
        secs = []
        n_wave = 6
        for k in range(11):
            z = z_bot + (z_top - z_bot) * k / 10.0
            ring = []
            for j in range(n_wave * 2 + 1):
                u = j / (n_wave * 2)
                xx = cx - w / 2 + w * u
                yy = P.ROOM_Y[0] + 0.16 + math.sin(u * math.pi * n_wave) * 0.022
                ring.append((xx, yy, z))
            secs.append(ring)
        ob = C.loft(f"DC_Curtain_{side}", secs, closed_ring=False, cap=False,
                    mat=m, col=col, shade="smooth")
        # 给一个薄壳厚度（实心化）
        sol = ob.modifiers.new("Solidify", "SOLIDIFY")
        sol.thickness = 0.006
        C.apply_mods(ob)
        objs.append(ob)
        # 帘环
        for j in range(6):
            xx = cx - w / 2 + w * j / 5.0
            objs.append(C.ring_tube(f"DC_CurtainRing_{side}_{j}", R=0.016, r=0.003,
                                    segs=10, rsegs=4,
                                    loc=(xx, P.ROOM_Y[0] + 0.16, z_top - 0.01),
                                    rot=(PI / 2, 0, 0), mat=M_["brass"], col=col))
    return objs


def _spot_fixtures(M_, col):
    objs = []
    m_black = M_["black_metal"]
    m_brass = M_["brass"]
    m_bulb = M_["bulb"]
    # 吧台射灯 3 个（装在天花跌级底面，朝吧台）
    for i, s in enumerate(P.BAR_SPOTS):
        z = P.CEIL_RECESS_Z - 0.02
        # 底座
        objs.append(C.cyl(f"DC_BarSpotBase_{i}", r=0.045, h=0.03, segs=16,
                          loc=(s["x"], s["y"], z), mat=m_black, col=col))
        # 灯筒（斜向台面）
        objs.append(C.cyl(f"DC_BarSpotBody_{i}", r=0.028, h=0.10, segs=16,
                          rot=(-30 * D2R, 0, 0),
                          loc=(s["x"], s["y"] - 0.035, z - 0.06), mat=m_black, col=col))
        objs.append(C.sphere(f"DC_BarSpotBulb_{i}", r=0.020, segs=12, rings=8,
                             loc=(s["x"], s["y"] - 0.062, z - 0.105), mat=m_bulb, col=col))
    # 展示柜射灯 2 个
    for i, dx in enumerate((-0.35, 0.35)):
        ds = P.DISPLAY_SPOT
        x = ds["x"] + dx * 1.2
        objs.append(C.cyl(f"DC_DispSpotBase_{i}", r=0.04, h=0.025, segs=14,
                          loc=(x, ds["y"], P.CEIL_RECESS_Z - 0.02), mat=m_black, col=col))
        objs.append(C.cyl(f"DC_DispSpotBody_{i}", r=0.025, h=0.09, segs=14,
                          rot=(-20 * D2R, 0, 0),
                          loc=(x, ds["y"] + 0.02, P.CEIL_RECESS_Z - 0.08),
                          mat=m_black, col=col))
        objs.append(C.sphere(f"DC_DispSpotBulb_{i}", r=0.017, segs=12, rings=8,
                             loc=(x, ds["y"] + 0.035, P.CEIL_RECESS_Z - 0.125),
                             mat=m_bulb, col=col))
    return objs


def _plants(M_, col):
    objs = []
    # 角落大盆栽：外部 calathea 模型减面后放进陶盆
    pot_r = 0.24
    pot_h = 0.42
    pc = P.PLANT_CORNER
    pot = C.lathe("DC_PlantPot",
                  [(0.0, 0.0), (pot_r * 0.72, 0.0), (pot_r * 0.86, 0.06),
                   (pot_r, pot_h * 0.55), (pot_r * 0.94, pot_h * 0.94),
                   (pot_r * 0.90, pot_h)],
                  segs=28, loc=(pc["x"], pc["y"], 0.0),
                  mat=M_["terracotta"], col=col)
    C.shade_auto(pot, 30 * D2R)
    objs.append(pot)
    # 土壤
    objs.append(C.cyl("DC_PlantSoil", r=pot_r * 0.90, h=0.02, segs=24,
                      loc=(pc["x"], pc["y"], pot_h - 0.01), mat=M_["soil"], col=col))
    # 老兄要求：删除 DC_PlantLeaves——该 calathea 叶子模型的冠幅无法可靠
    # 约束在陶盆内，会穿到室内（多轮归一化后仍有叶片伸出墙/吧台）。
    # 保留陶盆 DC_PlantPot 与土壤 DC_PlantSoil 作为空盆装饰。
    # （注意：这里在 _plants() 内部，不能用 build() 的 notes 变量）
    # 窗台小盆栽 ×2（程序化，省面）
    # 窗台板实测 y=[-3.00,-2.86]、顶面 z=0.7225。原 y=ROOM_Y[0]+0.16=-2.84
    # 已落在板外 20mm（老兄看到的"窗边盆栽悬空"）。改 y=-2.90 居中，z 用台面顶。
    for i, (px, pz) in enumerate([(P.WIN_X[0] + 0.55, 0.7225),
                                  (P.WIN_X[0] + 1.6, 0.7225)]):
        objs.append(C.lathe(f"DC_WinPot_{i}",
                            [(0.0, 0.0), (0.06, 0.0), (0.075, 0.05), (0.07, 0.12),
                             (0.066, 0.125)],
                            segs=18, loc=(px, -2.920, pz),
                            mat=M_["terracotta"], col=col))
        # 叶片（5 片斜插的薄片）
        for k in range(5):
            a = C.TAU * k / 5
            objs.append(C.box(f"DC_WinLeaf_{i}_{k}", (0.02, 0.09, 0.006),
                              rot=(0.6, 0, a),
                              loc=(px + math.cos(a) * 0.035,
                                   -2.920 + math.sin(a) * 0.035,
                                   pz + 0.125),
                              mat=M_["leaf"], col=col))
    return objs


def _umbrella_stand(M_, col):
    objs = []
    uc = P.COAT_RACK
    x, y = uc["x"], uc["y"]
    m_steel = M_["steel"]
    # 筒
    objs.append(C.lathe("DC_UmbrellaStand",
                        [(0.0, 0.0), (0.13, 0.0), (0.14, 0.03), (0.14, 0.48),
                         (0.135, 0.50)],
                        segs=24, loc=(x, y, 0.0), mat=m_steel, col=col))
    # 两把伞（伞面圆锥 + 伞柄）
    for i, (dx, dy, tilt) in enumerate([(-0.03, 0.0, 8), (0.035, 0.03, -10)]):
        objs.append(C.cyl(f"DC_UmbrellaShaft_{i}", r=0.008, h=0.86, segs=8,
                          rot=(tilt * D2R, 0, 0),
                          loc=(x + dx, y + dy, 0.45), mat=M_["wood_dark"], col=col))
        objs.append(C.cyl(f"DC_UmbrellaCanopy_{i}", r=0.055, h=0.22, segs=16, r2=0.0,
                          rot=(tilt * D2R, 0, 0),
                          loc=(x + dx, y + dy + 0.02, 0.78),
                          mat=MAT.M.pbr(f"MAT_Umbrella_{i}",
                                        base=["#3A4B66", "#6B4A52"][i], rough=0.8),
                          col=col))
        # 弯钩手柄
        objs.append(C.ring_tube(f"DC_UmbrellaHandle_{i}", R=0.035, r=0.008, segs=16, rsegs=6,
                                loc=(x + dx, y + dy, 0.90), rot=(PI / 2, 0, 0),
                                mat=M_["wood_dark"], col=col))
    return objs


def _door_sign(M_, col):
    objs = []
    tex = P.tex_gen_path("sign_cafe.png") or P.tex_gen_path("sign_cafe")
    x = (P.DOOR_X[0] + P.DOOR_X[1]) / 2
    # 原 z=2.38 落在 RM_WallFront_5(z[2.2,3.0]) 墙体内部 → 从室内完全看不到。
    # 移到门洞高度内（门高 2.20），挂在门玻璃内侧 y=-2.90，室内一眼可见。
    z = 1.72
    y = P.ROOM_Y[0] + 0.10
    # 木牌底
    objs.append(C.box("DC_DoorSignBoard", (0.44, 0.03, 0.30),
                      loc=(x, y, z), mat=M_["wood_dark"], col=col,
                      bevel=0.006, segs=2))
    if tex:
        objs.append(_tex_plane("DC_DoorSignTex", 0.38, 0.25, (x, y + 0.018, z),
                               "+Y", tex, col, rough=0.78))
    # 吊链
    for i, dx in enumerate((-0.16, 0.16)):
        objs.append(C.cyl(f"DC_DoorSignChain_{i}", r=0.003, h=0.16, segs=6,
                          loc=(x + dx, y, z + 0.22), mat=M_["brass"], col=col))
    return objs


# ══════════════════════════════════════════════════════════════════════
def build(P_, C_, M_, assets):
    Pc, Cc = P, C
    M = M_ if M_ else MAT.palette()
    Cc.wipe_collection(COL)
    Cc.ensure_collection(COL)
    objs = []
    notes = []
    parts = [
        ("pendants", lambda: _pendants(M, COL)),
        ("cove", lambda: _cove(M, COL)),
        ("wall_lamps", lambda: _wall_lamps(M, COL)),
        ("chalkboard", lambda: _chalkboard(M, COL)),
        ("frames", lambda: _frames(M, COL)),
        ("noren", lambda: _noren(M, COL)),
        ("chime", lambda: _chime(M, COL)),
        ("bookshelf", lambda: _bookshelf(M, COL)),
        ("curtains", lambda: _curtains(M, COL)),
        ("spot_fixtures", lambda: _spot_fixtures(M, COL)),
        ("plants", lambda: _plants(M, COL)),
        ("umbrella", lambda: _umbrella_stand(M, COL)),
        ("door_sign", lambda: _door_sign(M, COL)),
    ]
    for name, fn in parts:
        try:
            got = [o for o in fn() if o is not None]
            objs += got
            notes.append("%s:%d" % (name, len(got)))
        except Exception as e:
            import traceback
            traceback.print_exc()
            Cc.log("WARN cdecor part failed:", name, repr(e))

    # 彩蛋：追加模块（若存在）
    try:
        import cdecor_extra
        extra = cdecor_extra.build_extra(P, C, M, assets)
        if extra and extra.get("objects"):
            objs += extra["objects"]
            notes.append("extra:%d" % len(extra["objects"]))
    except ImportError:
        pass
    except Exception as e:
        Cc.log("WARN cdecor_extra failed:", repr(e))

    colliders = []
    for ob in objs:
        if ob is None:
            continue
        if ob.name.startswith(("DC_Shelf", "DC_PlantPot", "DC_UmbrellaStand")):
            mn, mx = Cc.world_aabb(ob)
            colliders.append({"name": ob.name, "aabb": [mn, mx], "kind": "solid"})

    # 落地/贴墙自检（打印，不中断）
    bad = []
    for ob in objs:
        if ob is None:
            continue
        mn, mx = Cc.world_aabb(ob)
        if ob.name.startswith("DC_PlantPot") and abs(mn[2]) > 0.003:
            bad.append((ob.name, round(mn[2], 4)))
    if bad:
        Cc.log("cdecor: not-on-floor", bad)

    tris = Cc.tri_count(objs)
    Cc.log("cdecor: %d objects, %d tris (budget %d) parts=%s"
           % (len(objs), tris, TRI_BUDGET, ",".join(notes)))
    return {"objects": [o for o in objs if o], "collections": [COL],
            "colliders": colliders,
            "anchors": {"pendant_positions": [[p["x"], p["y"], p["shade_z"]]
                                              for p in P.PENDANTS],
                        "chalkboard": [P.CHALKBOARD["x"], (P.CHALKBOARD["y"][0] + P.CHALKBOARD["y"][1]) / 2,
                                       (P.CHALKBOARD["z"][0] + P.CHALKBOARD["z"][1]) / 2],
                        "noren": [[P.NOREN["x"][0], P.NOREN["x"][1]],
                                  [P.NOREN["z_bot"], P.NOREN["z_top"]]]},
            "notes": "; ".join(notes), "tris": tris}


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.open_mainfile(filepath=r"E:\dsh\maid_cafe\scene\maid_cafe.blend")
    M = MAT.palette()
    res = build(P, C, M, {})
    C.log("built", len(res["objects"]), res["tris"])
    C.selfcheck(MODULE, res["objects"], res=(1000, 760), samples=24,
                views=[
                    {"name": "black", "from": (-1.6, 0.2, 1.9), "look": (-3.9, 1.4, 1.7), "lens": 30},
                    {"name": "pend", "from": (0.4, 0.4, 1.4), "look": (-2.6, 0.4, 2.2), "lens": 26},
                    {"name": "frame", "from": (1.4, -0.6, 1.8), "look": (3.9, 0.1, 1.7), "lens": 32},
                    {"name": "shelf", "from": (-1.6, 0.4, 1.5), "look": (-3.7, 2.3, 1.1), "lens": 30},
                    {"name": "noren", "from": (1.7, 0.6, 1.5), "look": (1.8, -2.95, 1.7), "lens": 30},
                ])
