# 日式女仆咖啡馆 · Maid Café

> 一间 8m × 6m 的日式女仆咖啡馆：Blender 程序化建模 + Three.js 实时网页 + 3 分钟光影介绍片。

![女仆特写](renders/final/hero_maid.png)

**Q 版女仆双手捧托盘（草莓蛋糕 + 咖啡），烘焙导出 21.7 MB 单文件 GLB；
网页支持 4 档时间光照 × 6 种天气；另附 180 秒真 3D 动画介绍片（无音轨）。**

---

## 一、这是什么

| 组成 | 内容 |
|---|---|
| **场景** | 8m × 6m 室内 + 街道外景，1,124 个网格 / 512,504 三角面 |
| **角色** | Q 版女仆（233,097 面，占场景 45%），肤色发色烘进顶点 |
| **网页** | Three.js 实时渲染，时间滑条（0–24h）+ 6 种天气 + WASD 自由漫游 |
| **视频** | 180 秒 / 1920×1080 / 24fps / 4,320 帧真 3D 动画 / 30 条中文字幕 / **无音轨** |

| 项 | 数值 |
|---|---|
| **三角面** | 512,504（GLB 内） |
| **网格数** | 1,124 |
| **材质数** | 148 |
| **贴图** | 93 张（全部 WebP 内嵌，无外链） |
| **GLB** | 21.67 MB 单文件 |

> 📦 **素材授权与来源**：见 [`docs/ASSETS-CREDITS.md`](docs/ASSETS-CREDITS.md)

---

## 二、快速开始

```bash
# 1) 起一个本地服务器（必须，不能用 file:// 直接打开）
python -m http.server 8000
# 或
node tools/web/serve.mjs

# 2) 浏览器打开
http://localhost:8000/
```

> ⚠️ **不能双击 `index.html`** —— 页面用 ES module + `fetch` 加载 GLB / HDRI / 音频，
> `file://` 协议会被 CORS 拒绝，必然白屏。必须起 HTTP 服务。

### 需要自己补的文件

| 文件 | 说明 |
|---|---|
| `assets/music/*.ogg` | **版权**：flap+frog 的商业音乐。仓库**不含**，自行购买后放入（文件名见 `docs/ASSETS-CREDITS.md`），或改 `js/audio.js` 的 `MUSIC_TRACKS` 用你自己的 |
| `assets/models/` `assets/textures/` | 394 MB，PolyHaven CC0，可免费重下。**跑网页不需要**（GLB 已内嵌贴图），只在重新生成 Blender 场景时需要 |

**只有 music 缺失时网页仍能跑** —— 音乐播放器会提示「音频模块未就绪」，其余功能正常。

---

## 三、网页能做什么

| 功能 | 说明 |
|---|---|
| **时间** | 0–24h 滑条，连续过渡；4 个关键档位（清晨 / 正午 / 黄昏 / 夜晚） |
| **天气** | 晴 / 多云 / 小雨 / 中雨 / 大雨 / 雷阵雨（含闪电） |
| **漫游** | WASD 移动 · 空格/C 升降 · Shift 加速 · V 环绕 · H 沉浸 |
| **亮度** | 左下常驻滑块，15%–200%，双击标签复位 |
| **面板** | 每个面板右上角眼睛按钮：收起 / 隐藏 / 恢复（三态，存 localStorage） |
| **音量** | 音乐 / 雨声分开控制 |
| **调试参数** | `?debug=1` 显示 FPS / 三角面 / draw call；`?hour=18&weather=rain_med` 指定初始状态 |

---

## 四、已知问题

### ⚠️ 网页运行卡顿（已知，暂不修复）

**现象**：进入场景后有明显卡顿，时间/天气切换时掉帧。
**在低配机器（集显 / 老笔记本）上尤其严重，可能卡到不可用。**

**原因**
1. **几何量偏大**：1,124 个网格 / 512,504 三角面，draw call 数量高。
2. **材质双面渲染**：148 个材质里大部分 `doubleSided`，three.js 需按材质分批排序。
3. **光照实时计算**：4 档时间 × 6 种天气的组合会触发灯光/HDRI/材质重算。
4. **大 GLB 首帧开销**：21.67 MB 单文件解压 + 93 张 WebP 上传显存，首帧要 3–8 秒。

**为什么现在不修**
本项目已消耗约 12 亿 tokens，继续大改性能有把整个工程改崩的风险。
**当前版本功能完整、逻辑正确、测试全过（235 项），选择就此收尾，把问题写清楚。**

**你可以自己缓解的办法**
- 用 **H 键沉浸模式** 而不是 F11
- 浏览器开**硬件加速**（Chrome：设置 → 系统 → 使用硬件加速）
- 缩小窗口尺寸（像素越少越快）
- 换独显机器 / 关闭其他占用 GPU 的程序

**如果将来要修，优先级建议**
1. 合并静态网格（1,124 → 约 100），砍 draw call
2. 材质按透明度分组，减少状态切换
3. GLB 拆分成按需加载的多个 chunk
4. 加 LOD：远处物体换低模

### ⚠️ 拖动时间滑条会明显卡顿（最严重的卡顿来源）

**现象**：只要动一下时间滑条，整个页面就会卡、掉帧，甚至拖不动。
**这是本项目最直观的卡顿来源，比"进入场景时慢"更影响使用。**

**调用链**（`app.js` → `weather.js`）：

```
拖动 time-slider
  → applyHour(hour)
    → app.weather.setHour(hour)        // weather.js:1359
      → this._retarget()
        → computeTargetState(hour, weatherKey, data)   // 完整重算
```

**`computeTargetState()` 每次都要重算的量**（weather.js:789 起）：

| 重算内容 | 说明 |
|---|---|
| 太阳位置 / 强度 / 颜色 | 按时段插值 |
| 4 档 phase 混合 | 清晨/正午/黄昏/夜晚之间连续插值 |
| hemi / ambient / 曝光 | 含 `Math.pow(a, 1.7)` 等 |
| 天空颜色（top / horizon / sun / glow / stars） | 多个 `THREE.Color` 插值 |
| 雾色 / 雾密度 | |
| 24 种天气组合参数 | 云量 / 雨的强度 / 湿地反射 |
| `lampOn` 开灯判定 | 时间 + 天气双条件 |
| 15 盏灯的强度分配 | 吊灯 / 壁灯 / 吧台射灯 / 展柜射灯 / 书架补光 |
| HDRI 时段切换判定 | 可能触发**异步加载新 HDRI**（几 MB） |

**然后 `_applyState()` 每帧还要把这些写进场景**：
灯的 `intensity`/`color`、`toneMappingExposure`、`scene.fog`、
材质 `envMapIntensity`（148 个材质）、雨/粒子系统的 drawRange…

**为什么滑条一拖动就卡**
- `input` 事件是**连续触发**的（拖动过程中每秒几十次），每次都跑上面整套计算
- 现有代码只在**音频切换**上做了 220ms 防抖（`timeDebounce`），
  **但光照计算本身没有任何节流** —— 每次 `input` 都完整跑一遍
- 拖动跨过时段边界时（比如 5:00→7:00、17:00→19:00）还会触发 **HDRI 换图**，
  那是几 MB 的纹理上传，一次就够卡一下

**如果将来要修，这一项收益最大**
```js
// 给 time-slider 的 input 加 rAF 节流（拖动时最多每帧算一次）
let pendingHour = null, hourRaf = 0;
ui.timeSlider.addEventListener('input', (e) => {
  pendingHour = Number(e.target.value);
  if (hourRaf) return;
  hourRaf = requestAnimationFrame(() => {
    hourRaf = 0;
    if (pendingHour != null) { applyHour(pendingHour); pendingHour = null; }
  });
});
```
另外可以：`computeTargetState` 结果按 `(hour 量化到 0.1, weather)` 缓存，
同参数直接命中缓存跳过整个计算。

### ✅ F11 全屏显示不全 —— 已修复

**原现象**：按 F11 进浏览器原生全屏后，3D 画面只占一部分，右侧/底部空白或裁切。

**根因**
- F11 是**浏览器级**全屏，不触发 `fullscreenchange` 事件。
- 原实现只用 `ResizeObserver` 观察 `#stage` 容器；F11 时容器 CSS 尺寸不变，
  但视口（`window.innerWidth/Height`）变了 → canvas 尺寸没跟上。
- H 键走 `requestFullscreen()` 会触发事件，所以一直正常。

**修复**（`js/app.js`）
```js
// 每 400ms 轮询视口尺寸（F11 不触发事件，只能轮询）
setInterval(() => {
  if (window.innerWidth !== lastVW || window.innerHeight !== lastVH) {
    lastVW = window.innerWidth; lastVH = window.innerHeight;
    app.scene.resize();
    setTimeout(() => app.scene.resize(), 150);   // 全屏动画期间补正
    setTimeout(() => app.scene.resize(), 500);
  }
}, 400);
// 标准 resize 事件也接
window.addEventListener('resize', ...);
```

### 其他说明

- **画质选项已移除**：曾有「低/中/高」三档 + L 键面板，因「bug 不修了、默认最好画质」的要求已全部删除，
  现固定最高画质（`antialias: true` / `pixelRatio = min(dpr, 2)` / `PCFSoftShadowMap` / 全特效）。
- **视频无音轨**：180 秒介绍片刻意不含任何音频，背景音乐由使用者自己配。
- **书柜内容**：六层分别为 书 / 小玩偶 / 盆栽 / 茶具 / 酒瓶 / 空。

---

## 五、项目结构

```
.
├── index.html              # 网页入口
├── css/style.css           # 全部样式
├── js/
│   ├── app.js              # 应用主逻辑（UI / 状态 / 快捷键）
│   ├── scene.js            # Three.js 场景装配 / GLB 加载 / 粒子
│   ├── weather.js          # 天气与光照系统（4 时段 × 6 天气）
│   ├── freecam.js          # WASD 自由漫游
│   ├── audio.js            # Web Audio 音乐/雨声引擎
│   └── vendor/             # three.js + GLTFLoader + OrbitControls
├── scene/
│   ├── maid_cafe.blend     # Blender 工程（本地保留，git 忽略）
│   ├── maid_cafe.glb       # ★ 交付模型（21.67 MB）
│   └── scene_manifest.json # 场景清单（尺寸/机位/灯位/材质名）
├── renders/
│   ├── final/              # 9 张成品图
│   ├── audit/              # 13 张质检图
│   └── video/
│       └── maid_cafe_lighting_180s.mp4   # ★ 180 秒介绍片（无音轨）
├── blender/                # 程序化建模模块（croom / cbar / cdisplay / cmaid …）
├── tools/                  # 构建 / 渲染 / 质检 / 测试脚本
├── docs/                   # 文档（运行说明 / 素材版权 / 视频字幕）
└── .gitignore / .gitattributes / LICENSE
```

---

## 六、重新生成场景

```bash
# 1. 生成 Blender 场景（需要 assets/models 与 assets/textures）
blender -b -P blender/cbuild.py

# 2. 导出 GLB（含材质修正 / 结构自检 / WEBP 回退）
blender -b -P tools/export_after_model.py
```

---

## 七、质检

```bash
# GLB 结构（nodes / tris / 贴图内嵌 / 扩展）
node tools/web/check-glb.mjs scene/maid_cafe.glb

# 网页行为测试（8 个套件 / 235 项）
node tools/test_api.mjs
node tools/test_features.mjs
node tools/test_integration.mjs
node tools/test_lighting_rules.mjs
node tools/test_esc_imm.mjs
node tools/test_freecam.mjs
node tools/test_exposure.mjs
node tools/test_round2.mjs
```

**当前状态：235 项全部通过。**

---

## 八、视频

**文件**：`renders/video/maid_cafe_lighting_180s.mp4`

| 项 | 值 |
|---|---|
| 时长 | 180.00 s |
| 分辨率 / 帧率 | 1920×1080 / 24 fps |
| 帧数 | 4,320（真 3D 动画，非静帧推拉） |
| 大小 | 103 MB |
| 音轨 | **无**（刻意不加，音乐自配） |
| 字幕 | 30 条中文，已烧录 |

### 30 段结构

| 段 | 内容 | 段 | 内容 |
|---|---|---|---|
| 1–2 | 线框 → 白模 | 15–16 | 晴天（窗 / 吧台） |
| 3–5 | 吧台 / 甜品柜 / 女仆 | 17–18 | 多云 |
| 6 | 成品全景 | 19–21 | 小雨 / 中雨 / 大雨 |
| 7–8 | 清晨 | 22 | 雷阵雨（含闪电） |
| 9–10 | 正午 | 23–24 | 雨天 / 雷雨全景 |
| 11–12 | 黄昏（开灯） | 25 | 全场景统计 |
| 13–14 | 夜晚 | 26 | **书架六层** |
| | | 27–30 | 女仆 / 吧台 / 窗 / 收尾 |

---

## 九、授权

- **代码**：MIT（见 `LICENSE`）
- **模型贴图**：PolyHaven CC0（可自由使用）
- **背景音乐**：flap+frog 商业作品，**仓库不含**，版权归原作者
- **字体**：系统中文字体（微软雅黑），未内嵌

详见 `docs/ASSETS-CREDITS.md`。
