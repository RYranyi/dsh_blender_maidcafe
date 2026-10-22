# 如何运行这个项目

> 注意：网页**不能双击打开** `index.html`（浏览器会因 CORS 拒绝加载 3D 模型和脚本）。
> 必须用下面任一方式启动**本地服务器**，然后用浏览器访问 `http://127.0.0.1:8000/index.html`。

---

## ✅ 最简单：双击 `启动预览.bat`

双击项目根目录的 **`启动预览.bat`**，它会：
1. 自动找 Python（找不到就用 Node.js）
2. 启动本地服务器
3. 自动打开浏览器

**关闭那个黑窗口就停止服务器。**

---

## ✅ 方式二：命令行（Python，推荐）

打开 PowerShell 或 CMD：

```powershell
cd <项目目录>
python serve.py
```

看到这样的输出就成功了：

```
  ╔══════════════════════════════════════════════════════╗
  ║   日式女仆咖啡馆 · 本地预览服务器                     ║
  ╚══════════════════════════════════════════════════════╝

   根目录： <项目根>
   地址：   http://127.0.0.1:8000/index.html
```

浏览器会自动打开。如果没有，手动访问：**http://127.0.0.1:8000/index.html**

**换端口**（8000 被占用时）：
```powershell
python serve.py 8080
```

**不自动开浏览器**：
```powershell
python serve.py --no-browser
```

---

## ✅ 方式三：命令行（Node.js，本项目也自带）

```powershell
cd <项目目录>
node tools/web/serve.mjs 8000
```

然后访问 `http://127.0.0.1:8000/index.html`

---

## ✅ 方式四：最原始的 Python 一行命令

如果 `serve.py` 有问题，这是**绝对不会失败**的兜底方案：

```powershell
cd <项目目录>
python -m http.server 8000
```

然后访问 `http://127.0.0.1:8000/index.html`

> ⚠️ 这个方式有个小缺陷：Windows 注册表里 `.glb` / `.webp` 的 MIME 类型可能缺失，
> 导致浏览器拒绝加载模型。如果画面白屏，用 `serve.py`（它内置了正确 MIME）。

---

## 进入后能做什么

| 操作 | 效果 |
|---|---|
| **点击「点击进入」** | 解锁音频（浏览器自动播放策略要求用户手势） |
| **拖动时间滑条** | 00:00–24:00，4 档光照实时切换（清晨/正午/黄昏/夜晚） |
| **点天气按钮** | 晴天 / 多云 / 雨天（展开后有小雨/中雨/大雨/雷阵雨） |
| **拖动音量滑条** | 0–100% 总音量 |
| **点「默认机位」** | 视角复位 |
| **鼠标拖拽 / 滚轮 / 右键** | 旋转 / 缩放 / 平移 |

**雷阵雨**会随机打闪电（天空爆白 + 光强脉冲 + 延迟雷声）。

---

## 直接定格到某个时刻（免操作）

URL 后面加参数就能直接进到指定状态，适合截图/演示：

```
http://127.0.0.1:8000/index.html?auto=1&time=21.5&weather=storm
```

| 参数 | 说明 |
|---|---|
| `auto=1` | 自动进入（跳过「点击进入」，无音频） |
| `time=21.5` | 时间（0–24，可小数） |
| `weather=clear` | 晴天 |
| `weather=cloudy` | 多云 |
| `weather=rain_light` | 小雨 |
| `weather=rain_med` | 中雨 |
| `weather=rain_heavy` | 大雨 |
| `weather=storm` | 雷阵雨 |
| `debug=1` | 显示右上角调试面板（FPS / 三角面 / draw calls） |

例：
- 黄昏晴天：`?auto=1&time=18&weather=clear`
- 夜晚雷雨：`?auto=1&time=21.5&weather=storm`
- 正午中雨：`?auto=1&time=12.5&weather=rain_med`

---

## 常见问题

### Q: 打开是白屏 / 一直卡在「正在准备店面…」
1. **确认你是通过 `http://127.0.0.1:8000/` 访问的**，不是 `file:///...`
   —— 地址栏里如果看到 `file://` 就一定失败，这是最可能的原因。
2. 确认服务器窗口还在运行（关掉就没了）。
3. 按 `F12` 打开浏览器控制台，看红色报错。

### Q: 端口 8000 被占用
`serve.py` 会自动顺延到 8001/8002… 并在启动信息里打印实际端口。
或者手动指定：`python serve.py 8080`

### Q: 没有 Python 也没有 Node.js
安装其中一个即可：
- Python：https://www.python.org/downloads/ （安装时勾选 "Add to PATH"）
- Node.js：https://nodejs.org/

### Q: 能不能直接双击 index.html？
**不能。** 这个页面用 ES module + fetch 加载 GLB 模型、HDRI、JSON 清单，
浏览器的 `file://` 协议会把这些请求全部按 CORS 拒绝，所以必然白屏。
这是浏览器的安全限制，不是 bug。

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `启动预览.bat` | Windows 一键启动（双击即可） |
| `serve.py` | Python 静态服务器（零依赖，推荐） |
| `tools/web/serve.mjs` | Node.js 静态服务器（备选，零依赖） |
| `index.html` | 网页入口 |
| `scene/maid_cafe.glb` | 3D 模型（21.67 MB，单文件） |
| `scene/scene_manifest.json` | 场景清单（锚点/灯光/材质名） |
| `assets/hdri/*.hdr` | 环境贴图：4 档时间各 1 张 |
| `assets/audio/` | 雨声循环（`amb_rain_med.ogg`）；雷电是画面闪 + 雨声加重，无独立雷声样本 |

---

## 重新生成素材（可选）

`blender/` 与 `tools/` 下的脚本都按**脚本自身所在目录**推导项目根，不写死机器路径，
所以仓库克隆到任何位置都能直接跑。唯一的外部依赖是 **ffmpeg**：
`tools/audio/*.py` 默认调用 `PATH` 上的 `ffmpeg` / `ffprobe`，
装在别处时用环境变量指定：

```powershell
$env:FFMPEG  = "<ffmpeg 目录>\ffmpeg.exe"
$env:FFPROBE = "<ffmpeg 目录>\ffprobe.exe"
```

（只影响音频素材的重新生成，不影响网页运行。）

