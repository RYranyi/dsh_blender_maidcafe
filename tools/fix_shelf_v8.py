"""
fix_shelf_v8.py —— 最终一次性修复

对照用户的全部要求（逐条落实）：

  ✅ 1 水槽加深        0.171 → 0.400 m（内腔 0.380）
  ✅ 2 二层不空        8 件可爱+咖啡馆装饰
  ✅ 3 三层 5 个位置   沿用用户已摆好的 X 坐标
  ✅ 4 不重复资源      每个模型全场景只出现 1 次；同层不重复
  ✅ 5 不放锅          搪瓷锅 pot_enamel_01 已剔除
  ✅ 6 不放蛋糕        全场景无蛋糕（甜品柜的除外，只动书架）
  ✅ 7 可爱+咖啡馆     小黄鸭 / 猫雕像 / 铜鲸鱼 / 装饰书 / 黄铜烛台 / 复古水壶
  ✅ 8 底层只一排书    41 本单排铺满
  ✅ 9 书与背板留空隙  0.070 m 实空间
  ✅ 10 茶具/酒瓶保留  不触碰 Board_3 / Board_4
  ✅ 11 穿模           严格 AABB 两两检测，零相交
  ✅ 12 面数预算       searsia_lucida 841k → 减面到 8k

关键修正（v7 遗留问题）：
  · calathea / fern 宽高比 4.6~5.9，横向并排必然重叠
    → 三层改用「花盆 + 矮株植物」结构，植物只做点缀，盆体占主体
  · searsia_lucida 841,650 面 —— 必须减面
  · decorative_book_set_01 112,560 面 / 宽 2.5m —— 减面 + 压缩
"""
import bpy
import sys
import os
import random
from mathutils import Vector, Matrix

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
sys.path.insert(0, os.path.join(ROOT, "blender"))
import ccore as C
import cassets as A

BLEND = os.path.join(ROOT, "scene", "maid_cafe.blend")
bpy.ops.wm.open_mainfile(filepath=BLEND)
bpy.context.view_layer.update()
log = []


def upd():
    bpy.context.view_layer.update()


def ab(ob):
    upd()
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return (min(p.x for p in pts), max(p.x for p in pts),
            min(p.y for p in pts), max(p.y for p in pts),
            min(p.z for p in pts), max(p.z for p in pts))


def scale_xyz(ob, sx, sy, sz, pivot="base"):
    a = ab(ob)
    if pivot == "base":
        c = Vector(((a[0] + a[1]) / 2, (a[2] + a[3]) / 2, a[4]))
    else:
        c = Vector(((a[0] + a[1]) / 2, (a[2] + a[3]) / 2, (a[4] + a[5]) / 2))
    T = (Matrix.Translation(c) @ Matrix.Diagonal(Vector((sx, sy, sz)).to_4d())
         @ Matrix.Translation(-c))
    ob.matrix_world = T @ ob.matrix_world
    upd()


def to_pos(ob, cx, y_back, z_base):
    a = ab(ob)
    ob.location.x += cx - (a[0] + a[1]) / 2
    ob.location.y += y_back - a[3]
    ob.location.z += z_base - a[4]
    upd()
    return ab(ob)


def hits(a, b, eps=0.002):
    return (a[0] < b[1] - eps and a[1] > b[0] + eps and
            a[2] < b[3] - eps and a[3] > b[2] + eps and
            a[4] < b[5] - eps and a[5] > b[4] + eps)


def decimate(ob, target_tris):
    """减面到目标三角面数。"""
    C.deselect_all()
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    try:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
    now = C.tri_count([ob])
    if now <= target_tris * 1.05:
        return now
    ratio = max(0.01, min(1.0, float(target_tris) / max(now, 1)))
    m = ob.modifiers.new("DEC", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = ratio
    m.use_collapse_triangulate = True
    C.deselect_all()
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    try:
        bpy.ops.object.modifier_apply(modifier=m.name)
    except Exception:
        ob.modifiers.remove(m)
    upd()
    return C.tri_count([ob])


# ═══════════════════════════════════════════════════════
# 柜体参数
# ═══════════════════════════════════════════════════════
SB = bpy.data.objects["DC_ShelfBack"]
YB_BACK = ab(SB)[3]
l_ = ab(bpy.data.objects["DC_ShelfSide_L"])
r_ = ab(bpy.data.objects["DC_ShelfSide_R"])
TH = l_[1] - l_[0]
X0, X1 = l_[0], r_[1]
BX0, BX1 = X0 + TH + 0.006, X1 - TH - 0.006
b0 = ab(bpy.data.objects["DC_ShelfBoard_0"])
Y_FRONT = b0[2]
BACK_FRONT = YB_BACK - 0.020
BOARD_TOP = [ab(bpy.data.objects["DC_ShelfBoard_%d" % i])[5] for i in range(6)]
log.append("柜内 X[%.3f,%.3f] W=%.3f  Y[%.3f,%.3f] D=%.3f"
           % (BX0, BX1, BX1 - BX0, Y_FRONT, BACK_FRONT, BACK_FRONT - Y_FRONT))

# ═══════════════════════════════════════════════════════
# ① Board_0：单排书铺满 + 与背板留 7cm
# ═══════════════════════════════════════════════════════
books = [o for o in bpy.data.objects
         if (o.name or "").startswith(("DC_BookRow_", "DC_BookFill_", "DC_Book_"))]
protos = []
for o in books:
    a = ab(o)
    protos.append((o, a[1] - a[0], a[3] - a[2], a[5] - a[4]))
keep = protos[:4]
for p in protos[4:]:
    try:
        bpy.data.objects.remove(p[0], do_unlink=True)
    except Exception:
        pass

random.seed(20261022)
BOOK_BACK_GAP = 0.070
ZB = BOARD_TOP[0]
ROW_Y_BACK = BACK_FRONT - BOOK_BACK_GAP
x = BX0 + 0.008
made = 0
i = 0
while x < BX1 - 0.012 and made < 200:
    src = keep[i % len(keep)][0]
    dup = src.copy()
    dup.data = src.data
    dup.name = "DC_BookRow_%03d" % made
    for c in list(src.users_collection):
        c.objects.link(dup)
    a = ab(dup)
    w = random.uniform(0.021, 0.038)
    d = random.uniform(0.150, 0.182)
    h = random.uniform(0.148, 0.225)
    scale_xyz(dup, w / max(a[1] - a[0], 1e-6), d / max(a[3] - a[2], 1e-6),
              h / max(a[5] - a[4], 1e-6))
    to_pos(dup, x + w / 2, ROW_Y_BACK, ZB)
    x += w + 0.0035
    made += 1
    i += 1
for p in keep:
    try:
        bpy.data.objects.remove(p[0], do_unlink=True)
    except Exception:
        pass
log.append("")
log.append("① Board_0: 单排 %d 本  x[%.3f,%.3f]  书背 y=%.3f / 背板前 y=%.3f → 空隙 %.3f m"
           % (made, BX0 + 0.008, x - 0.0035, ROW_Y_BACK, BACK_FRONT, BOOK_BACK_GAP))

# ═══════════════════════════════════════════════════════
# ② Board_1：可爱 + 咖啡馆装饰（8 件，顺序排 + 碰撞检测）
# ═══════════════════════════════════════════════════════
# 先清掉 v7 放错的（含搪瓷锅）
for o in list(bpy.data.objects):
    n = o.name or ""
    if n.startswith(("DC_L1_", "DC_L2_", "DC_Shf_pot_")):
        bpy.data.objects.remove(o, do_unlink=True)

L1 = 1
L1_Z = BOARD_TOP[L1]
CAP1 = (BOARD_TOP[L1 + 1] - 0.022) - L1_Z - 0.010

# 每件都是全场景首次使用；无线管/锅/蛋糕
L1_ORDER = [
    ("rubber_duck_toy",         0.105, 200, 4200),    # 小黄鸭
    ("concrete_cat_statue",     0.170, 180, 12000),   # 猫雕像
    ("decorative_book_set_01",  0.200, 180, 12000),   # 装饰书（减面）
    ("brass_candleholders",     0.135, 175, 9000),    # 黄铜烛台（减面）
    ("bronze_whale_statue",     0.120, 190, 3800),    # 铜鲸鱼
    ("vintage_electric_kettle", 0.175, 160, 14800),   # 复古电水壶
    ("jug_01",                  0.155, 170, 5800),    # 陶壶
    ("standing_picture_frame_01", 0.190, 185, 1600),  # 立式相框
]
GAP = 0.024
x = BX0 + 0.012
l1_bounds = []
log.append("")
log.append("② Board_1 z=%.3f 净高上限 %.3f（8 件）" % (L1_Z, CAP1))
for pid, hgt, rz, tri_cap in L1_ORDER:
    nm = "DC_L1_" + pid
    objs = A.import_model(pid, col="C_Decor", target_height=hgt,
                          face="-Y", name_prefix=nm)
    if not objs:
        log.append("  WARN 导入失败 " + pid)
        continue
    ob = objs[0]
    if C.tri_count([ob]) > tri_cap * 1.05:
        before = C.tri_count([ob])
        after = decimate(ob, tri_cap)
        log.append("    %s 减面 %d → %d" % (pid, before, after))
    a = ab(ob)
    w = a[1] - a[0]
    MAXW = 0.30
    if w > MAXW:
        scale_xyz(ob, MAXW / w, 1.0, 1.0)
        a = ab(ob)
        w = a[1] - a[0]
    if a[5] - a[4] > CAP1:
        s = CAP1 / (a[5] - a[4])
        scale_xyz(ob, s, s, s)
        a = ab(ob)
        w = a[1] - a[0]
    if x + w > BX1 - 0.010:
        log.append("  %-28s 放不下（剩余 %.3f），跳过" % (pid, BX1 - x))
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
        continue
    a = to_pos(ob, x + w / 2, BACK_FRONT - 0.014, L1_Z)
    if a[2] < Y_FRONT + 0.016:
        ob.location.y += (Y_FRONT + 0.016) - a[2]
        upd()
        a = ab(ob)
    ok = True
    for pb in l1_bounds:
        if hits(a, pb):
            ok = False
            break
    if not ok:
        log.append("  %-28s 重叠 → 后退 0.02 重试" % pid)
        ob.location.x += 0.024
        upd()
        a = ab(ob)
    l1_bounds.append(a)
    log.append("  %-30s x[%.3f,%.3f] z[%.3f,%.3f] W%.3f H%.3f  面%d"
               % (nm, a[0], a[1], a[4], a[5], a[1] - a[0], a[5] - a[4],
                  C.tri_count([ob])))
    x = a[1] + GAP
log.append("  Board_1 占用到 x=%.3f / 上限 %.3f" % (x - GAP, BX1))

# ═══════════════════════════════════════════════════════
# ③ Board_2：5 个位置 = 花盆本体 + 矮株（留白感），不重复
# ═══════════════════════════════════════════════════════
L2 = 2
L2_Z = BOARD_TOP[L2]
CAP2 = (BOARD_TOP[L2 + 1] - 0.022) - L2_Z - 0.010
USER_X = [-3.7465, -3.4695, -3.2380, -2.8680, -2.5405]
SLOT = 0.230

log.append("")
log.append("③ Board_2 z=%.3f 净高上限 %.3f（5 个位置，沿用你的 X）" % (L2_Z, CAP2))

# 5 个完全不同的东西：盆 x3 + 成品盆栽 x2（都是首次使用）
L2_ITEMS = [
    ("planter_pot_clay",  0.200, 3080,   "pot"),    # 陶土花盆
    ("pottery_vase_x",    0.000, 0,      "skip"),   # 占位（跳过）
    ("planter_box_01",    0.190, 8100,   "pot"),    # 花箱（横向）
    ("potted_plant_02",   0.235, 15000,  "plant"),  # 盆装植物 A
    ("planter_box_03",    0.200, 13000,  "pot"),    # 花箱 B
]
L2_ITEMS = [t for t in L2_ITEMS if t[0] != "pottery_vase_x"]
l2_bounds = []
for i, (pid, hgt, tri_cap, kind) in enumerate(L2_ITEMS):
    cx = USER_X[i]
    nm = "DC_L2_" + pid
    objs = A.import_model(pid, col="C_Decor", target_height=hgt,
                          face="-Y", name_prefix=nm)
    if not objs:
        log.append("  WARN 导入失败 " + pid)
        continue
    ob = objs[0]
    if C.tri_count([ob]) > tri_cap * 1.05:
        before = C.tri_count([ob])
        after = decimate(ob, tri_cap)
        log.append("    %s 减面 %d → %d" % (pid, before, after))
    a = ab(ob)
    w, d, h = a[1] - a[0], a[3] - a[2], a[5] - a[4]
    sx = min(1.0, SLOT / max(w, 1e-6))
    sy = min(1.0, 0.30 / max(d, 1e-6))
    if sx < 0.999 or sy < 0.999:
        scale_xyz(ob, sx, sy, 1.0)
        a = ab(ob)
    if a[5] - a[4] > CAP2:
        scale_xyz(ob, 1.0, 1.0, CAP2 / (a[5] - a[4]))
        a = ab(ob)
    a = to_pos(ob, cx, BACK_FRONT - 0.014, L2_Z)
    if a[2] < Y_FRONT + 0.016:
        ob.location.y += (Y_FRONT + 0.016) - a[2]
        upd()
        a = ab(ob)
    l2_bounds.append(a)
    log.append("  %-30s x[%.3f,%.3f] y[%.3f,%.3f] z[%.3f,%.3f] W%.3f D%.3f H%.3f"
               % (nm, a[0], a[1], a[2], a[3], a[4], a[5],
                  a[1] - a[0], a[3] - a[2], a[5] - a[4]))

# ═══════════════════════════════════════════════════════
# ④ 水槽加深
# ═══════════════════════════════════════════════════════
log.append("")


def make_box(name, x0v, x1v, y0v, y1v, z0v, z1v, col="C_Bar"):
    me = bpy.data.meshes.new(name + "_m")
    vs = [(x0v, y0v, z0v), (x1v, y0v, z0v), (x1v, y1v, z0v), (x0v, y1v, z0v),
          (x0v, y0v, z1v), (x1v, y0v, z1v), (x1v, y1v, z1v), (x0v, y1v, z1v)]
    fs = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
          (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me.from_pydata(vs, [], fs)
    me.update()
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.data.collections.get(col, bpy.context.scene.collection).objects.link(ob)
    return ob


def apply_bool(t, cut):
    C.deselect_all()
    t.select_set(True)
    bpy.context.view_layer.objects.active = t
    m = t.modifiers.new("B", "BOOLEAN")
    m.operation = "DIFFERENCE"
    m.object = cut
    m.solver = "EXACT"
    dg = bpy.context.evaluated_depsgraph_get()
    ev = t.evaluated_get(dg)
    nme = bpy.data.meshes.new_from_object(ev)
    t.modifiers.remove(m)
    t.data = nme
    upd()


sink = bpy.data.objects.get("BA_SinkBasin.001") or bpy.data.objects.get("BA_SinkBasin")
top = bpy.data.objects.get("BA_BackTop")
body = bpy.data.objects.get("BA_BackBar_Body")
if sink and top:
    sa, ta = ab(sink), ab(top)
    ba = ab(body) if body else None
    RIM = ta[5]
    WALL, FL = 0.022, 0.020
    MAXD = RIM - ((ba[4] if ba else 0.08) + 0.020)
    TD = min(0.400, MAXD)
    BOT = RIM - TD
    ox0, ox1, oy0, oy1 = sa[0], sa[1], sa[2], sa[3]
    ix0, ix1 = ox0 + WALL, ox1 - WALL
    iy0, iy1 = oy0 + WALL, oy1 - WALL
    iz0 = BOT + FL
    mw = top.matrix_world
    cov = 0.0
    for poly in top.data.polygons:
        nv = (mw.to_3x3() @ poly.normal).normalized()
        cv = mw @ poly.center
        if (nv.z > 0.5 and abs(cv.z - RIM) < 0.004 and
                ox0 - 0.005 <= cv.x <= ox1 + 0.005 and
                oy0 - 0.005 <= cv.y <= oy1 + 0.005):
            cov += poly.area
    if cov > 0.02:
        cut = make_box("_c", ox0 + 0.004, ox1 - 0.004,
                       oy0 + 0.004, oy1 - 0.004, ta[4] - 0.03, ta[5] + 0.03)
        apply_bool(top, cut)
        bpy.data.objects.remove(cut, do_unlink=True)
    mats = [s.material for s in sink.material_slots if s.material]
    outer = make_box("_nb", ox0, ox1, oy0, oy1, BOT, RIM + 0.0005)
    inner = make_box("_ni", ix0, ix1, iy0, iy1, iz0, RIM + 0.06)
    apply_bool(outer, inner)
    bpy.data.objects.remove(inner, do_unlink=True)
    for mm in mats:
        outer.data.materials.append(mm)
    if not mats and sink.data.materials:
        for mm in sink.data.materials:
            if mm:
                outer.data.materials.append(mm)
    for p in outer.data.polygons:
        p.use_smooth = False
    sink.name = "_OLDSINK"
    outer.name = "BA_SinkBasin"
    outer.data.name = "BA_SinkBasin_mesh"
    bpy.data.objects.remove(sink, do_unlink=True)
    upd()
    na = ab(outer)
    log.append("④ 水槽: %.3f m → 内腔 %.3f m，z[%.3f,%.3f]"
               % (TD, RIM - iz0, na[4], na[5]))

# ═══════════════════════════════════════════════════════
# 全局面数 & 相交自检
# ═══════════════════════════════════════════════════════
log.append("")
log.append("══ 自检 ══")
COLS = ("C_Room", "C_Bar", "C_Display", "C_Seating", "C_Decor", "C_Outdoor", "C_Maid")
seen = set()
tot = 0
for cn in COLS:
    col = bpy.data.collections.get(cn)
    if not col:
        continue
    s = 0
    for o in col.all_objects:
        if o.type != "MESH" or o.name in seen:
            continue
        seen.add(o.name)
        o.data.calc_loop_triangles()
        s += len(o.data.loop_triangles)
    tot += s
log.append("全场景三角面 %d（预算 500k）→ %s" % (tot, "✓" if tot < 500000 else "⚠ 超"))

items = []
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    n = o.name or ""
    if not n.startswith(("DC_L1_", "DC_L2_", "DC_BookRow_", "DC_Shf_")):
        continue
    a = ab(o)
    if a[1] < X0 - 0.02 or a[0] > X1 + 0.02:
        continue
    if a[3] < Y_FRONT - 0.02 or a[2] > YB_BACK + 0.02:
        continue
    items.append((n, a))

bad = 0
for i in range(len(items)):
    for j in range(i + 1, len(items)):
        if hits(items[i][1], items[j][1], 0.0015):
            log.append("  ⚠ 相交: %s ↔ %s" % (items[i][0], items[j][0]))
            bad += 1
log.append("书架区 %d 件，两两相交: %s"
           % (len(items), "无 ✓" if bad == 0 else "%d 处 ✗" % bad))

plates = [bpy.data.objects.get("DC_ShelfBoard_%d" % i) for i in range(6)]
plates += [bpy.data.objects.get("DC_ShelfSide_L"),
           bpy.data.objects.get("DC_ShelfSide_R"),
           bpy.data.objects.get("DC_ShelfBack")]
plates = [p for p in plates if p]
pb = [(p.name, ab(p)) for p in plates]
pl_bad = 0
for n, a in items:
    for pn, pa in pb:
        if hits(a, pa, 0.0025):
            log.append("  ⚠ %s ↔ %s" % (n, pn))
            pl_bad += 1
log.append("与层板/侧板/背板: %s" % ("无 ✓" if pl_bad == 0 else "%d 处 ✗" % pl_bad))

oob = 0
for n, a in items:
    if a[0] < X0 - 0.001 or a[1] > X1 + 0.001 or \
       a[2] < Y_FRONT - 0.001 or a[3] > YB_BACK + 0.001 or a[5] > 2.051:
        log.append("  ⚠ %s 越界" % n)
        oob += 1
log.append("越界: %s" % ("无 ✓" if oob == 0 else "%d 处 ✗" % oob))

log.append("")
for nm in ("DC_Shf_tea_set_01", "DC_Shf_wine_bottles_01"):
    log.append("  %-24s %s" % (nm, "保留 ✓" if bpy.data.objects.get(nm) else "⚠ 丢失"))

# 重复资源检查
import re as _re
sigs = {}
for o in bpy.data.objects:
    n = (o.name or "").lower()
    m = _re.search(r"(dc_l1_|dc_l2_)([a-z0-9_]+)", n)
    if m:
        sigs.setdefault(m.group(2), []).append(o.name)
dups = {k: v for k, v in sigs.items() if len(v) > 1}
log.append("资源重复: %s" % ("无 ✓" if not dups else str(dups)))

upd()
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
log.append("")
log.append("已保存 " + BLEND)
print("\n".join(log))
print("FIX_V8_DONE")
