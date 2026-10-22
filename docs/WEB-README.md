# 日式女仆咖啡馆 · 网页端使用说明

> 项目根：`<项目根>`　作者：web-dev　最后更新：2026-10-21
> 纯静态、零构建、零 CDN。Three.js 从 npm 包解出放在 `js/vendor/`。

---

## 1. 怎么跑起来

### 1.1 最简：Python 自带 http.server

```powershell
cd <项目根>
python -m http.server 7800
# 浏览器打开 http://127.0.0.1:7800/index.html
```

### 1.2 推荐：项目自带零依赖静态服务器（会自动挑空闲端口，输出 READY 行）

```powershell
node <项目根>/tools/web/serve.mjs
# 输出：READY http://127.0.0.1:7800
# 输出：ROOT  <项目根>
```

指定端口：`node tools/web/serve.mjs --port 8080`；详细日志：`--verbose`。

> **必须走 HTTP**：页面是 ES module + `fetch()` 读 manifest，直接双击 `index.html`（`file://`）会被浏览器 CORS 拦掉。

### 1.3 首屏

打开后先看到「点击进入」遮罩 —— 这是浏览器自动播放策略的要求：**必须先有用户手势**才能创建/恢复 AudioContext。点「点击进入」后才会 `audio.init()`（`js/audio.js` 未就绪时静默降级，场景与全部交互照常工作，右上角显示「音频模块未就绪」）。

---

## 2. 交互说明

| 控件 | 位置 | 行为 |
|---|---|---|
| **时间滑块** | 左下 | 0–24h，步进 0.25。拖动时光照/天空/雾/室内灯**阻尼插值**（约 1.5s 平滑到位），不跳变。标签显示「清晨 07:00」这类档位名。松手 260ms 后调 `audio.setTimePhase()`。 |
| **天气按钮** | 左中 | 一级：晴天 / 多云 / 雨天。点「雨天」展开二级：小雨 / 中雨 / 大雨 / 雷阵雨。切换 1.5s 过渡，并调 `audio.setWeather()`。 |
| **音量滑块** | 右上 | 0–100%。**0 时调用 `audio.setMasterVolume(0)`**，不会 suspend/mute 整个 AudioContext。 |
| **默认机位** | 右上 | 回到 manifest 的 `anchors.cam_default`（带自动避障，见 §4）。 |
| **3D 视口** | 全屏 | 左键拖动旋转 / 滚轮缩放 / 右键平移。相机有 AABB 碰撞与房间钳制，出不了墙。 |

### 键盘快捷键
- `R`：复位相机
- `1` / `2` / `3` / `4`：晴天 / 多云 / 中雨 / 雷阵雨
- 时间滑块聚焦时 `←` `→`：±0.25h

### 雷阵雨
进入雷阵雨后，每 **3–10 秒**随机一次闪电：
1. 先 `audio.notifyLightning()`（雷声由 audio 内部按 manifest 延迟）；
2. 页面同步做**天空瞬时白光爆闪**（全屏 Sprite overlay）+ `DirectionalLight` 强度脉冲 + 路灯闪烁；
3. 同时监听 `audio.on('lightning')` 做二次同步（两条触发源都不漏）。

---

## 3. URL 参数（便于验收 / 直接定位状态）

| 参数 | 例 | 说明 |
|---|---|---|
| `hour` | `?hour=21.5` | 初始时间（0–24） |
| `weather` | `?weather=rain_med` | 初始天气：`clear` `cloudy` `rain_light` `rain_med` `rain_heavy` `storm` |
| `debug` | `?debug=1` | 显示右上角调试面板（fps / tri / drawcall / sun / exp / fog），并显示「模型未就绪」标签 |

例：`http://127.0.0.1:7800/index.html?hour=18&weather=storm&debug=1`

### 控制台调试句柄 `window.__CAFE__`
```js
__CAFE__.snapshot()                          // 全部状态快照（灯光数字、渲染数字、错误数）
__CAFE__.setState({hour: 12.5, weather:'rain_med'})
__CAFE__.matrix()                             // 4 时段 × 6 天气 = 24 组全部跑一遍，返回每组的太阳强度/曝光/雾
__CAFE__.triggerLightning()                   // 手动触发一次闪电视觉
__CAFE__.weather.info()                       // 当前灯光系统数字
__CAFE__.scene.stats()                        // renderer.info + GLB 加载耗时 + 预检结果
__CAFE__.scene.cameraDiagnostics()            // 相机位置 / 目标 / 视线遮挡检测 / 是否在房间内
__CAFE__.weather.overrides = { hemi: 0.4, ambient: 0.5, lampMul: 0.45, exposure: 0.7 }  // 运行时调参（只影响当前会话）
```

---

## 4. 关键实现（便于后续接手）

### 4.1 坐标口径
CONTRACT 全部是 **Blender z-up**；glTF 导出后是 **Y-up**。转换规则：
```
three.x = bx    three.y = bz    three.z = -by
```
所以房间在 three 空间是 `x∈[-4,4] y∈[0,3] z∈[-3,3]`，**街道/大玻璃窗在 three.z = +3 面**。`js/scene.js` 的 `toThree()` / `aabbToThree()` 负责转换，对外仍用 CONTRACT 数字。

### 4.2 依赖注入（不猜名字）
`scene_manifest.json` 提供：`room`、`anchors`（cam_default / win / door / maid_pos / street…）、`colliders`、`light_rig`（phases / weather / anchors / no_shadow_objects / lit_window_objects / hdri）、`fx_nodes`、`counts`。
manifest 缺失时全部退回 `js/scene.js` / `js/weather.js` 顶部的 `DEFAULT_*` 常量（数值即 CONTRACT §1.1 / §8）。

`js/weather.js` 的 `resolveLightData()` 支持 **两种 manifest 光照写法**并自动识别：
- 「Blender 量纲」：`sun_rot` / `sun_energy` / `sun_color` / `sky` / `ambient` / `exposure` / `indoor` / `fog`（cbuild/clight 实际产出）
- 「网页量纲」：直接给 `sunIntensity` / `skyTop` 等字段

### 4.3 光照（`js/weather.js`）
- **主光**：`DirectionalLight`（shadowMapSize 2048，shadow camera ±8.5m，覆盖室内 + 窗外街道近景）
- **天光**：`HemisphereLight`（sky=时段天空色，ground=暖木色 `#B98A5E` —— 天花板靠它反照）+ `AmbientLight`（暖白 `#FFF0E0`）
- **窗光**：`DirectionalLight` 从街道方向射入（不投影）+ 窗内侧 `RectAreaLight`（3.7×1.86m，朝室内，需 `RectAreaLightUniformsLib.init()`）
- **室内**：`PointLight` ≤6（吊灯 + 壁灯，`distance`/`decay` 取自 manifest，**带距离衰减**）+ 吧台/展示柜 `SpotLight` + 女仆补光 `PointLight`
- **色调映射**：`ACESFilmicToneMapping`、`outputColorSpace = SRGBColorSpace`、r160 物理光照单位（不再设 `useLegacyLights`，r155 起已移除）
- **天空**：程序化 ShaderMaterial 穹顶（`uTop`/`uHorizon`/`uStars` 连续可调，夜景才真是深蓝、雨天才是灰云）
- **HDRI**：4 张 1k `.hdr`（morning/noon/dusk/night），`RGBELoader` + `PMREMGenerator` → **只给 `scene.environment`（IBL）**。
  > ⚠ three r160 **没有** `scene.environmentIntensity` / `scene.backgroundIntensity`（实测 `in` 判断为 false），所以强度靠逐材质 `envMapIntensity` 缩放；可见天空仍用程序化穹顶，否则夜里窗外会亮白。

### 4.4 天气（6 态）
`clear / cloudy / rain_light / rain_med / rain_heavy / storm`。过渡 1.5s 阻尼插值：太阳强度/色温、半球光、环境光、曝光、雾密度与颜色、室内灯强度、窗上水帘不透明度、材质湿滑度。

**雨**：`THREE.Points` + 自定义 `ShaderMaterial`（竖直速度 + 风偏移 + 距离衰减 alpha）。粒子数按档位 **3000 / 6000 / 12000**（`RAIN_MAX`）。雨柱跟随相机，但整柱平移到窗外街道，**室内那半在 vertex shader 里按房间盒裁掉**（`uRoomMin/uRoomMax`，`vAlpha=0`）—— 从窗里看出去正好是「窗外在下雨」，室内一滴不落。
**水花**：地面圆环 sprite 池（420，CPU 驱动，扩散 + 淡出）。
**闪电**：全屏 Sprite 白光 overlay + 光源强度脉冲，衰减系数 6.5/s。

### 4.5 相机 / 防穿墙
- `OrbitControls`，`minDistance 0.45 / maxDistance 6.2`，极角 8°–86°
- **房间盒钳制**：`x∈[-3.9,3.9] y∈[0.25,2.85] z∈[-2.9,2.9]`（three 空间）
- **AABB 推挤**：球半径 0.25，对 manifest `colliders`（当前 125 个）取最小穿透轴推出，两轮迭代，最后再钳一次房间盒
- **OrbitControls target** 也限制在房间内
- **自动避障**：`resetCamera()` 依次试 4 个候选机位，用射线检测「相机→目标 0.55m 内无遮挡」取第一个通过的（manifest 的 cam_default 在本工程里正好卡在门洞，实测会被两片门叶切开）
- **近距淡出**：相机 1.35m 内的小件按**包围盒最近点距离**渐隐（门叶/吧台不会糊屏），墙/天花级大件（对角线 > 6.5m）不动

### 4.6 GLB 加载（含预检修补）
`loadGLB()` 不直接 `loader.load()`，而是先 `fetch` → **预检 GLB JSON chunk** → 再 `loader.parse()`。预检会找出「**空 texture 槽**」（既无 `source` 也无 `EXT_texture_webp.source` 的 `textures[i]`）——这类槽会让 `GLTFLoader` 在 `assignTexture` 时抛 `undefined.uri` 并**整包失败**。发现后把坏槽指向内嵌的 1×1 占位 PNG，重拼 GLB 再解析。

> 这个容错是为 v3 GLB 的 `textures[22]`（`carrot_cake` 的 mask 贴图 WebP 保存失败留下的空槽）加的。v5 冻结版已无此问题，容错保留作为双保险。

GLB 加载失败时**降级为占位场景**（墙体/吧台/圆桌/女仆胶囊全部程序化生成，按 CONTRACT 尺寸），并在左上角显示「模型未就绪 · 占位场景」，全部交互照常可用。

加载后处理：
- manifest `light_rig.no_shadow_objects` 里的 29 个玻璃物体 → `castShadow = false`（否则玻璃投影把室内糊黑）
- `COLOR_0` 顶点色（17 个 primitive，女仆皮肤/头发/虹膜）→ 保持 `vertexColors = true`，不覆盖
- 对街 `OD_WindowLit_*`（64 个）→ 只在黄昏/夜晚显示，白天 `visible = false`（否则白得发假）
- GLB 自带 `OD_SkyDome`（80m 双面球，会把相机包住、内壁挡住整个画面）→ **隐藏**，天空交给程序化穹顶
- 女仆浅色材质（`M_Skin/M_Hair/M_Iris/M_White/M_Satin/M_Sclera`）→ 压低 `sheen` / `clearcoat` / `envMapIntensity`（`MeshPhysicalMaterial` 在强环境光下会整体泛白）

### 4.7 性能
- `setPixelRatio(Math.min(devicePixelRatio, 2))`
- 雨粒子一次分配 12000，靠 `setDrawRange` 控密度；距离剔除在 shader 里
- 阴影只用主方向光（点光/射灯/面光全部 `castShadow = false`）
- `?debug=1` 看实时 fps / tri / drawcall / points

---

## 5. 工具脚本（`tools/web/`）

全部是 Node ESM 脚本，零第三方依赖（除验收脚本需要 `puppeteer-core`+`pngjs`，装到 `.scratch/webtools/`）。

| 脚本 | 用途 |
|---|---|
| `prepare-vendor.mjs` | 从 npm 包的 three@0.160.0 解出 `three.module.js` / `OrbitControls.js` / `GLTFLoader.js` / `BufferGeometryUtils.js` / `RGBELoader.js` / `RectAreaLightUniformsLib.js` 到 `js/vendor/`，并把裸说明符 `from 'three'` 改写成 `from './three.module.js'` |
| `serve.mjs` | 零依赖静态服务器，自动挑 7800–7899 空闲端口，输出 `READY http://127.0.0.1:<port>` |
| `start-headless-edge.mjs` | 拉起固定调试端口的无头 Edge（`--headless=new --remote-debugging-port=9333`），供 puppeteer `connect` |
| `check-glb.mjs` | **GLB 结构体检**（不依赖 Blender）：容器/chunk、`extensionsRequired` 支持表、texture→source 完整性、image→bufferView、material 贴图索引越界、tri/材质/贴图统计。可检出本次的「空 texture 槽」事故 |
| `verify.mjs` | 无头验收（console/pageerror/像素方差/滑块/天气/24 组矩阵/相机钳制/截图） |
| `final-shots.mjs` | 验收出图（4 时段 + 雨天 + 雷阵雨 + 朝窗机位） |
| `probe-final.mjs` | 诊断：机位遮挡射线、女仆材质参数、灯光实际值 |
| `sweep-light.mjs` / `ablate.mjs` | 光照参数扫描 / A-B 消融（用 `__CAFE__.weather.overrides`） |

### vendor 重建
```powershell
cd <项目根>/.scratch/webtools      # 任意临时目录
npm i three@0.160.0
node <项目根>/tools/web/prepare-vendor.mjs
```
脚本会自检 vendor 目录里没有残留裸 `'three'` 说明符。

### GLB 体检
```powershell
node <项目根>/tools/web/check-glb.mjs
# PASS ✓ / FAIL + 逐条错误原因；--json 出机器可读结果
```

### 无头验收（本机特有坑）
DSH 沙箱内**直接 spawn `msedge.exe` 会 FATAL（mojo 0x5 拒绝访问）**，`puppeteer.launch()` 也会 `spawn EPERM`。可行路径：
1. 用 **Blender 无头进程**（沙箱外）当启动器拉起 Edge，或用 `start-headless-edge.mjs`（需要在沙箱外执行）；
2. `puppeteer.connect({ browserURL: 'http://127.0.0.1:9333' })` 连上去；
3. 全部临时产物（profile / tmp / 日志）必须落在 `.scratch/` 下，**收工前删干净**。

---

## 6. 已验证的数字（v5 冻结版 GLB）

GLB 指纹：`md5 D599BA1C0CE14384EA926E758F1626E7` / 15.38 MB / 391,341 tri / `GLB OK (WEBP)`。

| 项目 | 值 |
|---|---|
| 静态服务器 | `http://127.0.0.1:7800/index.html` → **200** |
| `check-glb.mjs` | **PASS ✓**（0 error / 44 张 WebP 全内嵌 / extensionsRequired = `EXT_texture_webp` + `KHR_texture_transform`，均有 loader 支持） |
| 无头验收 | 0 pageerror / 0 unhandled rejection / app 内部错误 0 |
| 4 时段 × 6 天气 | 24 组全部可切换；太阳强度 **0.01–4.4**，曝光 **0.55–1.29** |
| 滑块 0/6/12/18/23 | 「夜晚 00:00 / 清晨 06:00 / 正午 12:00 / 黄昏 18:00 / 夜晚 23:00」，sun 极差 **3.12** |
| 雨粒子 | 小雨 3000 / 中雨 6000 / 大雨·雷阵雨 12000 |
| 渲染（1280×800，默认机位） | triangels ≈ 362,755 / drawcalls ≈ 761 / points 350 |
| 截图 | `renders/web/` 共 105 张 |

### 已知限制
1. **女仆头发/皮肤偏白**（v5 冻结版）：GLB 里 `M_Hair` / `M_Skin` 是 `MeshPhysicalMaterial` 且带 `KHR_materials_specular` + sheen + clearcoat，在强环境光 + 大面积窗光下整体泛白。已在 `js/scene.js` 中把 `M_Skin`（sheen 0 / clearcoat 0 / env 0.3）、`M_Hair`（sheen 0.18 / clearcoat 0 / env 0.3）、`M_White`/`M_Satin`（env ≤0.3）压低，观感明显改善但**未完全还原 Blender 侧的棕发**。彻底解决需要 Blender 侧导出时削减 `M_Hair` 的 specular/sheen 扩展，或网页端直接覆盖 `M_Hair.color = 0x6B4226`（可接受的兜底，一行改动）。
2. **夜景仍偏亮**：`RectAreaLight`（窗内侧 3.7×1.86m）在 2m 内对浅色材质贡献很大；已把夜间窗光/方向光置 0、HDRI 强度降到 0.07，但若还要更暗，调 `__CAFE__.weather.overrides = { exposure: 0.55, hemi: 0.2, ambient: 0.25 }`。
3. **drawcall ≈ 761 偏高**（1278 个 mesh）：未做静态合批。后续可按材质/集合合并静态小件（GLB 侧合并更划算）。
4. **无头 SwiftShader** 下 fps 10–14，**不代表真机性能**；FPS 需要真实 GPU 环境测量。

---

## 7. 文件清单（网页端）

```
index.html                    首屏遮罩 / HUD / 三个控件
css/style.css                 奶油色圆角卡片 UI（#FFF7EC / #5B3A29 / 16px）
js/app.js                     主入口 module：初始化、UI 绑定、时间/天气状态机、动画循环、音频桥接
js/scene.js                   GLB 加载（含预检修补/降级）、相机与 OrbitControls、AABB 碰撞、粒子、室外
js/weather.js                 时间 4 档 × 天气 6 态 → 光照/天空/雾/材质过渡（纯数据驱动，读 manifest light_rig）
js/audio.js                   audio-dev 交付（本文件不写，只 import；缺失时静默降级）
js/vendor/three.module.js     three r160（本地，非 CDN）
js/vendor/OrbitControls.js
js/vendor/GLTFLoader.js
js/vendor/BufferGeometryUtils.js
js/vendor/RGBELoader.js
js/vendor/RectAreaLightUniformsLib.js
js/vendor/VENDOR-REPORT.json  vendor 生成记录（版本 / 字节 / md5）
tools/web/*.mjs               见 §5
```
