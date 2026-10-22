# 女仆咖啡馆项目 · 施工契约（CONTRACT）

> 本文件是**唯一口径**。所有队员的模块/页面必须按下表实现；有异议先找 Lead 改契约，不要各自发明。
> 最后更新：Lead @ 2026-10-21

## 0. 目录与写入范围（严格不越界）

```
<项目根>/
├─ CONTRACT.md              # 本文件（只读，Lead 维护）
├─ index.html               # web-dev
├─ css\style.css            # web-dev
├─ js\app.js                # web-dev（主入口 module）
├─ js\scene.js              # web-dev（GLB 加载/相机/碰撞/粒子）
├─ js\weather.js            # web-dev（时间/天气/灯光过渡）
├─ js\audio.js              # audio-dev（音频引擎，接口见 §9）
├─ blender\
│  ├─ cprop.py              # Lead（尺寸/配色/锚点唯一数值源）
│  ├─ ccore.py              # Lead（基元/材质工具/集合/导出工具）
│  ├─ cmat.py               # Lead（PBR 材质工厂：贴图 + 程序化兜底）
│  ├─ croom.py              # Lead（地面/墙/窗/门/墙裙/天花）
│  ├─ cbar.py               # Lead（L 台/后吧/设备/杯架/冰箱）
│  ├─ cdisplay.py           # prop-modeler
│  ├─ cseating.py           # prop-modeler
│  ├─ cdecor.py             # prop-modeler
│  ├─ coutdoor.py           # env-modeler
│  ├─ clight.py             # Lead（4 时段 + 天气灯光预设，供 QC 渲染与场景清单）
│  ├─ cmaid.py              # Lead（女仆导入/减面/托盘/蛋糕/咖啡/补光）
│  ├─ cbuild.py             # Lead（总装配 + 存 .blend + 导出 GLB + scene_manifest.json）
│  └─ qc\*.py               # qc-inspector（体检脚本，只读场景不改几何）
├─ renders\                 # 出图（各模块预览 + 终检）
├─ assets\
│  ├─ tex\  generated\  models\<id>\  hdri\  audio\   # asset-scout / audio-dev
│  └─ MANIFEST.md
└─ docs\                    # Lead：验收报告 / 使用说明
```

**写入范围硬约束**：每人只写自己名下的文件。`.blend` 成品与 `scene_manifest.json` 只由 Lead 的 cbuild.py 产出。
**临时目录**：一律 `<项目根>/.scratch/<任务名>/`；严禁写 `<用户目录>` 与 `%TEMP%`；收工前清空自己的 scratch。

## 1. 坐标系与空间（**硬性，不可改**）

- +Z 向上；单位米。**室内地面 z = 0**。室内范围 `x ∈ [-4.0, 4.0]`、`y ∈ [-3.0, 3.0]`、层高 `z = 3.0`。
- **街道侧 = −Y**（大玻璃窗 + 大门在此面）；**后吧台墙 = +Y**；左墙 `x=-4`（书架/黑板），右墙 `x=+4`（相框/墙灯）。
- 墙厚 0.16，向室外方向伸出（室内净尺寸不变）。
- 角色默认朝向 **−Y**（导入后被摆放旋转，见 §7）。
- 家具建模时，物体原点尽量放在**其自身的功能基准点**：桌面类原点在桌面中心（z=桌面高）；落地类原点在底面前中；挂墙类原点在墙面挂点。旋转/缩放必须在导出前 apply。

### 1.1 功能锚点（全项目共用，写在 cprop.py 里，模块内引用常量，禁止硬编码）

| 名称 | 值 | 说明 |
|---|---|---|
| `ROOM_X` | `(-4.0, 4.0)` | 室内 x 范围 |
| `ROOM_Y` | `(-3.0, 3.0)` | 室内 y 范围 |
| `CEIL_Z` | `3.0` | 天花高 |
| `WALL_T` | `0.16` | 墙厚 |
| `WIN_OPEN` | x `(-3.70, 0.35)`, z `(0.72, 2.58)` | 前墙大玻璃窗洞口 |
| `DOOR_OPEN` | x `(1.15, 2.45)`, z `(0.0, 2.20)` | 入户玻璃门洞口 |
| `WAINSCOT_Z` | `0.95` | 墙裙/腰线上沿 |
| `BAR_MAIN` | x `(-0.20, 3.70)`, y `(1.15, 1.87)`, top z `0.95` | L 吧台主段（台面厚 0.05） |
| `BAR_RETURN` | x `(2.98, 3.70)`, y `(1.15, 2.95)` | L 吧台回折段 |
| `BAR_BACK` | x `(-1.60, 2.70)`, y `(2.55, 2.95)`, top z `0.90` | 后操作台（水槽） |
| `BAR_SHELF` | x `(-1.60, 2.70)`, y `(2.78, 2.98)`, z `1.45 / 1.95 / 2.45` | 后吧层架 |
| `CUP_RAIL` | x `(0.00, 2.60)`, y `2.72`, z `1.32` | 倒挂杯架 |
| `ESPRESSO` | x `(2.15, 2.95)`, y `(1.30, 1.75)`, z `0.95 → 1.50` | 意式咖啡机占地 |
| `GRINDER` | x `(1.72, 2.06)`, y `(1.34, 1.66)` | 磨豆机 |
| `POUR_OVER` | x `(1.10, 1.66)`, y `(1.38, 1.72)` | 手冲台 |
| `SYRUP` | x `(3.02, 3.58)`, y `(1.30, 1.72)` | 糖浆瓶组 |
| `REGISTER` | x `(-0.08, 0.42)`, y `(1.42, 1.82)` | 收银机 |
| `DISPLAY` | x `(-1.60, -0.05)`, y `(1.25, 1.95)`, z `0 → 1.38` | 甜品展示柜（面朝 −Y） |
| `TABLE_R` | `0.38` | 圆桌半径 |
| `TABLE_H` | `0.74` | 桌面高 |
| `TABLES` | `(-2.95,-2.05) (-1.05,-2.10) (-3.25,0.55) (-2.55,1.95) (2.95,-1.70)` | 5 组圆桌中心 |
| `STOOLS` | `(0.55,0.82) (1.70,0.82)` | 吧台凳（面朝 +Y） |
| `BOOKSHELF` | x `(-3.95,-3.35)`, y `(1.60,2.95)`, z `0 → 2.05` | 左后角书架 |
| `CHALKBOARD` | 左墙 `x=-3.92`, y `(0.90, 2.10)`, z `(1.25, 2.45)` | 黑板菜单挂墙 |
| `FRAMES_RIGHT` | 右墙 `x=3.92`, y `(-1.30,-0.10)` / `(0.15,1.05)` | 相框 |
| `PENDANTS` | `(-2.90,-2.00) (-2.55,1.05) (1.85,1.50)` | 吊灯（灯罩底 z≈2.22） |
| `WALL_LAMPS` | 左墙 `y=-2.35`；右墙 `y=-2.05`；后墙 `x=0.60` | 壁灯，z≈1.95 |
| `MAID_POS` | `(-1.70, 0.30)`, 绕 Z 旋转 `+48°` | 女仆站位与朝向（面朝大门方向） |
| `CAM_DEFAULT` | pos `(1.85, -2.55, 1.55)`, target `(-1.20, 0.50, 1.05)` | 网页默认机位（从门口斜望） |
| `STREET` | 人行道 y `(-4.60,-3.0)`；马路 y `(-9.0,-5.2)`；对面建筑 y `(-14.0,-9.6)` | 室外低模 |

> 任何模块需要新占地，先在本表登记（找 Lead），别私自挤占别人的空间。

## 2. 命名规范

- **集合**：`C_Room` `C_Bar` `C_Seating` `C_Display` `C_Decor` `C_Outdoor` `C_Maid` `C_Light` `C_QC`
- **物体名**：`RM_xx`（建筑）、`BA_xx`（吧台设备）、`DS_xx`（展示柜）、`TB_xx`/`CH_xx`（桌椅）、`DC_xx`（装饰）、`OD_xx`（室外）、`MD_xx`（女仆）、`LT_xx`（灯，仅 Blender QC 用，不导出）。
- **材质名**：`MAT_<类别>_<名>`，类别 ∈ `Wood Marble Metal Glass Fabric Leather Ceramic Paint Plastic Emissive Paper Plant Liquid Chalk`。同一材质全场景复用（不要每件新建）。
- **贴图路径约定**：`assets/tex/<polyhaven_id>_<map>_<res>.jpg`，map ∈ `diff nor_gl arm rough disp`；文字/自绘贴图在 `assets/tex/generated/`。

## 3. 模块接口（每个 .py 都必须满足）

```python
MODULE = "cseating"          # 模块名
OWNER  = "prop-modeler"
TRI_BUDGET = 45000           # 本模块三角面上限

def build(P, C, M, assets):
    """P=cprop, C=ccore, M=cmat(材质工厂), assets=dict(贴图/模型路径解析器)
    必须：只在集合 C_Seating 内建物体；返回 dict:
      {"objects":[...], "collections":["C_Seating"],
       "colliders":[{"name":"TB_01","aabb":[min3,max3],"kind":"solid|soft"}],
       "anchors":{"table_01": (x,y,z)},
       "notes":"..."}
    必须幂等：重复调用不产生重名物体（用 C.wipe_collection("C_Seating") 先清）。
    """

# 独立自检：直接 `blender -b -P cseating.py` 时，构建本模块 + 简易三点光 + 相机，
# 渲染 2 张 800x600 预览到 renders/modules/cseating_front.png / _persp.png（EEVEE, 32 samples）
```

- 只允许 `bpy / bmesh / math / mathutils / random / json / os`，**不得**联网、不得依赖 numpy。
- 所有随机必须 `random.seed(固定值)`，保证可复现。
- 面数：默认按「视觉可辨」够用即止；圆角/倒角用 `bevel` 修改器或 bmesh 倒角，段数 ≤3。圆柱段数 ≤24（近景主件 ≤48）。
- **禁止**导出前留修改器；`cbuild.py` 会统一 apply，但模块自检也请 apply。
- 物体不要重叠摆放：模块提供 `colliders`（世界 AABB），QC 用它查干涉。

## 4. 视觉规范（配色）

| 用途 | HEX | 材质 |
|---|---|---|
| 奶油墙面 | `#F2E6D6` | `MAT_Paint_Cream`（rough .85） |
| 原木色（墙裙/家具） | `#B98A5E`～`#8B5E3C` | `MAT_Wood_Oak` / `MAT_Wood_Walnut`（贴图） |
| 地板人字拼 | `#C8A277` | `MAT_Wood_Herringbone`（贴图 2k，UV 平铺 2m/重复） |
| 吧台面大理石 | `#EFEAE3` 带灰纹 | `MAT_Marble_Top` |
| 海军蓝（女仆裙） | `#1E2B4D` | 角色自带 M_Navy |
| 蕾丝/桌布/围裙 | `#FFFDF8` | `MAT_Fabric_Lace`（半透 alpha .85 / sheen） |
| 黄铜/暖金属 | `#C9A227` | `MAT_Metal_Brass` |
| 玻璃 | 透射 | `MAT_Glass_Clear`（transmission .95, rough .05） |
| 灯罩发光 | `#FFD9A0` | `MAT_Emissive_Shade`（Emission 3.0，暖白） |
| 室内主暖光色温 | 2700–3000K | `#FFC98A`（暖）/ `#FFB86B`（更暖） |

## 5. 三角面预算（导出 GLB 时的硬上限）

| 区块 | 上限 tri |
|---|---|
| C_Room | 60k |
| C_Bar | 70k |
| C_Display | 40k |
| C_Seating | 70k |
| C_Decor | 60k |
| C_Outdoor | 35k |
| C_Maid（减面后） | 260k |
| **合计** | **< 500k（目标 420k 以内）** |

## 6. 材质与贴图（M 工厂）

`cmat.py` 暴露：`M.get("MAT_Wood_Oak")`、`M.pbr(name, diff=..., nor=..., arm=..., rough=..., scale=..., metal=..., alpha=..., emit=...)`。
**贴图缺失必须自动降级**为程序化纯色/噪声（不准报错崩溃）。贴图按 §2 路径查找，找不到就打印 `WARN missing tex` 并用 fallback。
`assets` 由 `cbuild.py` 传入：`assets.model("WoodenTable_01")` → 已导入对象的集合名前缀；`assets.tex("herringbone_parquet","diff")` → 绝对路径或 None。

## 7. 女仆改造要求（cmaid.py，Lead）

- 导入 `<女仆源模型>/procedural_v2/chibi_maid_USER.blend` 的 68 个网格（按集合 01_Head…06_Details 保留层级），**整体缩放 1.30**，使身高 ≈1.33 m（Q 版比例，站在真人尺度咖啡馆里是「小手办大场景」的可爱感；网格 1.02 m 原高过矮）。
- 减面：用 Decimate(Collapse) 把总量从 1.33M 降到 ~250k；头部/脸部/眼睛保证不被削成多边形，眼睛相关物体单独限制比值。
- 姿态：原模型手臂下垂 → 通过绕肩点旋转左右上臂，使**双手在身前捧托盘**；如几何无法自然弯曲，采用「单手抬臂 + 托盘靠在掌上」方案，并确保袖口/裙摆无穿模。托盘（`MD_Tray`）位于双手上方 z≈0.86，直径 0.30。
- 托盘上：`MD_Cake`（草莓小蛋糕，纸盘盛）+ `MD_Cup`（白瓷杯碟）+ `MD_Steam`（半透明蒸汽面片，网页可动画）。
- 角色面向大门；额外给她一盏 `LT_MaidFill`（面光 3000K，柔和，强度以不爆脸为准），仅供 Blender QC。

## 8. GLB 导出与场景清单（cbuild.py）

- 导出：选中 `C_Room C_Bar C_Display C_Seating C_Decor C_Outdoor C_Maid`，`export_format='GLB'`，apply modifiers，+Y up（默认），贴图内嵌（JPEG 质量 80，法线/alpha 用 PNG），`export_lights=False`（网页自己打灯），`export_cameras=False`。
- 目标：`<项目根>/scene/maid_cafe.glb`，**< 40 MB**，tri < 500k。
- 同时产出 `<项目根>/scene/scene_manifest.json`：
  ```json
  {"room":{"x":[-4,4],"y":[-3,3],"z":[0,3],"wall_t":0.16},
   "anchors":{"cam_default":{"pos":[...],"target":[...]}, "maid_pos":[...], ...},
   "colliders":[{"name":"...","aabb":[[..],[..]],"kind":"solid"}],
   "light_rig":{"phases":{...},"weather":{...}},
   "fx_nodes":{"window_glass_material":"MAT_Glass_Window","steam_node":"MD_Steam","lamp_materials":["MAT_Emissive_Shade"]},
   "material_names":[...], "counts":{"tri":123456,"objects":456}}
  ```
  网页**只依赖这个清单**做碰撞、灯光、特效，不猜物体名。

## 9. 音频接口（audio-dev 交付 js/audio.js）

```js
import { AudioEngine } from './js/audio.js';
const audio = new AudioEngine('/assets/audio/');
await audio.init();                       // 首次用户手势后 resume
audio.setMasterVolume(0..1);
audio.setTimePhase('morning'|'noon'|'dusk'|'night', {fadeMs:1200});
audio.setWeather('clear'|'cloudy'|'rain_light'|'rain_med'|'rain_heavy'|'storm', {fadeMs:1500});
audio.playOnce('sfx_cup_clink');
audio.notifyLightning();                  // 内部按 manifest 延迟播雷
audio.startEventScheduler();              // 随机事件（雷阵雨 3–10s 打闪电）
audio.on('lightning', cb);                // 回调：网页做白光爆闪 + 光强脉冲
audio.setPaused(bool);
```
`assets/audio/manifest.json` 结构见 audio-dev 交付说明。

## 10. 网页规范（web-dev）

- 纯静态：`index.html` + ES module；**不依赖 CDN**（本机 cdn.jsdelivr 不通），Three.js 用 `js/vendor/three.module.js` 本地文件（从 npm 包解出，见 `tools/`）。
- 交互：OrbitControls（旋转/缩放/平移）、默认机位来自 manifest、限制不穿墙（用 colliders 做简单 AABB 推挤 + 房间包围盒钳制）、时间条（4 档 + 24h 显示）、天气按钮组（晴天/多云/雨天→小/中/大/雷阵雨）、右上角总音量滑块、UI 奶油色圆角卡片 + 暖咖色文字 + 圆润字体（系统字体栈）。
- 时间过渡 1–2s 平滑（灯光强度/颜色/Sun 角度/天空/雾），天气过渡同步（粒子密度、雾、窗玻璃贴图透明度、路面反光、闪电）。
- 性能：粒子实例化 + 距离剔除 + 上限；`renderer.setPixelRatio(min(dpr,2))`；GLB 加载显示进度条。
- 必须能在 `python -m http.server` 下直接跑；无 404、无 console 报错。

## 11. QC 门（穿模 / 光影 / 合规）

1. **干涉**：模块 colliders 两两 AABB 检查，重叠 > 5mm 报 FAIL（椅子可插入桌下除外，用 `kind:"soft"` 声明）；静态物体不得插进墙体。
2. **落地/贴合**：所有落地物 `min_z ∈ [-2mm, +2mm]`；挂墙物与墙间隙 ∈ [0, 6mm]；吊灯/纱帘不得穿天花。
3. **女仆**：脚底 z=0；托盘与手掌接触不穿；蛋糕/杯子在托盘内；裙摆不穿桌/柜。
4. **光影**：4 时段 × 晴/多云/雨 各渲 1 张 1280×720；不得有纯黑死区（除阴影）、不得过曝（高光 <0.2% 面积爆白）、色温一致（室内 2700–3000K）。
5. **GLB**：`blender_rt_plan(op="gltf_validate")` 通过；tri/bytes 达标；three.js 里 60 个随机机位无穿墙、无黑屏。
6. **网页**：无 console 报错；时间/天气/音量三控件都生效；雨/闪电/雷声时序正确。

## 12. 协作纪律

- 改契约先发消息给 lead；**不要直接改别人文件**（哪怕看到 bug，报告给 Lead）。
- 每完成一个阶段发一条短消息给 lead：做了什么 / 路径 / 自检数字 / 阻塞。
- 渲染预览统一用 **blender_rt_headless**（独立进程，勿用 rt_do/rt_see/rt_loop，那是 Lead 的 GUI 通道）。并发渲染 ≤2 个进程。
- 一切“看起来像”不算验收：用数字（面数/间隙/占比）说话。
