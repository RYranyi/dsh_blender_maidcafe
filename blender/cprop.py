"""
cprop.py — 女仆咖啡馆项目 · 比例/尺寸/配色/贴图索引 的**唯一数值源**

任何模块不得硬编码尺寸；一律 `import cprop as P` 后引用。
所有值单位为米，坐标系见 CONTRACT.md §1（+Z 上，街道侧 −Y，地面 z=0）。
"""
import os

# ══════════════════════════════════════════════════════════════════════
# 0. 路径
# ══════════════════════════════════════════════════════════════════════
# 项目根目录：从本文件位置推导（blender/ 的上一级），不再硬编码盘符
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
TEX = os.path.join(ASSETS, "tex")
TEX_GEN = os.path.join(TEX, "generated")
MODELS = os.path.join(ASSETS, "models")
HDRI = os.path.join(ASSETS, "hdri")
AUDIO = os.path.join(ASSETS, "audio")
SCENE_DIR = os.path.join(ROOT, "scene")
RENDERS = os.path.join(ROOT, "renders")
BLENDER_DIR = os.path.join(ROOT, "blender")

# ══════════════════════════════════════════════════════════════════════
# 1. 房间
# ══════════════════════════════════════════════════════════════════════
ROOM_X = (-4.0, 4.0)          # 室内净宽 8.0
ROOM_Y = (-3.0, 3.0)          # 室内净深 6.0
CEIL_Z = 3.0                  # 层高
WALL_T = 0.16                 # 墙厚（向外）
FLOOR_T = 0.10                # 地面板厚（向下）

# 前墙（街道侧 y = -3.0）：大玻璃窗 + 入户门
WIN_X = (-3.70, 0.35)         # 窗洞口 x 范围
WIN_Z = (0.72, 2.58)          # 窗洞口 z 范围
WIN_MULLIONS = 3              # 竖向分格条数（4 块玻璃）
DOOR_X = (1.15, 2.45)         # 门洞 x 范围
DOOR_Z = (0.0, 2.20)          # 门洞 z 范围
DOOR_LEAF = 0.06              # 门框料宽
WAINSCOT_Z = 0.95             # 墙裙上沿
WAINSCOT_T = 0.018            # 墙裙凸出墙面厚度
CHAIR_RAIL_Z = 0.82           # 墙裙压边条中心高

# 天花（吊顶下沿 / 灯带）
CEIL_RECESS_Z = 2.86          # 吊顶下沿（局部吊顶）

# ══════════════════════════════════════════════════════════════════════
# 2. 吧台区（L 形）
# ══════════════════════════════════════════════════════════════════════
BAR_TOP_Z = 0.95              # 台面上表面
BAR_SLAB_T = 0.05             # 台面板厚
BAR_FRONT_Z = (0.0, 0.90)     # 前立面高度范围（下部 0–0.12 为踢脚凹槽）
BAR_MAIN = dict(x=(-0.20, 3.70), y=(1.15, 1.87))
BAR_RETURN = dict(x=(2.98, 3.70), y=(1.15, 2.92))   # 收到 2.92，避免台面出檐压到后墙腰线
BAR_OVERHANG = 0.04           # 台面比柜体每侧出檐

BAR_BACK = dict(x=(-1.60, 2.70), y=(2.55, 2.95))   # 后操作台柜体
BAR_BACK_TOP_Z = 0.90
BACKSPLASH = dict(h=0.55, t=0.03)                 # 后墙防溅板

BAR_SHELF_Z = (1.45, 1.95, 2.45)                  # 后吧层架三层
# 货架贴墙段：后端 y=2.99（贴后墙内表面 3.00），前端 2.99-0.20=2.79
# 原来 y=(2.78,2.98) 会让货架立柱与 BA_Backsplash(y=[2.96,2.99]) 重叠 20mm 穿透 10mm。
BAR_SHELF = dict(x=(-1.60, 2.70), y=(2.79, 2.96))
CUP_RAIL = dict(x=(0.00, 2.60), y=2.72, z=1.32)   # 倒挂杯架（横杆）
CUP_RAIL_HANG = 0.72                              # 杯架下垂到台面上方高度差（视觉）

# 设备占位（确保不相互穿插）
ESPRESSO = dict(x=(2.15, 2.95), y=(1.30, 1.75), z=(BAR_TOP_Z, 1.50))
GRINDER = dict(x=(1.72, 2.06), y=(1.34, 1.66), z=(BAR_TOP_Z, 1.46))
POUR_OVER = dict(x=(1.10, 1.66), y=(1.38, 1.72), z=(BAR_TOP_Z, 1.28))
SYRUP = dict(x=(3.02, 3.58), y=(1.30, 1.72))
REGISTER = dict(x=(-0.08, 0.42), y=(1.42, 1.82), z=(BAR_TOP_Z, 1.24))
SINK = dict(x=(-0.90, -0.30), y=(2.62, 2.90))     # 后操作台水槽（在 BAR_BACK 台面上）
SINK_RECESS = 0.18                                # 水槽下沉深度

# 甜品展示柜：放在吧台主段西端「前方」（不嵌进吧台），面朝 −Y 顾客方向。
# 依据：BAR_MAIN y 从 1.15 起 → 柜体 y 上界收在 1.14，与吧台留 10mm 缝；
# x 保持契约区间 (-1.60,-0.05)，这样既不压吧台、也不压 TB_04 圆桌。
DISPLAY = dict(x=(-1.60, -0.28), y=(0.55, 1.08), z=(0.0, 1.36))
DISPLAY_GLASS_Z = (1.36, 1.62)                    # 柜内到顶罩
DISPLAY_SHELVES = (0.42, 0.78, 1.12)              # 层板高度（蛋糕位面）

# 吧台凳
BAR_STOOL = dict(x=(0.55, 1.70), y=0.82, seat_z=0.74, r=0.19)
BAR_FOOT_RAIL_Z = 0.95                            # 吧台前脚下横杆（前立面外侧）

# ══════════════════════════════════════════════════════════════════════
# 3. 客座区：5 组桌椅
# ══════════════════════════════════════════════════════════════════════
TABLE_R = 0.38                # 圆桌半径
TABLE_H = 0.74                # 桌面上表面
TABLE_OVERHANG = 0.03
TABLE_PEDESTAL_R = 0.10       # 中柱半径
TABLE_FOOT_R = 0.28           # 底盘半径
CHAIR_W = 0.44
CHAIR_D = 0.46
CHAIR_SEAT_H = 0.45
CHAIR_BACK_H = 0.92
CHAIR_CUSHION_T = 0.05
TABLE_RING_R = 0.60           # 椅子中心绕桌心距离
TABLE_RING_ANG = (0.0, 118.0, 242.0)  # 3 椅，朝向桌心；靠窗那组 2 椅

# 老兄反馈：「旁边两张椅子和桌子的组合挡住路显得太挤要去掉」
# 实测 TB_03 桌面离左墙只有 0.37m，3 把椅子环布后
# CH_03_1 离墙 117mm、CH_03_3 离墙 93mm（几乎贴墙），整组把左侧走道挤到 <0.6m。
# → 删掉 TB_03 整组（含 3 椅），保留 4 桌布局，中央走道从 0.6m 拓到 1.6m+。
# 老兄要求：只留 TB_01 / TB_02 / TB_05；TB_03 与 TB_04 都已去掉。
# TB_05 离大门再远一点（门 x[1.15,2.45] y=-3）：从 (2.95,-1.70) → (3.05,-0.95)
# 椅子改为 2 把对称：一把朝门（-Y 侧）、一把朝吧台（+Y 侧），都贴近右墙。
TABLES = [   # (x, y, n_chairs, has_window)
    dict(name="TB_01", x=-2.95, y=-2.05, chairs=2, window=True),
    dict(name="TB_02", x=-1.05, y=-2.10, chairs=3, window=True),
    # TB_05 老兄要求「一把朝门、一把朝吧台、对称」→ window=False 让它走 (0°,180°) 分支：
    # θ=0 → (3.05,-0.35) 朝门 −Y；θ=180 → (3.05,-1.55) 朝吧台 +Y，两椅 x 均 3.05 对称。
    dict(name="TB_05", x=3.05, y=-0.95, chairs=2, window=False),
]
TABLETOP_LACE_R = TABLE_R + 0.06           # 蕾丝桌布垂边半径
TABLETOP_CLOTH_DROP = 0.10                 # 桌布下垂

# 桌上小物
VASE_R = 0.035
VASE_H = 0.15
MENU_CARD_W = 0.105
MENU_CARD_H = 0.148
SUGAR_BOWL_R = 0.045

# ══════════════════════════════════════════════════════════════════════
# 4. 墙面装饰 / 收纳
# ══════════════════════════════════════════════════════════════════════
BOOKSHELF = dict(x=(-3.95, -3.32), y=(1.55, 2.95), z=(0.0, 2.05), shelves=5)
# 老兄要求：黑板放墙面中央、旁边加小装饰。
# 左墙 y∈[-3,3] 中央=0；书架占 y[1.55,2.95]。
# 黑板收窄到 1.20m 宽并居中于 y=0（y∈[-0.60,0.60]），两侧各留装饰位。
CHALKBOARD = dict(face="-X", x=-3.92, y=(-0.60, 0.60), z=(1.25, 2.45), frame=0.035)
# 两框必须同中心线、同高（老兄指出"相框没对齐"）：
# 原 z=(1.30,2.05) 中心1.675 高0.75；z=(1.42,2.10) 中心1.76 高0.68 → 中心差 85mm、高差 70mm
FRAMES_RIGHT = [dict(y=(-1.32, -0.10), z=(1.345, 2.095)),
                dict(y=(0.12, 1.02), z=(1.345, 2.095))]
FRAME_WALL_X = 3.92
# 注：第 3 盏不能放 +Y 后墙 —— 那整面墙被后吧台三层货架占满（BA_Shelf_0/1/2），
#     壁灯与支臂会直接插进层板（实测 BA_Shelf_1↔DC_WallLampBase_2 20mm）。
#     改为右墙靠后处（后吧台右端 y>2.95 之外的空墙段）。
WALL_LAMPS = [dict(wall="-X", x=-3.95, y=-2.35, z=1.95, face="+X"),
              dict(wall="+X", x=3.95, y=-2.05, z=1.95, face="-X"),
              # 第 3 盏：右墙 y=-0.55（Frame_0 y≈-0.55±0.35、Frame_1 y≈1.0，中间空档避免撞相框）
              # 第 3 盏：右墙 y=0.55 —— FRAMES_RIGHT y∈(-1.32,-0.10) 与 (0.75,1.65)，取两框之间空档
              # 右墙被两相框(y -1.32..-0.10 / 0.12..1.02)占满，壁灯无处安放 →
              # 改到前墙窗间柱（y=-2.95，x 在窗洞之间），面朝室内 +Y
              dict(wall="-Y", y=-2.95, x=3.25, z=1.95, face="+Y")]
NOREN = dict(x=(1.10, 2.50), z_top=2.22, z_bot=1.42)   # 门帘（门洞内侧）
WIND_CHIME = dict(x=3.02, y=-2.92, z=2.05)             # 门边风铃
PLANT_CORNER = dict(x=-3.52, y=-2.58)                    # 右后角大盆栽
COAT_RACK = dict(x=1.05, y=-2.82)                      # 门内旁伞架/衣帽钩

# ══════════════════════════════════════════════════════════════════════
# 5. 吊灯 / 照明锚点（Blender 内灯光 & 网页光锚点共用）
# ══════════════════════════════════════════════════════════════════════
PENDANTS = [
    dict(name="LT_P1", x=-2.90, y=-2.00, shade_z=2.10, drop=0.55, r=0.19),
    dict(name="LT_P2", x=-2.55, y=1.05, shade_z=2.14, drop=0.52, r=0.21),
    dict(name="LT_P3", x=1.85, y=1.50, shade_z=2.06, drop=0.60, r=0.17),
]
PENDANT_CANOPY_Z = CEIL_Z
BAR_SPOTS = [dict(x=0.30, y=1.35, z=2.72), dict(x=1.90, y=1.35, z=2.72),
             dict(x=3.20, y=1.35, z=2.72)]              # 吧台射灯
DISPLAY_SPOT = dict(x=-0.94, y=0.83, z=2.55)            # 展示柜顶射灯（2 个）
CEILING_COVE = True                                     # 顶棚暗藏灯带

# ══════════════════════════════════════════════════════════════════════
# 6. 女仆
# ══════════════════════════════════════════════════════════════════════
# 女仆源模型（可选）。优先读环境变量 MAID_SRC，其次找 assets/maid/chibi_maid_USER.blend
MAID_SRC = os.environ.get(
    "MAID_SRC",
    os.path.join(ROOT, "assets", "maid", "chibi_maid_USER.blend"),
)
MAID_SCALE = 1.47             # 原高 1.0224 → 1.503 m（吧台 0.95 到她腰胸之间，视觉合理）
MAID_POS = (-1.85, -0.25)     # 站位（xy）：移到展示柜前方、客座走道中间
MAID_ROT_Z = 42.0             # 绕 Z 旋转（度），面朝大门斜前方
MAID_HEIGHT = 1.0224 * MAID_SCALE

# 托盘系统（世界尺寸，米；角色原点=脚底中心，面朝 -Y）
TRAY_R = 0.165                # 托盘半径（直径 33cm）
TRAY_T = 0.014                # 托盘厚度
TRAY_Z = 0.742                # 托盘上表面高度（与双手 0.674–0.771 齐平）
TRAY_Y = -0.170               # 托盘中心 y（双手中心 y≈−0.13，围裙前表面 y≈−0.09）
CAKE_R = 0.066                # 草莓小蛋糕半径
PLATE_R = 0.094               # 纸盘半径
CUP_R = 0.032                 # 咖啡杯口半径
SAUCER_R = 0.052              # 杯碟半径
STEAM_H = 0.150               # 蒸汽面片高度
HAND_Y = -0.130               # 双手中心 y（供校验托盘包裹）

# 女仆减面目标（集合 C_Maid 总 tri 上限 260k）
MAID_DECIMATE = {
    "big": 0.105,        # 裙/胸衣/围裙/腿等大件（体积大但形简单）
    "head": 0.22,        # 头/脖子/手
    "face": 0.38,        # 五官/眼
    "small": 0.32,       # 小配件（扣子/蝴蝶结/袜圈等）
}

# ══════════════════════════════════════════════════════════════════════
# 7. 室外（低模）
# ══════════════════════════════════════════════════════════════════════
SIDEWALK = dict(y=(-4.60, -3.0), z=(-0.02, 0.02), curb_h=0.12)
ROAD = dict(y=(-9.20, -5.20), z=-0.14)
BLDG_FAR = dict(y=(-15.0, -9.60), x=(-18.0, 18.0), h=14.0)
BLDG_SPAN_X = 6.0             # 对面建筑分段宽度
STREET_LAMPS = [dict(x=-3.0, y=-4.35), dict(x=2.4, y=-4.35)]
PED_SPEED = 0.0               # 行人静态（低模剪影）

# ══════════════════════════════════════════════════════════════════════
# 8. 配色（HEX → linear 由 ccore.hexc 转）
# ══════════════════════════════════════════════════════════════════════
C_WALL_CREAM = "#F2E6D6"
C_WALL_ACCENT = "#EADCC8"
C_WOOD_OAK = "#B98A5E"
C_WOOD_WALNUT = "#8B5E3C"
C_WOOD_DARK = "#6B4530"
C_FLOOR_HERRING = "#C8A277"
C_MARBLE = "#EFEAE3"
C_NAVY = "#1E2B4D"
C_LACE = "#FFFDF8"
C_BRASS = "#C9A227"
C_STEEL = "#B8BCC0"
C_BLACK = "#1A1715"
C_GLASS_TINT = "#DCEAF2"
C_LAMP_WARM = "#FFD9A0"
C_LAMP_LIGHT = "#FFC98A"
C_LAMP_WARMER = "#FFB86B"
C_COFFEE = "#4A2C1A"
C_CREAM_DEEP = "#D9C3A5"
C_PINK = "#F3C6D2"
C_SAGE = "#8A9A7B"
C_CUSHION = "#E8CBB4"

# 时段/天气光照参数（Blender QC 与网页共用；数值可调但两处必须同源）
LIGHT_RIG = {
    "morning": dict(
        sun_rot=(74.0, 0.0, 46.0), sun_energy=2.5, sun_color="#DCE9FF",
        sky="#BFD8F2", ambient=0.55, exposure=-0.15, indoor=0.45, fog=0.0,
    ),
    "noon": dict(
        sun_rot=(22.0, 0.0, 12.0), sun_energy=4.4, sun_color="#FFF8EE",
        sky="#CFE8FF", ambient=0.85, exposure=-0.45, indoor=0.25, fog=0.0,
    ),
    "dusk": dict(
        sun_rot=(72.0, 0.0, -20.0), sun_energy=2.8, sun_color="#FFA95C",
        sky="#F5C08A", ambient=0.45, exposure=-0.20, indoor=0.95, fog=0.0,
    ),
    "night": dict(
        sun_rot=(80.0, 0.0, 160.0), sun_energy=0.10, sun_color="#4C6FA8",
        sky="#16233C", ambient=0.16, exposure=0.10, indoor=1.75, fog=0.0,
    ),
}
WEATHER_RIG = {
    "clear": dict(sun_mult=1.00, ambient_mult=1.00, fog=0.0, cloud_cover=0.0, rain=0.0),
    "cloudy": dict(sun_mult=0.38, ambient_mult=1.70, fog=0.012, cloud_cover=0.85, rain=0.0),
    "rain_light": dict(sun_mult=0.24, ambient_mult=1.45, fog=0.020, cloud_cover=0.9, rain=0.25),
    "rain_med": dict(sun_mult=0.18, ambient_mult=1.35, fog=0.032, cloud_cover=0.95, rain=0.55),
    "rain_heavy": dict(sun_mult=0.12, ambient_mult=1.20, fog=0.050, cloud_cover=1.0, rain=0.85),
    "storm": dict(sun_mult=0.08, ambient_mult=1.10, fog=0.045, cloud_cover=1.0, rain=1.0),
}

# ══════════════════════════════════════════════════════════════════════
# 9. 贴图索引 —— 物理 id 在 PolyHaven 上，asset-scout 下载后按此命名
# ══════════════════════════════════════════════════════════════════════
TEXTURES = {
    # 地板（人字拼，2k）
    "floor_herringbone": ("herringbone_parquet", "2k"),
    "floor_parquet_alt": ("wooden_floor_01", "1k"),
    "floor_wood_alt": ("wood_floor", "1k"),
    # 木
    "wood_counter": ("wood_table", "1k"),
    "wood_wainscot": ("japanese_cedar_planks", "1k"),
    "wood_shelf": ("wood_table", "1k"),
    "wood_table": ("wood_table", "1k"),
    "wood_dark": ("wood_floor", "1k"),
    # 石/大理石
    "marble_top": ("marble_01", "1k"),
    "marble_tile": ("marble_01", "1k"),
    # 墙面
    "wall_cream": ("white_stucco", "1k"),
    "wall_plaster": ("plastered_wall_02", "1k"),
    # 布料
    "fabric_linen": ("rough_linen", "1k"),
    "fabric_satin": ("crepe_satin", "1k"),
    "fabric_gingham": ("gingham_check", "1k"),
    "fabric_cotton": ("waffle_pique_cotton", "1k"),
    "fabric_velvet": ("rough_linen", "1k"),
    # 金属
    "metal_plate": ("metal_plate", "1k"),
    "metal_grate": ("metal_grate_rusty", "1k"),
    # 皮革
    "leather": ("fabric_leather_01", "1k"),
    # 室外
    "out_asphalt": ("asphalt_floor", "1k"),
    "out_pavers": ("concrete_pavers_02", "1k"),
    "out_concrete": ("plastered_wall_02", "1k"),
    "out_brick": ("red_brick", "1k"),
    "out_plaster": ("plastered_wall_02", "1k"),
    # 其他
    "ceramic_tile": ("square_concrete_pavers", "1k"),
}

# 生成贴图（asset-scout 用 Pillow 造）
TEX_GENERATED = {
    "menu_blackboard": "menu_blackboard.png",
    "noren_welcome": "noren_welcome.png",
    "sign_cafe": "sign_cafe.png",
    "menu_card": "menu_card.png",
    "label_beans": "label_beans.png",
    "label_tea": "label_tea.png",
    "picture_art_01": "picture_art_01.png",
    "picture_art_02": "picture_art_02.png",
    "picture_art_03": "picture_art_03.png",
    "chalk_open": "chalk_open.png",
    "window_drops": "window_drops.png",
}

# ══════════════════════════════════════════════════════════════════════
# 10. 集合 + 预算
# ══════════════════════════════════════════════════════════════════════
COLS = ["C_Room", "C_Bar", "C_Display", "C_Seating", "C_Decor", "C_Outdoor",
        "C_Maid", "C_Light", "C_QC", "C_Helper"]
BUDGET = {"C_Room": 60000, "C_Bar": 70000, "C_Display": 40000,
          "C_Seating": 70000, "C_Decor": 60000, "C_Outdoor": 35000,
          "C_Maid": 260000, "TOTAL": 500000}

# ══════════════════════════════════════════════════════════════════════
# 11. 辅助
# ══════════════════════════════════════════════════════════════════════
def tex_path(key, map_="diff", res=None):
    """按 TEXTURES 索引返回贴图绝对路径（不存在时用 glob 兜底；全无 → None）。"""
    import os as _os
    import glob as _glob
    ent = TEXTURES.get(key)
    if not ent:
        return None
    pid, r = ent
    r = res or r
    suffix = {"diff": "diff", "nor": "nor_gl", "rough": "rough",
              "arm": "arm", "disp": "disp", "metal": "metal"}.get(map_, map_)
    p = _os.path.join(TEX, f"{pid}_{suffix}_{r}.jpg")
    if _os.path.exists(p):
        return p
    # 兜底 1：同 id 任意分辨率
    hits = sorted(_glob.glob(_os.path.join(TEX, f"{pid}_{suffix}_*.jpg")),
                  key=lambda x: -_os.path.getsize(x))
    if hits:
        return hits[0]
    # 兜底 2：同 id 任意 map
    hits = sorted(_glob.glob(_os.path.join(TEX, f"{pid}_*.jpg")))
    if hits:
        return hits[0]
    return None


def tex_gen_path(key):
    """生成贴图路径。key 可以是 TEX_GENERATED 的键，也可以直接给文件名。"""
    import os as _os
    f = TEX_GENERATED.get(key)
    if f:
        p = _os.path.join(TEX_GEN, f)
        return p if _os.path.exists(p) else None
    # 直接给文件名（含扩展名）
    if key.endswith((".png", ".jpg")):
        p = _os.path.join(TEX_GEN, key)
        return p if _os.path.exists(p) else None
    return None


def model_dir(pid):
    import os as _os
    p = _os.path.join(MODELS, pid)
    return p if _os.path.isdir(p) else None


def table_world(name):
    for t in TABLES:
        if t["name"] == name:
            return t
    return None
