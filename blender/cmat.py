"""
cmat.py — 女仆咖啡馆项目 · PBR 材质工厂（贴图优先，缺失自动降级为程序化）

对外接口
--------
    M = cmat.M
    m = M.get("MAT_Wood_Oak")                # 取已建材质（不存在则按配方建）
    m = M.pbr("MAT_Custom", diff=..., nor=..., arm=..., uv_scale=2.0, ...)
    M.ensure_palette()                        # 一次性建全调色板

设计要点
--------
1. 贴图全部走 `assets/tex/*.jpg`（PolyHaven CC0），按 cprop.TEXTURES 索引；
   缺失 → 打印 WARN 并退回程序化节点（绝不崩溃）。
2. UV：ccore.uv_world 已把 UV 化成「米/uv_scale」，这里 Mapping 的 Scale 表示
   「每米重复次数」，所以 uv_scale=2 → 贴图 1 张覆盖 2m。
3. glTF 兼容：只用 Principled BSDF + Image Texture + Normal Map + Separate Color，
   导出器能正确烘成 glTF PBR（含 ORM）。
"""
import os
import bpy
import ccore as C
import cprop as P


# ══════════════════════════════════════════════════════════════════════
# Principled 输入名兼容层（Blender 4.x / 5.x 改名过几次）
# ══════════════════════════════════════════════════════════════════════
_ALIAS = {
    "base_color": ("Base Color", "Base Color "),
    "metallic": ("Metallic",),
    "roughness": ("Roughness",),
    "ior": ("IOR",),
    "alpha": ("Alpha",),
    "normal": ("Normal",),
    "emission_color": ("Emission Color", "Emission"),
    "emission_strength": ("Emission Strength",),
    "specular": ("Specular IOR Level", "Specular"),
    "coat": ("Coat Weight", "Clearcoat"),
    "coat_rough": ("Coat Roughness", "Clearcoat Roughness"),
    "sheen": ("Sheen Weight", "Sheen"),
    "sheen_rough": ("Sheen Roughness",),
    "sheen_tint": ("Sheen Tint",),
    "sss": ("Subsurface Weight", "Subsurface"),
    "sss_radius": ("Subsurface Radius",),
    "transmission": ("Transmission Weight", "Transmission"),
    "aniso": ("Anisotropic",),
    "aniso_rot": ("Anisotropic Rotation",),
}


def set_in(node, key, value):
    """按别名设置 Principled 输入；不存在则静默跳过。"""
    for name in _ALIAS.get(key, (key,)):
        inp = node.inputs.get(name)
        if inp is not None:
            try:
                if isinstance(value, tuple) and len(value) == 3:
                    inp.default_value = (*value, 1.0)
                else:
                    inp.default_value = value
                return True
            except Exception:
                return False
    return False


def sock(node, key):
    for name in _ALIAS.get(key, (key,)):
        inp = node.inputs.get(name)
        if inp is not None:
            return inp
    return None


def _bsdf_of(mat):
    if not mat.use_nodes:
        mat.use_nodes = True
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    nt = mat.node_tree
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if out is None:
        out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return b


# ══════════════════════════════════════════════════════════════════════
# 贴图节点
# ══════════════════════════════════════════════════════════════════════
def load_image(path, noncolor=False):
    """载入贴图（带缓存）；失败返回 None。"""
    if not path or not os.path.exists(path):
        return None
    name = os.path.basename(path)
    img = bpy.data.images.get(name)
    if img is None:
        try:
            img = bpy.data.images.load(path, check_existing=True)
        except Exception as e:
            C.log("image load failed", path, e)
            return None
    img.name = name
    try:
        img.colorspace_settings.name = "Non-Color" if noncolor else "sRGB"
    except Exception:
        pass
    # 打包：保证 GLB 内嵌 / .blend 不丢图
    try:
        if not img.packed_file:
            img.pack()
    except Exception:
        pass
    return img


def _tex_node(nt, img, uv_scale=1.0, loc=(0, 0), label=""):
    """UV → Mapping(scale) → Image Texture。返回色输出 socket。"""
    img_node = nt.nodes.new("ShaderNodeTexImage")
    img_node.image = img
    img_node.label = label or img.name
    img_node.location = loc
    if uv_scale and abs(uv_scale - 1.0) > 1e-6:
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.location = (loc[0] - 220, loc[1])
        mapping.inputs["Scale"].default_value = (uv_scale, uv_scale, 1.0)
        uvn = nt.nodes.new("ShaderNodeUVMap")
        uvn.location = (loc[0] - 420, loc[1])
        nt.links.new(uvn.outputs["UV"], mapping.inputs["Vector"])
        # 用 UV 直接连即可（Mapping 的 Scale 作用于 UV）
        nt.links.new(uvn.outputs["UV"], img_node.inputs["Vector"]) if False else None
        nt.links.new(mapping.outputs["Vector"], img_node.inputs["Vector"])
    return img_node.outputs["Color"]


def _normal_chain(nt, img, strength=1.0, loc=(0, 0)):
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.location = loc
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.location = (loc[0] + 200, loc[1])
    nm.inputs["Strength"].default_value = strength
    nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
    return nm.outputs["Normal"]


def _arm_chain(nt, img, loc=(0, 0)):
    """ORM：R=AO, G=Roughness, B=Metallic → (rough_socket, metal_socket)"""
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.location = loc
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    sep.location = (loc[0] + 200, loc[1])
    nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
    return sep.outputs[1], sep.outputs[2]   # Green=Rough, Blue=Metal


# ══════════════════════════════════════════════════════════════════════
# 程序化降级（缺贴图时）
# ══════════════════════════════════════════════════════════════════════
def _noise_color(nt, c1, c2, scale=8.0, detail=6.0, roughness=0.55, loc=(-600, 0)):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (loc[0] - 220, loc[1])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = loc
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    noise.inputs["Roughness"].default_value = roughness
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (loc[0] + 220, loc[1])
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = C.hexc(c1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = C.hexc(c2)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    return ramp.outputs["Color"]


def _wood_grain(nt, c1, c2, scale=14.0, loc=(-600, 0)):
    """竖纹木：沿 Z 拉伸的噪声 + 波纹。"""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (6.0, 6.0, 0.55)
    mp.location = (loc[0] - 220, loc[1])
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.location = loc
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = scale
    wave.inputs["Distortion"].default_value = 6.0
    wave.inputs["Detail"].default_value = 3.0
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (loc[0] + 200, loc[1])
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = C.hexc(c1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = C.hexc(c2)
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    return ramp.outputs["Color"]


def _fabric_bump(nt, bsdf, scale=120.0, strength=0.25, loc=(-600, -400)):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 2.0
    noise.location = loc
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (loc[0] + 220, loc[1])
    bump.inputs["Strength"].default_value = strength
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    n = sock(bsdf, "normal")
    if n:
        nt.links.new(bump.outputs["Normal"], n)
    return bump


# ══════════════════════════════════════════════════════════════════════
# 材质工厂
# ══════════════════════════════════════════════════════════════════════
class _Factory:
    def __init__(self):
        self.cache = {}

    # ---------- 底层 ----------
    def new(self, name):
        m = bpy.data.materials.get(name)
        if m is None:
            m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = _bsdf_of(m)
        m["project"] = "maid_cafe"
        self.cache[name] = m
        return m, m.node_tree, b

    def get(self, name):
        if name in self.cache:
            return self.cache[name]
        m = bpy.data.materials.get(name)
        if m is not None and m.use_nodes:
            self.cache[name] = m
            return m
        fn = getattr(self, "_build_" + name.replace("MAT_", "").lower(), None)
        if fn:
            return fn()
        C.log("WARN unknown material", name)
        return self.pbr(name, base="#CCCCCC")

    # ---------- 通用 PBR ----------
    def pbr(self, name, base="#CCCCCC", diff=None, nor=None, arm=None,
            rough=None, metal=0.0, alpha=1.0, emit=None, emit_strength=0.0,
            uv_scale=1.0, nor_strength=1.0, specular=None, sheen=None,
            sheen_rough=None, sheen_tint=None,
            coat=None, coat_rough=None, transmission=None, ior=None,
            sss=None, sss_radius=None, aniso=None, blend=None, procedural=None,
            **extra):
        """通用 PBR。diff/nor/arm 可为路径或已载入 image。"""
        m, nt, b = self.new(name)
        # 颜色
        img = diff if isinstance(diff, bpy.types.Image) else load_image(diff) if diff else None
        if img:
            col = _tex_node(nt, img, uv_scale, loc=(-700, 250), label="diff")
            nt.links.new(col, sock(b, "base_color"))
        elif procedural == "wood":
            col = _wood_grain(nt, _shade(base, 0.82), _shade(base, 1.10), uv_scale)
            nt.links.new(col, sock(b, "base_color"))
        elif procedural == "noise":
            col = _noise_color(nt, _shade(base, 0.85), _shade(base, 1.12), uv_scale * 6)
            nt.links.new(col, sock(b, "base_color"))
        else:
            set_in(b, "base_color", C.hexc(base))
        # 法线
        nimg = nor if isinstance(nor, bpy.types.Image) else load_image(nor, noncolor=True) if nor else None
        if nimg:
            nout = _normal_chain(nt, nimg, nor_strength, loc=(-700, 0))
            nt.links.new(nout, sock(b, "normal"))
        # ORM
        aimg = arm if isinstance(arm, bpy.types.Image) else load_image(arm, noncolor=True) if arm else None
        if aimg:
            r_sock, m_sock = _arm_chain(nt, aimg, loc=(-700, -250))
            nt.links.new(r_sock, sock(b, "roughness"))
            nt.links.new(m_sock, sock(b, "metallic"))
            set_in(b, "metal_srgb_note", 0) if False else None
        else:
            if rough is not None:
                set_in(b, "roughness", rough)
            if metal:
                set_in(b, "metallic", metal)
        if metal and aimg:
            pass
        elif metal:
            set_in(b, "metallic", metal)
        if specular is not None:
            set_in(b, "specular", specular)
        if sheen is not None:
            set_in(b, "sheen", sheen)
        if sheen_rough is not None:
            set_in(b, "sheen_rough", sheen_rough)
        if sheen_tint is not None:
            set_in(b, "sheen_tint", sheen_tint if isinstance(sheen_tint, tuple) else C.hexc(sheen_tint))
        if coat is not None:
            set_in(b, "coat", coat)
        if coat_rough is not None:
            set_in(b, "coat_rough", coat_rough)
        if transmission is not None:
            set_in(b, "transmission", transmission)
        if ior is not None:
            set_in(b, "ior", ior)
        if sss is not None:
            set_in(b, "sss", sss)
        if sss_radius is not None:
            set_in(b, "sss_radius", sss_radius)
        if aniso is not None:
            set_in(b, "aniso", aniso)
        if alpha < 1.0:
            set_in(b, "alpha", alpha)
        if emit:
            set_in(b, "emission_color", C.hexc(emit) if isinstance(emit, str) else emit)
            set_in(b, "emission_strength", emit_strength or 1.0)
        if blend:
            try:
                m.blend_method = blend
            except Exception:
                pass
            try:
                m.surface_render_method = "BLENDED" if blend == "BLEND" else "DITHERED"
            except Exception:
                pass
        m.diffuse_color = C.hexc(base) if isinstance(base, str) else (*base[:3], 1.0)
        # 记录贴图用量，导出前可核查
        m["uv_scale"] = float(uv_scale)
        return m

    # ---------- 调色板 ----------
    def ensure_palette(self):
        """建全场景共用材质（幂等）。返回 dict。"""
        out = {}
        # 地板
        out["floor"] = self.pbr("MAT_Wood_Herringbone", base=P.C_FLOOR_HERRING,
                                diff=os.path.join(P.TEX, "tinted", "floor_warm_diff.jpg"),
                                nor=P.tex_path("floor_herringbone", "nor", "2k"),
                                arm=P.tex_path("floor_herringbone", "arm", "2k"),
                                rough=0.58, uv_scale=2.4, procedural="wood",
                                specular=0.30, nor_strength=0.7)
        # 木
        out["wood_oak"] = self.pbr("MAT_Wood_Oak", base="#B98757",
                                   diff=os.path.join(P.TEX, "tinted", "wood_light_diff.jpg"),
                                   nor=P.tex_path("wood_table", "nor"),
                                   rough=0.54, uv_scale=1.5, procedural="wood")
        out["wood_counter"] = self.pbr("MAT_Wood_Counter", base=P.C_WOOD_WALNUT,
                                       diff=os.path.join(P.TEX, "tinted", "wood_walnut_diff.jpg"),
                                       nor=P.tex_path("wood_counter", "nor"),
                                       arm=P.tex_path("wood_counter", "arm"),
                                       rough=0.46, uv_scale=2.0, procedural="wood")
        out["wood_dark"] = self.pbr("MAT_Wood_Dark", base="#6B4530",
                                    diff=P.tex_path("wood_counter", "diff"),
                                    nor=P.tex_path("wood_counter", "nor"),
                                    rough=0.56, uv_scale=1.6, procedural="wood")
        out["wood_table"] = self.pbr("MAT_Wood_Table", base=P.C_WOOD_OAK,
                                     diff=P.tex_path("wood_table", "diff"),
                                     nor=P.tex_path("wood_table", "nor"),
                                     rough=0.40, uv_scale=1.2, procedural="wood")
        out["wood_shelf"] = self.pbr("MAT_Wood_Shelf", base="#A97C52",
                                     diff=P.tex_path("wood_shelf", "diff"),
                                     nor=P.tex_path("wood_shelf", "nor"),
                                     rough=0.62, uv_scale=1.4, procedural="wood")
        # 石
        out["marble"] = self.pbr("MAT_Marble_Top", base=P.C_MARBLE,
                                 diff=P.tex_path("marble_top", "diff"),
                                 nor=P.tex_path("marble_top", "nor"),
                                 rough=0.16, coat=0.35, coat_rough=0.06,
                                 uv_scale=1.2, procedural="noise")
        out["ceramic_tile"] = self.pbr("MAT_Ceramic_Tile", base="#E8E2D8",
                                       diff=P.tex_path("ceramic_tile", "diff"),
                                       nor=P.tex_path("ceramic_tile", "nor"),
                                       rough=0.22, uv_scale=1.0)
        # 墙（奶油色平滑乳胶漆 + 局部米色）
        out["wall"] = self.pbr("MAT_Paint_Cream", base="#F0E5D2",
                               diff=os.path.join(P.TEX, "tinted", "wall_cream_diff.jpg"),
                               nor=P.tex_path("wall_cream", "nor"),
                               rough=0.88, uv_scale=4.0, procedural="noise")
        out["wall_accent"] = self.pbr("MAT_Paint_Accent", base="#E8DAC2",
                                      diff=P.tex_path("wall_plaster", "diff"),
                                      rough=0.85, uv_scale=3.0, procedural="noise")
        # 布
        out["lace"] = self.pbr("MAT_Fabric_Lace", base=P.C_LACE,
                               diff=P.tex_gen_path("fabric_lace_white.png"),
                               rough=0.42, sheen=0.72, sheen_rough=0.30,
                               uv_scale=0.75)
        out["linen"] = self.pbr("MAT_Fabric_Linen", base="#F5EFE6",
                                diff=P.tex_path("fabric_linen", "diff"),
                                nor=P.tex_path("fabric_linen", "nor"),
                                rough=0.72, sheen=0.45, uv_scale=1.0)
        out["gingham"] = self.pbr("MAT_Fabric_Gingham", base="#F3D0D9",
                                  diff=P.tex_gen_path("fabric_gingham_pink.png"),
                                  rough=0.70, sheen=0.45, uv_scale=0.55)
        out["cotton"] = self.pbr("MAT_Fabric_Cotton", base="#EFE6DA",
                                 diff=P.tex_path("fabric_cotton", "diff"),
                                 nor=P.tex_path("fabric_cotton", "nor"),
                                 rough=0.78, uv_scale=1.2)
        out["velvet"] = self.pbr("MAT_Fabric_Velvet", base=P.C_CUSHION,
                                 diff=P.tex_gen_path("fabric_velvet_warm.png"),
                                 rough=0.62, sheen=0.60, sheen_rough=0.40,
                                 uv_scale=0.9)
        # 蛋糕（展示柜里的外部模型统一换成简化材质：它们的遮罩贴图在 WEBP 导出时会失败，
        # 导致 GLB 里出现没有 source 的空 texture 槽，整包加载失败）
        out["cake_carrot"] = self.pbr("MAT_Cake_Carrot", base="#C8874A", rough=0.62)
        out["cake_strawberry"] = self.pbr("MAT_Cake_Strawberry", base="#F2E6D2", rough=0.55)
        # 奶白漆木（椅子）——偏暖的木器漆色，不刺眼的纯白
        out["chair_paint"] = self.pbr("MAT_Chair_Paint", base="#D9C3A2",
                                      rough=0.46, specular=0.42, coat=0.10,
                                      coat_rough=0.38)
        out["table_wood"] = self.pbr("MAT_Table_Wood", base="#A8764C",
                                     diff=P.tex_path("wood_table", "diff"),
                                     nor=P.tex_path("wood_table", "nor"),
                                     rough=0.42, uv_scale=0.9, procedural="wood")
        out["leather"] = self.pbr("MAT_Leather", base="#5A3222",
                                  diff=P.tex_path("leather", "diff"),
                                  nor=P.tex_path("leather", "nor"),
                                  rough=0.44, uv_scale=1.0)
        # 金属
        out["brass"] = self.pbr("MAT_Metal_Brass", base=P.C_BRASS, metal=1.0,
                                rough=0.22)
        out["steel"] = self.pbr("MAT_Metal_Steel", base="#C2C6CA", metal=1.0, rough=0.30)
        out["steel_brushed"] = self.pbr("MAT_Metal_Brushed", base="#C8CCD0", metal=1.0,
                                        rough=0.22, uv_scale=1.0, aniso=0.6)
        out["chrome"] = self.pbr("MAT_Metal_Chrome", base="#DCDEE0", metal=1.0, rough=0.06)
        out["black_metal"] = self.pbr("MAT_Metal_Black", base="#22201E",
                                      metal=0.85, rough=0.34)
        out["grille"] = self.pbr("MAT_Metal_Grille", base="#3A3A3A", metal=0.9,
                                 rough=0.5, diff=P.tex_path("metal_grate", "diff"),
                                 uv_scale=0.5)
        # 玻璃：用 alpha 混合（EEVEE 与 three.js 都稳定可见透明；transmission 在
        # 无光线追踪的实时管线下会渲染成不透明灰块，故这里不用 transmission）
        out["glass"] = self.pbr("MAT_Glass_Clear", base="#E8F4FA", rough=0.04,
                                alpha=0.10, blend="BLEND", specular=0.9,
                                coat=0.2, coat_rough=0.02, ior=1.45)
        out["glass_window"] = self.pbr("MAT_Glass_Window", base="#EAF4FA", rough=0.02,
                                       alpha=0.08, blend="BLEND", specular=1.0,
                                       coat=0.25, coat_rough=0.01, ior=1.45)
        out["glass_frost"] = self.pbr("MAT_Glass_Frost", base="#DCE8EE", rough=0.32,
                                      transmission=0.55, alpha=0.82, blend="BLEND")
        out["glass_case"] = self.pbr("MAT_Glass_Case", base="#F0F8FF", rough=0.02,
                                     alpha=0.07, blend="BLEND", specular=1.0,
                                     coat=0.15, coat_rough=0.01)
        out["mirror"] = self.pbr("MAT_Mirror", base="#CFD6DA", metal=1.0, rough=0.03)
        # 瓷/陶
        out["porcelain"] = self.pbr("MAT_Porcelain", base="#FBF8F3", rough=0.10,
                                    coat=0.6, coat_rough=0.04, specular=0.6)
        out["ceramic_mat"] = self.pbr("MAT_Ceramic_Glaze", base="#E7DFD2", rough=0.16,
                                      coat=0.45, coat_rough=0.10)
        # 塑料
        out["plastic"] = self.pbr("MAT_Plastic", base="#2B2B2E", rough=0.38)
        out["plastic_white"] = self.pbr("MAT_Plastic_White", base="#F2F2F0", rough=0.32)
        # 纸/菜单
        out["paper"] = self.pbr("MAT_Paper", base="#FBF6EC", rough=0.78)
        out["paper_menu"] = self.pbr("MAT_Paper_Menu", base="#FBF6EC", rough=0.80)
        out["chalk"] = self.pbr("MAT_Chalk_Board", base="#22282A", rough=0.92)
        # 液
        out["coffee"] = self.pbr("MAT_Liquid_Coffee", base=P.C_COFFEE, rough=0.08,
                                 coat=0.8, coat_rough=0.02)
        out["milk"] = self.pbr("MAT_Liquid_Milk", base="#F3EFE7", rough=0.10,
                               coat=0.7, coat_rough=0.03)
        out["syrup"] = self.pbr("MAT_Liquid_Syrup", base="#8C4A16", rough=0.06,
                                transmission=0.55, ior=1.4, coat=0.6)
        # 植物
        out["leaf"] = self.pbr("MAT_Plant_Leaf", base=P.C_SAGE, rough=0.62, sss=0.15)
        out["leaf_dark"] = self.pbr("MAT_Plant_Leaf_Dark", base="#4E6B45", rough=0.66)
        out["stem"] = self.pbr("MAT_Plant_Stem", base="#6C7A4E", rough=0.7)
        out["soil"] = self.pbr("MAT_Plant_Soil", base="#3B2A1E", rough=0.95)
        out["terracotta"] = self.pbr("MAT_Terracotta", base="#B5654A", rough=0.72)
        # 布/帘
        out["curtain"] = self.pbr("MAT_Fabric_Curtain", base="#EFE7DA", rough=0.85,
                                  sheen=0.4, uv_scale=1.4)
        out["noren"] = self.pbr("MAT_Fabric_Noren", base="#2E4A62", rough=0.86,
                                sheen=0.3, uv_scale=1.0)
        # 发光
        out["shade"] = self.pbr("MAT_Emissive_Shade", base="#F3E2C7",
                                emit=P.C_LAMP_WARM, emit_strength=0.9, rough=0.72)
        out["bulb"] = self.pbr("MAT_Emissive_Bulb", base="#FFF3DC",
                               emit="#FFE9C4", emit_strength=8.0, rough=0.3)
        out["led"] = self.pbr("MAT_Emissive_LED", base="#FFF4E0",
                              emit="#FFEFD0", emit_strength=2.2, rough=0.5)
        # 室外
        out["asphalt"] = self.pbr("MAT_Out_Asphalt", base="#3E3E42",
                                  diff=P.tex_path("out_asphalt", "diff"),
                                  nor=P.tex_path("out_asphalt", "nor"),
                                  rough=0.78, uv_scale=3.0, procedural="noise")
        out["pavers"] = self.pbr("MAT_Out_Pavers", base="#8C8A85",
                                 diff=P.tex_path("out_pavers", "diff"),
                                 nor=P.tex_path("out_pavers", "nor"),
                                 rough=0.72, uv_scale=2.0)
        out["outer_wall"] = self.pbr("MAT_Out_Concrete", base="#9A9791",
                                     diff=P.tex_path("out_concrete", "diff"),
                                     nor=P.tex_path("out_concrete", "nor"),
                                     rough=0.85, uv_scale=3.5)
        out["brick"] = self.pbr("MAT_Out_Brick", base="#A8785F",
                                diff=P.tex_path("out_brick", "diff"),
                                nor=P.tex_path("out_brick", "nor"),
                                rough=0.88, uv_scale=3.0)
        out["plaster_out"] = self.pbr("MAT_Out_Plaster", base="#C9C2B6",
                                      diff=P.tex_path("out_plaster", "diff"),
                                      rough=0.86, uv_scale=3.5)
        # 女仆补充
        out["skin_soft"] = self.pbr("MAT_Skin_Soft", base="#F6DCC4", rough=0.42,
                                    sss=0.22, sss_radius=(1.0, 0.4, 0.26))
        out["steam"] = self.pbr("MAT_Steam", base="#FFFFFF", rough=0.9, alpha=0.28,
                                blend="BLEND", emit="#FFF6EA", emit_strength=0.6)
        out["frost"] = self.pbr("MAT_Frost", base="#EAF4FA", rough=0.35, alpha=0.55,
                                blend="BLEND", transmission=0.6)
        return out


def _shade(hexcolor, mult):
    c = C.hexc(hexcolor)
    return "#%02X%02X%02X" % tuple(int(min(255, max(0, c[i] ** (1 / 2.4) * 255 * mult))) for i in range(3))


M = _Factory()


# ══════════════════════════════════════════════════════════════════════
# 便捷包装
# ══════════════════════════════════════════════════════════════════════
def get(name):
    return M.get(name)


def palette():
    return M.ensure_palette()


def apply(ob, mat, slot=0):
    return C.mat_assign(ob, mat, slot)


def textured(name, key, map_="diff", uv_scale=1.0, **kw):
    """按 cprop.TEXTURES 索引快速建材质。"""
    return M.pbr(name, diff=P.tex_path(key, map_), uv_scale=uv_scale, **kw)
