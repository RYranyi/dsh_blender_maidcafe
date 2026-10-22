"""
cmaid.py — C_Maid：chibi 女仆导入 / 减面 / 骨骼摆姿势（双手托托盘）/ 托盘+蛋糕+咖啡

来源：由 maid_chibi 程序化生成，路径由 cprop.MAID_SRC 指定（可用环境变量覆盖）
      （68 mesh / 1.33M tris / 无 UV / 原高 1.0224 m / 面朝 -Y）

流程（顺序很重要）
  1. append 全部网格 → 链接进 C_Maid
  2. 分组 Decimate（大件重、脸轻）→ 目标 ≤ 240k tris
  3. 统一缩放到 MAID_SCALE，落地 z=0，仍以原点为中心、面朝 -Y
  4. 给双臂建 2 段骨骼（上臂 / 前臂），按 z 高度做软权重绑定
  5. 摆姿势：上臂前收、前臂上抬 → 双手在身前托盘下方；bake 后删骨骼
  6. 建托盘 + 草莓蛋糕 + 白瓷杯碟 + 蒸汽面片（世界米制，贴着双手）
  7. 整体旋转 MAID_ROT_Z 并平移到 MAID_POS
"""
import bpy
import math
import os
import sys
from mathutils import Vector, Matrix, Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
                else os.getcwd())
import ccore as C
import cprop as P
import cmat as MAT

MODULE = "cmaid"
OWNER = "lead"
TRI_BUDGET = 260000
COL = "C_Maid"
D2R = C.D2R
PI = C.PI

# ── 原模型（未缩放）关键解剖高度（来自 _probe_maid_arms.py）──────────
Z_SHOULDER = 0.552
Z_ELBOW = 0.418
Z_WRIST = 0.352
ORIG_H = 1.0224        # 原模型身高（未缩放）
X_SHOULDER = 0.104
X_ELBOW = 0.125
X_WRIST = 0.140
Y_SHOULDER = -0.010
Y_ELBOW = -0.055
Y_WRIST = -0.130

# ── 姿势角度（度，骨骼局部）────────────────────────────────────────
POSE_UPPER = (-14.0, 0.0, -6.0)    # 上臂：先前收 + 微外张
POSE_FORE = (-78.0, 0.0, 0.0)      # 前臂：上抬 78° → 手到胸前高度
POSE_HAND_TWIST = 0.0


# ══════════════════════════════════════════════════════════════════════
def _alive(ob):
    try:
        return ob is not None and ob.name in bpy.data.objects
    except Exception:
        return False


def _load_maid_objects():
    src = P.MAID_SRC
    if not os.path.exists(src):
        C.log("FATAL maid blend missing", src)
        return []
    with bpy.data.libraries.load(src, link=False) as (s, d):
        d.objects = list(s.objects)
        d.materials = list(s.materials)
        d.images = list(s.images)
    col = bpy.context.scene.collection
    got = []
    for ob in d.objects:
        if ob is None:
            continue
        try:
            if ob.name not in col.objects:
                col.objects.link(ob)
            got.append(ob)
        except Exception as e:
            C.log("maid link fail", getattr(ob, "name", "?"), e)
    C.log("maid: loaded %d objects" % len(got))
    return got


def _purge_nonmesh(objs):
    for ob in list(objs):
        if _alive(ob) and ob.type != "MESH":
            try:
                bpy.data.objects.remove(ob, do_unlink=True)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# 减面
# ══════════════════════════════════════════════════════════════════════
def _classify(ob):
    n = ob.name.lower()
    if any(k in n for k in ("iris", "eyehl", "lash", "brow", "mouth", "redaccent", "lowerlid", "eyewhite")):
        return "face"
    if any(k in n for k in ("head", "neck", "hand")):
        return "head"
    if any(k in n for k in ("skirt", "bodice", "apron", "sleeve", "leg", "torso", "hair", "fringe", "haircap", "lock")):
        return "big"
    return "small"


def _decimate_group(objs):
    stats = {}
    for ob in objs:
        if not _alive(ob) or ob.type != "MESH":
            continue
        t0 = C.tri_count(ob)
        g = _classify(ob)
        ratio = P.MAID_DECIMATE[g]
        if t0 > 400 and ratio < 0.999:
            try:
                C.decimate(ob, ratio)
            except Exception as e:
                C.log("decimate fail", ob.name, e)
        t1 = C.tri_count(ob)
        s = stats.setdefault(g, [0, 0, 0])
        s[0] += 1
        s[1] += t0
        s[2] += t1
    for g in ("big", "head", "face", "small"):
        if g in stats:
            v = stats[g]
            C.log("decimate %-5s %2d objs %8d -> %7d tris" % (g, v[0], v[1], v[2]))
    return stats


# ══════════════════════════════════════════════════════════════════════
# 顶点色烘焙（程序化材质 → 顶点色，让 glTF/Three.js 也能看到渐变）
# ══════════════════════════════════════════════════════════════════════
SKIN_HEX = "#F7CBB8"
BLUSH_HEX = "#EE948C"
HAIR_DARK = "#4A2E1E"
HAIR_MID = "#654028"
HAIR_LIGHT = "#7C5539"


def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _hx(h):
    h = h.lstrip("#")
    return tuple(_srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def _smoothstep(a, b, x):
    if b <= a:
        return 0.0
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def _lerp3(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _ensure_col(ob, name="Col"):
    me = ob.data
    ca = me.color_attributes.get(name)
    if ca is None:
        # glTF 需要 POINT / FLOAT_COLOR（导出为 COLOR_0）
        ca = me.color_attributes.new(name=name, type="FLOAT_COLOR", domain="POINT")
    return ca


def _paint_skin(ob):
    """腮红/鼻子暖色：按到两个腮红中心 + 鼻尖距离计算（原模型坐标）。"""
    skin = _hx(SKIN_HEX)
    blush = _hx(BLUSH_HEX)
    ca = _ensure_col(ob)
    mw = ob.matrix_world
    for i, v in enumerate(ob.data.vertices):
        p = mw @ v.co
        d1 = (p - Vector((0.094, -0.150, 0.6735))).length
        d2 = (p - Vector((-0.094, -0.150, 0.6735))).length
        f = max(1.0 - _smoothstep(0.010, 0.056, d1), 1.0 - _smoothstep(0.010, 0.056, d2))
        d3 = (p - Vector((0.0, -0.150, 0.6500))).length
        f3 = 0.45 * (1.0 - _smoothstep(0.008, 0.045, d3))
        s = min(1.0, f + f3)
        c = _lerp3(skin, blush, s)
        ca.data[i].color = (c[0], c[1], c[2], 1.0)


def _paint_hair(ob):
    """头发：按高度做 4 段渐变（与原 ColorRamp 一致）。"""
    dark, mid, light = _hx(HAIR_DARK), _hx(HAIR_MID), _hx(HAIR_LIGHT)
    ca = _ensure_col(ob)
    mw = ob.matrix_world
    h = ORIG_H
    for i, v in enumerate(ob.data.vertices):
        z = max(0.0, min(1.0, (mw @ v.co).z / h))
        # stops: 0.55 dark, 0.72 mid, 0.87 light, 0.99 mid
        if z <= 0.55:
            c = dark
        elif z <= 0.72:
            c = _lerp3(dark, mid, _smoothstep(0.55, 0.72, z))
        elif z <= 0.87:
            c = _lerp3(mid, light, _smoothstep(0.72, 0.87, z))
        else:
            c = _lerp3(light, mid, _smoothstep(0.87, 0.99, z))
        ca.data[i].color = (c[0], c[1], c[2], 1.0)


def _sanitize_materials():
    """压掉女仆材质上的 sheen / clearcoat / anisotropy。

    为什么必须在**导出前**做（而不是只在网页侧修）：
    原模型 M_Hair 的 Principled 带 Sheen Weight，glTF 导出成
    `KHR_materials_sheen: {sheenColorFactor: [1,1,1]}`。three.js 会把 sheenColor
    解析成纯白，在**深棕发色**（顶点色 0.139,0.056,0.024）上叠一层白色绒光——
    实测浏览器里女仆头发整片渲染成白色。M_White/M_Satin/M_Navy 有同样问题（泛白/发灰）。
    Blender 自己的 EEVEE 观感不明显，但任何实时 PBR 查看器都会翻车，所以在源头关掉。
    """
    cfg = {
        # name: (sheen_weight, coat_weight, anisotropy, specular_level, roughness|None)
        # 全部压到 0：只要 Sheen Weight > 0，glTF 就会写出 KHR_materials_sheen，
        # 且 sheenColorFactor 取 Sheen Tint（默认纯白）→ three.js 里整片泛白。
        "M_Hair": (0.0, 0.0, 0.0, 0.38, 0.50),
        "M_White": (0.0, 0.0, 0.0, 0.38, None),
        "M_Satin": (0.0, 0.0, 0.0, 0.38, None),
        "M_Navy": (0.0, 0.0, 0.0, 0.38, None),
        "M_Skin": (0.0, 0.0, 0.0, 0.42, 0.55),
        "M_Sclera": (0.0, 0.0, 0.0, 0.55, None),
    }
    done = []
    for name, (sheen, coat, aniso, spec, rough) in cfg.items():
        m = bpy.data.materials.get(name)
        if not m or not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type != "BSDF_PRINCIPLED":
                continue
            ins = n.inputs
            if "Sheen Weight" in ins:
                ins["Sheen Weight"].default_value = sheen
                if sheen <= 0.0 and "Sheen Tint" in ins:
                    ins["Sheen Tint"].default_value = (0.0, 0.0, 0.0, 1.0)
            if "Coat Weight" in ins:
                ins["Coat Weight"].default_value = coat
            if "Anisotropic" in ins:
                ins["Anisotropic"].default_value = aniso
            if "Specular IOR Level" in ins:
                ins["Specular IOR Level"].default_value = spec
            if rough is not None and "Roughness" in ins:
                ins["Roughness"].default_value = rough
        done.append(name)
    C.log("maid: sanitized materials %s" % ",".join(done))
    return done


def _use_vcol(mat_name):
    m = bpy.data.materials.get(mat_name)
    if not m or not m.use_nodes:
        return False
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return False
    for l in list(nt.links):
        if l.to_node == bsdf and l.to_socket.name in ("Base Color",):
            nt.links.remove(l)
    ca_node = nt.nodes.new("ShaderNodeVertexColor")
    ca_node.layer_name = "Col"
    ca_node.location = (-520, 260)
    nt.links.new(ca_node.outputs["Color"], bsdf.inputs["Base Color"])
    return True


def _bake_vertex_colors(meshes):
    """对 M_Skin / M_Hair 的网格烘焙顶点色；M_Iris 已有 Col。"""
    n_skin = n_hair = 0
    for ob in meshes:
        if not _alive(ob) or ob.type != "MESH":
            continue
        mats = [m.name for m in ob.data.materials if m]
        if "M_Skin" in mats:
            _paint_skin(ob)
            n_skin += 1
        elif "M_Hair" in mats:
            _paint_hair(ob)
            n_hair += 1
    _use_vcol("M_Skin")
    _use_vcol("M_Hair")
    C.log("vertex colors baked: skin %d objs, hair %d objs" % (n_skin, n_hair))
    return n_skin + n_hair


# ══════════════════════════════════════════════════════════════════════
# 手臂骨骼
# ══════════════════════════════════════════════════════════════════════
ARM_GROUP = ("Arm", "Arm.001", "Hand", "Hand.001", "Sleeve", "Sleeve.001",
             "Cuff", "Cuff.001")


def _arm_objects(objs):
    return [o for o in objs if _alive(o) and o.type == "MESH" and o.name in ARM_GROUP]


def _make_armature(scale):
    """两段骨骼 ×2。坐标已乘 scale（此时角色已缩放到米制）。"""
    arm_data = bpy.data.armatures.new("MD_ArmatureData")
    arm_ob = bpy.data.objects.new("MD_Armature", arm_data)
    C.ensure_collection(COL).objects.link(arm_ob)
    bpy.context.view_layer.objects.active = arm_ob
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    for side, sx in (("R", 1.0), ("L", -1.0)):
        up = eb.new("MD_Up_" + side)
        up.head = Vector((sx * X_SHOULDER * scale, Y_SHOULDER * scale, Z_SHOULDER * scale))
        up.tail = Vector((sx * X_ELBOW * scale, Y_ELBOW * scale, Z_ELBOW * scale))
        fo = eb.new("MD_Fore_" + side)
        fo.head = up.tail
        fo.tail = Vector((sx * X_WRIST * scale, Y_WRIST * scale, Z_WRIST * scale))
        fo.parent = up
        fo.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_ob


def _bind_and_pose(arm_ob, arm_meshes, scale):
    """按 z 高度软权重建顶点组 → Armature 修改器 → 摆姿势 → bake。"""
    if not arm_meshes:
        return
    z_hi = Z_ELBOW + 0.045
    z_lo = Z_ELBOW - 0.045
    for ob in arm_meshes:
        side = "L" if ob.name.endswith(".001") else "R"
        # 先应用物体变换（让顶点坐标=世界坐标），权重才按世界 z 算
        C.deselect_all()
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        C.deselect_all()
        g_up = ob.vertex_groups.new(name="MD_Up_" + side)
        g_fo = ob.vertex_groups.new(name="MD_Fore_" + side)
        me = ob.data
        for v in me.vertices:
            z = v.co.z / scale if scale else v.co.z     # 反算原模型 z
            # w_up = 1 高于肘，0 低于肘；中间平滑
            t = (z - z_lo) / (z_hi - z_lo) if z_hi > z_lo else 1.0
            t = 0.0 if t < 0 else (1.0 if t > 1 else t)
            w_up = t * t * (3 - 2 * t)
            if w_up > 0.001:
                g_up.add([v.index], w_up, "REPLACE")
            if 1.0 - w_up > 0.001:
                g_fo.add([v.index], 1.0 - w_up, "REPLACE")
        m = ob.modifiers.new("MDArm", "ARMATURE")
        m.object = arm_ob
        m.use_vertex_groups = True
    # 摆姿势
    for pb in arm_ob.pose.bones:
        pb.rotation_mode = "XYZ"
    for side in ("R", "L"):
        up = arm_ob.pose.bones["MD_Up_" + side]
        fo = arm_ob.pose.bones["MD_Fore_" + side]
        sgn = 1.0 if side == "R" else -1.0
        # 上臂：绕 X（前收）、绕 Z（内收，左右对称取反）
        up.rotation_euler = Euler((POSE_UPPER[0] * D2R,
                                   POSE_UPPER[1] * D2R,
                                   POSE_UPPER[2] * D2R * sgn), "XYZ")
        # 前臂：绕 X 上抬（左右一致），再绕 Z 微微内收
        fo.rotation_euler = Euler((POSE_FORE[0] * D2R,
                                   POSE_FORE[1] * D2R,
                                   (POSE_FORE[2] if len(POSE_FORE) > 2 else 0.0) * D2R * sgn), "XYZ")
    bpy.context.view_layer.update()
    # bake 姿势到网格后移除骨骼
    for ob in arm_meshes:
        C.deselect_all()
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        for m in list(ob.modifiers):
            if m.type == "ARMATURE":
                try:
                    bpy.ops.object.modifier_apply(modifier=m.name)
                except Exception as e:
                    C.log("armature apply fail", ob.name, e)
                    ob.modifiers.remove(m)
        for g in list(ob.vertex_groups):
            ob.vertex_groups.remove(g)
        C.deselect_all()
    bpy.data.objects.remove(arm_ob, do_unlink=True)
    C.log("arms posed & baked")


# ══════════════════════════════════════════════════════════════════════
# 托盘 + 食物（世界米制，角色原点在脚底中心，面朝 -Y）
# ══════════════════════════════════════════════════════════════════════
def _tray(M_, col):
    objs = []
    r = P.TRAY_R
    t = P.TRAY_T
    z = P.TRAY_Z
    y = P.TRAY_Y
    body = C.lathe("MD_Tray",
                   [(0.0, z - t), (r * 0.86, z - t), (r * 0.98, z - t * 0.45),
                    (r, z - t * 0.1), (r * 0.99, z), (r * 0.97, z + t * 0.12),
                    (r * 0.90, z + t * 0.16), (0.0, z + t * 0.16)],
                   segs=40, loc=(0.0, y, 0.0), mat=M_["wood_table"], col=col)
    C.shade_auto(body, 30 * D2R)
    objs.append(body)
    objs.append(C.ring_tube("MD_TrayRim", R=r * 0.985, r=t * 0.5, segs=40, rsegs=8,
                            loc=(0.0, y, z + t * 0.08), mat=M_["brass"], col=col))
    # 防滑衬垫：用米色棉布（避免 rough_linen 自带的冷蓝灰调）
    m_mat = MAT.M.pbr("MAT_Tray_Cloth", base="#F0E4D2", rough=0.86, sheen=0.35)
    objs.append(C.cyl("MD_TrayMat", r=r * 0.79, h=0.004, segs=36,
                      loc=(0.0, y, z + t * 0.18), mat=m_mat, col=col))
    return objs


def _cake_and_coffee(M_, col):
    objs = []
    y0 = P.TRAY_Y
    z0 = P.TRAY_Z + P.TRAY_T * 0.20
    plate_r = P.PLATE_R
    cake_r = P.CAKE_R
    cup_r = P.CUP_R
    saucer_r = P.SAUCER_R

    # 纸盘（左前）
    pxy = (-0.052, y0 - 0.012)
    objs.append(C.lathe("MD_Plate",
                        [(0.0, 0.0), (plate_r * 0.55, 0.0), (plate_r * 0.92, plate_r * 0.09),
                         (plate_r, plate_r * 0.28), (plate_r * 0.93, plate_r * 0.32),
                         (0.0, plate_r * 0.32)],
                        segs=30, loc=(pxy[0], pxy[1], z0), mat=M_["paper"], col=col))
    objs.append(C.ring_tube("MD_PlateRuffle", R=plate_r * 0.97, r=plate_r * 0.032,
                            segs=30, rsegs=5,
                            loc=(pxy[0], pxy[1], z0 + plate_r * 0.28),
                            mat=M_["paper"], col=col))

    # 蛋糕
    cz = z0 + plate_r * 0.28
    m_sponge = MAT.M.pbr("MAT_Cake_Sponge", base="#E5C286", rough=0.78)
    m_cream = MAT.M.pbr("MAT_Cream_White", base="#FFF8EE", rough=0.40, sheen=0.35)
    m_straw = MAT.M.pbr("MAT_Strawberry", base="#C42430", rough=0.32, coat=0.25)
    m_leafg = MAT.M.pbr("MAT_StrawLeaf", base="#4C7B3A", rough=0.60)
    objs.append(C.cyl("MD_CakeBase", r=cake_r * 0.95, h=cake_r * 0.50, segs=28,
                      loc=(pxy[0], pxy[1], cz + cake_r * 0.25),
                      mat=m_sponge, col=col, bevel=0.004, bsegs=2))
    objs.append(C.cyl("MD_CakeCream", r=cake_r * 0.99, h=cake_r * 0.11, segs=28,
                      loc=(pxy[0], pxy[1], cz + cake_r * 0.55), mat=m_cream, col=col))
    objs.append(C.cyl("MD_CakeTop", r=cake_r * 0.93, h=cake_r * 0.42, segs=28,
                      loc=(pxy[0], pxy[1], cz + cake_r * 0.81),
                      mat=m_sponge, col=col, bevel=0.004, bsegs=2))
    # 顶部奶油裱花 ×6 + 中央大花
    for i in range(6):
        a = C.TAU * i / 6
        objs.append(C.lathe(f"MD_Cream_{i}",
                            [(0.0, 0.0), (cake_r * 0.19, 0.0), (cake_r * 0.23, cake_r * 0.09),
                             (cake_r * 0.13, cake_r * 0.24), (0.0, cake_r * 0.28)],
                            segs=12,
                            loc=(pxy[0] + math.cos(a) * cake_r * 0.60,
                                 pxy[1] + math.sin(a) * cake_r * 0.60,
                                 cz + cake_r * 1.02),
                            mat=m_cream, col=col))
    objs.append(C.lathe("MD_CreamTop",
                        [(0.0, 0.0), (cake_r * 0.25, 0.0), (cake_r * 0.29, cake_r * 0.10),
                         (cake_r * 0.17, cake_r * 0.30), (0.0, cake_r * 0.36)],
                        segs=14, loc=(pxy[0], pxy[1], cz + cake_r * 1.02),
                        mat=m_cream, col=col))
    # 草莓 ×3
    for i in range(3):
        a = C.TAU * i / 3 + 0.35
        sx = pxy[0] + math.cos(a) * cake_r * 0.40
        sy = pxy[1] + math.sin(a) * cake_r * 0.40
        sz = cz + cake_r * 1.18
        objs.append(C.sphere(f"MD_Strawberry_{i}", r=cake_r * 0.155, segs=14, rings=10,
                             loc=(sx, sy, sz), scale=(1.0, 1.0, 1.22),
                             mat=m_straw, col=col))
        objs.append(C.lathe(f"MD_StrawTip_{i}",
                            [(0.0, 0.0), (cake_r * 0.095, 0.0), (cake_r * 0.042, cake_r * 0.11),
                             (0.0, cake_r * 0.17)],
                            segs=10, loc=(sx, sy, sz + cake_r * 0.09),
                            mat=m_straw, col=col))
        for k in range(3):
            aa = C.TAU * k / 3
            objs.append(C.box(f"MD_StrawLeaf_{i}{k}",
                              (cake_r * 0.10, cake_r * 0.028, cake_r * 0.010),
                              loc=(sx + math.cos(aa) * cake_r * 0.045,
                                   sy + math.sin(aa) * cake_r * 0.045,
                                   sz + cake_r * 0.17),
                              rot=(0, 0, aa), mat=m_leafg, col=col))

    # 咖啡杯碟（右后）
    cxy = (0.056, y0 + 0.020)
    objs.append(C.lathe("MD_Saucer",
                        [(0.0, 0.0), (saucer_r * 0.50, 0.0), (saucer_r * 0.86, saucer_r * 0.08),
                         (saucer_r, saucer_r * 0.25), (saucer_r * 0.92, saucer_r * 0.29),
                         (0.0, saucer_r * 0.29)],
                        segs=28, loc=(cxy[0], cxy[1], z0),
                        mat=M_["porcelain"], col=col))
    cz2 = z0 + saucer_r * 0.29
    cup_h = cup_r * 1.50
    objs.append(C.lathe("MD_Cup",
                        [(0.0, 0.0), (cup_r * 0.60, 0.0), (cup_r * 0.66, cup_h * 0.06),
                         (cup_r * 0.85, cup_h * 0.60), (cup_r, cup_h * 0.94),
                         (cup_r * 0.93, cup_h), (cup_r * 0.87, cup_h * 0.95),
                         (cup_r * 0.79, cup_h * 0.58), (cup_r * 0.58, cup_h * 0.10),
                         (0.0, cup_h * 0.10)],
                        segs=26, loc=(cxy[0], cxy[1], cz2),
                        mat=M_["porcelain"], col=col))
    objs.append(C.ring_tube("MD_CupHandle", R=cup_r * 0.60, r=cup_r * 0.15,
                            segs=18, rsegs=6,
                            loc=(cxy[0] + cup_r * 0.95, cxy[1], cz2 + cup_h * 0.50),
                            rot=(0, PI / 2, 0), mat=M_["porcelain"], col=col))
    objs.append(C.cyl("MD_Coffee", r=cup_r * 0.86, h=cup_r * 0.05, segs=26,
                      loc=(cxy[0], cxy[1], cz2 + cup_h * 0.82), mat=M_["coffee"], col=col))
    objs.append(C.ring_tube("MD_CupGold", R=cup_r * 0.98, r=cup_r * 0.03, segs=26, rsegs=5,
                            loc=(cxy[0], cxy[1], cz2 + cup_h * 0.95),
                            mat=M_["brass"], col=col))
    # 蒸汽面片 ×3
    m_steam = MAT.M.pbr("MAT_Steam", base="#FFFFFF", rough=0.9, alpha=0.20,
                        blend="BLEND", emit="#FFF6EA", emit_strength=0.45)
    for i in range(3):
        a = C.TAU * i / 3
        objs.append(C.plane(f"MD_Steam_{i}", sx=cup_r * 1.05, sy=P.STEAM_H * 0.8,
                            loc=(cxy[0] + math.cos(a) * cup_r * 0.22,
                                 cxy[1] + math.sin(a) * cup_r * 0.22,
                                 cz2 + cup_h + P.STEAM_H * 0.42),
                            rot=(0, 0, a), mat=m_steam, col=col))
    return objs


# ══════════════════════════════════════════════════════════════════════
def build(P_, C_, M_, assets, scale=None, pos=None, rot_z=None):
    scale = scale if scale else P.MAID_SCALE
    pos = pos if pos else P.MAID_POS
    rot_z = rot_z if rot_z is not None else P.MAID_ROT_Z

    C.wipe_collection(COL)
    C.ensure_collection(COL)
    colliders = []
    notes = []

    objs = _load_maid_objects()
    _purge_nonmesh(objs)
    meshes = [o for o in objs if _alive(o) and o.type == "MESH"]
    if not meshes:
        C.wipe_collection(COL)
        return {"objects": [], "collections": [COL], "colliders": [],
                "error": "maid source missing or empty"}
    t_orig = C.tri_count(meshes)
    C.log("maid: %d meshes, %d tris" % (len(meshes), t_orig))
    for ob in meshes:
        C.link_to(ob, COL)

    # 1) 减面
    stats = _decimate_group(meshes)
    C.log("maid after decimate: %d tris" % C.tri_count(meshes))

    # 1.5) 顶点色烘焙（必须在缩放前：用原模型坐标算腮红/发色渐变）
    _bake_vertex_colors(meshes)

    # 1.6) 压掉「实时 PBR 会洗白深色材质」的 sheen / clearcoat / anisotropy
    _sanitize_materials()

    # 2) 缩放（用空物体做父级，再 parent_clear + apply）→ 真实米制
    root = bpy.data.objects.new("MD_ScaleRoot", None)
    C.ensure_collection(COL).objects.link(root)
    for ob in meshes:
        ob.parent = root
        ob.matrix_parent_inverse = Matrix.Identity(4)
    root.scale = (scale, scale, scale)
    C.deselect_all()
    for ob in meshes:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    C.deselect_all()
    for ob in meshes:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    C.deselect_all()
    bpy.data.objects.remove(root, do_unlink=True)
    mn, mx = C.world_aabb(meshes)
    dz = -mn[2]
    for ob in meshes:
        ob.location.z += dz
    C.log("maid scaled x%.3f, foot dz=%.4f, height=%.3f m"
          % (scale, dz, mx[2] - mn[2]))

    # 3) 手臂骨骼摆姿势
    arm_ob = _make_armature(scale)
    arm_meshes = _arm_objects(meshes)
    _bind_and_pose(arm_ob, arm_meshes, scale)
    notes.append("arms: 2-bone armature, baked")

    # 4) 托盘与食物
    tray_objs = _tray(M_, COL)
    food_objs = _cake_and_coffee(M_, COL)
    all_objs = meshes + tray_objs + food_objs

    # 5) 整体旋转 + 平移（一次性烘焙进顶点，之后物体的变换恒为单位阵）
    #    实测教训（trace_food.py 逐步验证）：
    #      `matrix_world = xform @ matrix_world` 对带 rotation_euler 的基元
    #      （ring_tube / plane，如 MD_CupGold、MD_Steam_*）会与 location 失同步，
    #      任何后续 location 写入都会把它们打回 z≈0。
    #    解法：算出每个物体**应有的世界矩阵**，直接烧进 mesh 顶点，
    #          然后把 location/rotation/scale 全部归零。之后不可能再丢位置。
    rot = Matrix.Rotation(rot_z * D2R, 4, "Z")
    xform = Matrix.Translation(Vector((pos[0], pos[1], 0.0))) @ rot
    bpy.context.view_layer.update()
    worlds = {ob.name: (xform @ ob.matrix_world) for ob in all_objs}
    for ob in all_objs:
        mw = worlds[ob.name]
        ob.matrix_basis = Matrix.Identity(4)
        ob.matrix_world = Matrix.Identity(4)
        ob.data.transform(mw)
    bpy.context.view_layer.update()

    # 落地复核（≤2mm 微调，同样只烧顶点，不动 location）
    mn2, mx2 = C.world_aabb(meshes)
    if abs(mn2[2]) > 0.002:
        C.log("WARN maid floor drift %.4f m, correcting" % mn2[2])
        dz = -mn2[2]
        for ob in all_objs:
            ob.data.transform(Matrix.Translation(Vector((0.0, 0.0, dz))))
        bpy.context.view_layer.update()
        mn2, mx2 = C.world_aabb(meshes)

    # 硬校验：托盘与食物必须在走道高度（0.3–1.2m），绝不允许沉到地面
    bpy.context.view_layer.update()
    bad = []
    for ob in tray_objs + food_objs:
        wmn, wmx = C.world_aabb(ob)
        if wmx[2] < 0.30 or wmn[2] > 1.20:
            bad.append("%s z=%.3f-%.3f" % (ob.name, wmn[2], wmx[2]))
    if bad:
        C.log("ERROR maid props misplaced: " + "; ".join(bad))
        raise RuntimeError("maid props misplaced: " + "; ".join(bad))

    tmn, tmx = C.world_aabb(tray_objs)
    colliders.append({"name": "MD_Body", "aabb": [mn2, mx2], "kind": "soft"})
    colliders.append({"name": "MD_Tray", "aabb": [tmn, tmx], "kind": "solid"})

    tris = C.tri_count(all_objs)
    C.log("%s: %d objects, %d tris (budget %d)" % (MODULE, len(all_objs), tris, TRI_BUDGET))
    return {"objects": all_objs, "collections": [COL], "colliders": colliders,
            "anchors": {
                "maid_pos": [pos[0], pos[1], 0.0],
                "maid_rot_z_deg": rot_z,
                "maid_height": round(mx2[2] - mn2[2], 3),
                "tray_top_z": P.TRAY_Z,
                "steam_node": "MD_Steam_0",
                "body_aabb": [mn2, mx2],
            },
            "notes": "; ".join(notes) + " tris %d->%d" % (t_orig, tris),
            "tris": tris, "orig_tris": t_orig, "decimate_stats": stats}


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    M = MAT.palette()
    res = build(P, C, M, {})
    objs = res["objects"]
    C.log("built", len(objs), res["tris"], res.get("anchors", {}).get("body_aabb"))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scene", "_maid_only.blend"))
    px, py = P.MAID_POS
    tgt = (px, py, 0.82)
    C.selfcheck(MODULE, objs, res=(900, 900), samples=32,
                views=[
                    {"name": "front", "from": (px + 0.75, py - 2.10, 1.30), "look": tgt, "lens": 62},
                    {"name": "persp", "from": (px + 1.85, py - 1.70, 1.60), "look": tgt, "lens": 52},
                    {"name": "close", "from": (px + 0.60, py - 1.05, 1.10), "look": (px, py - 0.15, 0.76), "lens": 66},
                    {"name": "top", "from": (px + 0.30, py - 0.95, 2.45), "look": (px, py - 0.15, 0.80), "lens": 50},
                ])
