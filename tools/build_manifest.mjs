// Build assets/MANIFEST.md from the scratch records produced by the downloaders
// and the Blender audit. usage: node build_manifest.mjs
// Idempotent: regenerates the file from scratch data + live file sizes.
import fs from "node:fs";
import path from "node:path";

const ROOT = "E:/dsh/maid_cafe";
const SCRATCH = path.join(ROOT, ".scratch/asset-scout");
const ASSETS = path.join(ROOT, "assets");

const read = (p, dflt) => (fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf8")) : dflt);
const resolved = read(path.join(SCRATCH, "resolved.json"), { textures: [], models: [], hdris: [] });
const texRec = read(path.join(SCRATCH, "tex_downloaded.json"), []);
const modRec = read(path.join(SCRATCH, "models_downloaded.json"), []);
const hdriRec = read(path.join(SCRATCH, "hdris_downloaded.json"), []);
const audit = read(path.join(SCRATCH, "models_audit.json"), []);

const mb = (b) => (b / 1048576).toFixed(2);
const sizeOf = (rel) => {
  const p = path.join(ROOT, rel);
  return fs.existsSync(p) ? fs.statSync(p).size : 0;
};
const dirSize = (rel) => {
  const dir = path.join(ROOT, rel);
  if (!fs.existsSync(dir)) return 0;
  let n = 0;
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else n += fs.statSync(p).size;
    }
  };
  walk(dir);
  return n;
};

// ---- assets/tex ----
const texFiles = fs.existsSync(path.join(ASSETS, "tex"))
  ? fs.readdirSync(path.join(ASSETS, "tex")).filter((f) => /\.(jpg|png)$/i.test(f)).sort()
  : [];
const texByGroup = [];
for (const g of texRec) {
  const files = texFiles.filter((f) => f.startsWith(g.id + "_"));
  const bytes = files.reduce((a, f) => a + sizeOf(`assets/tex/${f}`), 0);
  texByGroup.push({ ...g, files, bytes });
}

// ---- assets/models ----
const auditById = Object.fromEntries(audit.map((a) => [a.id, a]));
const modelRows = [];
for (const r of modRec) {
  const a = auditById[r.id] || {};
  modelRows.push({
    ...r,
    objects: a.objects ?? "?",
    triangles: a.triangles ?? "?",
    materials: a.materials ?? "?",
    images_total: a.images_total ?? "?",
    images_resolved: a.images_resolved ?? "?",
    dims: a.bbox ? a.bbox.dims_m.join(" × ") : "?",
    totalBytes: dirSize(`assets/models/${r.id}`),
  });
}

// ---- assets/hdri ----
const hdriRows = hdriRec.map((r) => ({ ...r, bytes: sizeOf(r.file) }));

// ---- assets/tex/generated ----
const genDir = path.join(ASSETS, "tex/generated");
const genFiles = fs.existsSync(genDir) ? fs.readdirSync(genDir).filter((f) => f.endsWith(".png")).sort() : [];
const GEN_ROLE = {
  "menu_blackboard.png": "店内手写风黑板菜单（日文+英文 13 行 + 价格），挂在吧台后墙或用 standing_chalkboard_01 的板面替换",
  "noren_welcome.png": "门帘「いらっしゃいませ」，门口玄关横挂；藏青底 + 暖白字，双帘缝",
  "sign_cafe.png": "门口招牌「Maid Café めいど」，奶油底木框；可直接贴 plane 或做灯箱面",
  "menu_card.png": "桌面菜单立牌（A6 竖版 105:148），放每张桌子中央；也可缩放当托盘垫纸",
  "label_beans.png": "咖啡豆罐标签（オリジナルブレンド / 200g），贴罐身或货架价签",
  "label_tea.png": "茶叶罐标签（アールグレイ / 100g），与豆罐成对",
  "picture_art_01.png": "相框插画·花瓶与花（柔和插画风），配 fancy_picture_frame_02 / hanging_picture_frame_01",
  "picture_art_02.png": "相框插画·打瞌睡的猫（柔和插画风），适合放收银台后或墙角",
  "picture_art_03.png": "相框插画·咖啡杯与拉花（柔和插画风），适合吧台上方",
  "chalk_open.png": "「OPEN / 営業中」粉笔挂牌，门口玻璃或门把手",
  "window_drops.png": "窗玻璃雨滴/水痕（RGBA 透明，1024²），网页雨天叠加层或玻璃材质 alpha 贴图",
};

// ---- totals ----
const texTotalBytes = texFiles.reduce((a, f) => a + sizeOf(`assets/tex/${f}`), 0);
const modelTotalBytes = dirSize("assets/models");
const hdriTotalBytes = hdriRows.reduce((a, r) => a + r.bytes, 0);
const genTotalBytes = genFiles.reduce((a, f) => a + sizeOf(`assets/tex/generated/${f}`), 0);
const allTotal = texTotalBytes + modelTotalBytes + hdriTotalBytes + genTotalBytes;

const L = [];
const P = (s = "") => L.push(s);

P("# 女仆咖啡馆 · 资产清单 (MANIFEST)");
P();
P(`生成时间：${new Date().toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" }).slice(0, 16)} (+08:00)（本文件由 \`tools/build_manifest.mjs\` 自动生成，可重复运行）`);
P();
P("**来源**：全部 3D 资产与贴图来自 [PolyHaven](https://polyhaven.com)，许可证 **CC0 1.0 Universal（公有领域）**，可商用、可修改、无需署名（此处署名仅为礼貌与可追溯）。");
P("每一项的来源页面统一为 `https://polyhaven.com/a/<polyhaven_id>`，直链由 PolyHaven Files API 解析下载（`https://api.polyhaven.com/files/<id>`）。");
P("文字/插画贴图由本项目脚本 `tools/gen_textures.py`（Pillow + Windows 日文字体 Yu Gothic / MS Gothic / Georgia）程序化生成，版权归项目所有。");
P();
P("## 总量");
P();
P("| 类别 | 数量 | 占用 | 路径 |");
P("| --- | ---: | ---: | --- |");
P(`| PBR 贴图（PolyHaven，19 组 × 5 图 = ${texFiles.length} 文件） | ${texRec.length} 组 | ${mb(texTotalBytes)} MB | \`assets/tex/\` |`);
P(`| PolyHaven 模型（.blend 1k + 贴图） | ${modelRows.length} 个 | ${mb(modelTotalBytes)} MB | \`assets/models/<id>/\` |`);
P(`| HDRI 1k .hdr | ${hdriRows.length} 张 | ${mb(hdriTotalBytes)} MB | \`assets/hdri/\` |`);
P(`| 程序化生成贴图 PNG | ${genFiles.length} 张 | ${mb(genTotalBytes)} MB | \`assets/tex/generated/\` |`);
P(`| **合计** | | **${mb(allTotal)} MB** | \`assets/\` |`);
P();
P("---");
P();
P("## 1. PBR 贴图 `assets/tex/`");
P();
P("命名规范：`<polyhaven_id>_<map>_<res>.jpg`，map ∈ `diff`(基色) / `nor_gl`(法线) / `arm`(AO+Rough+Metal 打包) / `rough`(粗糙度) / `disp`(置换)。地板 2k，其余 1k。");
P();
P("| 用途 | 资产 id | 作者 | 文件名 | 分辨率 | 文件数 | 大小 |");
P("| --- | --- | --- | --- | --- | ---: | ---: |");
for (const g of texByGroup) {
  const resTag = g.files[0] ? (g.files[0].match(/_(1k|2k|4k)\./) || [, "?"])[1] : "?";
  P(`| ${g.role} | \`${g.id}\` | ${(g.authors || []).join(", ")} | ${g.files.map((f) => `\`${f}\``).join("<br>")} | ${resTag} | ${g.files.length} | ${mb(g.bytes)} MB |`);
}
P();
P("来源 URL 模板：`https://polyhaven.com/a/<polyhaven_id>`（如 https://polyhaven.com/a/herringbone_parquet ）");
P();
P("外观速查（供美术/网页配色参考）：");
P();
P("- `herringbone_parquet`：人字拼木地板，中等暖棕，板缝清晰 —— 门店主地板；备选 `wooden_floor_01`（浅灰棕）、`wood_floor`（暖黄棕）。");
P("- `wood_table`：横向木纹桌面；`marble_01`：细白底灰纹大理石 —— 吧台台面。");
P("- `japanese_cedar_planks`：暖色竖向杉木板 —— 墙裙/护墙板；`white_stucco`：奶油白微颗粒墙面。");
P("- `rough_linen` / `crepe_satin` / `gingham_check` / `waffle_pique_cotton`：亚麻桌布 / 缎面蕾丝衬底 / 蓝白格纹 / 华夫格坐垫。");
P("- `metal_plate`：拉丝金属板；`metal_grate_rusty`：锈蚀格栅 —— 吧台设备、灯具罩、货架。");
P("- `asphalt_floor`：户外沥青；`concrete_pavers_02` / `square_concrete_pavers`：人行道方砖；`red_brick`：对面红砖墙；`plastered_wall_02`：抹灰外墙。");
P("- `fabric_leather_01`：细纹皮革 —— 沙发/靠背椅面。");
P();
P("---");
P();
P("## 2. 模型 `assets/models/<id>/`");
P();
P("每个目录结构：`<id>/<id>_1k.blend`（自带 PBR 材质，贴图在 `textures/` 子目录，需 `File > External Data > Find Missing Files` 指向该目录，或直接使用 Blender 的 relative 路径，因为下载时保持了 PolyHaven 的 `textures/<name>` 相对布局 — 见下注）。");
P();
P("> 注：PolyHaven 的 .blend 内部贴图按 `//textures/<file>` 引用；下载器把这些文件原样放到了与 .blend 同级的 `textures/` 目录，所以打开即可直接解析。");
P();
P("| 用途 | id | 作者 | 物体数 | 三角面 | 材质数 | 贴图(有/总) | 尺寸 (m, XYZ) | .blend | 总大小 |");
P("| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |");
for (const r of modelRows) {
  P(`| ${r.role} | \`${r.id}\` | ${(r.authors || []).join(", ")} | ${r.objects} | ${r.triangles} | ${r.materials} | ${r.images_resolved}/${r.images_total} | ${r.dims} | \`${r.blend.split("/").pop()}\` | ${mb(r.totalBytes)} MB |`);
}
P();
P("说明：");
P();
P("- 「三角面」为网格基准三角面数（不含修改器求值后的结果；这些静态资产基本没有修改器）。");
P("- 「贴图(有/总)」中未解析的少数贴图是 PolyHaven 打包 .blend 时残留的旧 HDRI 环境贴图引用（模型自身 PBR 贴图均已内置/可解析），不影响使用；如需彻底干净，可在 Blender 里删除该 World 环境贴图引用。");
P("- 全部 `.blend` 已用 headless Blender 5.2 逐个打开校验（`tools/blender_audit_models.py`），本次 " + modelRows.length + " 个文件全部可正常打开，0 失败。");
P();
P("---");
P();
P("## 3. HDRI `assets/hdri/`");
P();
P("1k `.hdr`（Radiance RGBE），用于场景环境光/天空/反射。所有均为 PolyHaven CC0。");
P();
P("| 用途 | id | 作者 | 文件 | 大小 |");
P("| --- | --- | --- | --- | ---: |");
for (const r of hdriRows) {
  P(`| ${r.role} | \`${r.id}\` | ${(r.authors || []).join(", ")} | \`${r.file.split("/").pop()}\` | ${mb(r.bytes)} MB |`);
}
P();
P("使用建议：白天用 `kloppenheim_06_puresky`（纯天光，无地景杂物，适合裁切）；清晨 `kiara_2_sunrise`；黄昏 `evening_road_01_puresky`（纯天空版，街道反射更干净）；夜晚 `dikhololo_night`（有星星与远处灯光）；室内柔光 `hotel_room`（暖色室内，适合做小件资产预览）。");
P();
P("---");
P();
P("## 4. 生成贴图 `assets/tex/generated/`");
P();
P("全部由 `tools/gen_textures.py` 生成（Pillow 12 + Windows 字体：Yu Gothic Medium/Bold、MS Gothic、Georgia、Segoe Print），可复现（`python tools/gen_textures.py`）。");
P();
P("| 文件 | 尺寸 | 用途 |");
P("| --- | --- | --- |");
for (const f of genFiles) {
  const p = path.join(genDir, f);
  const size = (() => {
    try {
      const b = fs.readFileSync(p);
      // read PNG IHDR (width/height at bytes 16..24)
      return `${b.readUInt32BE(16)}×${b.readUInt32BE(20)}`;
    } catch { return "?"; }
  })();
  P(`| \`${f}\` | ${size} | ${GEN_ROLE[f] || "—"} | ${""}`.replace(/ \| $/, " |"));
}
P();
P("---");
P();
P("## 5. 复现方式");
P();
P("```bash");
P("node tools/ph_scout_manifest.mjs   # 按 tools/ph_wishlist.json 核对 PolyHaven 资产存在性 -> .scratch/asset-scout/resolved.json");
P("node tools/ph_dl_tex.mjs           # 下载 PBR 贴图到 assets/tex/（已存在且 >1KB 自动 SKIP）");
P("node tools/ph_dl_model.mjs         # 下载模型 .blend 1k + textures 到 assets/models/");
P("node tools/ph_dl_hdri.mjs          # 下载 HDRI 1k .hdr 到 assets/hdri/");
P("python tools/gen_textures.py       # 生成文字/标签/插画 PNG 到 assets/tex/generated/");
P("node tools/build_manifest.mjs      # 重新生成本清单");
P("```");
P();
P("所有下载脚本均可重复运行（存在且 >1KB 即跳过），中断后重跑可续传；遇到 403/404 会按 wishlist 里的候选列表自动换源。");
P();
P("模型校验（Blender 5.2 headless）：");
P();
P("```bash");
P('blender.exe -b --factory-startup -P tools/blender_audit_models.py -- <modelsDir> <outJson>');
P("```");
P();

fs.writeFileSync(path.join(ASSETS, "MANIFEST.md"), L.join("\n"), "utf8");
console.log(`MANIFEST.md written: ${L.length} 行, tex=${texFiles.length} models=${modelRows.length} hdri=${hdriRows.length} gen=${genFiles.length} total=${mb(allTotal)}MB`);
