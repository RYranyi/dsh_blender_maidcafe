"""
cdecor_extra.py — C_Decor 的「提质」追加件（不 wipe，只追加）

由 cdecor.py 负责主装饰；本文件只补充 4 件提气的小物：
  1. DC_Sign_Cafe       营业牌（木牌 + sign_cafe 贴图 + 黄铜链），门边窗内朝街
  2. DC_StringLights    吧台上方灯串（一行小灯珠 + 悬链）
  3. DC_Candle / DC_Incense  窗台蜡烛 + 薰香座
  4. DC_DessertTray     吧台甜品托盘（3 块切件 + 蛋糕刀 + 餐巾）

约定：
  * 绝不清除集合（不调 wipe_collection），只往已有 C_Decor 追加。
  * 不写 assert；任何一步失败只 print，不影响主构建。
  * 文字贴图必须正着：平面朝 -Y（朝街），从 -Y 看向 +Y 时世界 +X 在观者左侧，
    所以 u 必须随 x 减小而增大，否则文字镜像。

调用：cdecor_extra.build_extra(P_, C_, M_, assets) -> {"objects": [...], "tris": n}
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
import cassets as A

MODULE = "cdecor_extra"
OWNER = "env-decor-v2"
COL = "C_Decor"

D2R = C.D2R
PI = C.PI
TAU = 2.0 * math.pi

IX = P.ROOM_X          # (-4.0, 4.0)
IY = P.ROOM_Y          # (-3.0, 3.0)
RECESS = P.CEIL_RECESS_Z

# ══════════════════════════════════════════════════════════════════════
def _uv_face(ob, sx, sy, view_from="+X"):
    """把平面 UV 归一到 0..1，并按观看方向修正镜像。

    实测（见渲染对比）：C.plane(toward="-Y") 从街道侧（-Y）看过去时，
    UV 的 u 需要随世界 x 递增才不镜像；之前反向处理导致 "Maid Café" 左右翻转。
    ±X 沿用 cdecor 里验证过的翻转规则。
    """
    me = ob.data
    uvl = me.uv_layers.active or me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        co = me.vertices[loop.vertex_index].co
        if view_from in ("-Y", "+Y"):
            u = co.x / sx + 0.5
            if view_from == "+Y":
                u = 1.0 - u
            v = co.y / sy + 0.5
        else:
            u = co.y / sy + 0.5
            if view_from == "+X":
                u = 1.0 - u
            v = co.x / sx + 0.5
        uvl.data[loop.index].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
    return ob


def _text_mat(name, key, rough=0.8):
    path = P.tex_gen_path(key)
    if not path:
        C.log("[cdecor_extra] WARN texture missing", key)
        return MAT.M.pbr(name, base="#D8CDB8", rough=rough)
    return MAT.M.pbr(name, diff=path, rough=rough, uv_scale=1.0)


# ══════════════════════════════════════════════════════════════════════
def _place_asset(Cc, pid, cx, cy, z_bottom, target_h, prefix, align="center",
                 target_size=None):
    """导入现成模型，按真实世界 AABB 摆放。

    align="center"：把 AABB 中心放到 (cx,cy)
    align="wall-x" ：把 AABB 的**右缘(mx[0])** 贴到 cx（用于壁架上的物件靠墙摆放）
    """
    try:
        if target_size:
            got = A.import_model(pid, col=COL, target_size=target_size,
                                 name_prefix=prefix)
        else:
            got = A.import_model(pid, col=COL, target_height=target_h,
                                 name_prefix=prefix)
    except Exception as e:
        C.log("[cdecor_extra] import %s failed: %r" % (pid, e))
        return []
    if not got:
        return []
    bpy.context.view_layer.update()
    mn, mx = Cc.world_aabb(got)
    if align == "wall-x":
        dx = cx - mx[0]        # 右缘对齐 cx（贴墙）
    else:
        dx = cx - (mn[0] + mx[0]) / 2.0
    dy = cy - (mn[1] + mx[1]) / 2.0
    dz = z_bottom - mn[2]
    for o in got:
        o.location.x += dx
        o.location.y += dy
        o.location.z += dz
    bpy.context.view_layer.update()
    mn2, mx2 = Cc.world_aabb(got)
    C.log("[cdecor_extra] %s -> center(%.3f,%.3f) z=[%.3f,%.3f]"
          % (pid, (mn2[0] + mx2[0]) / 2, (mn2[1] + mx2[1]) / 2, mn2[2], mx2[2]))
    return got


def build_extra(P_=None, C_=None, M_=None, assets=None):
    """只往 C_Decor 追加物体，不清集合。"""
    Pc = P_ or P
    Cc = C_ or C
    M = M_ or MAT.palette()

    objs = []
    colliders = []
    notes = []

    def add(ob):
        if ob is not None:
            objs.append(ob)
        return ob

    try:
        Cc.ensure_collection(COL)

        m_wood = M["wood_oak"]
        m_dark = M["wood_dark"]
        m_brass = M["brass"]
        m_black = M["black_metal"]
        m_bulb = M["bulb"]
        m_paper = M["paper"]
        m_porcelain = M["porcelain"]
        m_glass = M["glass_frost"]
        m_linen = M["linen"]
        m_cake_a = M["cake_carrot"]
        m_cake_b = M["cake_strawberry"]
        m_cream = M["milk"]

        # ── 1. 营业牌 DC_Sign_Cafe（窗玻璃内侧，面朝街道 -Y）──────────
        # 门在 x 1.15~2.45；窗右沿 0.35；牌挂在窗洞内靠左，不挡门。
        # 位置必须在窗洞内（WIN_X / WIN_Z 范围内），因为此处没有墙可贴：
        # 牌靠 4 个黄铜支撑柱顶在窗玻璃内表面上（QC: 之前离墙 40mm 判悬空）。
        sx = -0.16
        sign_w = 0.66
        sign_ar = 1800.0 / 1100.0          # sign_cafe 贴图 1.636
        sign_h = sign_w / sign_ar
        sign_z = 1.52
        # 窗玻璃内表面：croom 里玻璃中心 y = (y0-WALL_T/2)+0.005、厚 0.012
        glass_inner_y = (IY[0] - P.WALL_T / 2) + 0.005 + 0.006     # ≈ -3.069
        standoff = 0.020
        sign_y = glass_inner_y + standoff                          # ≈ -3.049
        m_sign = _text_mat("MAT_Decor_Sign", "sign_cafe", rough=0.55)
        sign = Cc.plane("DC_Sign_Cafe", sx=sign_w, sy=sign_h,
                        loc=(sx, sign_y, sign_z), toward="-Y",
                        mat=m_sign, col=COL)
        _uv_face(sign, sign_w, sign_h, view_from="-Y")
        add(sign)
        # 木牌底框（略大于画面，露出木边；贴着画面背后）
        add(Cc.box("DC_Sign_Cafe_Back", (sign_w + 0.05, 0.014, sign_h + 0.05),
                   loc=(sx, sign_y + 0.009, sign_z), mat=m_wood, col=COL,
                   bevel=0.004, segs=2))
        # 上下黄铜压边
        for tag, dz in (("T", (sign_h + 0.05) / 2), ("B", -(sign_h + 0.05) / 2)):
            add(Cc.box(f"DC_Sign_Cafe_Edge{tag}", (sign_w + 0.055, 0.020, 0.012),
                       loc=(sx, sign_y + 0.010, sign_z + dz),
                       mat=m_brass, col=COL, bevel=0.003, segs=1))
        # 4 个黄铜支撑柱：从牌背顶到窗玻璃内表面（牌因此有真实支撑，不悬空）
        for i, (ox, oz) in enumerate([(-sign_w / 2 + 0.06, sign_h / 2 - 0.06),
                                      (sign_w / 2 - 0.06, sign_h / 2 - 0.06),
                                      (-sign_w / 2 + 0.06, -sign_h / 2 + 0.06),
                                      (sign_w / 2 - 0.06, -sign_h / 2 + 0.06)]):
            add(Cc.cyl(f"DC_Sign_Cafe_Stand{i}", r=0.0055, h=standoff, segs=8,
                       loc=(sx + ox, glass_inner_y + standoff / 2, sign_z + oz),
                       rot=(PI / 2, 0, 0), mat=m_brass, col=COL,
                       shade="smooth"))
        colliders.append({"name": "DC_Sign_Cafe", "kind": "hang",
                          "aabb": [[sx - sign_w / 2, glass_inner_y,
                                    sign_z - sign_h / 2],
                                   [sx + sign_w / 2, sign_y + 0.03,
                                    sign_z + sign_h / 2]]})
        notes.append("sign_cafe plaque on window glass inner face via 4 brass standoffs "
                     f"(y={sign_y:.3f}, glass={glass_inner_y:.3f}), faces -Y (street), "
                     "text upright")

        # ── 2. 吧台灯串 DC_StringLights ──────────────────────────
        bar = P.BAR_MAIN
        bar_y = (bar["y"][0] + bar["y"][1]) / 2          # 1.51
        str_y = bar["y"][1] - 0.09                        # 1.78，避开 P3 吊线(y=1.50)
        # 两端必须真的固定住：右端挂到右墙（x=4.0 内表面），左端挂到吧台后墙立柱。
        # QC 报过 DC_StringLights_Bulb* 悬空 2343mm —— 那就是两端吸顶座悬在半空。
        x_wall_r = IX[1] - 0.03                            # 3.97，右墙内表面内侧
        x_beam_l = 0.90                                    # 左端：吧台区上方
        z_end = 2.52                                       # 与吊顶跌级下沿 2.86 之间留空
        sag = 0.11
        n_bulb = 9
        x_a, x_b = x_beam_l, x_wall_r
        pts = []
        for k in range(n_bulb + 1):
            t = k / n_bulb
            x = x_a + (x_b - x_a) * t
            z = z_end - sag * math.sin(PI * t)
            pts.append((x, str_y, z))
        # 灯线（细管）
        add(Cc.tube_along("DC_StringLights_Wire", pts, radius=0.0045, segs=5,
                          mat=m_black, col=COL))
        # 两端固定：右端贴右墙做墙面固定座；左端做吊杆挂到吊顶（2.86）
        add(Cc.box("DC_StringLights_WallPlate", (0.018, 0.075, 0.075),
                   loc=(IX[1] - 0.009, str_y, pts[-1][2]),
                   mat=m_brass, col=COL, bevel=0.003, segs=1))
        add(Cc.cyl("DC_StringLights_Anchor1", r=0.020, h=0.028, segs=12,
                   loc=(pts[-1][0] - 0.012, str_y, pts[-1][2]),
                   rot=(0, PI / 2, 0), mat=m_brass, col=COL, shade="smooth"))
        # 左端：细吊杆从跌级下沿垂到灯线起点
        drop_top = RECESS - 0.004
        drop_bot = pts[0][2]
        add(Cc.cyl("DC_StringLights_Drop", r=0.0035, h=drop_top - drop_bot, segs=6,
                   loc=(pts[0][0], str_y, (drop_top + drop_bot) / 2),
                   mat=m_black, col=COL, shade="smooth"))
        add(Cc.cyl("DC_StringLights_Anchor0", r=0.026, h=0.018, segs=12,
                   loc=(pts[0][0], str_y, drop_top - 0.009),
                   mat=m_brass, col=COL, shade="smooth"))
        # 灯珠（发光球 + 铜帽）
        for k in range(1, n_bulb):
            x, y, z = pts[k]
            add(Cc.cyl(f"DC_StringLights_Cap{k}", r=0.014, h=0.022, segs=8,
                       loc=(x, y, z - 0.012), mat=m_brass, col=COL, shade="smooth"))
            add(Cc.sphere(f"DC_StringLights_Bulb{k}", r=0.026, segs=10, rings=7,
                          loc=(x, y, z - 0.042), mat=m_bulb, col=COL))
        notes.append(f"string lights over bar: {n_bulb - 1} bulbs on sagging wire "
                     f"y={str_y:.2f}, z {z_end - sag:.2f}~{z_end:.2f}; "
                     "right end on right wall plate, left end on drop from ceiling recess")

        # ── 3. 窗台蜡烛 + 薰香座 ──────────────────────────────────
        # 窗台板：croom 的 RM_WinSill 中心 z=fz0-0.02=0.70, 厚 0.045 → 顶面 0.7225
        # RM_WinSill 实测 z=[0.6775,0.7225]，真正的台面顶是 0.7225；
        # 但老兄看到盆栽悬空 —— 说明 croom 建窗台时实际顶面在 0.745（板厚 0.045 从 0.70 起）。
        # 用实测保守值：台面顶 = 0.7225，所有小物底面都落到这里。
        sill_top = 0.7225
        sill_y = IY[0] + 0.07                      # -2.93
        # 蜡烛玻璃杯
        cx, cy = -2.62, sill_y
        add(Cc.cyl("DC_Candle_Jar", r=0.042, h=0.085, segs=16,
                   loc=(cx, cy, sill_top + 0.0425), mat=m_glass, col=COL,   # cyl 的 loc.z = 中心（实测确认）
                   shade="smooth"))
        add(Cc.cyl("DC_Candle_Wax", r=0.037, h=0.062, segs=16,
                   loc=(cx, cy, sill_top + 0.036), mat=m_cream, col=COL,
                   shade="smooth"))
        add(Cc.cyl("DC_Candle_Wick", r=0.0022, h=0.012, segs=5,
                   loc=(cx, cy, sill_top + 0.073), mat=m_black, col=COL))
        add(Cc.sphere("DC_Candle_Flame", r=0.011, segs=8, rings=6,
                      loc=(cx, cy, sill_top + 0.089), mat=m_bulb, col=COL,   # sphere=中心
                      scale=(0.75, 0.75, 1.55)))
        # 薰香座（小碟 + 斜插香）
        ix, iy = -2.40, sill_y
        add(Cc.cyl("DC_Incense_Dish", r=0.048, h=0.012, segs=16,
                   loc=(ix, iy, sill_top + 0.006), mat=m_porcelain, col=COL,   # cyl 中心
                   bevel=0.003, bsegs=1, shade="smooth"))
        add(Cc.cyl("DC_Incense_Ash", r=0.040, h=0.006, segs=14,
                   loc=(ix, iy, sill_top + 0.009), mat=M["soil"], col=COL))
        add(Cc.cyl("DC_Incense_Stick", r=0.0022, h=0.20, segs=6,
                   loc=(ix + 0.012, iy, sill_top + 0.112),
                   rot=(0, -9 * D2R, 0), mat=M["wood_shelf"], col=COL,
                   shade="smooth"))
        add(Cc.sphere("DC_Incense_Tip", r=0.0035, segs=6, rings=4,
                      loc=(ix + 0.043, iy, sill_top + 0.211),
                      mat=M["bulb"], col=COL))
        notes.append(f"candles/incense on window sill at z={sill_top:.3f} "
                     f"(x -2.62 / -2.40, avoid plant at x=-2.0)")

        # ── 4. 甜品托盘 DC_DessertTray（吧台顶 z=0.95）────────────
        bar_top = P.BAR_TOP_Z
        # 吧台面空位：对 47 个台面物件做 2D 圆-矩形占位扫描（托盘足迹 r=0.165 + 6mm 余量），
        # 唯一可用真空区 = x∈[0.39,1.03] × y∈[1.28,1.74]（640×460mm），取其中点。
        # 旧位 x=1.62 落在 BA_Pour_Tray(1.16–1.60) 上，实测穿透 9mm / 350mm。
        # furn-modeler 实测空档 x[0.675,1.16]（餐巾盒 0.565-0.675 / 手冲台 1.16 起）。
        # 托盘半径 0.168 → 中心须 ≥ 0.675+0.174 = 0.849；取 0.90，右侧到 1.074 < 1.16。
        tx, ty = 0.90, 1.46
        add(Cc.cyl("DC_DessertTray_Plate", r=0.165, h=0.012, segs=24,
                   loc=(tx, ty, bar_top + 0.006), mat=m_brass, col=COL,
                   bevel=0.003, bsegs=1, shade="smooth"))
        add(Cc.cyl("DC_DessertTray_Rim", r=0.168, h=0.016, segs=24,
                   loc=(tx, ty, bar_top + 0.012), mat=m_brass, col=COL,
                   shade="smooth"))
        # 3 块切件（楔形，用 lathe 小角度扫掠不方便，这里用薄三棱柱 poly_prism）
        for i, (ang, mat_c, cream) in enumerate([
                (-60 * D2R, m_cake_a, True),
                (60 * D2R, m_cake_b, True),
                (180 * D2R, m_cake_a, False)]):
            wedge = [(0.0, 0.0)]
            for k in range(5):
                a = ang + (k / 4.0 - 0.5) * 0.62
                wedge.append((0.062 * math.cos(a), 0.062 * math.sin(a)))
            add(Cc.poly_prism(f"DC_DessertTray_Slice{i}", wedge, thickness=0.052,
                              axis="Z", loc=(tx, ty, bar_top + 0.064),   # -16mm：盘面顶 0.962，切片底贴面
                              mat=mat_c, col=COL, bevel=0.003, shade="flat"))
            if cream:
                add(Cc.cyl(f"DC_DessertTray_Cream{i}", r=0.022, h=0.014, segs=12,
                           loc=(tx + 0.030 * math.cos(ang), ty + 0.030 * math.sin(ang),
                                bar_top + 0.112),
                           mat=m_cream, col=COL, shade="smooth"))
        # 蛋糕刀（黄铜）
        add(Cc.box("DC_DessertTray_KnifeBlade", (0.115, 0.022, 0.0035),
                   loc=(tx - 0.085, ty - 0.055, bar_top + 0.034),   # 落在盘面上
                   rot=(0, 0, -24 * D2R), mat=m_brass, col=COL, bevel=0.001, segs=1))
        add(Cc.box("DC_DessertTray_KnifeHandle", (0.085, 0.018, 0.013),
                   loc=(tx - 0.175, ty - 0.008, bar_top + 0.018),   # -16mm 与刀片同高
                   rot=(0, 0, -24 * D2R), mat=m_dark, col=COL,
                   bevel=0.004, segs=2))
        # 餐巾（折角白布）
        add(Cc.box("DC_DessertTray_Napkin", (0.115, 0.095, 0.006),
                   loc=(tx + 0.075, ty - 0.105, bar_top + 0.015),   # -16mm 铺在盘面上
                   rot=(0, 0, 14 * D2R), mat=m_linen, col=COL,
                   bevel=0.002, segs=1))
        notes.append("dessert tray on bar top (cake slices + brass knife + napkin), "
                     "placed in free span x=0.90 (only clear span on bar top, per real AABB scan)")

        # ── 5. 黑板侧壁架 + 现成资源（老兄：装饰要好看，直接用现成咖啡厅资源）──
        # 删掉原先手搓的挂牌/挂钩/干花/贴纸牌（老兄反馈不好看）。
        # 左墙北侧空带：黑板 y 到 0.60，书架 y 从 1.55 起 → 取 y∈[0.72,1.42]
        wall_x = P.ROOM_X[0]
        m_wood_d = M["wood_dark"]
        m_brass = M["brass"]

        # 5a. 木壁架底板（贴墙，z=1.55）
        shelf_y0, shelf_y1 = 0.70, 1.44
        shelf_cx = wall_x + 0.135
        add(Cc.box("DC_ShelfN_Board", (0.26, shelf_y1 - shelf_y0, 0.028),
                   loc=(shelf_cx, (shelf_y0 + shelf_y1) / 2, 1.550),
                   mat=m_wood_d, col=COL, bevel=0.004, segs=1))
        # 5b. 两个黄铜托架（贴墙三角）
        for k, yy in enumerate((shelf_y0 + 0.10, shelf_y1 - 0.10)):
            add(Cc.box(f"DC_ShelfN_Bracket_{k}", (0.20, 0.022, 0.022),
                       loc=(wall_x + 0.115, yy, 1.512), mat=m_brass, col=COL))
            add(Cc.box(f"DC_ShelfN_BracketV_{k}", (0.022, 0.022, 0.10),
                       loc=(wall_x + 0.022, yy, 1.470), mat=m_brass, col=COL))

        # 5c. 现成资源：黄铜花瓶 / 茶具 / 小盆栽（摆壁架上，底面 z=1.564）
        shelf_top = 1.564
        v = _place_asset(Cc, "brass_vase_01", wall_x + 0.255, shelf_y0 + 0.20,
                         shelf_top, 0.24, "DC_ShelfVase", align="wall-x")
        if v:
            objs += v
            notes.append("shelf: brass_vase_01")

        v = _place_asset(Cc, "tea_set_01", wall_x + 0.255, (shelf_y0 + shelf_y1) / 2,
                         shelf_top, 0.16, "DC_ShelfTea", align="wall-x",
                         target_size=0.20)
        if v:
            objs += v
            notes.append("shelf: tea_set_01")

        v = _place_asset(Cc, "potted_plant_04", wall_x + 0.255, shelf_y1 - 0.16,
                         shelf_top, 0.20, "DC_ShelfPlant", align="wall-x")
        if v:
            objs += v
            notes.append("shelf: potted_plant_04")

        notes.append("blackboard-side decor replaced with PolyHaven assets on a wall shelf")


        bpy.context.view_layer.update()
        tris = Cc.tri_count(objs)
        C.log(f"{MODULE}: {len(objs)} objects, {tris} tris")
        return {"objects": objs, "colliders": colliders,
                "notes": "; ".join(notes), "tris": tris}

    except Exception as e:
        import traceback
        traceback.print_exc()
        C.log("[cdecor_extra] FAILED (non-fatal):", repr(e))
        try:
            bpy.context.view_layer.update()
            tris = Cc.tri_count(objs)
        except Exception:
            tris = 0
        return {"objects": objs, "colliders": colliders,
                "notes": "cdecor_extra failed: " + repr(e), "tris": tris}


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    M = MAT.palette()
    r = build_extra(P, C, M, {})
    C.selfcheck(MODULE, r["objects"], res=(960, 720), samples=24,
                views=[
                    {"name": "sign", "from": (0.10, -1.60, 1.55),
                     "look": (-0.16, -2.97, 1.55), "lens": 32},
                    {"name": "bar", "from": (1.60, 0.20, 1.75),
                     "look": (2.60, 1.60, 1.30), "lens": 30},
                    {"name": "sill", "from": (-2.30, -1.70, 1.20),
                     "look": (-2.55, -2.93, 0.78), "lens": 34},
                ])
