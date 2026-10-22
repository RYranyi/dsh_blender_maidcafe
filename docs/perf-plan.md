# 网站性能诊断报告

## 现状

| 项 | 值 | 问题 |
|---|---|---|
| GLB | 21.67 MB / 1,124 mesh / 512,504 三角面 | 单文件大，首次加载慢 |
| 材质 | 148 个 | 每个材质独立 draw call |
| 贴图 | 121 textures / 93 images (WebP) | 显存占用高 |
| 雨粒子 | RAIN_MAX = 12,000 个 Points | 顶点着色器每帧计算 |
| 阴影 | PCFSoftShadowMap, 2048×2048 | 软阴影开销大 |
| pixelRatio | `min(devicePixelRatio, 2)` | 4K 屏 = 2 倍像素 |
| antialias | true | MSAA 额外开销 |

## 根因分析

### 1. 加载进度条完全不可见（用户明确反馈）
- `#enter` 的 `z-index: 40`，全屏不透明遮罩
- `#loader` 的 `z-index: 30`
- **进度条被进入页完全盖住**，所以用户看到的永远是"卡住"
- 修复：把 loader 挪进 `#enter` 内部显示

### 2. 切换时间/天气卡顿
- `_applyState()` **每帧**都跑完整灯光计算（148 材质的 envMapIntensity、灯光、天空、雾、曝光）
- `_applyEnvIntensityToMaterials()` 里 `if (Math.abs(v - last) < 0.004) return;` 有帮助，但 `_applyLampMaterials` 和 `_applyWetness` 每帧仍遍历材质
- `collectReflectiveMaterials()` 每次调用都重新遍历（只在 applyEnvironmentMap 用，可缓存）
- 切时段触发 `loadHdriForPhase()` 异步加载新 HDRI，加载完成瞬间 `_activateHdri` 会重设所有材质 envMap

### 3. 低配机器可能崩溃
- `antialias: true` + `pixelRatio 2` + 2048 PCFSoft 阴影 + 12000 雨粒子 + 21.67 MB GLB
- 显存估算：121 张贴图 × 1K 分辨率 × 4B ≈ 500 MB（未压缩显存）+ 几何 512k tris
- 低端集显（Intel UHD）容易 OOM

## 优化方案（按收益排序）

### A. 加载进度真正可见（用户首要诉求）
- `#loader` z-index 从 30 → **45**（高于 `#enter` 的 40）
- 或把 loader DOM 放进 `#enter` 内部
- 加载期间进入页按钮置灰 + 显示"正在加载 42%"

### B. 自适应画质（防低配崩溃）
```js
// 根据 devicePixelRatio / 硬件推测 3 档
const TIER = detectTier(); // low | mid | high
// low:  pixelRatio 1,   antialias off, shadow 1024, RAIN 3000, 阴影关
// mid:  pixelRatio 1.5, antialias on,  shadow 1536, RAIN 7000
// high: pixelRatio 2,   antialias on,  shadow 2048, RAIN 12000
```
用 `renderer.info.memory` + 首帧耗时动态降级。

### C. 减少每帧开销
1. `_applyState` 只在值变化时应用（dirty flag）
2. `_applyLampMaterials` / `_applyWetness` 加变化检测
3. `collectReflectiveMaterials()` 结果缓存
4. 雨粒子在 `rainCount === 0` 时跳过整个更新循环

### D. 材质与几何优化
1. **共享材质实例**（GLB 已共享，148 个不算多）
2. **关闭不需要阴影投射的物体**（场景里 334 个户外对象大多不需要）
3. 静态物体 `matrixAutoUpdate = false`（省每帧矩阵更新）

### E. 减少纹理显存
1. 已有 WebP（好）
2. 可考虑把 4K 贴图降到 1K（GLB 里多数已是 1K）
3. `texture.anisotropy = 1`（默认 1，OK）

## 我会做的改动

1. **`index.html` / `css`**：loader 提到 z-index 45，进入页内嵌进度
2. **`js/scene.js`**：
   - 画质自适应（3 档，按硬件能力 + 首帧耗时）
   - `matrixAutoUpdate = false` for 静态 mesh
   - 阴影投射白名单（只让主要物体投影）
   - 雨粒子低配降级
3. **`js/weather.js`**：
   - `_applyState` 加 dirty flag，静止时不重算
   - 缓存 `collectReflectiveMaterials()`
   - `_applyLampMaterials` / `_applyWetness` 加变化检测
4. **删除**：`#loader` 的无用进度条（用户说"完全没体现"→ 改成进入页内进度）

## 风险

- 画质自适应需要真机验证（沙箱无法跑浏览器）
- 我会用 Node 做逻辑测试 + 静态检查，但最终效果需要用户刷新确认
