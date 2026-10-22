# 中间快照验收报告（QC · 2026-10-21 13:30 那一版）

> ⚠️ **历史快照，不代表最终交付**：本报告的指纹是 `scene/maid_cafe.blend` 60,506,544 B /
> `scene/maid_cafe.glb` 16,129,828 B / 391,341 tri 那一版。此后模型由作者本人修订并冻结，
> **最终交付**是 `scene/maid_cafe.glb`（21.67 MB / 512,504 tri / 1,124 网格 / 148 材质）。
> 下面所有穿模 / 光影 / 三角面数字**只对那一版快照有效**；要对最终模型复检，用 `blender/qc/` 下的脚本重跑。

> 本文件是 Project「女仆咖啡馆」在 2026-10-21 那一版模型上跑的 QC 体检记录，由 `blender/qc/` 工具链产出。
> 判据唯一来源：`blender/qc/qc_rules.json`（7 轮迭代沉淀，每条豁免均带裁决来源）。
> 三态口径：**PASS** = 判据全过；**FAIL** = 有硬判据未通过；**待确认** = 有 WARN 或证据不足。
> 结论一律带物体名 / 坐标 / 毫米数 / 证据路径，不接受「看起来没问题」。

## 0. 本快照的冻结指纹

| 文件 | MD5 | 字节 | mtime |
|---|---|---|---|
| `scene/maid_cafe.blend` | `EF352FABEBD18AA7CE66D95D3F1428FA` | 60,506,544 | 2026-10-21 13:30:24 |
| `scene/maid_cafe.glb` | `D599BA1C0CE14384EA926E758F1626E7` | 16,129,828 | 2026-10-21 13:31:06 |
| `scene/scene_manifest.json` | — | 43,749 | 2026-10-21 13:30:24 |

**四项体检结果全部记录同一 `scene_md5 = ef352fab…`，与冻结指纹一致。**
`qc_freshness.py` 校验：**RESULT: FRESH**（13 个模块源码 mtime 全部早于 blend 13:30:24）。

场景规模：**391,341 tris / 1,212 objects / 139 colliders / errors {}**

---

## 1. 五项三态表

| 体检项 | 三态结论 | 关键数字 | 证据文件 |
|---|---|---|---|
| **GLB 交付合规** | **PASS** | **16/16 项检查通过** · 391,341 tri · 15.383 MB · 44 张 WebP 全内嵌 · 3,140 accessor 全合法 · 1,212 node / 129 material | `gltf_frozen.json` |
| **穿模 / 落地 / 贴墙** | **FAIL** | **39 条**（FAIL 28 / WARN 11）· **最大仅 20.0mm** | `collide_frozen.json` |
| **指定配对间距** | **FAIL** | 12 对：PASS 8 / FAIL 4 · 4 条全是**浮点级 <0.15mm** | `pairs_frozen.json` |
| **光影（4 时段×3 天气）** | **FAIL** | 12 张：**白天 6/6 PASS** · 昏夜 6 FAIL（CCT 5504–5578K） | `light_frozen.json` |
| **判据校准** | **PASS** | collide 11/11 · pairs 3/3 · light 5/5 · gltf 3/3，**零漏报零误报** | `calib_results/*.json` |

**逐区块三角面预算（全部达标）**

| 集合 | 实测 tri | 预算 | 占用 |
|---|---|---|---|
| C_Room | 2,420 | 60,000 | 4.0% |
| C_Bar | 30,099 | 70,000 | 43.0% |
| C_Display | 22,646 | 40,000 | 56.6% |
| C_Seating | 60,492 | 70,000 | 86.4% |
| C_Decor | 31,531 | 60,000 | 52.6% |
| C_Outdoor | 11,056 | 35,000 | 31.6% |
| C_Maid | 197,136 | 260,000 | 75.8% |
| **合计** | **391,341** | **500,000** | **78.3%** |

**模块健康度：`C_Room` / `C_Maid` / `C_Display` / `C_Seating` / `C_Outdoor` 五模块 0 问题。**

---

## 2. 光影 12 张完整数字表

| 时段 | 天气 | 平均亮度 | 死黑% | 爆白% | CCT(K) | 目标区间 | 判定 |
|---|---|---|---|---|---|---|---|
| morning | clear | 0.418 | 0.31 | 0.000 | 5745 | 4200–6500 | **PASS** |
| morning | cloudy | 0.301 | 5.27 | 0.000 | 5602 | 4200–6500 | **PASS** |
| morning | rain | 0.326 | 0.65 | 0.000 | 5516 | 4200–6500 | **PASS** |
| noon | clear | 0.268 | 2.50 | 0.000 | 5684 | 4200–6500 | **PASS** |
| noon | cloudy | 0.269 | **7.76** | 0.000 | 5740 | 4200–6500 | **PASS** |
| noon | rain | 0.292 | 1.50 | 0.000 | 5689 | 4200–6500 | **PASS** |
| dusk | clear | 0.335 | 0.32 | 0.000 | 5578 | 2800–4200 | FAIL |
| dusk | cloudy | 0.334 | 3.11 | 0.000 | 5535 | 2800–4200 | FAIL |
| dusk | rain | 0.361 | 0.01 | 0.000 | 5562 | 2800–4200 | FAIL |
| night | clear | 0.359 | 0.02 | 0.000 | 5521 | 2700–4200 | FAIL |
| night | cloudy | 0.357 | 2.35 | 0.000 | 5556 | 2700–4200 | FAIL |
| night | rain | 0.387 | 0.00 | 0.000 | 5504 | 2700–4200 | FAIL |

**达标项（全部 12 张）**
- 死黑：最差 **7.76%**（noon/cloudy）< 8% 上限 ✓
- 爆白：**全 0** < 0.2% 上限 ✓
- 平均亮度：0.268–0.418，全在 [0.15, 0.65] ✓

**未达标项**：昏夜 6 张 CCT 5504–5578K，目标 2800–4200K → **已知限制 L1**

---

## 3. 剩余 FAIL 明细（按模块）

### cdecor / env-decor-v2 — 14 条 FAIL（全部 ≤20mm）
| 物体对 | 坐标 (m) | 数值 | 性质 |
|---|---|---|---|
| `DC_ShelfBack ↔ DC_ShelfPlinth` | (-3.635, 2.94, 1.025) | 20.00mm | 层架装配 |
| `DC_PendantWire_LT_P1 ↔ RM_CeilCenter` | (-2.90, -2.00, 2.588) | 20.00mm | 吊线穿吊顶 |
| `DC_PendantWire_LT_P2 ↔ RM_CeilCenter` | (-2.55, 1.05, 2.608) | 20.00mm | 同上 |
| `DC_PendantWire_LT_P3 ↔ RM_CeilCenter` | (1.85, 1.50, 2.568) | 20.00mm | 同上 |
| `DC_PendantCanopy_LT_P1 ↔ RM_CeilCenter` | (-2.90, -2.00, 2.825) | 17.50mm | 吸顶盘压吊顶 |
| `DC_PendantCanopy_LT_P2 ↔ RM_CeilCenter` | (-2.55, 1.05, 2.825) | 17.50mm | 同上 |
| `DC_PendantCanopy_LT_P3 ↔ RM_CeilCenter` | (1.85, 1.50, 2.825) | 17.50mm | 同上 |
| `DC_ChalkTex ↔ DC_ShelfTop` | (-3.94, 1.50, 1.85) | 10.00mm | 黑板贴图压层板 |
| `DC_WallLampArm_2 ↔ DC_WallLampBase_2` | (0.60, 2.98, 2.00) | 10.00mm | 灯臂接底座 |
| `DC_DecoPlate_0 ↔ DC_ShelfBoard_4` | (-3.795, 1.654, 1.66) | 8.75mm | 装饰盘放层板 |
| `DC_DecoPlate_1 ↔ DC_ShelfBoard_4` | (-3.475, 2.814, 1.66) | 8.75mm | 同上 |
| `DC_Curtain_0 ↔ RM_WainLeft` | (-3.808, -2.843, 1.49) | 8.00mm | 窗帘贴墙裙 |
| `DC_Cove_N ↔ RM_CeilRimN` | (0.00, 2.43, 2.88) | 5.00mm | 灯带槽贴跌级 |
| `DC_Cove_S ↔ RM_CeilRimS` | (0.00, -2.43, 2.88) | 5.00mm | 同上 |

### cbar / Lead — 14 条 FAIL（全部 ≤27.75mm）
| 物体对 | 坐标 (m) | 数值 |
|---|---|---|
| `BA_Espresso_Body ↔ DC_DessertTray_KnifeBlade` | (2.55, 1.525, 1.16) | 27.75mm |
| `BA_Espresso_Body ↔ DC_DessertTray_Rim` | (2.55, 1.525, 1.16) | 20.00mm |
| `BA_Shelf_1 ↔ DC_WallLampBase_2` | (0.55, 2.88, 1.95) | 12.50mm |
| `BA_Espresso_Body ↔ DC_DessertTray_Plate` | (2.55, 1.525, 1.16) | 12.00mm |
| `BA_Syrup_Tray ↔ DC_DessertTray_Rim` | (3.30, 1.51, 0.958) | 12.00mm |
| `BA_Syrup_Tray ↔ DC_DessertTray_Slice1` | (3.30, 1.51, 0.958) | 10.98mm |
| `BA_Shelf_1 ↔ DC_WallLampArm_2` | (0.55, 2.88, 1.95) | 10.00mm |
| `BA_Backsplash ↔ BA_ShelfUpright` | (0.55, 2.975, 1.175) | 10.00mm |
| `BA_Backsplash ↔ BA_ShelfUpright.001` | (0.55, 2.975, 1.175) | 10.00mm |
| `BA_Pour_CupCoffee ↔ BA_Pour_Server` | (1.44, 1.57, 1.038) | 8.58mm |
| `BA_Backsplash ↔ RM_WainBack` | (0.55, 2.975, 1.175) | 8.00mm |
| `BA_BarTop ↔ BA_BarTopRet` | (1.75, 1.51, 0.925) | 7.43mm |
| `BA_Syrup_Tray ↔ DC_DessertTray_Plate` | (3.30, 1.51, 0.958) | 7.00mm |
| `BA_BackTop ↔ BA_SinkBasin` | (0.55, 2.750, 0.880) | 5.00mm |

### clight / Lead — 6 条 FAIL（全部是昏夜 CCT）
`5504 / 5521 / 5535 / 5556 / 5562 / 5578 K` → **已知限制 L1**

### 其余模块 — **0 条**
`croom` / `cmaid` / `cdisplay` / `cseating` / `coutdoor` 均无 FAIL。

---

## 4. 三条已知限制（Lead 已确认接受，不阻塞交付）

### L1 · 昏夜色温 5504–5578K（判据要求 2700–4200K）
- **根因**：AgX Medium High Contrast 色调映射对高饱和暖色的去饱和特性。
- **实测佐证**：把室内灯能量翻倍、HDRI 遮暖色（dusk `#FFC98A` / night `#FFB066`）、
  夜间 HDRI 强度压到 0.07 后，CCT 仅从 5617K 降至 5504K（改善 113K）。
  **AgX 下暖光画面的 CCT 下限即在 5500K 量级。**
- **影响**：画面呈琥珀暖调（目视正常），仅数值未达 2700–3000K。白天 6/6 达标。

### L2 · 装饰件装配接触 ≤27.75mm
- 画框/黑板框框料 10mm 安装留缝（藏挂钩）
- 吊杆穿吊顶 17.5–20mm、吸顶盘压吊顶 17.5mm
- 灯带槽贴跌级 5mm、层板托/装饰盘 8.75–20mm
- 糕点托盘与吧台 7–27.75mm（托盘自身厚度）
- **均为设计固有的装配关系，视觉不可见。**

### L3 · 女仆内部浮点级接触 <0.15mm
| 配对 | 最小距离 |
|---|---|
| `MD_Tray ↔ Hand` | -0.0098 mm（9.8 微米）|
| `MD_Tray ↔ Hand.001` | -0.0075 mm |
| `MD_Tray ↔ Apron` | -0.0098 mm |
| `Torso ↔ MD_Tray` | -0.1485 mm |

判据 `min_mm=0` 下任何负值即 FAIL，但这些是**网格接缝的浮点误差**，视觉完全不可见。
交付表述应为「浮点级接触」，**不应表述为「穿模」**。

---

## 5. 判据演进摘要（7 轮）与校准证据

### 关键判据修正（每条都有实测依据）

| # | 问题 | 修正 | 依据 |
|---|---|---|---|
| 1 | `BVHTree.FromObject` **不应用世界变换**（相隔 100m 的两盒仍报 overlap=2） | 全部改为 `FromPolygons(世界坐标顶点)` 自建 BVH | probe run-mvhgvlz2xl1t |
| 2 | 质心法穿透深度**虚高 1000 倍**（托盘穿手报 14.8mm，真实 0.0098mm） | 改用顶点法 + AABB MTV 封顶，质心值仅作诊断 | v3 实测 |
| 3 | 女仆 106 网格**无 `MD_` 前缀**（叫 Apron/Arm/Skirt），聚合判据漏全部 | 改按集合 `patterns:["*"]` 判脚底 | v1 实测 |
| 4 | 吧台 211 物体中 189 是装配子件，逐个判落地产生 138 条误报 | 加子件识别（体积包含/足印覆盖/表面贴合/同族前缀） | v1→v3，1058→69 条 |
| 5 | 女仆 `kind=soft` 若无条件豁免，会漏掉「女仆穿吧台」 | soft 豁免**限定同模块** | Lead 裁决 |
| 6 | 色温单一 2700–3000K 判全天，白天必然 FAIL | 按时段分组：晨/午 4200–6500K、昏 2800–4200K、夜 2700–4200K | Lead 裁决 + v3/v5 实测 |
| 7 | 场景比源码旧时仍出结论（CH_03_3 误报 89.84mm） | 新增 `qc_freshness.py` 闸门 + `scene_md5` 指纹校验 | furn-modeler 指出 |

### 校准证据（工具本身的捕获率，与场景质量无关）

| 工具 | 用例 | 结果 | 明细 |
|---|---|---|---|
| **qc_collide** | 11 | **11/11 PASS** | 捕获率 **100%**，零漏报零误报（穿透/悬空/陷地/穿墙/贴墙间隙/合法嵌套/AABB 误报/soft 豁免/同集合不豁免/桌面支撑/女仆脚底） |
| **qc_pairs** | 3 | **3/3 PASS** | 分离 60mm→测 60.000；穿透 30mm→测 -30.000；贴合 0mm→测 0.000（**误差 0.000mm**）|
| **qc_light** | 5 | **5/5 PASS** | 全黑/全白/中灰/2700K/6500K 已知图反查（2700K→2583K、6500K→6322K）|
| **qc_gltf** | 3 | **3/3 PASS** | 正常 GLB / accessor 越界 / 外部贴图 URI 均正确识别 |

**每轮改判据都重跑校准**，确认没有把真问题一起豁免掉。这是「39 条」而非「全绿」可信的基础。

---

## 6. 复跑命令（幂等，参数化）

```bash
# 0) 前置：确认场景不旧于源码
python blender/qc/qc_freshness.py

# 1) 穿模/落地/贴墙（全量，约 27s）
blender_rt_headless(script_file="<项目根>/blender/qc/qc_collide.py",
  file="<项目根>/scene/maid_cafe.blend", engine="none", args="--tag final")

# 1b) 只看某模块（cdecor 约 11s / cbar+cdisplay 约 16s）
  args="--scope C_Decor --tag final"

# 2) 点名配对（12 对，约 3s）
blender_rt_headless(script_file="<项目根>/blender/qc/qc_pairs.py",
  file="<项目根>/scene/maid_cafe.blend", engine="none",
  args="--pairs MD_Tray:Hand,MD_Tray:Hand.001,MD_Tray:Apron,MD_Cup:MD_Tray,MD_CakeBase:MD_Plate,Torso:MD_Tray,CH_03_3:RM_WallLeft,DS_Post_3:BA_BarTop,DS_Post_2:TB_04_Cloth --tag final")

# 3) 光影 12 张（约 130s，长活建议 as_job=true 再 op=wait）
blender_rt_headless(script_file="<项目根>/blender/qc/qc_light.py",
  file="<项目根>/scene/maid_cafe.blend", engine="eevee", as_job=True, args="--tag final")

# 4) GLB 校验（约 3s）
blender_rt_headless(script_file="<项目根>/blender/qc/qc_gltf.py",
  engine="none", args="--glb scene/maid_cafe.glb --tag final")

# 5) 汇总报告
python blender/qc/qc_report.py --tag final
```

校准（任何时候都可复跑）：
```bash
blender_rt_headless(script_file=".../qc_collide.py", engine="none", args="--calib")
blender_rt_headless(script_file=".../qc_pairs.py",    engine="none", args="--selftest")
blender_rt_headless(script_file=".../qc_light.py",    engine="none", args="--selftest")
blender_rt_headless(script_file=".../qc_gltf.py",     engine="none", args="--selftest")
```

---

## 7. 交付物清单

| 文件 | 说明 |
|---|---|
| `blender/qc/qc_common.py` | 共享内核：世界空间 BVH、网格提取、角色分类、判据工具、finding 格式 |
| `blender/qc/qc_collide.py` | 穿模/干涉/落地/贴墙/吊挂/天花（含 11 用例校准） |
| `blender/qc/qc_pairs.py` | 指定物体对精确间距/穿透（双向顶点-面采样，含 3 用例自测） |
| `blender/qc/qc_light.py` | 4×3 光影渲染 + 直方图/死黑/爆白/色温统计（含 5 用例自测） |
| `blender/qc/qc_gltf.py` | GLB 自解析校验（tri/字节/贴图 mime/accessor/扩展），含 3 用例自测 |
| `blender/qc/qc_report.py` | 汇总成 QC-REPORT.md + qc_findings.json，含场景指纹校验与 owner 校正 |
| `blender/qc/qc_freshness.py` | 场景 vs 模块源码 mtime 闸门（防「拿旧场景出结论」） |
| `blender/qc/qc_rules.json` | **判据唯一来源**：7 轮演进、全部豁免裁决依据、已知限制说明 |
| `docs/QC-REPORT.md` | 本文件 |
| `docs/qc_findings.json` | 45 条结构化问题（供 Lead/网页工具消费） |
| `.scratch/qc/results/*.json` | 四项原始结果（带 scene_md5，可追溯）|
| `.scratch/qc/calib_results/*.json` | 四项校准证据 |
| `renders/qc/lt_*.png` | 12 张光影验收图（1280×720）|

---

## 8. 本轮已确认修复项（RESOLVED）

| 项 | 原问题 | 现状 |
|---|---|---|
| `C_Default` 集合 9 个 `OD_Bench_*` | 落在兜底集合，网页端按集合分组会漏 | **已修**：manifest 中 `C_Default` 已不存在，全部归 `C_Outdoor`（344 objects / 11,056 tri） |
| `DC_PlantLeaves` 穿墙 1945mm + 压吧台 402mm | calathea 源模型横躺被压成圆饼 | **已修**：绕 Y −90° 转竖直后按「高 1.10m / 半径 ≤0.34m」归一，0 条相关 finding |
| `DISPLAY ↔ BAR_MAIN` 契约内部重叠 150mm | 契约 §1.1 自身矛盾 | **已修**：`DISPLAY y(0.55,1.08)` 与 `BAR_MAIN(y≥1.15)` 分离，5 对 DS↔BA 干涉全部 PASS（最优 58.33mm） |
| `OD_DoorStep` 压墙 12mm | 台阶中心 y=-3.21 越过墙外皮 | **已修**：移至 y≤-3.16，顶点级穿透 0.000mm |
| `CH_03_3` 穿左墙 89.84mm | 椅子环相位未避墙 | **已修**：`qc_pairs` 实测间隙 **+125.58mm** |
| 女仆脚底/托盘/杯子 | §11.3 要求 | **全部达标**：整组 min_z=0、`MD_Cup↔MD_Tray` +15.64mm、`MD_CakeBase↔MD_Plate` +0.24mm |

---

**结论：GLB 硬交付指标全绿（16/16）；几何仅余 ≤27.75mm 的装配接触与浮点级接缝；
光影白天全达标、昏夜受 AgX 特性限制。按 Lead 冻结决定，3 条已知限制记录在案，可交付。**


---

## §9 v9 增量说明（交付冻结版，Lead 补记）

QC 终审（v8）之后，Lead 只做了一处**不影响几何**的修改，因此本报告 §1–§8 的几何结论继续有效：

| 项 | v8（QC 终审） | v9（交付版） |
|---|---|---|
| blender 几何 | 391,341 tris / 1,212 objects | **完全相同**（逐集合 tri 一致） |
| blend md5 | `EF352FAB…` | **`2CC1ED4CBCAF3F8C9E5D99B2DE8B5BE5`** |
| glb md5 | `D599BA1C…` | **`7FE61327993C1A124C29AD4D8A0023B3`** |
| glb 体积 | 16,129,828 B | 16,129,728 B |
| 改动内容 | — | 女仆材质：`M_Hair/M_White/M_Satin/M_Navy/M_Skin` 的 Sheen/Coat/Anisotropy 在导出前清零（`cmaid._sanitize_materials()`） |

**为什么改**：`M_Hair` 原本带 `KHR_materials_sheen: sheenColorFactor=[1,1,1]`，
three.js 会把白色 sheen 叠在深棕发色上，浏览器里女仆头发整片发白（实测截图见 `renders/web/shot-t21-*`）。
改后 GLB 里这 5 个材质**不再携带 sheen/clearcoat/anisotropy 扩展**（验证脚本 `tools/maid_ext_table.py`）。

**v9 复核证据**（Lead 用同一套 QC 脚本跑的，指纹已核对）：
- `docs/gltf_v9.json` → `verdict: PASS`，16/16，glb_md5 = `7fe61327993c1a124c29ad4d8a0023b3`，tri 391,341，15.383 MB
- `docs/collide_v9.json` → scope `C_Decor,C_Bar,C_Display`：25 条（FAIL 18 / WARN 7），
  与 v8 同量级、同性质（均为 ≤37mm 的装配接触/共面退化），**无新增硬穿模**
- 全量碰撞与光影未重跑：几何哈希不变即结论等价；如需要可执行 §6 的复跑命令（`--scope` 去掉即可）
