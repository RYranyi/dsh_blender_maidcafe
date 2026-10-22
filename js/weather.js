/**
 * js/weather.js — 时间（4 档）× 天气（6 态）→ 光照/天空/雾/材质参数的**纯数据驱动**系统。
 *
 * 职责边界：
 *   - 本文件只做「数据 → 灯光/天空/雾/曝光/材质参数」的插值与平滑过渡，不碰 GLB、不碰相机、不碰粒子。
 *   - 所有参数默认值集中在本文件顶部（CONTRACT §1.1 / §4 / §8 的兜底口径）；
 *     若 scene_manifest.json 提供 `light_rig.phases` / `light_rig.weather`，则逐字段覆盖默认值。
 *   - 坐标：**输入一律 Blender z-up**（CONTRACT 口径），输出给 three.js 时由 scene.js 的 toThree() 转换；
 *     本文件内 `_lampWorld()` 自行做 (x, z, y) 交换，因为它直接给 three 场景建灯。
 *
 * 供 scene.js / app.js 使用的入口：
 *   const ws = new WeatherSystem(scene, renderer, { manifest, roomThree });
 *   ws.setHour(9.4); ws.setWeather('rain_med'); ws.flash();
 *   ws.update(dt); ws.state            // 当前（平滑后）状态
 *   ws.targetState                    // 目标状态
 *   ws.info()                         // 给自检打印的数字
 */

import * as THREE from './vendor/three.module.js';
import { RGBELoader } from './vendor/RGBELoader.js';
import { RectAreaLightUniformsLib } from './vendor/RectAreaLightUniformsLib.js';

/* ─────────────────────────────── 时间 4 档锚点 ───────────────────────────────
 * 色温/光强/太阳角/天空色/曝光/室内灯亮度/ambient 强度。
 * 太阳位置：方向光半径 9m，elev=仰角(°)，azim=绕 Y 轴方位角(°，0=正对 -Z 街道面，正值偏 +X)。
 */
export const PHASE_ANCHORS = [
  {
    key: 'morning',
    label: '清晨',
    hour: 7.0,
    sunIntensity: 1.15, // 低角度柔阳（室内主要靠灯 + 天光）
    sunElevation: 10,
    sunAzimuth: -124, // 太阳在**窗前**（three +z 侧偏左）：azim 使 dir.z>0 才能照进玻璃窗
    sunColor: 0xffd8b4, // 低角度暖阳（清晨冷暖对比：暖光 + 冷影）
    sunGlow: 0.55,
    skyTop: 0x8fb4d8, // 冷蓝上层
    skyHorizon: 0xffdcc8, // 暖橙地平线
    hemiIntensity: 0.34,
    hemiSky: 0xc6d8ea,
    hemiGround: 0x4a3a30,
    ambientIntensity: 0.1,
    ambientColor: 0xffe9d6,
    fogColor: 0xd9e4ee,
    fogDensity: 0.012,
    exposure: 0.90,
    lampIntensity: 1.15, // 室内灯还亮着（清晨氛围）
    lampColor: 0xffc98a,
    emissiveIntensity: 1.1,
    starOpacity: 0.0,
    dustOpacity: 0.55,
    lampMaterialsEmissive: 0xffd9a0,
  },
  {
    key: 'noon',
    label: '正午',
    hour: 12.5,
    sunIntensity: 2.0,
    sunElevation: 64,
    sunAzimuth: 190, // 太阳在窗外（three +z 侧）高处：正午强直射能打进来
    sunColor: 0xfff4e2,
    sunGlow: 0.28,
    skyTop: 0x6fa8dc,
    skyHorizon: 0xe6f2fb,
    hemiIntensity: 0.4,
    hemiSky: 0xcfe4f5,
    hemiGround: 0x6b5744,
    ambientIntensity: 0.12,
    ambientColor: 0xfff3e4,
    fogColor: 0xeaf2f8,
    fogDensity: 0.0055,
    exposure: 0.86,
    lampIntensity: 0.42, // 正午室内暖灯几乎看不出
    lampColor: 0xffd2a0,
    emissiveIntensity: 0.35,
    starOpacity: 0.0,
    dustOpacity: 0.85,
    lampMaterialsEmissive: 0xffe0b0,
  },
  {
    key: 'dusk',
    label: '黄昏',
    hour: 18.0,
    sunIntensity: 1.5,
    sunElevation: 13,
    sunAzimuth: 148, // 黄昏斜射（窗外偏右、低角度长影）
    sunColor: 0xffb277, // 橙金斜射（不做纯橙，避免整屋染色）
    sunGlow: 0.9,
    skyTop: 0x4d4d86,
    skyHorizon: 0xff9a5c,
    hemiIntensity: 0.26,
    hemiSky: 0xffc79a,
    hemiGround: 0x33241d,
    ambientIntensity: 0.08,
    ambientColor: 0xffcfa8,
    fogColor: 0xf0b088,
    fogDensity: 0.013,
    exposure: 0.88,
    lampIntensity: 1.9,
    lampColor: 0xffbe7d,
    emissiveIntensity: 1.8,
    starOpacity: 0.06,
    dustOpacity: 0.7,
    lampMaterialsEmissive: 0xffd9a0,
  },
  {
    key: 'night',
    label: '夜晚',
    hour: 21.5,
    sunIntensity: 0.16, // 月光
    sunElevation: 36,
    sunAzimuth: 142,
    sunColor: 0x8fa8d6,
    sunGlow: 0.12,
    skyTop: 0x070d1e, // 深蓝
    skyHorizon: 0x1a2340,
    hemiIntensity: 0.075,
    hemiSky: 0x2a3a5c,
    hemiGround: 0x14100c,
    ambientIntensity: 0.03,
    ambientColor: 0x9fb4d8,
    fogColor: 0x141c30,
    fogDensity: 0.016,
    exposure: 0.62,
    lampIntensity: 4.0, // 室内暖灯全亮（夜景主要光源）
    lampColor: 0xffc07a,
    emissiveIntensity: 2.6,
    starOpacity: 0.85,
    dustOpacity: 0.3,
    lampMaterialsEmissive: 0xffd29a,
  },
];

/* ─────────────────────────────── 天气 6 态 ─────────────────────────────── */
export const WEATHER_STATES = {
  clear: {
    key: 'clear',
    label: '晴天',
    rainLevel: 0, // 0 无 1 小 2 中 3 大
    cloudCover: 0.04,
    sunMul: 1.0,
    hemiMul: 1.0,
    ambientMul: 1.0,
    fogMul: 0.85,
    exposureAdd: 0.0,
    lampMul: 1.0,
    windowDropsOpacity: 0.0,
    wetness: 0.0,
    lightning: false,
    starVisibility: 1.0,
    skyDesaturate: 0.0,
    windStrength: 0.15,
  },
  cloudy: {
    key: 'cloudy',
    label: '多云',
    rainLevel: 0,
    cloudCover: 0.90,   // ⑤ 多云更浓（用户要求朦胧感加强）
    sunMul: 0.34,
    hemiMul: 1.18,
    ambientMul: 1.35,
    fogMul: 2.6,      // ⑤ 多云雾感 1.6 → 2.6
    exposureAdd: -0.04,
    lampMul: 1.5,
    windowDropsOpacity: 0.05,
    wetness: 0.06,
    lightning: false,
    starVisibility: 0.35,
    skyDesaturate: 0.72,
    windStrength: 0.4,
  },
  rain_light: {
    key: 'rain_light',
    label: '小雨',
    rainLevel: 1,
    cloudCover: 0.9,
    sunMul: 0.22,
    hemiMul: 1.05,
    ambientMul: 1.35,
    fogMul: 2.4,
    exposureAdd: -0.06,
    lampMul: 1.9,
    windowDropsOpacity: 0.42,
    wetness: 0.45,
    lightning: false,
    starVisibility: 0.12,
    skyDesaturate: 0.8,
    windStrength: 0.5,
  },
  rain_med: {
    key: 'rain_med',
    label: '中雨',
    rainLevel: 2,
    cloudCover: 0.95,
    sunMul: 0.13,
    hemiMul: 0.92,
    ambientMul: 1.3,
    fogMul: 3.2,
    exposureAdd: -0.09,
    lampMul: 2.2,
    windowDropsOpacity: 0.68,
    wetness: 0.72,
    lightning: false,
    starVisibility: 0.04,
    skyDesaturate: 0.86,
    windStrength: 0.65,
  },
  rain_heavy: {
    key: 'rain_heavy',
    label: '大雨',
    rainLevel: 3,
    cloudCover: 1.0,
    sunMul: 0.07,
    hemiMul: 0.8,
    ambientMul: 1.22,
    fogMul: 4.1,
    exposureAdd: -0.13,
    lampMul: 2.5,
    windowDropsOpacity: 0.86,
    wetness: 0.92,
    lightning: false,
    starVisibility: 0.0,
    skyDesaturate: 0.92,
    windStrength: 0.85,
  },
  storm: {
    key: 'storm',
    label: '雷阵雨',
    rainLevel: 3,
    cloudCover: 1.0,
    sunMul: 0.045,
    hemiMul: 0.62,
    ambientMul: 1.1,
    fogMul: 4.8,
    exposureAdd: -0.09,
    lampMul: 2.8,
    windowDropsOpacity: 0.94,
    wetness: 1.0,
    lightning: true,
    starVisibility: 0.0,
    skyDesaturate: 0.96,
    windStrength: 1.0,
  },
};

export const WEATHER_ORDER = ['clear', 'cloudy', 'rain_light', 'rain_med', 'rain_heavy', 'storm'];

/* 光照参数默认值（manifest 缺失时兜底） */
export const LIGHT_DEFAULTS = {
  sun: { intensity: 2.15, elevation: 45, azimuth: 0, color: 0xfff0d8, shadowMapSize: 2048 },
  // 天花板要亮：hemi 的 groundColor 是暖木色 #B98A5E（见 _buildLights），强度给足
  // ★ 下调：hemi 负责"填平"整个空间，是最容易导致室内一片白的项
  hemi: { intensity: 0.62 },
  // ★ 下调：ambient 是纯加色，叠上去墙/地立刻失去层次
  ambient: { intensity: 0.28 },
  // 室内：three r160 物理单位。吊灯点光 25–45（distance 6 / decay 2）、壁灯 10–18
  // ★ 下调：32 cd 在 6m 距离上会把整间店打爆；14 cd 才接近 Blender 的 150W 吊灯观感
  lamp: {
    intensity: 7.4,
    color: 0xffc98a,
    distance: 5.0,
    decay: 2,
    maxCount: 6,
  },
  // 窗光（街道方向射入的 DirectionalLight）+ 窗内侧 RectAreaLight
  windowSky: { intensity: 1.7, color: 0xdce9ff },
  windowRect: { intensity: 4.2 },
  barSpot: { intensity: 10.0 },
  displaySpot: { intensity: 3.7 },
  // 女仆补光离脸仅 0.5–0.8m，物理衰减 intensity/d² 下单靠 14 就会把人打成纯白 → 这个量级必须小
  maidFill: { intensity: 1.9 },
  // 书架补光：夜里书架在墙角，室内灯照不到，会整片看不清。
  // 这盏灯只在 lampOn 时开，位置在书架前上方，朝下打，范围小、不溢到别处。
  shelfFill: { intensity: 1.9, color: 0xffd6ab, distance: 2.6, decay: 2 },
};

/* 灯位兜底（CONTRACT §1.1，Blender z-up；本文件内部转 three） */
export const LAMP_ANCHOR_FALLBACK = {
  pendants: [
    [-2.9, -2.0, 2.22],
    [-2.55, 1.05, 2.22],
    [1.85, 1.5, 2.22],
  ],
  wall_lamps: [
    [-3.86, -2.35, 1.95],
    [3.86, -2.05, 1.95],
    [0.6, 2.88, 1.95],
  ],
};

const ROOM_FALLBACK_BLENDER = { x: [-4, 4], y: [-3, 3], z: [0, 3] };

/* HDRI 兜底（manifest.light_rig.hdri 缺失时用；文件由 asset-scout 提供） */
export const HDRI_FALLBACK = {
  base_url: 'assets/hdri/',
  by_phase: {
    morning: 'kiara_2_sunrise_1k.hdr',
    noon: 'kloppenheim_06_puresky_1k.hdr',
    dusk: 'evening_road_01_puresky_1k.hdr',
    night: 'dikhololo_night_1k.hdr',
  },
  strength: { morning: 0.85, noon: 1.0, dusk: 0.75, night: 0.35 },
};

/* ─────────────────────────────── 数学小工具 ─────────────────────────────── */
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const lerp = (a, b, t) => a + (b - a) * t;
const smoothstep = (t) => {
  const x = clamp(t, 0, 1);
  return x * x * (3 - 2 * x);
};
const DEG = Math.PI / 180;

function colorOf(hex) {
  return new THREE.Color(hex);
}

/** 色温 K → 近似 RGB（网页只需要「暖/冷」的观感，用近似黑体色） */
export function kelvinToColor(kelvin) {
  const t = clamp(kelvin, 1000, 12000) / 100;
  let r, g, b;
  if (t <= 66) {
    r = 255;
    g = clamp(99.4708025861 * Math.log(t) - 161.1195681661, 0, 255);
    b = t <= 19 ? 0 : clamp(138.5177312231 * Math.log(t - 10) - 305.0447927307, 0, 255);
  } else {
    r = clamp(329.698727446 * Math.pow(t - 60, -0.1332047592), 0, 255);
    g = clamp(288.1221695283 * Math.pow(t - 60, -0.0755148492), 0, 255);
    b = 255;
  }
  return new THREE.Color(r / 255, g / 255, b / 255);
}

/** 把 0–24h 映射到 4 个锚点之间的平滑插值（跨午夜时环绕） */
export function segmentForHour(hour) {
  const h = ((hour % 24) + 24) % 24;
  const anchors = PHASE_ANCHORS;
  // 构造环形段列表：最后一段从 night 跨到 morning(+24)
  let a = null;
  let b = null;
  for (let i = 0; i < anchors.length; i++) {
    const cur = anchors[i];
    const nxt = anchors[(i + 1) % anchors.length];
    let hCur = cur.hour;
    let hNxt = nxt.hour + (i === anchors.length - 1 ? 24 : 0);
    let hh = h;
    if (h < anchors[0].hour) hh = h + 24;
    if (hh >= hCur && hh < hNxt) {
      a = cur;
      b = nxt;
      break;
    }
  }
  if (!a) {
    a = anchors[anchors.length - 1];
    b = anchors[0];
  }
  const hCur = a.hour;
  const hNxt = b.hour + (b.hour < a.hour ? 24 : 0);
  const hh = h < a.hour ? h + 24 : h;
  const raw = hNxt === hCur ? 0 : (hh - hCur) / (hNxt - hCur);
  return { a, b, t: smoothstep(raw), rawT: clamp(raw, 0, 1) };
}

/** 最近的时间档（给音量/音频 setTimePhase 用） */
export function nearestPhase(hour) {
  const h = ((hour % 24) + 24) % 24;
  let best = PHASE_ANCHORS[0];
  let bestD = Infinity;
  for (const p of PHASE_ANCHORS) {
    let d = Math.abs(h - p.hour);
    if (d > 12) d = 24 - d;
    if (d < bestD) {
      bestD = d;
      best = p;
    }
  }
  return best;
}

export function formatHour(hour) {
  const h = ((hour % 24) + 24) % 24;
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  const hh2 = mm === 60 ? (hh + 1) % 24 : hh;
  const mm2 = mm === 60 ? 0 : mm;
  return `${String(hh2).padStart(2, '0')}:${String(mm2).padStart(2, '0')}`;
}

/** 时间标签：「清晨 07:00」 */
export function phaseLabel(hour) {
  return `${nearestPhase(hour).label} ${formatHour(hour)}`;
}

function asHex(v) {
  if (v == null) return null;
  if (typeof v === 'number') return v;
  if (Array.isArray(v) && v.length >= 3) {
    // 允许 [r,g,b] 0–1 或 0–255
    const norm = v.every((x) => x <= 1.0001) ? v.map((x) => Math.round(x * 255)) : v.map(Math.round);
    return (norm[0] << 16) | (norm[1] << 8) | norm[2];
  }
  if (typeof v === 'string') {
    const s = v.trim().replace(/^#/, '');
    if (/^[0-9a-fA-F]{6}$/.test(s)) return parseInt(s, 16);
  }
  return null;
}

/* ─────────────────────────────── manifest 合并 ─────────────────────────────── */

/**
 * 支持两种 manifest 写法，二选一自动识别：
 *
 * A)「Blender 量纲」—— cbuild/clight 实际产出的写法：
 *    light_rig.phases.morning = {sun_rot:[rx,ry,rz], sun_energy, sun_color:"#RRGGBB",
 *                                sky:"#RRGGBB", ambient, exposure, indoor, fog}
 *    light_rig.weather.clear  = {sun_mult, ambient_mult, fog, cloud_cover, rain}
 *    light_rig.anchors        = {sun_target, pendants:[{pos,r}], wall_lamps:[[x,y,z]], indoor_base:{...}}
 *
 * B)「网页量纲」—— 本文件 PHASE_ANCHORS / WEATHER_STATES 的字段名直接覆盖。
 *
 * 识别规则：phase 里出现 sun_energy / sun_rot 即判 A；weather 里出现 sun_mult / rain 即判 A。
 * 两种写法都容错：单个字段缺失就保留默认值。
 */
function isBlenderPhase(p) {
  return !!p && (p.sun_energy != null || p.sun_rot != null || p.indoor != null);
}
function isBlenderWeather(w) {
  return !!w && (w.sun_mult != null || w.rain != null || w.cloud_cover != null);
}

/** Blender 太阳 Euler(rx,ry,rz) → 网页的「仰角/方位角」（degrees） */
function sunRotToElevAzim(rot) {
  const rx = ((rot[0] || 0) * Math.PI) / 180;
  const rz = ((rot[2] || 0) * Math.PI) / 180;
  // Blender 太阳默认朝 -Z；travel = Rz*Rx*(0,0,-1)，toLight = -travel
  // toLight_blender = ( sin(rz)sin(rx), -cos(rz)sin(rx), cos(rx) )
  // 转 three (x, z, -y) → (sin(rz)sin(rx), cos(rx), cos(rz)sin(rx))
  const tlx = Math.sin(rz) * Math.sin(rx);
  const tly = Math.cos(rx);
  const tlz = Math.cos(rz) * Math.sin(rx);
  const elevation = (Math.asin(clamp(tly, -1, 1)) * 180) / Math.PI;
  const azimuth = (Math.atan2(tlx, -tlz) * 180) / Math.PI;
  return { elevation, azimuth };
}

/** Blender 太阳能量（W/m²）→ three DirectionalLight 强度 */
const SUN_ENERGY_SCALE = 0.62;

/** 0–1 的 rain 强度 → 雨量档 0/1/2/3 */
function rainRatioToLevel(r) {
  if (!(r > 0.02)) return 0;
  if (r <= 0.3) return 1;
  if (r <= 0.65) return 2;
  return 3;
}

/** Blender 写法的 phase → 网页锚点 */
function adaptBlenderPhase(base, p) {
  const out = { ...base };
  if (p.sun_rot) {
    const ea = sunRotToElevAzim(p.sun_rot);
    out.sunElevation = ea.elevation;
    out.sunAzimuth = ea.azimuth;
  }
  if (typeof p.sun_energy === 'number') out.sunIntensity = p.sun_energy * SUN_ENERGY_SCALE;
  const sc = asHex(p.sun_color);
  if (sc != null) out.sunColor = sc;
  const sky = asHex(p.sky);
  if (sky != null) {
    out.skyTop = sky;
    // 地平线：向同色相的高亮端偏（同色系更接近 Blender 的天空梯度观感）
    const c = new THREE.Color(sky);
    const hsl = {};
    c.getHSL(hsl);
    out.skyHorizon = new THREE.Color().setHSL(hsl.h, Math.min(1, hsl.s * 0.62), Math.min(0.95, hsl.l * 1.5 + 0.16)).getHex();
    out.fogColor = out.skyHorizon;
  }
  if (typeof p.ambient === 'number') {
    // Blender 环境光强度 → 半球光 + 环境光。
    // 关键：夜间必须压得很低，否则夜景会像下午（暖灯失去主导权）。
    // 用非线性映射（幂次）让弱环境光更快衰减。
    const a = clamp(p.ambient, 0, 1.2);
    // ★ 原系数 1.45 / 0.55 会把室内填成一片白；按 Blender 的 HDRI 强度(0.62~0.70)
    //   与 AgX 压缩后的观感，改成 0.62 / 0.26
    // ④ 系数 0.62 → 0.55：压低填充光，阴影更实，观感更接近 Blender AgX
    out.hemiIntensity = clamp(0.06 + Math.pow(a, 1.7) * 0.50, 0.06, 0.56);
    out.ambientIntensity = clamp(0.02 + Math.pow(a, 2.0) * 0.26, 0.02, 0.26);
    // 半球光的地面反照色：白天暖木色，夜间压暗（否则天花发白）
    out.hemiGround = lerp(0x1c1612, 0xb98a5e, clamp(a * 1.25, 0, 1));
  }
  // 曝光：manifest 的 exposure 是**相对基准的档位偏移**（-0.35…+0.15）。
  // 基准按太阳高度给：夜 0.55 / 黄昏 0.9 / 白天 0.72（Lead 定稿要求），再用偏移微调。
  const sunE = p.sun_energy || 0;
  // ★ Blender 的 exposure 是**档位(stops)**：three 的 toneMappingExposure = 2^stops。
  //   morning -0.15 → 0.90 / noon -0.45 → 0.73 / dusk -0.20 → 0.87 / night +0.10 → 1.07
  //   再乘一个 0.95 的整体系数，让 ACES 的中调不过亮
  const stops = (p.exposure == null ? 0 : p.exposure);
  // ★ 系数 0.95 会让 noon 得到 0.695，比旧公式(0.515)还亮 35% —— 方向反了。
  //   改 0.78 → noon 0.570 / morning 0.703 / dusk 0.679 / night 0.836
  // 系数 0.62 保证四个时段都比旧公式更暗（旧：晨0.825/午0.515/昏0.800/夜0.650）
  // 新：晨0.559/午0.454/昏0.540/夜0.665，配合已下调 45%~56% 的灯光强度
  // 系数 0.60 保证四个时段都比旧公式更暗：
  //   晨 0.825→0.541 / 午 0.515→0.439 / 昏 0.800→0.523 / 夜 0.650→0.643
  out.exposure = clamp(Math.pow(2, stops) * 0.60, 0.36, 0.96);
  if (typeof p.indoor === 'number') {
    // 室内灯强度：以 LIGHT_DEFAULTS.lamp.intensity(=32) 为 1.0 基准（indoor 0.25–1.75）
    out.lampIntensity = LIGHT_DEFAULTS.lamp.intensity * p.indoor;
  }
  // 窗光：白天强、夜里**完全关掉**（Lead 要求夜间只保留暖灯）
  const sunN0 = clamp(sunE / 6.5, 0, 1);
  out.windowSkyIntensity = sunN0 < 0.08 ? 0.0 : 0.4 + sunN0 * 4.2;
  out.windowRectIntensity = sunN0 < 0.08 ? 0.0 : 0.6 + sunN0 * 9.0;
  if (typeof p.fog === 'number' && p.fog > 0) out.fogDensity = p.fog;
  // 夜间/黄昏的星空、尘埃：按太阳强度推断（Blender 不给这些，属于网页表现层）
  const sunN = clamp(out.sunIntensity / 3.0, 0, 1);
  out.starOpacity = base.starOpacity * clamp(1 - sunN * 1.15, 0, 1);
  out.dustOpacity = base.dustOpacity;
  out.sunGlow = base.sunGlow;
  // 晴天尘埃要淡（Lead 反馈：350 pts 像下雪）；夜间/逆光反而更多
  out.dustOpacity = base.dustOpacity * (0.28 + 0.5 * clamp(1 - sunN, 0, 1));
  return out;
}

/** Blender 写法的 weather → 网页天气表 */
function adaptBlenderWeather(base, w) {
  const out = { ...base };
  if (typeof w.sun_mult === 'number') out.sunMul = w.sun_mult;
  if (typeof w.ambient_mult === 'number') {
    out.ambientMul = w.ambient_mult;
    out.hemiMul = w.ambient_mult;
  }
  if (typeof w.cloud_cover === 'number') out.cloudCover = clamp(w.cloud_cover, 0, 1);
  if (typeof w.fog === 'number') {
    // manifest 给的是**绝对**雾密度（Blender 侧量级 0–0.05）；保留绝对值，由 computeTargetState
    // 直接换算成 three 的 FogExp2 density（不再乘相位基线，避免夜景叠成浓雾）
    out.fogAbsolute = w.fog;
    out.fogMul = 1;
  }
  if (typeof w.rain === 'number') {
    out.rainLevel = rainRatioToLevel(w.rain);
    out.wetness = clamp(w.rain * 1.05, 0, 1);
    out.windowDropsOpacity = Math.min(0.95, w.rain * 1.05);
    out.lightning = w.rain >= 1 && out.cloudCover >= 1; // storm 由 key 决定，见 resolveLightData
  }
  out.starVisibility = clamp(1 - (out.cloudCover || 0) * 1.15, 0, 1);
  return out;
}

function mergePhase(base, extra) {
  if (!extra || typeof extra !== 'object') return base;
  if (isBlenderPhase(extra)) return adaptBlenderPhase(base, extra);
  const out = { ...base };
  for (const [k, v] of Object.entries(extra)) {
    if (k === 'key' || k === 'label') {
      out[k] = v;
      continue;
    }
    if (k.endsWith('Color') || k.endsWith('Sky') || k.endsWith('Ground') || k.endsWith('Horizon') || k === 'sunColor' || k === 'lampColor' || k === 'ambientColor' || k === 'fogColor' || k === 'lampMaterialsEmissive' || k === 'skyTop') {
      const hex = asHex(v);
      if (hex != null) out[k] = hex;
      continue;
    }
    if (typeof v === 'number') out[k] = v;
    else if (typeof v === 'boolean') out[k] = v;
    else if (typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v)) out[k] = parseFloat(v);
  }
  return out;
}

function mergeWeather(base, extra) {
  if (!extra || typeof extra !== 'object') return base;
  if (isBlenderWeather(extra)) return adaptBlenderWeather(base, extra);
  const out = { ...base };
  for (const [k, v] of Object.entries(extra)) {
    if (k === 'key' || k === 'label') {
      out[k] = v;
      continue;
    }
    if (typeof v === 'number' || typeof v === 'boolean' || typeof v === 'string') out[k] = v;
  }
  return out;
}

/** 由 manifest 得到「生效」的时间锚点 / 天气表 / 灯光参数 */
export function resolveLightData(manifest) {
  const rig = (manifest && (manifest.light_rig || manifest.lightRig)) || {};
  const phasesIn = rig.phases || rig.timePhases || null;
  const weatherIn = rig.weather || rig.weathers || null;

  const phases = PHASE_ANCHORS.map((base) => {
    const key = base.key;
    const extra = phasesIn && (phasesIn[key] || phasesIn[base.label] || null);
    return mergePhase(base, extra);
  });

  // 允许 manifest 直接给 4 段时间数组，缺的保留默认
  if (Array.isArray(phasesIn)) {
    for (const item of phasesIn) {
      const idx = phases.findIndex((p) => p.key === item.key || p.label === item.label);
      if (idx >= 0) phases[idx] = mergePhase(phases[idx], item);
    }
  }

  const weather = {};
  let maxFogAbsolute = 0;
  for (const key of WEATHER_ORDER) {
    const raw = weatherIn ? weatherIn[key] : null;
    weather[key] = mergeWeather(WEATHER_STATES[key], raw);
    // storm 强制点亮闪电；其余按 cloud/rain 推断
    weather[key].lightning = key === 'storm';
    weather[key].label = WEATHER_STATES[key].label;
    if (weather[key].fogAbsolute) maxFogAbsolute = Math.max(maxFogAbsolute, weather[key].fogAbsolute);
  }
  // 绝对雾密度归一：全部按 manifest 的绝对量级直接用（不归一化），
  // fogAbsolute 留在 weather[key] 里供 computeTargetState 取用。
  void maxFogAbsolute;

  // 多云：朦胧感定向加强（用户要求）
  // manifest 里 cloudy 是 cloud 0.85 / fog 0.012；这里加 云量+0.05、雾 x1.45
  // 仍严格低于 rain_light(0.020)，保持 多云 < 小雨 < 中雨 的层次。
  if (weather.cloudy) {
    weather.cloudy.cloudCover = Math.min(0.92, (weather.cloudy.cloudCover || 0.85) + 0.05);
    if (weather.cloudy.fogAbsolute) weather.cloudy.fogAbsolute *= 1.45;
  }

  const la = rig.anchors || {};
  const light = {
    sun: { ...LIGHT_DEFAULTS.sun, ...(rig.sun || {}) },
    hemi: { ...LIGHT_DEFAULTS.hemi, ...(rig.hemi || {}) },
    ambient: { ...LIGHT_DEFAULTS.ambient, ...(rig.ambient || {}) },
    lamp: { ...LIGHT_DEFAULTS.lamp, ...(rig.lamp || rig.lamps || {}) },
    sunTarget: la.sun_target || null,
    indoorBase: la.indoor_base || null,
  };
  if (rig.sun && rig.sun.shadowMapSize) light.sun.shadowMapSize = rig.sun.shadowMapSize;

  // 灯位：优先 light_rig.anchors（真实 manifest），退回 manifest.anchors（CONTRACT 风格）
  const anchors = (manifest && (manifest.anchors || {})) || {};
  const pendants = coerceAnchorList(la.pendants || anchors.pendants || anchors.pendant_lights);
  const walls = coerceAnchorList(la.wall_lamps || anchors.wall_lamps || anchors.wallLamps);
  const spots = coerceAnchorList(la.bar_spots || anchors.bar_spots);
  const lampPositions = [];
  for (const p of pendants.length ? pendants : LAMP_ANCHOR_FALLBACK.pendants) lampPositions.push(p);
  const maxCount = Math.max(1, Math.min(6, light.lamp.maxCount | 0));
  for (const p of walls.length ? walls : LAMP_ANCHOR_FALLBACK.wall_lamps) {
    if (lampPositions.length >= maxCount) break;
    lampPositions.push(p);
  }
  // 名额还有剩 → 用吧台射灯补（真实 manifest 给了 3 个）
  for (const p of spots) {
    if (lampPositions.length >= maxCount) break;
    lampPositions.push(p);
  }
  light.lamp.positions = lampPositions.slice(0, maxCount);
  light.barSpots = coerceAnchorList(la.bar_spots || anchors.bar_spots);
  light.displaySpots = coerceAnchorList(la.display_spots || anchors.display_spots);
  light.maidFill = toTriple(la.maid_fill || anchors.maid_fill);
  light.windowRectXZ = rig.window || anchors.window || null;
  // 窗光/室内灯的逐时段倍率（manifest v3 新增）
  light.indoorScale = la.indoor_scale || null;
  light.windowSkyDay = la.window_sky_day || null;
  light.windowSkyPos = toTriple(la.window_sky);
  light.windowSkyTarget = toTriple(la.window_sky_target);
  return {
    phases,
    weather,
    light,
    schema: phasesIn && isBlenderPhase(Object.values(phasesIn)[0]) ? 'blender' : 'web',
  };
}

function toTriple(v) {
  if (!Array.isArray(v) || v.length < 2) return null;
  return [Number(v[0]) || 0, Number(v[1]) || 0, Number(v[2]) || 0];
}

function coerceAnchorList(v) {
  if (!Array.isArray(v)) return [];
  const out = [];
  for (const item of v) {
    if (Array.isArray(item) && item.length >= 2) {
      out.push([Number(item[0]) || 0, Number(item[1]) || 0, Number(item[2]) || 0]);
    } else if (item && typeof item === 'object') {
      const p = item.pos || item.position || item.point || null;
      if (Array.isArray(p) && p.length >= 2) out.push([Number(p[0]) || 0, Number(p[1]) || 0, Number(p[2]) || 0]);
    }
  }
  return out;
}

/* ─────────────────────────────── 目标状态计算 ─────────────────────────────── */

const COLOR_KEYS = [
  'sunColor',
  'skyTop',
  'skyHorizon',
  'hemiSky',
  'hemiGround',
  'ambientColor',
  'fogColor',
  'lampColor',
  'emissiveColor',
];

function blankState() {
  const st = {
    sunIntensity: 0,
    sunElevation: 0,
    sunAzimuth: 0,
    sunColor: new THREE.Color(),
    skyTop: new THREE.Color(),
    skyHorizon: new THREE.Color(),
    sunGlow: 0,
    hemiIntensity: 0,
    hemiSky: new THREE.Color(),
    hemiGround: new THREE.Color(),
    ambientIntensity: 0,
    ambientColor: new THREE.Color(),
    fogColor: new THREE.Color(),
    fogDensity: 0,
    exposure: 1,
    lampIntensity: 0,
    lampColor: new THREE.Color(),
    lampDistance: 7.5,
    lampDecay: 2,
    emissiveIntensity: 0,
    emissiveColor: new THREE.Color(),
    starOpacity: 0,
    dustOpacity: 0,
    // 窗光 / 射灯 / 补光（r160 物理单位）
    windowSkyIntensity: 0,
    windowRectIntensity: 0,
    barSpotIntensity: 0,
    displaySpotIntensity: 0,
    maidFillIntensity: 0,
    shelfFillIntensity: 0,
    // 天气侧
    rainLevel: 0,
    cloudCover: 0,
    windStrength: 0,
    windowDropsOpacity: 0,
    wetness: 0,
    lightning: false,
    sunMul: 1,
    phaseKey: 'morning',
    phaseLabel: '清晨',
    weatherKey: 'clear',
    weatherLabel: '晴天',
    hour: 7,
  };
  return st;
}

const _cA = new THREE.Color();
const _cB = new THREE.Color();

/**
 * 逐字段插值。颜色字段的值可能是 THREE.Color 也可能是 0xRRGGBB 数字（来自锚点表），
 * 统一按 Color 处理并写回 out 里已存在的 Color 实例（不换对象引用，便于外部持有）。
 */
function lerpState(a, b, t, out) {
  for (const k in out) {
    const va = a[k];
    const vb = b[k];
    const isColorSlot = out[k] instanceof THREE.Color;
    if (isColorSlot) {
      if (va instanceof THREE.Color) _cA.copy(va);
      else if (typeof va === 'number') _cA.setHex(va);
      if (vb instanceof THREE.Color) _cB.copy(vb);
      else if (typeof vb === 'number') _cB.setHex(vb);
      out[k].copy(_cA).lerp(_cB, t);
    } else if (typeof va === 'number' && typeof vb === 'number') {
      out[k] = lerp(va, vb, t);
    } else {
      out[k] = t < 0.5 ? va : vb;
    }
  }
  return out;
}

const GRAY_TOP = 0x6b7480;
const GRAY_HORIZON = 0xa6adb6;
const STORM_TOP = 0x2b3138;
const STORM_HORIZON = 0x4b525b;

/** 计算某小时 + 某天气的「目标光照状态」 */
export function computeTargetState(hour, weatherKey, lightData) {
  const data = lightData || resolveLightData(null);
  const phases = data.phases;
  const seg = segmentForHour(hour);
  const A = phases.find((p) => p.key === seg.a.key) || phases[0];
  const B = phases.find((p) => p.key === seg.b.key) || phases[0];

  const st = lerpState(A, B, seg.t, blankState());
  st.phaseKey = seg.t < 0.5 ? A.key : B.key;
  st.phaseLabel = seg.t < 0.5 ? A.label : B.label;
  st.hour = ((hour % 24) + 24) % 24;

  const w = data.weather[weatherKey] || data.weather.clear;
  st.weatherKey = w.key;
  st.weatherLabel = w.label;

  // 天气对光照的乘性影响
  st.sunIntensity = st.sunIntensity * w.sunMul;
  st.hemiIntensity = st.hemiIntensity * w.hemiMul;
  st.ambientIntensity = st.ambientIntensity * w.ambientMul;
  st.lampIntensity = st.lampIntensity * w.lampMul;
  // 雾：manifest 给的是**绝对** FogExp2 密度（晴天 0 / 大雨 0.05），直接用；
  // 晴天为 0 时退回一个极小基线，保证「远处街道」仍有一点空气透视，不是死平的
  if (w.fogAbsolute != null) {
    st.fogDensity = w.fogAbsolute > 0 ? w.fogAbsolute : Math.min(st.fogDensity, 0.0035);
  } else {
    st.fogDensity = st.fogDensity * w.fogMul;
  }
  // 曝光上限从 2.0 收窄到 1.15：2.0 会让天空/窗户过曝发白（用户反馈"闪瞎眼"）。
  // 下限 0.4 保证夜晚不会全黑。
  st.exposure = clamp(st.exposure + w.exposureAdd, 0.40, 1.15);
  st.emissiveIntensity = st.emissiveIntensity * lerp(1, 1.35, w.cloudCover);
  st.starOpacity = st.starOpacity * w.starVisibility;

  // 云层压暗天空 + 去饱和（向灰蓝靠）
  const cc = clamp(w.cloudCover, 0, 1);
  st.skyTop.lerp(new THREE.Color(w.lightning ? STORM_TOP : GRAY_TOP), cc * 0.72);
  st.skyHorizon.lerp(new THREE.Color(w.lightning ? STORM_HORIZON : GRAY_HORIZON), cc * 0.78);
  st.fogColor.lerp(st.skyHorizon, 0.55 * cc);
  st.sunColor.lerp(new THREE.Color(0xdfe6ef), cc * 0.35);

  // 体量光/暖度：雨夜灯更暖
  st.lampColor.lerp(new THREE.Color(0xffb067), cc * 0.3);

  // 天气侧参数直接透传
  st.rainLevel = w.rainLevel;
  st.cloudCover = w.cloudCover;
  st.windStrength = w.windStrength;
  st.windowDropsOpacity = w.windowDropsOpacity;
  st.wetness = w.wetness;
  st.lightning = !!w.lightning;

  // 灯光默认参数（distance/decay 来自 manifest）
  st.lampDistance = data.light.lamp.distance;
  st.lampDecay = data.light.lamp.decay;

  // 窗光（方向光 + 窗内 RectAreaLight）：随天气压暗
  st.windowSkyIntensity =
    (st.windowSkyIntensity != null ? st.windowSkyIntensity : LIGHT_DEFAULTS.windowSky.intensity) * lerp(1, 0.22, cc);
  st.windowRectIntensity =
    (st.windowRectIntensity != null ? st.windowRectIntensity : LIGHT_DEFAULTS.windowRect.intensity) * lerp(1, 0.18, cc);
  // ══════════════════════════════════════════════════════════════
  // ⑤ 开灯规则（用户明确要求）
  //   「除了黄昏到凌晨开灯，其余时间不开灯；下雨和多云天气也开灯」
  // ──────────────────────────────────────────────────────────────
  const hh = ((hour % 24) + 24) % 24;
  const duskToDawn = (hh >= 16.5 || hh < 6.0) ||
                     st.phaseKey === 'dusk' || st.phaseKey === 'night';
  const GLOOMY = /^(cloudy|rain_light|rain_med|rain_heavy|storm)$/;
  const weatherNeedsLight = GLOOMY.test(st.weatherKey || '');
  const lampOn = (duskToDawn || weatherNeedsLight) ? 1 : 0;
  st.lampOn = lampOn;

  if (!lampOn) {
    // 白天 + 晴/多云以外的好天气 → 室内灯全关，只靠天光
    st.lampIntensity = 0;
    st.emissiveIntensity = 0;      // 灯罩不发光
  }

  // 室内灯的整体缩放（与 lampIntensity 联动）
  const lampN = clamp((st.lampIntensity || 0) / (LIGHT_DEFAULTS.lamp.intensity || 32), 0, 4);
  st.barSpotIntensity = LIGHT_DEFAULTS.barSpot.intensity * clamp(lampN * 1.45, 0.04, 2.2) * lampOn;
  st.displaySpotIntensity = LIGHT_DEFAULTS.displaySpot.intensity * clamp(lampN * 1.1, 0.04, 2.0) * lampOn;
  // 女仆补光：**极小**。它离女仆脸只有 0.5–0.8m，按物理衰减 intensity/d² 极易把她打成纯白
  // （实测 14 的强度在 0.8m 处 ≈ 22，直接把脸爆成 #FFFFFF）。这里给 0.6–1.6 的量级。
  st.maidFillIntensity = LIGHT_DEFAULTS.maidFill.intensity * clamp(0.25 + lampN * 0.35, 0.15, 0.9) * (lampOn ? 1 : 0.35);
  // 书架补光：只在开灯时给，避免白天过曝；夜里书架在墙角，室内灯照不到
  st.shelfFillIntensity = LIGHT_DEFAULTS.shelfFill.intensity * clamp(0.35 + lampN * 0.55, 0.25, 1.0) * lampOn;

  const ph = phases.find((p) => p.key === st.phaseKey);
  const emHex = ph && ph.lampMaterialsEmissive != null ? ph.lampMaterialsEmissive : 0xffd9a0;
  if (typeof emHex === 'number') st.emissiveColor.setHex(emHex);
  return st;
}

/* ─────────────────────────────── 天空穹顶 ─────────────────────────────── */

const SKY_VERT = /* glsl */ `
varying vec3 vDir;
void main() {
  vDir = normalize(position);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
}
`;

const SKY_FRAG = /* glsl */ `
uniform vec3 uTop;
uniform vec3 uHorizon;
uniform vec3 uSunColor;
uniform vec3 uSunDir;
uniform float uGlow;
uniform float uExponent;
uniform float uStars;
varying vec3 vDir;

// 便宜的星点：对方向做网格哈希
float starField(vec3 d) {
  vec3 p = floor(d * 220.0);
  float h = fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
  float bright = smoothstep(0.9975, 1.0, h);
  return bright;
}

void main() {
  vec3 d = normalize(vDir);
  float h = clamp(d.y * 0.5 + 0.5, 0.0, 1.0);
  float band = pow(clamp(d.y, 0.0, 1.0), 1.0 / max(uExponent, 0.08));
  vec3 col = mix(uHorizon, uTop, clamp(band, 0.0, 1.0));
  // 地平线以下压暗（作为室外地面背景）
  col = mix(col * 0.55, col, smoothstep(-0.08, 0.02, d.y));

  // 太阳/月亮光晕
  float c = max(dot(d, normalize(uSunDir)), 0.0);
  col += uSunColor * uGlow * (pow(c, 12.0) * 0.9 + pow(c, 3.0) * 0.12);

  // 星点（夜晚可见）
  if (uStars > 0.001) {
    float s = starField(d);
    col += vec3(0.9, 0.95, 1.0) * s * uStars * smoothstep(0.0, 0.25, d.y) * 1.6;
  }

  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}
`;

export class WeatherSystem {
  /**
   * @param {THREE.Scene} scene
   * @param {THREE.WebGLRenderer} renderer
   * @param {{manifest?:object, roomThree?:{x:[number,number],y:[number,number],z:[number,number]}, wetMaterials?:THREE.Material[]}} opts
   */
  constructor(scene, renderer, opts = {}) {
    this.scene = scene;
    this.renderer = renderer;
    this.manifest = opts.manifest || null;
    this.data = resolveLightData(this.manifest);
    this.room = opts.roomThree || {
      x: [-4, 4],
      y: [0, 3],
      z: [-3, 3],
    };

    this.hour = 7.0;
    this.weatherKey = 'clear';
    this.targetState = computeTargetState(this.hour, this.weatherKey, this.data);
    this.state = { ...this.targetState };
    // 状态里的 THREE.Color 需要独立实例，避免与 target 共享
    for (const k in this.state) {
      if (this.state[k] instanceof THREE.Color) this.state[k] = this.state[k].clone();
    }

    this._damping = 0.55; // 秒，约 1.5s 完成 95%
    this._timeScale = 1; // 过渡加速（测试时用 1/0 立即到位）
    this._flash = 0;
    this._flashDecay = 6.5;
    this._dirtySky = true;
    this._lastEnvKey = '';

    // HDRI：manifest.light_rig.hdri 或兜底表；贴图按需加载 + 缓存
    this.hdriCfg = this._resolveHdriConfig();
    this.hdriCache = new Map(); // phaseKey -> { equirect, pmrem, strength }
    this.hdriLoading = new Map();
    this.hdriUsedPhase = null;
    this.hdriStats = { loads: 0, bytes: 0, loadMs: 0, failures: [] };
    this.envTargetIntensity = 1.0;
    this._envCurIntensity = 0;

    this._buildLights();
    this._buildSky();
    this._applyState(this.state, true);
    this._buildEnvironment();
  }

  /** manifest.light_rig.hdri → 生效配置（文件缺失时降级到兜底表） */
  _resolveHdriConfig() {
    const rig = (this.manifest && this.manifest.light_rig) || {};
    const h = rig.hdri || {};
    const byPhase = { ...HDRI_FALLBACK.by_phase, ...(h.by_phase || h.phases || {}) };
    const strength = { ...HDRI_FALLBACK.strength, ...(h.strength || {}) };
    const base = h.base_url || h.baseUrl || HDRI_FALLBACK.base_url;
    return { base_url: base.endsWith('/') ? base : base + '/', by_phase: byPhase, strength, enabled: h.enabled !== false };
  }

  /** 异步预载当前时段 HDRI（不阻塞首帧；加载好自动应用） */
  loadHdriForPhase(phaseKey) {
    if (!this.hdriCfg || !this.hdriCfg.enabled) return Promise.resolve(null);
    const file = this.hdriCfg.by_phase[phaseKey];
    if (!file) return Promise.resolve(null);
    if (this.hdriCache.has(phaseKey)) return Promise.resolve(this.hdriCache.get(phaseKey));
    if (this.hdriLoading.has(phaseKey)) return this.hdriLoading.get(phaseKey);

    const url = this.hdriCfg.base_url + file;
    const t0 = performance.now();
    const p = new Promise((resolve) => {
      const loader = new RGBELoader();
      loader.load(
        url,
        (tex) => {
          tex.mapping = THREE.EquirectangularReflectionMapping;
          tex.colorSpace = THREE.LinearSRGBColorSpace;
          let pmremTex = null;
          try {
            const pm = new THREE.PMREMGenerator(this.renderer);
            pm.compileEquirectangularShader();
            pmremTex = pm.fromEquirectangular(tex).texture;
            pm.dispose();
          } catch (e) {
            console.warn('[weather] HDRI PMREM 失败:', e && e.message);
          }
          const rec = {
            equirect: tex,
            pmrem: pmremTex,
            strength: this.hdriCfg.strength[phaseKey] != null ? this.hdriCfg.strength[phaseKey] : 1,
            bytes: tex.image && tex.image.data ? tex.image.data.byteLength : 0,
            loadMs: Math.round(performance.now() - t0),
            url,
          };
          this.hdriCache.set(phaseKey, rec);
          this.hdriLoading.delete(phaseKey);
          this.hdriStats.loads++;
          this.hdriStats.bytes += rec.bytes;
          this.hdriStats.loadMs += rec.loadMs;
          if (this.hdriUsedPhase === phaseKey) this._activateHdri(phaseKey);
          resolve(rec);
        },
        undefined,
        (err) => {
          this.hdriLoading.delete(phaseKey);
          const msg = `${url}: ${(err && err.message) || 'load error'}`;
          this.hdriStats.failures.push(msg);
          console.warn('[weather] HDRI 加载失败，保留程序化天空:', msg);
          resolve(null);
        }
      );
    });
    this.hdriLoading.set(phaseKey, p);
    return p;
  }

  _activateHdri(phaseKey) {
    const rec = this.hdriCache.get(phaseKey);
    if (!rec) return;
    this.hdriUsedPhase = phaseKey;
    this.activeHdri = rec;
    // 注意：r160 没有 backgroundIntensity，HDRI 若当 background 就无法压暗 → 夜里窗外亮白。
    // 所以 HDRI **只**给 scene.environment（IBL 反射/环境光），可见天空交给程序化穹顶。
    this.scene.environment = rec.pmrem || null;
    this.envTargetIntensity = rec.strength;
    this._applyEnvIntensityToMaterials();
    if (typeof this.onHdriChanged === 'function') {
      try {
        this.onHdriChanged(rec);
      } catch (e) {
        console.warn('[weather] onHdriChanged 失败:', e && e.message);
      }
    }
  }

  /* ---------- 构建 ---------- */
  _buildLights() {
    // RectAreaLight 需要 LTC 查找表初始化（一次即可，全局生效）
    try {
      RectAreaLightUniformsLib.init();
    } catch (e) {
      console.warn('[weather] RectAreaLightUniformsLib.init 失败:', e && e.message);
    }
    const L = this.data.light;
    const sun = new THREE.DirectionalLight(new THREE.Color(L.sun.color), L.sun.intensity);
    sun.name = 'LT_Sun';
    sun.castShadow = true;
    sun.shadow.mapSize.set(L.sun.shadowMapSize || 2048, L.sun.shadowMapSize || 2048);
    const sc = sun.shadow.camera;
    // 阴影范围覆盖室内 + 窗外街道近景（单位 m）
    sc.left = -8.5;
    sc.right = 8.5;
    sc.top = 8.5;
    sc.bottom = -8.5;
    sc.near = 0.5;
    sc.far = 40;
    sun.shadow.bias = -0.0006;
    sun.shadow.normalBias = 0.02;
    sun.shadow.radius = 3;
    sun.target.position.set(0, 1.2, 0);
    this.scene.add(sun);
    this.scene.add(sun.target);
    this.sun = sun;

    // 半球光：sky = 时段天空色，ground = 暖木色（#B98A5E）——天花板要靠 groundColor 反照
    const hemi = new THREE.HemisphereLight(0xffffff, 0xb98a5e, L.hemi.intensity);
    hemi.name = 'LT_Hemisphere';
    hemi.position.set(0, 4, 0);
    this.scene.add(hemi);
    this.hemi = hemi;

    // 环境光（暖白）：补死黑，尤其女仆脸与天花
    const amb = new THREE.AmbientLight(0xfff0e0, L.ambient.intensity);
    amb.name = 'LT_Ambient';
    this.scene.add(amb);
    this.ambient = amb;

    // 窗光：从街道方向（three +z）射入的「大面积天光」方向光，不投影（避免玻璃投出硬影）
    const win = new THREE.DirectionalLight(0xdce9ff, 0.0);
    win.name = 'LT_WindowSky';
    win.castShadow = false;
    win.position.set(0, 1.7, this.room.z[1] + 6.0);
    win.target.position.set(0, 1.1, this.room.z[0] + 2.2);
    this.scene.add(win);
    this.scene.add(win.target);
    this.windowSkyLight = win;

    // 窗内侧 RectAreaLight：模拟整扇窗的天空漫射（不投影，需要 LTC 查找表）
    try {
      const winAnchor = this.data.light.windowRect || null;
      const wx = winAnchor ? winAnchor : this._windowRectFromManifest();
      const rect = new THREE.RectAreaLight(0xdce9ff, 0, wx.width, wx.height);
      rect.name = 'LT_WindowRect';
      rect.position.set(wx.x, wx.y, wx.z);
      rect.lookAt(wx.x, wx.y, wx.z - 1); // 朝室内（−z）
      this.scene.add(rect);
      this.windowRectLight = rect;
      this._windowRect = wx;
    } catch (e) {
      console.warn('[weather] RectAreaLight 创建失败，退回方向光:', e && e.message);
      this.windowRectLight = null;
    }

    // 室内点光（≤6，带距离衰减）：manifest anchors 的吊灯 + 壁灯
    // 灯的类型按位置区分：吊灯（z≈2.1）→ PointLight；其余按壁灯小强度处理
    this.lamps = [];
    const lampCfg = L.lamp;
    const indoorBase = L.indoorBase || null;
    for (let i = 0; i < lampCfg.positions.length; i++) {
      const p3 = lampCfg.positions[i];
      // Blender (x,y,z) → three (x, z, y)
      const pos = new THREE.Vector3(p3[0], p3[2], -p3[1]);
      const l = new THREE.PointLight(new THREE.Color(lampCfg.color), lampCfg.intensity, lampCfg.distance, lampCfg.decay);
      l.position.copy(pos);
      l.castShadow = false; // 点光不投影（性能），阴影由主方向光提供
      l.userData.isPendant = p3[2] > 1.9; // 高度的灯当吊灯
      l.name = `LT_Indoor_${i}`;
      this.scene.add(l);
      this.lamps.push(l);
    }

    // 吧台射灯（SpotLight）：从天花打向台面，manifest light_rig.anchors.bar_spots
    this.spots = [];
    const spotsIn = this.data.light.barSpots || [];
    for (let i = 0; i < spotsIn.length; i++) {
      const p = spotsIn[i];
      const sp = new THREE.SpotLight(0xffd9a0, 0, 4.2, Math.PI / 5.2, 0.55, 2);
      sp.position.set(p[0], p[2], -p[1]);
      sp.target.position.set(p[0], 0.95, -p[1]);
      sp.castShadow = false;
      sp.name = `LT_BarSpot_${i}`;
      this.scene.add(sp);
      this.scene.add(sp.target);
      this.spots.push(sp);
    }

    // 展示柜射灯（DownLight 近似，用 SpotLight 从上往下）
    this.displaySpots = [];
    const dspIn = this.data.light.displaySpots || [];
    for (let i = 0; i < dspIn.length; i++) {
      const p = dspIn[i];
      const sp = new THREE.SpotLight(0xffe0b8, 0, 3.0, Math.PI / 6, 0.6, 2);
      sp.position.set(p[0], p[2], -p[1]);
      sp.target.position.set(p[0], 0.6, -p[1]);
      sp.castShadow = false;
      sp.name = `LT_DisplaySpot_${i}`;
      this.scene.add(sp);
      this.scene.add(sp.target);
      this.displaySpots.push(sp);
    }

    // 女仆补光（面光近似：从门口方向来的柔光点光，强度随时段）
    this.maidFill = null;
    const mf = this.data.light.maidFill || null;
    if (mf) {
      const fl = new THREE.PointLight(0xffe2c4, 0, 3.2, 2);
      fl.position.set(mf[0], mf[2], -mf[1]);
      fl.castShadow = false;
      fl.name = 'LT_MaidFill';
      this.scene.add(fl);
      this.maidFill = fl;
    }

    // 灯光材质（GLB 灯罩 emissive）稍后由 scene.js 注入
    // 书架补光：Blender 书架 x[-3.93,-2.29] y[2.33,2.98] z[0,2.05]
    // → three x[-3.93,-2.29] y[0,2.05] z[-2.98,-2.33]
    // 灯放在书架正前方偏上，朝书架打，范围小、不外溢
    this.shelfFill = null;
    {
      const cfg = LIGHT_DEFAULTS.shelfFill;
      const fl = new THREE.PointLight(new THREE.Color(cfg.color), 0, cfg.distance, cfg.decay);
      fl.position.set(-3.05, 1.55, -2.02);
      fl.castShadow = false;
      fl.name = 'LT_ShelfFill';
      this.scene.add(fl);
      this.shelfFill = fl;
    }

    this.lampMaterials = [];
  }

  /** 由 manifest light_rig.window（x/z 范围）+ 前墙位置推出窗内侧矩形光参数 */
  _windowRectFromManifest() {
    const w = this.data.light.windowRectXZ || { x: [-3.7, 0.35], z: [0.72, 2.58] };
    const width = Math.max(0.4, w.x[1] - w.x[0]);
    const height = Math.max(0.4, w.z[1] - w.z[0]);
    return {
      x: (w.x[0] + w.x[1]) / 2,
      y: (w.z[0] + w.z[1]) / 2,
      z: (this.room ? this.room.z[1] : 3.0) - 0.12,
      width,
      height,
    };
  }

  _buildSky() {
    const geo = new THREE.SphereGeometry(90, 32, 20);
    this.skyUniforms = {
      uTop: { value: new THREE.Color(0x8fb4d8) },
      uHorizon: { value: new THREE.Color(0xffd9c2) },
      uSunColor: { value: new THREE.Color(0xffd2a1) },
      uSunDir: { value: new THREE.Vector3(0, 0.4, -1).normalize() },
      uGlow: { value: 0.5 },
      uExponent: { value: 0.55 },
      uStars: { value: 0 },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.skyUniforms,
      vertexShader: SKY_VERT,
      fragmentShader: SKY_FRAG,
      side: THREE.BackSide,
      depthWrite: false,
      depthTest: false,
      fog: false,
    });
    const sky = new THREE.Mesh(geo, mat);
    sky.name = 'WEB_SkyDome';
    sky.renderOrder = -1000;
    sky.frustumCulled = false;
    this.scene.add(sky);
    this.sky = sky;
  }

  /** 用天空穹顶烘一张环境贴图，供玻璃/大理石/湿路面反射（**不**挂到 scene.environment：
   *  r160 没有 environmentIntensity，全场景 IBL 会把墙/地面整体提亮成一片灰白。
   *  这里只产出贴图，由 scene.js 按材质类别选择性 envMap。） */
  _buildEnvironment() {
    if (this.activeHdri) return; // HDRI 已接管天空/环境
    try {
      const pmrem = new THREE.PMREMGenerator(this.renderer);
      pmrem.compileEquirectangularShader();
      const tmp = new THREE.Scene();
      const skyClone = new THREE.Mesh(this.sky.geometry, this.sky.material.clone());
      skyClone.material.depthTest = true;
      skyClone.scale.setScalar(0.25);
      tmp.add(skyClone);
      const groundGeo = new THREE.CircleGeometry(80, 24);
      const groundMat = new THREE.MeshBasicMaterial({ color: this._horizonColorForEnv() });
      const ground = new THREE.Mesh(groundGeo, groundMat);
      ground.rotation.x = -Math.PI / 2;
      ground.position.y = -1.2;
      tmp.add(ground);
      const rt = pmrem.fromScene(tmp, 0.04, 0.5, 200);
      const old = this.envRT;
      this.envRT = rt;
      this.envTexture = rt.texture;
      if (old && old !== rt) old.dispose();
      this.envScene = tmp;
      this._envGroundMat = groundMat;
      skyClone.material.dispose();
      ground.geometry.dispose();
      pmrem.dispose();
      if (typeof this.onEnvChanged === 'function') {
        try {
          this.onEnvChanged(this.envTexture);
        } catch (e) {
          console.warn('[weather] onEnvChanged 回调失败:', e && e.message);
        }
      }
    } catch (e) {
      console.warn('[weather] env map 生成失败，跳过:', e && e.message);
    }
  }

  _horizonColorForEnv() {
    return this.state.skyHorizon.clone().multiplyScalar(0.8);
  }

  setLampMaterials(mats) {
    this.lampMaterials = (mats || []).filter((m) => m && (m.emissive || m.color));
    this._applyLampMaterials(this.state);
  }

  _applyLampMaterials(st) {
    // 变化检测：灯材质只在强度/开灯状态真的变了才写，避免每帧遍历 100+ 材质
    {
      const sig = (st.lampOn ? 1 : 0) + '|' +
        Math.round((st.emissiveIntensity || 0) * 100) + '|' +
        Math.round((st.lampIntensity || 0) * 100);
      if (this._lampSig === sig) return;
      this._lampSig = sig;
    }
    for (const m of this.lampMaterials) {
      if (!m) continue;
      if (m.emissive) {
        m.emissive.copy(st.emissiveColor);
        m.emissiveIntensity = st.emissiveIntensity;
      }
      // ★ 注意：这里**不能**每帧设 m.needsUpdate = true。
      //   emissive / emissiveIntensity 只是 uniform，不需要重编译；
      //   每帧置 true 会让这三个灯罩材质的 shader 每帧重建，
      //   表现为「某些视角贴图闪烁、光影跳变」（用户反馈）。
      if (m.toneMapped !== true) m.toneMapped = true;
    }
  }

  /** 湿路面材质（scene.js 传入），weather 调 roughness / envMapIntensity */
  setWetMaterials(list) {
    this.wetMaterials = (list || []).map((m) => ({
      mat: m,
      roughness: m.roughness != null ? m.roughness : 0.8,
      envIntensity: m.envMapIntensity != null ? m.envMapIntensity : 1,
    }));
    this._applyWetness(this.state.wetness);
  }

  _applyWetness(w) {
    // 变化检测：湿度影响 roughness/metalness，量化到 0.01 再比较
    const wq = Math.round((w || 0) * 100) / 100;
    if (this._wetSig === wq) return;
    this._wetSig = wq;
    w = wq;
    if (!this.wetMaterials) return;
    for (const rec of this.wetMaterials) {
      const m = rec.mat;
      if (!m) continue;
      if (m.roughness != null) m.roughness = lerp(rec.roughness, Math.min(0.16, rec.roughness * 0.25), w);
      if ('envMapIntensity' in m) m.envMapIntensity = lerp(rec.envIntensity, rec.envIntensity + 1.6, w);
      if (m.metalness != null && m.userData && m.userData.webWetMetal) {
        m.metalness = lerp(0.0, 0.35, w);
      }
    }
  }

  /* ---------- 外部控制 ---------- */
  setHour(hour) {
    this.hour = clamp(hour, 0, 24);
    this._retarget();
  }

  setWeather(key) {
    if (!this.data.weather[key]) return false;
    this.weatherKey = key;
    this._retarget();
    return true;
  }

  /** 立即到位（验证脚本/首帧用） */
  snap() {
    this._retarget();
    Object.assign(this.state, this.targetState);
    for (const k in this.state) {
      if (this.targetState[k] instanceof THREE.Color) this.state[k] = this.targetState[k].clone();
    }
    this._applyState(this.state, true);
    return this.state;
  }

  _retarget() {
    this.targetState = computeTargetState(this.hour, this.weatherKey, this.data);
  }

  flash(strength = 1) {
    this._flash = Math.min(2.2, this._flash + strength);
  }
  get flashLevel() {
    return this._flash;
  }

  /* ---------- 每帧 ---------- */
  update(dt) {
    dt = Math.min(dt, 0.1);
    this._envDt = dt;
    const tau = this._damping / Math.max(this._timeScale, 0.001);
    const k = tau <= 0.0001 ? 1 : 1 - Math.exp(-dt / tau);

    // 数值 / 颜色阻尼插值
    for (const key in this.state) {
      const tgt = this.targetState[key];
      const cur = this.state[key];
      if (cur instanceof THREE.Color && tgt instanceof THREE.Color) cur.lerp(tgt, k);
      else if (typeof cur === 'number' && typeof tgt === 'number') this.state[key] = lerp(cur, tgt, k);
      else if (typeof tgt === 'boolean' || typeof tgt === 'string') this.state[key] = tgt;
    }

    if (this._flash > 0.0005) this._flash *= Math.exp(-dt * this._flashDecay);
    else this._flash = 0;

    this._applyState(this.state, false);
  }

  _applyState(st, force) {
    // 保底：overrides 可能未被外部初始化，这里兜住，避免 ov.exposure 读 undefined
    if (!this.overrides) this.overrides = {};
    // 运行时调参钩子（调光/验收脚本用；不影响正常 UI 流程）
    // 例：window.__CAFE__.weather.overrides = { lampMul: 0.15, maidFill: 0.3, hemi: 0.5 }
    const ov = this.overrides;
    const mul = (v) => (typeof v === 'number' && isFinite(v) ? v : 1);
    // 太阳（方向 + 强度 + 颜色）
    const elev = st.sunElevation * DEG;
    const azim = st.sunAzimuth * DEG;
    const R = 9.0;
    const dir = new THREE.Vector3(
      Math.sin(azim) * Math.cos(elev),
      Math.sin(elev),
      -Math.cos(azim) * Math.cos(elev)
    ).normalize();
    this.sun.position.copy(dir).multiplyScalar(R);
    this.sun.color.copy(st.sunColor);
    this.sun.intensity = st.sunIntensity * (1 + this._flash * 2.2);

    this.hemi.color.copy(st.hemiSky);
    this.hemi.groundColor.copy(st.hemiGround);
    this.hemi.intensity = st.hemiIntensity * (1 + this._flash * 0.6) * mul(ov && ov.hemi);

    this.ambient.color.copy(st.ambientColor);
    this.ambient.intensity = (st.ambientIntensity + this._flash * 0.5) * mul(ov && ov.ambient);

    for (let i = 0; i < this.lamps.length; i++) {
      const l = this.lamps[i];
      l.color.copy(st.lampColor);
      l.intensity = st.lampIntensity * (1 + this._flash * 0.25) * mul(ov && ov.lampMul);
      if (l.distance !== st.lampDistance) l.distance = st.lampDistance;
      if (l.decay !== st.lampDecay) l.decay = st.lampDecay;
    }

    // 窗光：DirectionalLight 从街道方向射入（不投影，玻璃不会挡光）
    if (this.windowSkyLight) {
      const wl = this.windowSkyLight;
      wl.intensity = st.windowSkyIntensity * mul(ov && ov.windowSky);
      // 颜色：白天取时段太阳色的去饱和版，夜里偏冷
      wl.color.copy(st.sunColor).lerp(st.skyTop, 0.45);
    }
    if (this.windowRectLight) {
      const rl = this.windowRectLight;
      rl.intensity = st.windowRectIntensity * mul(ov && ov.windowRect);
      rl.color.copy(st.sunColor).lerp(st.skyTop, 0.35);
    }
    for (const sp of this.spots || []) sp.intensity = st.barSpotIntensity * (1 + this._flash * 0.15) * mul(ov && ov.spots);
    for (const sp of this.displaySpots || []) sp.intensity = st.displaySpotIntensity * mul(ov && ov.spots);
    if (this.maidFill) this.maidFill.intensity = st.maidFillIntensity * (1 + this._flash * 0.1) * mul(ov && ov.maidFill);
    if (this.shelfFill) this.shelfFill.intensity = st.shelfFillIntensity * (1 + this._flash * 0.08) * mul(ov && ov.shelfFill);

    // 天空
    this.skyUniforms.uTop.value.copy(st.skyTop);
    this.skyUniforms.uHorizon.value.copy(st.skyHorizon);
    this.skyUniforms.uSunColor.value.copy(st.sunColor);
    this.skyUniforms.uSunDir.value.copy(dir);
    this.skyUniforms.uGlow.value = st.sunGlow;
    this.skyUniforms.uStars.value = st.starOpacity;

    // HDRI 天空 + 环境 IBL（r160 没有 scene.environmentIntensity → 调每个材质的 envMapIntensity）
    this._applyEnvironment(st);

    // 雾
    if (!this.scene.fog) this.scene.fog = new THREE.FogExp2(st.fogColor.getHex(), st.fogDensity);
    const fog = this.scene.fog;
    fog.color.copy(st.fogColor);
    fog.density = Math.max(st.fogDensity, 0.0008);

    // 曝光
    this.renderer.toneMappingExposure = st.exposure * mul(ov && ov.exposure);

    // 灯罩发光材质
    this._applyLampMaterials(st);
    this._applyWetness(st.wetness);

    // 程序化环境贴图的兜底重烘（有 HDRI 时不再需要，见 _applyEnvironment）
    if (this.envScene && !this.activeHdri) {
      const key = `${st.phaseKey}|${st.weatherKey}`;
      if (key !== this._lastEnvKey) {
        this._lastEnvKey = key;
        this._envGroundMat.color.copy(this._horizonColorForEnv());
        this._skyEnvUpdate = true;
      }
    }
  }

  /* ---------- HDRI 环境 ---------- */
  /**
   * 每帧调用：切换时段时按需加载 HDRI；天气压暗环境强度；强度阻尼过渡。
   *
   * 关键决策（r160 限制）：three r160 的 Scene **没有** backgroundIntensity / environmentIntensity
   * （实测 `'environmentIntensity' in scene === false`），所以：
   *   - HDRI **只用于 scene.environment（IBL）**，强度靠逐材质 envMapIntensity 缩放；
   *   - **可见天空**仍用程序化天空穹顶（自带 uTop/uHorizon/uStars，可随时段/天气连续变化，
   *     夜景才是深蓝、雨天才是灰云），避免「夜里窗外一片亮白」。
   */
  _applyEnvironment(st) {
    // 1) 目标时段变了 → 触发加载（已缓存则立刻切）
    const wantPhase = st.phaseKey;
    if (wantPhase && wantPhase !== this.hdriWantPhase) {
      this.hdriWantPhase = wantPhase;
      if (this.hdriCache.has(wantPhase)) this._activateHdri(wantPhase);
      else this.loadHdriForPhase(wantPhase);
    }

    // 2) 天空：始终用程序化穹顶（HDRI 不当 background）
    this.sky.visible = true;
    if (this.scene.background && this.scene.background.isTexture) this.scene.background = null;

    // 3) 环境强度 = HDRI 时段强度 × 天气衰减（阴雨天 IBL 也变弱）
    const rec = this.activeHdri;
    if (rec) {
      // 夜间 HDRI 再压一层到 ≤0.25：夜景 HDRI 本身偏亮，不压会让室内像下午（暖灯失去主导）
      // 夜晚环境强度下限从 0.25 提到 0.42：金属材质（metallic≥0.9 且无 MR 贴图）
      // 完全靠环境反射出亮，压到 0.25 会让酒瓶盖/吧台金属件渲染成纯黑块。
      const hdriK = st.phaseKey === 'night' ? Math.min(1, 0.42 / Math.max(rec.strength, 1e-3)) : 1;
      this.envTargetIntensity = rec.strength * hdriK * lerp(1.0, 0.45, clamp(st.cloudCover, 0, 1));
      // 夜间/阴沉时给一个绝对下限，避免金属件死黑
      const ENV_FLOOR = 0.30;
      if (this.envTargetIntensity < ENV_FLOOR) this.envTargetIntensity = ENV_FLOOR;
    } else {
      this.envTargetIntensity = 0;
    }

    // 4) 强度阻尼过渡（切时段/切天气都不闪）
    const target = this.envTargetIntensity;
    const dt = this._envDt != null ? this._envDt : 0.016;
    const tau = target > this._envCurIntensity ? 0.18 : 0.35; // 变亮快、变暗慢
    const kEnv = 1 - Math.exp(-dt / tau);
    this._envCurIntensity = lerp(this._envCurIntensity, target, kEnv);
    if (Math.abs(this._envCurIntensity - target) < 0.005) this._envCurIntensity = target;
    this._applyEnvIntensityToMaterials();
  }

  /** 统一缩放所有 PBR 材质的 envMapIntensity（r160 无 scene.environmentIntensity）
   *  材质可带 userData.webEnvCap 作为上限（女仆皮肤/白布等避免被环境光冲白） */
  _applyEnvIntensityToMaterials() {
    const v = this._envCurIntensity;
    if (Math.abs(v - (this._lastEnvApplied || -1)) < 0.012 && this._envAppliedOnce) return;
    this._lastEnvApplied = v;
    this._envAppliedOnce = true;
    const visit = (m) => {
      if (!m || !('envMapIntensity' in m)) return;
      const cap = m.userData && m.userData.webEnvCap != null ? m.userData.webEnvCap : Infinity;
      m.envMapIntensity = Math.min(v, cap);
    };
    if (this.scene.environment) {
      this.scene.traverse((o) => {
        if (!o.isMesh || !o.material) return;
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        for (const m of mats) visit(m);
      });
    }
    if (this._extraEnvMaterials) for (const m of this._extraEnvMaterials) visit(m);
  }

  /** 外部（scene.js）在 GLB 挂载后告知需要参与 IBL 的材质（含占位场景材质） */
  setEnvMaterials(list) {
    this._extraEnvMaterials = (list || []).filter(Boolean);
    this._envAppliedOnce = false;
    this._applyEnvIntensityToMaterials();
  }

  /** 重烘环境贴图（scene.js 在状态稳定后调用，避免每帧 PMREM） */
  refreshEnvironment() {
    if (this.activeHdri) return; // 有 HDRI 时不再用程序化 env
    if (!this.skipEnvRebuild) this._buildEnvironment();
  }

  info() {
    const s = this.state;
    const t = this.targetState;
    return {
      hour: +this.hour.toFixed(2),
      hourLabel: formatHour(this.hour),
      phase: s.phaseKey,
      phaseLabel: s.phaseLabel,
      weather: this.weatherKey,
      weatherLabel: s.weatherLabel,
      sunIntensity: +s.sunIntensity.toFixed(3),
      targetSunIntensity: +t.sunIntensity.toFixed(3),
      sunElevation: +s.sunElevation.toFixed(1),
      exposure: +this.renderer.toneMappingExposure.toFixed(3),
      targetExposure: +t.exposure.toFixed(3),
      fogDensity: +this.scene.fog.density.toFixed(4),
      lampIntensity: +s.lampIntensity.toFixed(2),
      lampCount: this.lamps.length,
      rainLevel: s.rainLevel,
      windowDropsOpacity: +s.windowDropsOpacity.toFixed(2),
      wetness: +s.wetness.toFixed(2),
      skyTop: '#' + s.skyTop.getHexString(),
      skyHorizon: '#' + s.skyHorizon.getHexString(),
    };
  }
}

export default WeatherSystem;
