# 素材来源与授权

本项目的几何体大部分由 `blender/` 下的程序化脚本生成；
另有部分模型 / 贴图 / HDRI 来自 **PolyHaven**（CC0 授权，可商用、可再分发）。

---

## 1. PolyHaven（CC0 1.0 Universal）

| 类别 | 目录 | 说明 |
|---|---|---|
| 模型 | `assets/models/` | 37 个 PolyHaven 模型，全部 **CC0** |
| 贴图 | `assets/textures/` | PolyHaven 贴图，**CC0** |
| HDRI | `assets/hdri/` | 4 张 1K HDR，**CC0** |

**授权原文**：https://polyhaven.com/license
> All assets on Poly Haven are licensed under CC0, meaning you can use them
> for any purpose, including commercial, without attribution.

本项目使用的 HDRI：
- `kiara_2_sunrise_1k.hdr` — 清晨
- `kloppenheim_06_puresky_1k.hdr` — 正午
- `evening_road_01_puresky_1k.hdr` — 黄昏
- `dikhololo_night_1k.hdr` — 夜晚

> 注：为控制仓库体积，`assets/models/` 与 `assets/textures/` 未纳入 git（见 `.gitignore`）。
> 需要重新生成 Blender 场景时，用 `tools/ph_dl_model.mjs` / `ph_dl_tex.mjs` / `ph_dl_hdri.mjs` 重新下载。
> **网页运行不需要它们** —— `scene/maid_cafe.glb` 已把全部贴图内嵌。

---

## 2. 背景音乐（**未包含在仓库内**）

`js/audio.js` 里配置了 5 首曲目，作者 **flap+frog**：

| 文件名（放入 `assets/music/`） | 曲目 |
|---|---|
| `01_creamydream.ogg` | creamydream |
| `02_lazy_red_sans.ogg` | lazy red sans |
| `03_mental_sketch.ogg` | mental sketch |
| `04_starry_sky.ogg` | starry sky |
| `05_un_fiore_rosa.ogg` | Un Fiore Rosa |

⚠️ **版权归原作者 flap+frog，本项目不附带音频文件**（`.gitignore` 已排除 `assets/music/*.ogg`）。
请自行购买 / 获取授权后放入该目录；或修改 `js/audio.js` 里的 `MUSIC_TRACKS` 换成你自己的曲目。

**没有音乐文件时网页仍可正常运行**，只是没有背景音乐（代码会静默降级）。

---

## 3. 环境音效

`assets/audio/amb_rain_med.ogg` — 雨声，本项目自制/合成，随仓库分发。

---

## 4. 字体

网页与视频字幕使用系统自带字体 **Microsoft YaHei（微软雅黑）**，
不随项目分发字体文件。

---

## 5. 角色模型

Q 版女仆模型来源：`maid_chibi` 项目的程序化生成结果，
经 `blender/cmaid.py` 二次处理（烘焙顶点色、清理材质、加托盘道具）。
该模型属于本项目自有资产。

---

## 6. 第三方代码

| 库 | 版本 | 授权 | 位置 |
|---|---|---|---|
| three.js | r160 | MIT | `js/vendor/three.module.js` |
| OrbitControls | r160 | MIT | `js/vendor/OrbitControls.js` |
| GLTFLoader | r160 | MIT | `js/vendor/GLTFLoader.js` |
| RGBELoader | r160 | MIT | `js/vendor/RGBELoader.js` |
| RectAreaLightUniformsLib | r160 | MIT | `js/vendor/RectAreaLightUniformsLib.js` |
| BufferGeometryUtils | r160 | MIT | `js/vendor/BufferGeometryUtils.js` |

three.js 授权全文：https://github.com/mrdoob/three.js/blob/dev/LICENSE
