# 女仆咖啡馆 · 资产清单 (MANIFEST)

生成时间：2026-10-21 12:01 (+08:00)（本文件由 `tools/build_manifest.mjs` 自动生成，可重复运行）

**来源**：全部 3D 资产与贴图来自 [PolyHaven](https://polyhaven.com)，许可证 **CC0 1.0 Universal（公有领域）**，可商用、可修改、无需署名（此处署名仅为礼貌与可追溯）。
每一项的来源页面统一为 `https://polyhaven.com/a/<polyhaven_id>`，直链由 PolyHaven Files API 解析下载（`https://api.polyhaven.com/files/<id>`）。
文字/插画贴图由本项目脚本 `tools/gen_textures.py`（Pillow + Windows 日文字体 Yu Gothic / MS Gothic / Georgia）程序化生成，版权归项目所有。

## 总量

| 类别 | 数量 | 占用 | 路径 |
| --- | ---: | ---: | --- |
| PBR 贴图（PolyHaven，19 组 × 5 图 = 95 文件） | 19 组 | 83.42 MB | `assets/tex/` |
| PolyHaven 模型（.blend 1k + 贴图） | 37 个 | 269.46 MB | `assets/models/<id>/` |
| HDRI 1k .hdr | 5 张 | 7.00 MB | `assets/hdri/` |
| 程序化生成贴图 PNG | 11 张 | 8.83 MB | `assets/tex/generated/` |
| **合计** | | **368.72 MB** | `assets/` |

---

## 1. PBR 贴图 `assets/tex/`

命名规范：`<polyhaven_id>_<map>_<res>.jpg`，map ∈ `diff`(基色) / `nor_gl`(法线) / `arm`(AO+Rough+Metal 打包) / `rough`(粗糙度) / `disp`(置换)。地板 2k，其余 1k。

| 用途 | 资产 id | 作者 | 文件名 | 分辨率 | 文件数 | 大小 |
| --- | --- | --- | --- | --- | ---: | ---: |
| 人字拼木地板（主地板） | `herringbone_parquet` | Jenelle van Heerden, Sergej Majboroda | `herringbone_parquet_arm_2k.jpg`<br>`herringbone_parquet_diff_2k.jpg`<br>`herringbone_parquet_disp_2k.jpg`<br>`herringbone_parquet_nor_gl_2k.jpg`<br>`herringbone_parquet_rough_2k.jpg` | 2k | 5 | 10.89 MB |
| 浅色木地板备选 A | `wooden_floor_01` | Charlotte Baglioni, Rico Cilliers | `wooden_floor_01_arm_2k.jpg`<br>`wooden_floor_01_diff_2k.jpg`<br>`wooden_floor_01_disp_2k.jpg`<br>`wooden_floor_01_nor_gl_2k.jpg`<br>`wooden_floor_01_rough_2k.jpg` | 2k | 5 | 10.55 MB |
| 浅色木地板备选 B | `wood_floor` | Dimitrios Savva | `wood_floor_arm_2k.jpg`<br>`wood_floor_diff_2k.jpg`<br>`wood_floor_disp_2k.jpg`<br>`wood_floor_nor_gl_2k.jpg`<br>`wood_floor_rough_2k.jpg` | 2k | 5 | 10.94 MB |
| 吧台木纹 | `wood_table` | Dimitrios Savva | `wood_table_arm_1k.jpg`<br>`wood_table_diff_1k.jpg`<br>`wood_table_disp_1k.jpg`<br>`wood_table_nor_gl_1k.jpg`<br>`wood_table_rough_1k.jpg` | 1k | 5 | 3.08 MB |
| 吧台台面大理石（细腻） | `marble_01` | Rob Tuytel | `marble_01_arm_1k.jpg`<br>`marble_01_diff_1k.jpg`<br>`marble_01_disp_1k.jpg`<br>`marble_01_nor_gl_1k.jpg`<br>`marble_01_rough_1k.jpg` | 1k | 5 | 0.61 MB |
| 墙裙木板（暖色） | `japanese_cedar_planks` | Charlotte Baglioni, Rico Cilliers | `japanese_cedar_planks_arm_1k.jpg`<br>`japanese_cedar_planks_diff_1k.jpg`<br>`japanese_cedar_planks_disp_1k.jpg`<br>`japanese_cedar_planks_nor_gl_1k.jpg`<br>`japanese_cedar_planks_rough_1k.jpg` | 1k | 5 | 2.88 MB |
| 奶油色墙面 | `white_stucco` | Amal Kumar | `white_stucco_arm_1k.jpg`<br>`white_stucco_diff_1k.jpg`<br>`white_stucco_disp_1k.jpg`<br>`white_stucco_nor_gl_1k.jpg`<br>`white_stucco_rough_1k.jpg` | 1k | 5 | 2.65 MB |
| 粗亚麻（桌布/坐垫） | `rough_linen` | colormass, Rico Cilliers | `rough_linen_arm_1k.jpg`<br>`rough_linen_diff_1k.jpg`<br>`rough_linen_disp_1k.jpg`<br>`rough_linen_nor_gl_1k.jpg`<br>`rough_linen_rough_1k.jpg` | 1k | 5 | 4.68 MB |
| 缎面（蕾丝衬底/缎带） | `crepe_satin` | colormass, Rico Cilliers | `crepe_satin_arm_1k.jpg`<br>`crepe_satin_diff_1k.jpg`<br>`crepe_satin_disp_1k.jpg`<br>`crepe_satin_nor_gl_1k.jpg`<br>`crepe_satin_rough_1k.jpg` | 1k | 5 | 3.72 MB |
| 格纹布（椅面/餐垫） | `gingham_check` | colormass, Rico Cilliers | `gingham_check_arm_1k.jpg`<br>`gingham_check_diff_1k.jpg`<br>`gingham_check_disp_1k.jpg`<br>`gingham_check_nor_gl_1k.jpg`<br>`gingham_check_rough_1k.jpg` | 1k | 5 | 4.47 MB |
| 华夫格棉（坐垫/毛巾） | `waffle_pique_cotton` | colormass, Rico Cilliers | `waffle_pique_cotton_arm_1k.jpg`<br>`waffle_pique_cotton_diff_1k.jpg`<br>`waffle_pique_cotton_disp_1k.jpg`<br>`waffle_pique_cotton_nor_gl_1k.jpg`<br>`waffle_pique_cotton_rough_1k.jpg` | 1k | 5 | 4.07 MB |
| 金属板（吧台设备） | `metal_plate` | Rob Tuytel | `metal_plate_arm_1k.jpg`<br>`metal_plate_diff_1k.jpg`<br>`metal_plate_disp_1k.jpg`<br>`metal_plate_nor_gl_1k.jpg`<br>`metal_plate_rough_1k.jpg` | 1k | 5 | 3.45 MB |
| 锈蚀金属格栅（灯具/货架） | `metal_grate_rusty` | Rob Tuytel, Dimitrios Savva | `metal_grate_rusty_arm_1k.jpg`<br>`metal_grate_rusty_diff_1k.jpg`<br>`metal_grate_rusty_disp_1k.jpg`<br>`metal_grate_rusty_nor_gl_1k.jpg`<br>`metal_grate_rusty_rough_1k.jpg` | 1k | 5 | 3.62 MB |
| 户外沥青路面 | `asphalt_floor` | eye-candy.xyz | `asphalt_floor_arm_1k.jpg`<br>`asphalt_floor_diff_1k.jpg`<br>`asphalt_floor_disp_1k.jpg`<br>`asphalt_floor_nor_gl_1k.jpg`<br>`asphalt_floor_rough_1k.jpg` | 1k | 5 | 4.39 MB |
| 人行道铺装 | `concrete_pavers_02` | Amal Kumar | `concrete_pavers_02_arm_1k.jpg`<br>`concrete_pavers_02_diff_1k.jpg`<br>`concrete_pavers_02_disp_1k.jpg`<br>`concrete_pavers_02_nor_gl_1k.jpg`<br>`concrete_pavers_02_rough_1k.jpg` | 1k | 5 | 2.35 MB |
| 人行道铺装备选 | `square_concrete_pavers` | Amal Kumar | `square_concrete_pavers_arm_1k.jpg`<br>`square_concrete_pavers_diff_1k.jpg`<br>`square_concrete_pavers_disp_1k.jpg`<br>`square_concrete_pavers_nor_gl_1k.jpg`<br>`square_concrete_pavers_rough_1k.jpg` | 1k | 5 | 3.58 MB |
| 对面建筑砖墙 | `red_brick` | Rob Tuytel | `red_brick_arm_1k.jpg`<br>`red_brick_diff_1k.jpg`<br>`red_brick_disp_1k.jpg`<br>`red_brick_nor_gl_1k.jpg`<br>`red_brick_rough_1k.jpg` | 1k | 5 | 2.88 MB |
| 对面建筑抹灰外墙 | `plastered_wall_02` | Charlotte Baglioni | `plastered_wall_02_arm_1k.jpg`<br>`plastered_wall_02_diff_1k.jpg`<br>`plastered_wall_02_disp_1k.jpg`<br>`plastered_wall_02_nor_gl_1k.jpg`<br>`plastered_wall_02_rough_1k.jpg` | 1k | 5 | 2.48 MB |
| 皮革（沙发/椅面） | `fabric_leather_01` | Rob Tuytel | `fabric_leather_01_arm_1k.jpg`<br>`fabric_leather_01_diff_1k.jpg`<br>`fabric_leather_01_disp_1k.jpg`<br>`fabric_leather_01_nor_gl_1k.jpg`<br>`fabric_leather_01_rough_1k.jpg` | 1k | 5 | 2.11 MB |

来源 URL 模板：`https://polyhaven.com/a/<polyhaven_id>`（如 https://polyhaven.com/a/herringbone_parquet ）

外观速查（供美术/网页配色参考）：

- `herringbone_parquet`：人字拼木地板，中等暖棕，板缝清晰 —— 门店主地板；备选 `wooden_floor_01`（浅灰棕）、`wood_floor`（暖黄棕）。
- `wood_table`：横向木纹桌面；`marble_01`：细白底灰纹大理石 —— 吧台台面。
- `japanese_cedar_planks`：暖色竖向杉木板 —— 墙裙/护墙板；`white_stucco`：奶油白微颗粒墙面。
- `rough_linen` / `crepe_satin` / `gingham_check` / `waffle_pique_cotton`：亚麻桌布 / 缎面蕾丝衬底 / 蓝白格纹 / 华夫格坐垫。
- `metal_plate`：拉丝金属板；`metal_grate_rusty`：锈蚀格栅 —— 吧台设备、灯具罩、货架。
- `asphalt_floor`：户外沥青；`concrete_pavers_02` / `square_concrete_pavers`：人行道方砖；`red_brick`：对面红砖墙；`plastered_wall_02`：抹灰外墙。
- `fabric_leather_01`：细纹皮革 —— 沙发/靠背椅面。

---

## 2. 模型 `assets/models/<id>/`

每个目录结构：`<id>/<id>_1k.blend`（自带 PBR 材质，贴图在 `textures/` 子目录，需 `File > External Data > Find Missing Files` 指向该目录，或直接使用 Blender 的 relative 路径，因为下载时保持了 PolyHaven 的 `textures/<name>` 相对布局 — 见下注）。

> 注：PolyHaven 的 .blend 内部贴图按 `//textures/<file>` 引用；下载器把这些文件原样放到了与 .blend 同级的 `textures/` 目录，所以打开即可直接解析。

| 用途 | id | 作者 | 物体数 | 三角面 | 材质数 | 贴图(有/总) | 尺寸 (m, XYZ) | .blend | 总大小 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| 木桌 A（长条木桌） | `WoodenTable_01` | Ethan Place | 1 | 952 | 1 | 4/4 | 1.8 × 0.657 × 0.549 | `WoodenTable_01_1k.blend` | 1.52 MB |
| 木桌 B（简单四腿） | `wooden_table_02` | Serhii Khromov | 1 | 196 | 1 | 4/4 | 1.134 × 0.706 × 0.8 | `wooden_table_02_1k.blend` | 1.64 MB |
| 木桌 C（圆桌，咖啡馆主用） | `round_wooden_table_01` | Ulan Cabanilla | 2 | 8640 | 1 | 5/6 | 1.399 × 1.399 × 1.005 | `round_wooden_table_01_1k.blend` | 2.39 MB |
| 木椅 A（白漆木椅） | `painted_wooden_chair_01` | Kuutti Siitonen | 1 | 724 | 1 | 4/4 | 0.432 × 0.54 × 0.956 | `painted_wooden_chair_01_1k.blend` | 1.38 MB |
| 木椅 B（灰梯背木椅） | `painted_wooden_chair_02` | Kirill Sannikov | 1 | 1246 | 1 | 3/3 | 0.639 × 0.662 × 1.264 | `painted_wooden_chair_02_1k.blend` | 3.43 MB |
| 木椅 C（皮革高背餐椅） | `dining_chair_02` | James Ray Cock | 1 | 22013 | 1 | 4/5 | 0.434 × 0.576 × 0.973 | `dining_chair_02_1k.blend` | 2.12 MB |
| 扶手椅/沙发椅 | `ArmChair_01` | Kirill Sannikov | 1 | 5626 | 1 | 4/4 | 0.848 × 0.766 × 1.065 | `ArmChair_01_1k.blend` | 2.58 MB |
| 吧椅 | `bar_chair_round_01` | Dairon Sanchez | 1 | 14373 | 1 | 4/4 | 0.483 × 0.486 × 0.751 | `bar_chair_round_01_1k.blend` | 2.87 MB |
| 书架/层架 A | `wooden_bookshelf_worn` | Ulan Cabanilla | 1 | 10106 | 1 | 4/4 | 1.374 × 0.581 × 2.063 | `wooden_bookshelf_worn_1k.blend` | 4.12 MB |
| 层架 B（金属/展示） | `steel_frame_shelves_01` | James Ray Cock | 1 | 4348 | 1 | 4/4 | 1.097 × 0.502 × 2.141 | `steel_frame_shelves_01_1k.blend` | 2.30 MB |
| 吊灯 A | `hanging_industrial_lamp` | Kuutti Siitonen | 1 | 9530 | 2 | 6/6 | 0.55 × 0.55 × 1.355 | `hanging_industrial_lamp_1k.blend` | 8.57 MB |
| 吊灯 B | `caged_hanging_light` | Ulan Cabanilla | 1 | 22893 | 1 | 5/5 | 1.162 × 0.315 × 0.75 | `caged_hanging_light_1k.blend` | 4.46 MB |
| 吊灯 C（黄铜/复古） | `brass_diya_lantern` | Bhargav Kubal | 3 | 12742 | 3 | 5/5 | 0.123 × 0.123 × 0.381 | `brass_diya_lantern_1k.blend` | 2.64 MB |
| 壁灯 A | `industrial_wall_lamp` | Kuutti Siitonen | 1 | 4446 | 2 | 8/8 | 0.273 × 0.14 × 0.43 | `industrial_wall_lamp_1k.blend` | 14.29 MB |
| 茶具组 | `tea_set_01` | James Ray Cock, Rico Cilliers, Jurita Burger | 10 | 40296 | 1 | 4/5 | 0.918 × 0.484 × 0.165 | `tea_set_01_1k.blend` | 3.46 MB |
| 陶瓷壶/罐 | `ceramic_pot` | Aron Łyczek | 1 | 3592 | 1 | 4/4 | 0.656 × 0.502 × 0.372 | `ceramic_pot_1k.blend` | 2.05 MB |
| 草莓巧克力蛋糕 | `strawberry_chocolate_cake` | Kuutti Siitonen | 1 | 27054 | 1 | 5/5 | 0.244 × 0.24 × 0.079 | `strawberry_chocolate_cake_1k.blend` | 5.10 MB |
| 胡萝卜蛋糕 | `carrot_cake` | Greg Zaal, James Ray Cock | 1 | 13790 | 1 | 8/9 | 0.225 × 0.225 × 0.098 | `carrot_cake_1k.blend` | 7.35 MB |
| 咖啡机类 | `CoffeeCart_01` | Joe Seabuhr | 3 | 27659 | 3 | 8/8 | 2.168 × 1.073 × 1.718 | `CoffeeCart_01_1k.blend` | 5.11 MB |
| 收银机 | `CashRegister_01` | Joe Seabuhr | 2 | 9927 | 2 | 9/9 | 0.6 × 0.624 × 0.621 | `CashRegister_01_1k.blend` | 2.87 MB |
| 相框 A（挂墙） | `hanging_picture_frame_01` | James Ray Cock | 1 | 2586 | 3 | 8/8 | 0.594 × 0.016 × 0.841 | `hanging_picture_frame_01_1k.blend` | 1.19 MB |
| 相框 B | `fancy_picture_frame_02` | Rob Tuytel, Rico Cilliers | 2 | 35102 | 2 | 6/6 | 0.661 × 0.089 × 0.771 | `fancy_picture_frame_02_1k.blend` | 5.34 MB |
| 立式黑板 | `standing_chalkboard_01` | ParzivalCG | 1 | 2372 | 2 | 8/8 | 0.92 × 0.759 × 1.509 | `standing_chalkboard_01_1k.blend` | 13.95 MB |
| 盆栽 A（大叶） | `calathea_orbifolia_01` | Rob Tuytel, Rico Cilliers | 5 | 16688 | 1 | 4/4 | 2.492 × 1.194 × 0.424 | `calathea_orbifolia_01_1k.blend` | 4.20 MB |
| 盆栽 B | `potted_plant_01` | Rico Cilliers | 4 | 96030 | 2 | 7/8 | 0.587 × 0.634 × 1.35 | `potted_plant_01_1k.blend` | 21.57 MB |
| 盆栽 C（蕨类） | `fern_02` | Rob Tuytel, Rico Cilliers | 4 | 6232 | 1 | 4/4 | 1.973 × 1.724 × 0.428 | `fern_02_1k.blend` | 1.68 MB |
| 花瓶 | `brass_vase_01` | Rico Cilliers | 1 | 21440 | 1 | 5/5 | 0.227 × 0.227 × 0.692 | `brass_vase_01_1k.blend` | 2.99 MB |
| 酒瓶/玻璃器 | `wine_bottles_01` | Rico Cilliers, Jurita Burger | 4 | 28848 | 12 | 22/22 | 0.676 × 0.081 × 0.331 | `wine_bottles_01_1k.blend` | 9.79 MB |
| 街灯 A（立杆式） | `street_lamp_01` | Josh Dean | 1 | 30610 | 3 | 5/5 | 0.704 × 0.386 × 3.871 | `street_lamp_01_1k.blend` | 3.27 MB |
| 对面建筑体块 A（公寓立面模块） | `modular_urban_apartments_facade` | James Ray Cock | 147 | 109535 | 5 | 14/14 | 51.53 × 6.665 × 17 | `modular_urban_apartments_facade_1k.blend` | 46.02 MB |
| 木桌 D（长餐桌，格纹桌布款） | `dining_table` | Aron Łyczek | 2 | 1048 | 1 | 3/3 | 2.256 × 1.39 × 0.877 | `dining_table_1k.blend` | 3.11 MB |
| 壁灯 B（笼式/复古） | `industrial_caged_sconce` | Ulan Cabanilla | 11 | 26576 | 1 | 5/5 | 1.21 × 0.389 × 0.913 | `industrial_caged_sconce_1k.blend` | 3.68 MB |
| 盆栽 D（小型桌面植物） | `potted_plant_04` | James Ray Cock | 4 | 6097 | 1 | 3/3 | 0.17 × 0.186 × 0.268 | `potted_plant_04_1k.blend` | 2.88 MB |
| 盆栽 E（花箱/窗台） | `planter_box_02` | James Ray Cock | 1 | 10944 | 1 | 4/4 | 1.252 × 0.467 × 0.453 | `planter_box_02_1k.blend` | 3.68 MB |
| 边桌/展示小几 | `side_table_01` | James Ray Cock | 1 | 2756 | 1 | 4/5 | 0.55 × 0.45 × 0.551 | `side_table_01_1k.blend` | 1.05 MB |
| 街灯 B（备选款） | `street_lamp_02` | Josh Dean | 1 | 20338 | 3 | 5/5 | 0.386 × 0.807 × 1.675 | `street_lamp_02_1k.blend` | 2.93 MB |
| 对面建筑体块 B（工厂立面模块） | `modular_factory_facade` | James Ray Cock | 192 | 133907 | 6 | 19/20 | 53.33 × 5.356 × 29 | `modular_factory_facade_1k.blend` | 61.85 MB |

说明：

- 「三角面」为网格基准三角面数（不含修改器求值后的结果；这些静态资产基本没有修改器）。
- 「贴图(有/总)」中未解析的少数贴图是 PolyHaven 打包 .blend 时残留的旧 HDRI 环境贴图引用（模型自身 PBR 贴图均已内置/可解析），不影响使用；如需彻底干净，可在 Blender 里删除该 World 环境贴图引用。
- 全部 `.blend` 已用 headless Blender 5.2 逐个打开校验（`tools/blender_audit_models.py`），本次 37 个文件全部可正常打开，0 失败。

---

## 3. HDRI `assets/hdri/`

1k `.hdr`（Radiance RGBE），用于场景环境光/天空/反射。所有均为 PolyHaven CC0。

| 用途 | id | 作者 | 文件 | 大小 |
| --- | --- | --- | --- | ---: |
| 晴朗白天天空 | `kloppenheim_06_puresky` | Greg Zaal, Jarod Guest | `kloppenheim_06_puresky_1k.hdr` | 1.12 MB |
| 清晨天空 | `kiara_2_sunrise` | Greg Zaal | `kiara_2_sunrise_1k.hdr` | 1.47 MB |
| 黄昏天空 | `evening_road_01_puresky` | Jarod Guest, Sergej Majboroda | `evening_road_01_puresky_1k.hdr` | 1.25 MB |
| 夜晚天空/街景 | `dikhololo_night` | Greg Zaal | `dikhololo_night_1k.hdr` | 1.66 MB |
| 室内柔光 | `hotel_room` | Greg Zaal | `hotel_room_1k.hdr` | 1.50 MB |

使用建议：白天用 `kloppenheim_06_puresky`（纯天光，无地景杂物，适合裁切）；清晨 `kiara_2_sunrise`；黄昏 `evening_road_01_puresky`（纯天空版，街道反射更干净）；夜晚 `dikhololo_night`（有星星与远处灯光）；室内柔光 `hotel_room`（暖色室内，适合做小件资产预览）。

---

## 4. 生成贴图 `assets/tex/generated/`

全部由 `tools/gen_textures.py` 生成（Pillow 12 + Windows 字体：Yu Gothic Medium/Bold、MS Gothic、Georgia、Segoe Print），可复现（`python tools/gen_textures.py`）。

| 文件 | 尺寸 | 用途 |
| --- | --- | --- |
| `chalk_open.png` | 1200×900 | 「OPEN / 営業中」粉笔挂牌，门口玻璃或门把手 |
| `label_beans.png` | 1024×640 | 咖啡豆罐标签（オリジナルブレンド / 200g），贴罐身或货架价签 |
| `label_tea.png` | 1024×640 | 茶叶罐标签（アールグレイ / 100g），与豆罐成对 |
| `menu_blackboard.png` | 1200×1700 | 店内手写风黑板菜单（日文+英文 13 行 + 价格），挂在吧台后墙或用 standing_chalkboard_01 的板面替换 |
| `menu_card.png` | 1050×1484 | 桌面菜单立牌（A6 竖版 105:148），放每张桌子中央；也可缩放当托盘垫纸 |
| `noren_welcome.png` | 1536×1024 | 门帘「いらっしゃいませ」，门口玄关横挂；藏青底 + 暖白字，双帘缝 |
| `picture_art_01.png` | 1024×1024 | 相框插画·花瓶与花（柔和插画风），配 fancy_picture_frame_02 / hanging_picture_frame_01 |
| `picture_art_02.png` | 1024×1024 | 相框插画·打瞌睡的猫（柔和插画风），适合放收银台后或墙角 |
| `picture_art_03.png` | 1024×1024 | 相框插画·咖啡杯与拉花（柔和插画风），适合吧台上方 |
| `sign_cafe.png` | 1800×1100 | 门口招牌「Maid Café めいど」，奶油底木框；可直接贴 plane 或做灯箱面 |
| `window_drops.png` | 1024×1024 | 窗玻璃雨滴/水痕（RGBA 透明，1024²），网页雨天叠加层或玻璃材质 alpha 贴图 |

---

## 5. 复现方式

```bash
node tools/ph_scout_manifest.mjs   # 按 tools/ph_wishlist.json 核对 PolyHaven 资产存在性 -> .scratch/asset-scout/resolved.json
node tools/ph_dl_tex.mjs           # 下载 PBR 贴图到 assets/tex/（已存在且 >1KB 自动 SKIP）
node tools/ph_dl_model.mjs         # 下载模型 .blend 1k + textures 到 assets/models/
node tools/ph_dl_hdri.mjs          # 下载 HDRI 1k .hdr 到 assets/hdri/
python tools/gen_textures.py       # 生成文字/标签/插画 PNG 到 assets/tex/generated/
node tools/build_manifest.mjs      # 重新生成本清单
```

所有下载脚本均可重复运行（存在且 >1KB 即跳过），中断后重跑可续传；遇到 403/404 会按 wishlist 里的候选列表自动换源。

模型校验（Blender 5.2 headless）：

```bash
blender.exe -b --factory-startup -P tools/blender_audit_models.py -- <modelsDir> <outJson>
```
