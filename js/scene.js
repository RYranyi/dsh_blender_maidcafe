/**
 * js/scene.js — 场景装配层：GLB 加载（含预检修补与无模型降级）、相机 / OrbitControls、
 * AABB 碰撞与房间钳制、粒子特效（雨 / 水花 / 蒸汽 / 尘埃）、室外天空与街道。
 *
 * 坐标口径（重要）：
 *   CONTRACT 里所有数值都是 **Blender z-up**（x 右、y 街道向、z 上）。
 *   glTF 导出后是 **Y-up**，标准映射：three.x = bx, three.y = bz, three.z = -by。
 *   → 房间 three 空间：x ∈ [-4,4]、y ∈ [0,3]、z ∈ [-3,3]；**街道/窗在 three.z = +3 面**。
 *   本文件对外仍然用 Blender 数字（与 CONTRACT 对齐），内部用 toThree() 转换。
 *
 * 依赖注入：房间尺寸 / 机位 / 碰撞盒 / 灯位 / 特效材质名，全部来自 scene_manifest.json；
 * 缺失时用本文件顶部 DEFAULT_* 常量兜底（数值即 CONTRACT §1.1 / §8）。
 */

import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';

/* ─────────────────────────── 兜底常量（CONTRACT 口径） ─────────────────────────── */
export const DEFAULT_ROOM_BLENDER = { x: [-4, 4], y: [-3, 3], z: [0, 3], wall_t: 0.16 };

export const DEFAULT_CAM_BLENDER = {
  pos: [1.85, -2.55, 1.55],
  target: [-1.2, 0.5, 1.05],
};

/** 房间钳制（Blender 口径，与 CONTRACT §10 一致：y 是进深方向、z 是高度） */
export const DEFAULT_CLAMP_BLENDER = { x: [-3.9, 3.9], y: [-2.9, 2.9], z: [0.25, 2.85] };

export const DEFAULT_ANCHORS_BLENDER = {
  win_open: { x: [-3.7, 0.35], z: [0.72, 2.58] },
  door_open: { x: [1.15, 2.45], z: [0, 2.2] },
  wainscot_z: 0.95,
  maid_pos: [-1.7, 0.3, 0],
  tables: [
    [-2.95, -2.05],
    [-1.05, -2.1],
    [-3.25, 0.55],
    [-2.55, 1.95],
    [2.95, -1.7],
  ],
  stools: [
    [0.55, 0.82],
    [1.7, 0.82],
  ],
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
  street: { sidewalk: [-4.6, -3.0], road: [-9.0, -5.2], buildings: [-14.0, -9.6] },
};

export const DEFAULT_COLLIDERS_BLENDER = [
  { name: 'BAR_MAIN', aabb: [[-0.2, 1.15, 0], [3.7, 1.87, 0.95]], kind: 'solid' },
  { name: 'BAR_RETURN', aabb: [[2.98, 1.15, 0], [3.7, 2.95, 0.95]], kind: 'solid' },
  { name: 'BAR_BACK', aabb: [[-1.6, 2.55, 0], [2.7, 2.95, 0.9]], kind: 'solid' },
  { name: 'DISPLAY', aabb: [[-1.6, 1.25, 0], [-0.05, 1.95, 1.38]], kind: 'solid' },
  { name: 'BOOKSHELF', aabb: [[-3.95, 1.6, 0], [-3.35, 2.95, 2.05]], kind: 'solid' },
  { name: 'TABLE_01', aabb: [[-3.33, -2.43, 0], [-2.57, -1.67, 0.74]], kind: 'soft' },
  { name: 'TABLE_02', aabb: [[-1.43, -2.48, 0], [-0.67, -1.72, 0.74]], kind: 'soft' },
  { name: 'TABLE_03', aabb: [[-3.63, 0.17, 0], [-2.87, 0.93, 0.74]], kind: 'soft' },
  { name: 'TABLE_04', aabb: [[-2.93, 1.57, 0], [-2.17, 2.33, 0.74]], kind: 'soft' },
  { name: 'TABLE_05', aabb: [[2.57, -2.08, 0], [3.33, -1.32, 0.74]], kind: 'soft' },
  { name: 'MAID', aabb: [[-2.05, -0.05, 0], [-1.35, 0.65, 1.35]], kind: 'solid' },
];

export const DEFAULT_FX = {
  window_glass_material: 'MAT_Glass_Window',
  steam_node: 'MD_Steam_0',
  lamp_materials: ['MAT_Emissive_Shade', 'MAT_Emissive_Bulb', 'MAT_Emissive_LED'],
  floor_materials: ['MAT_Wood_Herringbone'],
  wet_materials: ['MAT_Wood_Herringbone', 'MAT_Marble_Top', 'MAT_Out_Concrete'],
  counter_materials: ['MAT_Marble_Top'],
};

const CAM_RADIUS = 0.25;
const RAIN_MAX = 12000;


const RAIN_HEIGHT = 12;
const RAIN_RADIUS = 12;
const DEG = Math.PI / 180;

/* ─────────────────────────── 坐标转换 ─────────────────────────── */
export const toThree = (bx, by, bz) => new THREE.Vector3(bx, bz, -by);

export function aabbToThree(aabb) {
  const [mn, mx] = aabb;
  const a = toThree(mn[0], mn[1], mn[2]);
  const b = toThree(mx[0], mx[1], mx[2]);
  return {
    min: new THREE.Vector3(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.min(a.z, b.z)),
    max: new THREE.Vector3(Math.max(a.x, b.x), Math.max(a.y, b.y), Math.max(a.z, b.z)),
  };
}

/** Blender 的 x/y/z 区间盒 → three 的 x/y/z 区间盒（y↔z 交换 + z 取反） */
function rangeBoxToThree(b) {
  const bx = b.x || DEFAULT_ROOM_BLENDER.x;
  const by = b.y || DEFAULT_ROOM_BLENDER.y;
  const bz = b.z || DEFAULT_ROOM_BLENDER.z;
  return {
    x: [Math.min(bx[0], bx[1]), Math.max(bx[0], bx[1])],
    y: [Math.min(bz[0], bz[1]), Math.max(bz[0], bz[1])],
    z: [-Math.max(by[0], by[1]), -Math.min(by[0], by[1])],
  };
}

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const lerp = (a, b, t) => a + (b - a) * t;

/* ───────────────── 1×1 白色 PNG（GLB 预修补时替换坏 texture 槽） ───────────────── */
const ONE_PX_PNG_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
let _onePxCache = null;
function onePixelPng() {
  if (!_onePxCache) {
    const bin = atob(ONE_PX_PNG_B64);
    _onePxCache = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) _onePxCache[i] = bin.charCodeAt(i);
  }
  return _onePxCache;
}

/* ─────────────────────────── 程序化贴图（无外部资源依赖） ─────────────────────────── */
function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

function canvasTexture(c) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.needsUpdate = true;
  return t;
}

/** 窗上雨滴 / 水痕贴图（透明底 + 白亮水珠） */
function proceduralWindowDrops() {
  const c = makeCanvas(512, 512);
  const g = c.getContext('2d');
  g.clearRect(0, 0, 512, 512);
  // 细水痕
  for (let i = 0; i < 90; i++) {
    const x = Math.random() * 512;
    const y = Math.random() * 512;
    const len = 20 + Math.random() * 140;
    const grad = g.createLinearGradient(x, y, x, y + len);
    grad.addColorStop(0, 'rgba(255,255,255,0.30)');
    grad.addColorStop(0.6, 'rgba(220,235,255,0.16)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    g.strokeStyle = grad;
    g.lineWidth = 1 + Math.random() * 2;
    g.beginPath();
    g.moveTo(x, y);
    g.lineTo(x + (Math.random() - 0.5) * 6, y + len);
    g.stroke();
  }
  // 水珠
  for (let i = 0; i < 260; i++) {
    const x = Math.random() * 512;
    const y = Math.random() * 512;
    const r = 1.2 + Math.random() * 4.5;
    const grd = g.createRadialGradient(x - r * 0.3, y - r * 0.3, 0, x, y, r);
    grd.addColorStop(0, 'rgba(255,255,255,0.55)');
    grd.addColorStop(0.55, 'rgba(210,232,255,0.28)');
    grd.addColorStop(1, 'rgba(200,225,255,0)');
    g.fillStyle = grd;
    g.beginPath();
    g.arc(x, y, r, 0, Math.PI * 2);
    g.fill();
  }
  return canvasTexture(c);
}

/** 圆形软边 sprite（蒸汽 / 尘埃共用） */
function softDiscTexture() {
  const c = makeCanvas(64, 64);
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, 'rgba(255,255,255,1)');
  grd.addColorStop(0.4, 'rgba(255,255,255,0.55)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 64, 64);
  return canvasTexture(c);
}

/** 水花圆环 */
function ringTexture() {
  const c = makeCanvas(64, 64);
  const g = c.getContext('2d');
  g.clearRect(0, 0, 64, 64);
  g.strokeStyle = 'rgba(255,255,255,0.9)';
  g.lineWidth = 4;
  g.beginPath();
  g.arc(32, 32, 22, 0, Math.PI * 2);
  g.stroke();
  const grd = g.createRadialGradient(32, 32, 12, 32, 32, 32);
  grd.addColorStop(0, 'rgba(255,255,255,0)');
  grd.addColorStop(0.7, 'rgba(255,255,255,0.25)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 64, 64);
  return canvasTexture(c);
}

/* ─────────────────────────── 雨（GPU 驱动） ─────────────────────────── */
const RAIN_VERT = /* glsl */ `
attribute float aSpeed;
attribute float aSeed;
uniform float uTime;
uniform float uHeight;
uniform float uSize;
uniform float uWind;
uniform vec3 uRoomMin;   // 室内盒（three 空间）：雨不得落进室内
uniform vec3 uRoomMax;
uniform float uWallZ;    // 前墙 z（three 空间）：z 小于它一律丢弃 = 绝不会进室内
varying float vAlpha;
void main() {
  vec3 p = position;
  // 竖直下落在 [0, uHeight] 内循环
  float y = mod(p.y - uTime * aSpeed, uHeight);
  p.y = y;
  // 风：整体偏移 + 每滴小摆动
  float sway = sin(uTime * 1.7 + aSeed * 6.2831) * 0.05;
  p.x += (uWind * (uHeight - y) * 0.06) + sway;
  p.z += cos(uTime * 1.1 + aSeed * 5.0) * 0.04;

  // 局部 -> 世界（Points 的 matrixWorld 只有平移）
  vec3 wp = p + modelMatrix[3].xyz;
  // 室内盒内直接隐藏（雨只在窗外 / 街道可见）
  float inside = step(uRoomMin.x, wp.x) * step(wp.x, uRoomMax.x)
               * step(uRoomMin.y, wp.y) * step(wp.y, uRoomMax.y)
               * step(uRoomMin.z, wp.z) * step(wp.z, uRoomMax.z);
  // 硬裁剪：只允许出现在前墙之外（z > uWallZ），任何相机角度都不会进室内
  if (inside > 0.5 || wp.z < uWallZ) {
    vAlpha = 0.0;
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0); // 裁到屏幕外
    gl_PointSize = 0.0;
    return;
  }

  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = max(-mv.z, 0.001);
  gl_PointSize = clamp(uSize * (9.0 / dist), 1.0, 26.0);
  vAlpha = smoothstep(52.0, 8.0, dist);
}
`;

const RAIN_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacity;
varying float vAlpha;
void main() {
  vec2 uv = gl_PointCoord;
  // 竖条：水平窄、竖直长（点精灵是正方形，靠 alpha 塑形）
  float dx = abs(uv.x - 0.5);
  float streak = smoothstep(0.085, 0.0, dx);
  float taper = smoothstep(0.0, 0.25, uv.y) * smoothstep(1.0, 0.75, uv.y);
  float a = streak * taper * uOpacity * vAlpha;
  if (a < 0.01) discard;
  gl_FragColor = vec4(uColor, a);
}
`;

/* ─────────────────────────────── 主类 ─────────────────────────────── */
export class CafeScene {
  /**
   * @param {{container: HTMLElement, manifest?: object|null, debug?: boolean, onProgress?: Function}} opts
   */
  constructor(opts = {}) {
    this.container = opts.container;
    this.debug = !!opts.debug;
    this.onProgress = opts.onProgress || (() => {});
    this.manifest = opts.manifest || null;
    this.glbUrl = opts.glbUrl || './scene/maid_cafe.glb';
    this.loadedFromGlb = false;
    this.glbError = null;
    this.loadingProgress = 0;
    this.warnings = [];
    this.missingAssets = [];

    this._ingestManifest(this.manifest);

    this._initRenderer();
    this._initCamera();
    this._initColliders();
    this._buildParticles();
    this._buildWindowOverlay();
    this._buildOutdoor();
    this._buildFlash();
  }

  /* ── manifest → 内部数据 ── */
  _ingestManifest(man) {
    const m = man || {};
    this.roomBlender = {
      ...DEFAULT_ROOM_BLENDER,
      ...(m.room || {}),
      x: (m.room && m.room.x) || DEFAULT_ROOM_BLENDER.x,
      y: (m.room && m.room.y) || DEFAULT_ROOM_BLENDER.y,
      z: (m.room && m.room.z) || DEFAULT_ROOM_BLENDER.z,
    };
    this.room = rangeBoxToThree(this.roomBlender);

    const anchors = m.anchors || {};
    this.anchorsBlender = { ...DEFAULT_ANCHORS_BLENDER, ...anchors };

    // manifest 的窗洞有两种写法：{x:[..],z:[..]} 或 [[minx,minz],[maxx,maxz]]
    if (Array.isArray(anchors.win) && Array.isArray(anchors.win[0])) {
      this.anchorsBlender.win_open = {
        x: [anchors.win[0][0], anchors.win[1][0]],
        z: [anchors.win[0][1], anchors.win[1][1]],
      };
    } else if (anchors.window && anchors.window.x && anchors.window.z) {
      this.anchorsBlender.win_open = { x: anchors.window.x, z: anchors.window.z };
    }
    if (Array.isArray(anchors.door) && Array.isArray(anchors.door[0])) {
      this.anchorsBlender.door_open = {
        x: [anchors.door[0][0], anchors.door[1][0]],
        z: [anchors.door[0][1], anchors.door[1][1]],
      };
    }
    // 街道：manifest 可能是 {sidewalk_y,road_y,bldg_y} 或 CONTRACT 的 {sidewalk,road,buildings}
    if (anchors.street) {
      const s = anchors.street;
      this.anchorsBlender.street = {
        sidewalk: s.sidewalk || s.sidewalk_y || DEFAULT_ANCHORS_BLENDER.street.sidewalk,
        road: s.road || s.road_y || DEFAULT_ANCHORS_BLENDER.street.road,
        buildings: s.buildings || s.bldg_y || DEFAULT_ANCHORS_BLENDER.street.buildings,
      };
    }
    // tables 可能是 [{name,x,y}] 形式
    if (Array.isArray(anchors.tables) && anchors.tables.length && typeof anchors.tables[0] === 'object') {
      this.anchorsBlender.tables = anchors.tables.map((t) => [t.x || 0, t.y || 0]);
    }

    this.camDefaultBlender = {
      pos: (anchors.cam_default && anchors.cam_default.pos) || DEFAULT_CAM_BLENDER.pos,
      target: (anchors.cam_default && anchors.cam_default.target) || DEFAULT_CAM_BLENDER.target,
    };
    this.camDefault = {
      pos: toThree(...this.camDefaultBlender.pos),
      target: toThree(...this.camDefaultBlender.target),
    };
    this.clampBlender = m.clamp || DEFAULT_CLAMP_BLENDER;
    this.clamp = rangeBoxToThree(this.clampBlender);

    this.fx = { ...DEFAULT_FX, ...(m.fx_nodes || {}) };
    this.materialNames = Array.isArray(m.material_names) ? m.material_names : null;
    this.counts = m.counts || null;

    const rig = m.light_rig || {};
    this._noShadowObjects = Array.isArray(rig.no_shadow_objects) ? rig.no_shadow_objects : [];
    this._litWindowObjects = Array.isArray(rig.lit_window_objects) ? rig.lit_window_objects : [];
    this._lightAnchors = rig.anchors || {};
    this._hdriCfg = rig.hdri || null;
    this._rainSurfaceY = this.fx.rain_surface_y; // Blender y（−4.6 = 人行道外缘）
  }

  /* ── renderer ── */
  _initRenderer() {
    // 固定最高画质（用户要求：不要画质选项，默认最好）
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      powerPreference: 'high-performance',
      alpha: false,
      stencil: false,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(
      this.container.clientWidth || window.innerWidth,
      this.container.clientHeight || window.innerHeight
    );
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    // 曝光由 weather.js 按时段/天气统一驱动（这里只给初值），
    // 以免两处各写一次导致某些视角过曝。
    renderer.toneMappingExposure = 0.80;   // 基准曝光（weather.js 会按时段改写）
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // r160 光照已是物理单位（r155 起 legacy lights 移除）；不再设 useLegacyLights 以免 deprecation 警告
    renderer.domElement.id = 'cafe-canvas';
    this.container.appendChild(renderer.domElement);

    // 容器尺寸一变就 resize —— 比只监听 window.resize 更可靠
    //（全屏切换、移动端地址栏收起、CSS 布局变动都能捕获）
    try {
      if (typeof ResizeObserver !== 'undefined' && this.container) {
        this._ro = new ResizeObserver(() => {
          // 合并到下一帧，避免 ResizeObserver loop 警告
          if (this._roPending) return;
          this._roPending = true;
          requestAnimationFrame(() => {
            this._roPending = false;
            this.resize();
          });
        });
        this._ro.observe(this.container);
      }
    } catch (e) { /* ignore */ }
    this.renderer = renderer;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x141c30);
    this.clock = new THREE.Clock();
  }

  _initCamera() {
    const aspect =
      (this.container.clientWidth || window.innerWidth) /
      (this.container.clientHeight || window.innerHeight || 1);
    this.camera = new THREE.PerspectiveCamera(58, aspect, 0.05, 220);
    this.camera.position.copy(this.camDefault.pos);
    this.camera.lookAt(this.camDefault.target);

    const controls = new OrbitControls(this.camera, this.renderer.domElement);
    controls.target.copy(this.camDefault.target);
    controls.enableDamping = true;
    controls.dampingFactor = 0.075;
    controls.rotateSpeed = 0.62;
    controls.zoomSpeed = 0.7;
    controls.panSpeed = 0.6;
    controls.screenSpacePanning = false;
    controls.minDistance = 0.45;
    controls.maxDistance = 6.2;
    controls.minPolarAngle = 8 * DEG;
    controls.maxPolarAngle = 86 * DEG;
    controls.zoomToCursor = false;
    controls.update();
    this.controls = controls;

    // 目标点限制在房间内（避免把视角拽出墙外）
    this._targetClamp = {
      x: [this.clamp.x[0] + 0.3, this.clamp.x[1] - 0.3],
      y: [0.15, this.clamp.y[1] - 0.2],
      z: [this.clamp.z[0] + 0.3, this.clamp.z[1] - 0.35],
    };
  }

  /* ── 碰撞 ── */
  _initColliders() {
    const src =
      this.manifest && Array.isArray(this.manifest.colliders) && this.manifest.colliders.length
        ? this.manifest.colliders
        : DEFAULT_COLLIDERS_BLENDER;
    this.colliders = src
      .map((c) => {
        const box = aabbToThree(c.aabb);
        return { name: c.name || 'COL', kind: c.kind || 'solid', min: box.min, max: box.max };
      })
      .filter((c) => c.max.x > c.min.x && c.max.y > c.min.y && c.max.z > c.min.z);
  }

  /** 相机球体推挤（AABB 最小穿透轴推出），再叠一层房间盒钳制 */
  resolveCollision(pos) {
    const r = CAM_RADIUS;
    // 1) 房间盒钳制
    pos.x = clamp(pos.x, this.clamp.x[0], this.clamp.x[1]);
    pos.y = clamp(pos.y, this.clamp.y[0], this.clamp.y[1]);
    pos.z = clamp(pos.z, this.clamp.z[0], this.clamp.z[1]);

    // 2) AABB 推挤（两轮，处理角落）
    let pushed = 0;
    for (let iter = 0; iter < 2; iter++) {
      for (const c of this.colliders) {
        const minX = c.min.x - r;
        const maxX = c.max.x + r;
        const minY = c.min.y - r;
        const maxY = c.max.y + r;
        const minZ = c.min.z - r;
        const maxZ = c.max.z + r;
        if (pos.x <= minX || pos.x >= maxX) continue;
        if (pos.y <= minY || pos.y >= maxY) continue;
        if (pos.z <= minZ || pos.z >= maxZ) continue;
        // 已在盒内：取最小穿透轴推出
        const dxl = pos.x - minX;
        const dxr = maxX - pos.x;
        const dyl = pos.y - minY;
        const dyr = maxY - pos.y;
        const dzl = pos.z - minZ;
        const dzr = maxZ - pos.z;
        const m = Math.min(dxl, dxr, dyl, dyr, dzl, dzr);
        if (m === dxl) pos.x = minX;
        else if (m === dxr) pos.x = maxX;
        else if (m === dyl) pos.y = minY;
        else if (m === dyr) pos.y = maxY;
        else if (m === dzl) pos.z = minZ;
        else pos.z = maxZ;
        pushed++;
      }
    }
    // 3) 再钳一次，保证不会被推挤推出房间
    pos.x = clamp(pos.x, this.clamp.x[0], this.clamp.x[1]);
    pos.y = clamp(pos.y, this.clamp.y[0], this.clamp.y[1]);
    pos.z = clamp(pos.z, this.clamp.z[0], this.clamp.z[1]);
    return pushed;
  }

  _clampTarget(t) {
    t.x = clamp(t.x, this._targetClamp.x[0], this._targetClamp.x[1]);
    t.y = clamp(t.y, this._targetClamp.y[0], this._targetClamp.y[1]);
    t.z = clamp(t.z, this._targetClamp.z[0], this._targetClamp.z[1]);
  }

  /* ── 粒子系统 ── */
  _buildParticles() {
    const group = new THREE.Group();
    group.name = 'WEB_FX';
    this.fxGroup = group;
    this.scene.add(group);

    // 雨：一次分配 RAIN_MAX，靠 drawRange 控制密度
    const pos = new Float32Array(RAIN_MAX * 3);
    const speed = new Float32Array(RAIN_MAX);
    const seed = new Float32Array(RAIN_MAX);
    for (let i = 0; i < RAIN_MAX; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = Math.sqrt(Math.random()) * RAIN_RADIUS;
      pos[i * 3] = Math.cos(a) * r;
      pos[i * 3 + 1] = Math.random() * RAIN_HEIGHT;
      pos[i * 3 + 2] = Math.sin(a) * r;
      speed[i] = 7.5 + Math.random() * 6.5;
      seed[i] = Math.random();
    }
    const rainGeo = new THREE.BufferGeometry();
    rainGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    rainGeo.setAttribute('aSpeed', new THREE.BufferAttribute(speed, 1));
    rainGeo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
    rainGeo.setDrawRange(0, 0);
    rainGeo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, RAIN_HEIGHT / 2, 0), RAIN_RADIUS + 2);
    this.rainMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uHeight: { value: RAIN_HEIGHT },
        uSize: { value: 14.0 },
        uWind: { value: 0.2 },
        uColor: { value: new THREE.Color(0xcfe0ff) },
        uOpacity: { value: 0.55 },
        uRoomMin: { value: new THREE.Vector3(this.room.x[0], this.room.y[0], this.room.z[0]) },
        uRoomMax: { value: new THREE.Vector3(this.room.x[1], this.room.y[1] + 1.0, this.room.z[1] + 0.16) },
        uWallZ: { value: this.room.z[1] },
      },
      vertexShader: RAIN_VERT,
      fragmentShader: RAIN_FRAG,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      fog: false,
    });
    const rain = new THREE.Points(rainGeo, this.rainMat);
    rain.name = 'WEB_Rain';
    rain.frustumCulled = false;
    rain.renderOrder = 10;
    group.add(rain);
    this.rain = rain;
    this.rainCount = 0;
    this.rainTargetCount = 0;
    this._rainTargetLevel = 0;

    // 水花：地面圆环 sprite 池（CPU 驱动，上限 420）
    const SPLASH_MAX = 420;
    const sGeo = new THREE.BufferGeometry();
    const sPos = new Float32Array(SPLASH_MAX * 3);
    const sAlpha = new Float32Array(SPLASH_MAX);
    const sSize = new Float32Array(SPLASH_MAX);
    sGeo.setAttribute('position', new THREE.BufferAttribute(sPos, 3));
    sGeo.setAttribute('aAlpha', new THREE.BufferAttribute(sAlpha, 1));
    sGeo.setAttribute('aSize', new THREE.BufferAttribute(sSize, 1));
    sGeo.setDrawRange(0, 0);
    sGeo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 40);
    this.splashMat = new THREE.ShaderMaterial({
      uniforms: {
        uMap: { value: ringTexture() },
        uColor: { value: new THREE.Color(0xdbeeff) },
        uPixelRatio: { value: Math.min(window.devicePixelRatio || 1, 2) },
      },
      vertexShader: /* glsl */ `
        attribute float aAlpha;
        attribute float aSize;
        uniform float uPixelRatio;
        varying float vAlpha;
        void main() {
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = aSize * uPixelRatio * 300.0 / max(-mv.z, 0.2);
          gl_PointSize = clamp(gl_PointSize, 1.0, 90.0);
          vAlpha = aAlpha;
        }
      `,
      fragmentShader: /* glsl */ `
        uniform sampler2D uMap;
        uniform vec3 uColor;
        varying float vAlpha;
        void main() {
          vec4 t = texture2D(uMap, gl_PointCoord);
          float a = t.a * vAlpha;
          if (a < 0.02) discard;
          gl_FragColor = vec4(uColor, a);
          #include <colorspace_fragment>
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      fog: false,
    });
    this.splash = new THREE.Points(sGeo, this.splashMat);
    this.splash.name = 'WEB_Splash';
    this.splash.frustumCulled = false;
    this.splash.renderOrder = 9;
    group.add(this.splash);
    // 池：初始全部死亡（max=0），避免首帧在原点堆一团
    this.splashPool = Array.from({ length: SPLASH_MAX }, () => ({
      life: 1,
      max: 0,
      x: 0,
      y: 0,
      z: 0,
      size: 0.14,
    }));
    this.splashHead = 0;
    this.splashLive = 0;
    this._splashAcc = 0;

    // 蒸汽：跟随 MD_Steam（有 GLB 时）或默认托盘上方
    const STEAM_MAX = 90;
    const stGeo = new THREE.BufferGeometry();
    const stPos = new Float32Array(STEAM_MAX * 3);
    const stSeed = new Float32Array(STEAM_MAX);
    for (let i = 0; i < STEAM_MAX; i++) {
      stPos[i * 3] = (Math.random() - 0.5) * 0.1;
      stPos[i * 3 + 1] = Math.random() * 0.3;
      stPos[i * 3 + 2] = (Math.random() - 0.5) * 0.1;
      stSeed[i] = Math.random();
    }
    stGeo.setAttribute('position', new THREE.BufferAttribute(stPos, 3));
    stGeo.setAttribute('aSeed', new THREE.BufferAttribute(stSeed, 1));
    const disc = softDiscTexture();
    this.steamMat = new THREE.PointsMaterial({
      size: 0.16,
      map: disc,
      transparent: true,
      opacity: 0.28,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      color: 0xffeedd,
      sizeAttenuation: true,
      fog: true,
    });
    this.steam = new THREE.Points(stGeo, this.steamMat);
    this.steam.name = 'WEB_Steam';
    this.steam.frustumCulled = false;
    group.add(this.steam);
    // 用户明确要求：删掉地上那团冒烟的东西 —— 网页蒸汽粒子整体关闭
    this.steam.visible = false;
    this._steamDisabled = true;
    const maidB = this.anchorsBlender.maid_pos || [-1.7, 0.3, 0];
    // 托盘咖啡杯的蒸汽基准点。
    // 旧代码 toThree(maidB[0], maidB[1], 1.02) 把 1.02 当 Blender 的 z 传进去，
    // 而 toThree 会做 y/z 轴互换 → 实际落在 y≈maidB[1]（≈0.02m，贴地），
    // 于是蒸汽从地板往上冒（用户看到的"地上冒烟"）。
    // 正确高度：女仆 1.5m 高，托盘在 0.742 + 杯口 0.81，蒸汽应从 ≈0.82m 起。
    this.steamBaseThree = toThree(maidB[0], maidB[1], 0.82);
    this.steamBaseThree.y += 0.02;   // 抬到杯口上方一点

    // 尘埃：室内漂浮（数量少，室内为主）
    const DUST_MAX = 260;
    const dGeo = new THREE.BufferGeometry();
    const dPos = new Float32Array(DUST_MAX * 3);
    for (let i = 0; i < DUST_MAX; i++) {
      dPos[i * 3] = this.room.x[0] + 0.4 + Math.random() * (this.room.x[1] - this.room.x[0] - 0.8);
      dPos[i * 3 + 1] = 0.35 + Math.random() * 2.3;
      dPos[i * 3 + 2] = this.room.z[0] + 0.4 + Math.random() * (this.room.z[1] - this.room.z[0] - 0.8);
    }
    dGeo.setAttribute('position', new THREE.BufferAttribute(dPos, 3));
    this.dustMat = new THREE.PointsMaterial({
      size: 0.035,
      map: disc,
      transparent: true,
      opacity: 0.0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      color: 0xffe4c4,
      sizeAttenuation: true,
      fog: true,
    });
    this.dust = new THREE.Points(dGeo, this.dustMat);
    this.dust.name = 'WEB_Dust';
    this.dust.frustumCulled = false;
    group.add(this.dust);
    this.dustTime = 0;
    this.dustBase = dPos.slice();
  }

  _buildWindowOverlay() {
    const win = this.anchorsBlender.win_open || DEFAULT_ANCHORS_BLENDER.win_open;
    const x0 = win.x[0];
    const x1 = win.x[1];
    const y0 = win.z[0];
    const y1 = win.z[1];
    const w = x1 - x0;
    const h = y1 - y0;
    const geo = new THREE.PlaneGeometry(w, h);
    const mat = new THREE.MeshBasicMaterial({
      transparent: true,
      depthWrite: false,
      opacity: 0,
      side: THREE.DoubleSide,
      color: 0xffffff,
      fog: false,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name = 'WEB_WindowDrops';
    // 窗在 three z = +3（Blender -Y 面），贴在内侧 2cm
    mesh.position.set((x0 + x1) / 2, (y0 + y1) / 2, this.room.z[1] - 0.02);
    mesh.rotation.y = Math.PI; // 朝向室内
    mesh.renderOrder = 8;
    this.scene.add(mesh);
    this.windowDrops = mesh;
    this.windowDropsMat = mat;
    this._windowTex = proceduralWindowDrops();
    mat.map = this._windowTex;
    mat.needsUpdate = true;

    // 可选：若 assets/tex/generated/window_drops.png 存在则替换（失败静默）
    const texUrl = './assets/tex/generated/window_drops.png';
    const img = new Image();
    img.onload = () => {
      const t = new THREE.CanvasTexture(img);
      t.colorSpace = THREE.SRGBColorSpace;
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.repeat.set(2, 2);
      mat.map = t;
      mat.needsUpdate = true;
    };
    img.onerror = () => {
      this.missingAssets.push(texUrl);
    };
    img.src = texUrl;

    // 窗外雨幕（略靠外，模拟玻璃外的雨帘）
    const geo2 = new THREE.PlaneGeometry(w + 0.2, h + 0.2);
    const mat2 = new THREE.MeshBasicMaterial({
      transparent: true,
      depthWrite: false,
      opacity: 0,
      side: THREE.DoubleSide,
      color: 0x9fb6cc,
      fog: true,
    });
    const mesh2 = new THREE.Mesh(geo2, mat2);
    mesh2.name = 'WEB_WindowRainVeil';
    mesh2.position.set((x0 + x1) / 2, (y0 + y1) / 2, this.room.z[1] + 0.06);
    mesh2.renderOrder = 7;
    this.scene.add(mesh2);
    this.rainVeil = mesh2;
    this.rainVeilMat = mat2;
  }

  /* ── 室外：GLB 含 C_Outdoor 时不造；否则程序化街道 ── */
  _buildOutdoor() {
    const perCol = this.manifest && this.manifest.counts && this.manifest.counts.per_collection;
    const hasGlbOutdoor = !!(perCol && perCol.C_Outdoor && perCol.C_Outdoor.tris > 0);
    if (hasGlbOutdoor) {
      this.outdoorFromGlb = true;
      this.streetLights = [];
      this.outdoorGroup = null;
      return;
    }
    const street = this.anchorsBlender.street || DEFAULT_ANCHORS_BLENDER.street;
    const group = new THREE.Group();
    group.name = 'WEB_Outdoor';
    this.scene.add(group);
    this.outdoorGroup = group;

    const sw = street.sidewalk || [-4.6, -3.0];
    const rd = street.road || [-9.0, -5.2];
    const bg = street.buildings || [-14.0, -9.6];

    // Blender y -> three z = -y
    const zOf = (by) => -by;
    const sidewalkZ = [zOf(sw[1]), zOf(sw[0])]; // [3.0, 4.6]
    const roadZ = [zOf(rd[1]), zOf(rd[0])]; // [5.2, 9.0]
    const buildZ = [zOf(bg[1]), zOf(bg[0])]; // [9.6, 14.0]
    this._roadZ0 = roadZ[0];

    const swW = sidewalkZ[1] - sidewalkZ[0];
    this.streetMat = new THREE.MeshStandardMaterial({ color: 0x7a7c80, roughness: 0.9, metalness: 0.05 });
    const sidewalk = new THREE.Mesh(new THREE.BoxGeometry(26, 0.12, swW), this.streetMat);
    sidewalk.position.set(0, -0.06, (sidewalkZ[0] + sidewalkZ[1]) / 2);
    sidewalk.receiveShadow = true;
    group.add(sidewalk);

    const rwW = roadZ[1] - roadZ[0];
    this.roadMat = new THREE.MeshStandardMaterial({ color: 0x2b2d31, roughness: 0.62, metalness: 0.08 });
    const road = new THREE.Mesh(new THREE.BoxGeometry(26, 0.1, rwW), this.roadMat);
    road.position.set(0, -0.22, (roadZ[0] + roadZ[1]) / 2);
    road.receiveShadow = true;
    group.add(road);

    const curb = new THREE.Mesh(
      new THREE.BoxGeometry(26, 0.18, 0.24),
      new THREE.MeshStandardMaterial({ color: 0x9a9c9f, roughness: 0.85 })
    );
    curb.position.set(0, -0.09, roadZ[0] + 0.1);
    curb.receiveShadow = true;
    group.add(curb);

    const line = new THREE.Mesh(
      new THREE.BoxGeometry(26, 0.01, 0.14),
      new THREE.MeshStandardMaterial({ color: 0xc9a227, roughness: 0.7, emissive: 0x201a08, emissiveIntensity: 0.4 })
    );
    line.position.set(0, -0.165, (roadZ[0] + roadZ[1]) / 2);
    group.add(line);

    // 对街建筑（低模 + 亮窗）
    const bldMat = new THREE.MeshStandardMaterial({ color: 0x3a3f47, roughness: 0.86, metalness: 0.05 });
    this.buildingWinMat = new THREE.MeshBasicMaterial({ color: 0xffcf8a, fog: true });
    for (let i = 0; i < 5; i++) {
      const w = 4.2 + (i % 3) * 0.9;
      const h = 6.5 + ((i * 37) % 9);
      const x = -10 + i * 5.4;
      const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, 3.0), bldMat);
      b.position.set(x, h / 2 - 0.3, buildZ[0] + 1.8);
      group.add(b);
      for (let r = 0; r < Math.floor(h / 1.6); r++) {
        for (let c = 0; c < 3; c++) {
          if ((r * 7 + c * 3 + i) % 5 > 2) continue;
          const win = new THREE.Mesh(new THREE.PlaneGeometry(0.62, 0.72), this.buildingWinMat);
          win.position.set(x - w / 2 + 0.9 + c * 1.15, -0.3 + 0.9 + r * 1.6, buildZ[0] + 1.8 - 1.52);
          win.rotation.y = Math.PI;
          group.add(win);
        }
      }
    }

    // 路灯
    const poleMat = new THREE.MeshStandardMaterial({ color: 0x2a2c30, roughness: 0.7, metalness: 0.35 });
    const headMat = new THREE.MeshBasicMaterial({ color: 0xffe0a8, fog: true });
    this.streetHeadMat = headMat;
    this.streetLights = [];
    const lampZ = (sw[1] + rd[0]) / 2;
    for (let i = 0; i < 2; i++) {
      const x = i === 0 ? -4.6 : 4.2;
      const z = -lampZ;
      const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.075, 4.4, 8), poleMat);
      pole.position.set(x, 2.05, z);
      group.add(pole);
      const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1.1, 6), poleMat);
      arm.rotation.z = Math.PI / 2;
      arm.position.set(x - 0.55, 4.1, z);
      group.add(arm);
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.15, 12, 8), headMat);
      head.position.set(x - 1.05, 4.05, z);
      group.add(head);
      const pl = new THREE.PointLight(0xffd9a0, 0.0, 11, 2);
      pl.position.copy(head.position);
      pl.position.y -= 0.1;
      group.add(pl);
      this.streetLights.push({ light: pl, head });
    }

    // 一辆低模小车
    const carMat = new THREE.MeshStandardMaterial({ color: 0x8f2f2b, roughness: 0.42, metalness: 0.35 });
    const carBody = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.55, 3.9), carMat);
    carBody.position.set(5.2, 0.15, (roadZ[0] + roadZ[1]) / 2 + 1.0);
    group.add(carBody);
    const carTop = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.48, 1.9), carMat);
    carTop.position.set(5.2, 0.62, (roadZ[0] + roadZ[1]) / 2 + 0.75);
    group.add(carTop);

    this.roadMat.userData.webWetMetal = true;
    this.streetMat.userData.webWetMetal = true;
  }

  /* ── 闪电全屏光斑 ── */
  _buildFlash() {
    const spriteMat = new THREE.SpriteMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
      fog: false,
    });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.name = 'WEB_LightningFlash';
    sprite.scale.set(220, 220, 1);
    sprite.position.set(0, 8, 40);
    sprite.renderOrder = 999;
    this.scene.add(sprite);
    this.flashSprite = sprite;
    this.flashMat = spriteMat;
    this._flashLevel = 0;
  }

  /* ── 无 GLB 时的占位场景（房间壳 + 吧台 + 桌 + 女仆占位） ── */
  _buildPlaceholder() {
    if (this.placeholder) return;
    const g = new THREE.Group();
    g.name = 'WEB_Placeholder';
    this.scene.add(g);
    this.placeholder = g;

    const { x, z } = this.room;
    const w = x[1] - x[0];
    const d = z[1] - z[0];
    const h = this.room.y[1] - this.room.y[0];
    const wallT = 0.16;

    const creamWall = new THREE.MeshStandardMaterial({ color: 0xf2e6d6, roughness: 0.88 });
    const wood = new THREE.MeshStandardMaterial({ color: 0xb98a5e, roughness: 0.6, metalness: 0.05 });
    const darkWood = new THREE.MeshStandardMaterial({ color: 0x8b5e3c, roughness: 0.55, metalness: 0.05 });
    const marble = new THREE.MeshStandardMaterial({ color: 0xefeae3, roughness: 0.22, metalness: 0.1 });
    const brass = new THREE.MeshStandardMaterial({ color: 0xc9a227, roughness: 0.3, metalness: 0.85 });
    const white = new THREE.MeshStandardMaterial({ color: 0xfffdf8, roughness: 0.8 });
    const glow = new THREE.MeshBasicMaterial({ color: 0xffd9a0 });

    const floor = new THREE.Mesh(new THREE.BoxGeometry(w, 0.08, d), wood);
    floor.position.set((x[0] + x[1]) / 2, -0.04, (z[0] + z[1]) / 2);
    floor.receiveShadow = true;
    g.add(floor);

    const ceil = new THREE.Mesh(new THREE.BoxGeometry(w, 0.08, d), creamWall);
    ceil.position.set(0, h + 0.04, 0);
    g.add(ceil);

    const left = new THREE.Mesh(new THREE.BoxGeometry(wallT, h, d), creamWall);
    left.position.set(x[0] - wallT / 2, h / 2, 0);
    left.receiveShadow = true;
    g.add(left);
    const right = new THREE.Mesh(new THREE.BoxGeometry(wallT, h, d), creamWall);
    right.position.set(x[1] + wallT / 2, h / 2, 0);
    right.receiveShadow = true;
    g.add(right);
    const back = new THREE.Mesh(new THREE.BoxGeometry(w + 0.32, h, wallT), creamWall);
    back.position.set(0, h / 2, z[0] - wallT / 2);
    back.receiveShadow = true;
    g.add(back);

    // 前墙（three z 最大侧）带窗洞 + 门洞
    const win = this.anchorsBlender.win_open || DEFAULT_ANCHORS_BLENDER.win_open;
    const door = this.anchorsBlender.door_open || DEFAULT_ANCHORS_BLENDER.door_open;
    const fz = z[1] + wallT / 2;
    const wx0 = win.x[0];
    const wx1 = win.x[1];
    const wy0 = win.z[0];
    const wy1 = win.z[1];
    const dx0 = door.x[0];
    const dx1 = door.x[1];
    const dy1 = door.z[1];
    const front = (cx0, cx1, cy0, cy1) => {
      const cw = cx1 - cx0;
      const ch = cy1 - cy0;
      if (cw <= 0.001 || ch <= 0.001) return;
      const m = new THREE.Mesh(new THREE.BoxGeometry(cw, ch, wallT), creamWall);
      m.position.set((cx0 + cx1) / 2, (cy0 + cy1) / 2, fz);
      m.castShadow = true;
      m.receiveShadow = true;
      g.add(m);
    };
    front(x[0], wx0, 0, h);
    front(wx1, dx0, wy0, h);
    front(wx0, wx1, 0, wy0);
    front(wx0, wx1, wy1, h);
    front(dx1, x[1], 0, h);
    front(dx0, dx1, dy1, h);

    // 窗玻璃
    const glassMat = new THREE.MeshPhysicalMaterial({
      color: 0xdfeaf2,
      roughness: 0.06,
      metalness: 0.0,
      transmission: 0.92,
      thickness: 0.02,
      transparent: true,
      opacity: 0.22,
      side: THREE.DoubleSide,
    });
    const glass = new THREE.Mesh(new THREE.PlaneGeometry(wx1 - wx0, wy1 - wy0), glassMat);
    glass.position.set((wx0 + wx1) / 2, (wy0 + wy1) / 2, fz);
    g.add(glass);
    this.placeholderWindowGlass = glassMat;

    // 吧台
    const bar = new THREE.Mesh(new THREE.BoxGeometry(3.9, 0.95, 0.72), darkWood);
    bar.position.set(1.75, 0.475, -1.51);
    bar.castShadow = true;
    bar.receiveShadow = true;
    g.add(bar);
    const barTop = new THREE.Mesh(new THREE.BoxGeometry(3.95, 0.05, 0.77), marble);
    barTop.position.set(1.75, 0.975, -1.51);
    barTop.castShadow = true;
    g.add(barTop);

    // 后吧层架
    for (let i = 0; i < 3; i++) {
      const shelf = new THREE.Mesh(new THREE.BoxGeometry(4.3, 0.04, 0.2), darkWood);
      shelf.position.set(0.55, 1.45 + i * 0.5, -2.88);
      g.add(shelf);
    }

    // 圆桌 + 椅子
    for (const t of this.anchorsBlender.tables || DEFAULT_ANCHORS_BLENDER.tables) {
      const tx = t[0];
      const tz = -t[1];
      const top = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.05, 24), white);
      top.position.set(tx, 0.715, tz);
      top.castShadow = true;
      top.receiveShadow = true;
      g.add(top);
      const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.06, 0.68, 10), brass);
      stem.position.set(tx, 0.36, tz);
      g.add(stem);
      const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.22, 0.05, 16), brass);
      foot.position.set(tx, 0.025, tz);
      g.add(foot);
      for (let k = 0; k < 2; k++) {
        const ang = (k * Math.PI) / 1.3 + tx;
        const chair = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.42, 0.4), wood);
        chair.position.set(tx + Math.cos(ang) * 0.72, 0.21, tz + Math.sin(ang) * 0.72);
        chair.castShadow = true;
        g.add(chair);
        const back2 = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.45, 0.05), wood);
        back2.position.set(chair.position.x, 0.62, chair.position.z + Math.sin(ang) * 0.2);
        back2.rotation.y = -ang;
        g.add(back2);
      }
    }

    // 吧台凳
    for (const s of this.anchorsBlender.stools || DEFAULT_ANCHORS_BLENDER.stools) {
      const seat = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.05, 16), white);
      seat.position.set(s[0], 0.62, -s[1]);
      seat.castShadow = true;
      g.add(seat);
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.04, 0.6, 8), brass);
      leg.position.set(s[0], 0.31, -s[1]);
      g.add(leg);
    }

    // 吊灯（装饰；真实光源由 weather.js 提供）
    this.placeholderLampMats = [];
    for (const p of this.anchorsBlender.pendants || DEFAULT_ANCHORS_BLENDER.pendants) {
      const cone = new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.2, 16, 1, true), glow);
      cone.position.set(p[0], p[2], -p[1]);
      g.add(cone);
      const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, h - p[2], 6), darkWood);
      cord.position.set(p[0], (p[2] + h) / 2, -p[1]);
      g.add(cord);
      this.placeholderLampMats.push(glow);
    }
    this.placeholderLampMatList = this.placeholderLampMats;

    // 女仆占位
    const maidGroup = new THREE.Group();
    const mp = this.anchorsBlender.maid_pos || DEFAULT_ANCHORS_BLENDER.maid_pos;
    maidGroup.position.set(mp[0], 0, -mp[1]);
    maidGroup.rotation.y = 48 * DEG + Math.PI;
    const navy = new THREE.MeshStandardMaterial({ color: 0x1e2b4d, roughness: 0.75 });
    const skin = new THREE.MeshStandardMaterial({ color: 0xf6d7c0, roughness: 0.7 });
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.19, 0.4, 6, 14), navy);
    body.position.y = 0.55;
    body.castShadow = true;
    maidGroup.add(body);
    const apron = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.36, 0.02), white);
    apron.position.set(0, 0.56, 0.19);
    maidGroup.add(apron);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.165, 18, 14), skin);
    head.position.y = 0.98;
    head.castShadow = true;
    maidGroup.add(head);
    const hair = new THREE.Mesh(
      new THREE.SphereGeometry(0.175, 18, 14, 0, Math.PI * 2, 0, Math.PI * 0.6),
      new THREE.MeshStandardMaterial({ color: 0x6b4a34, roughness: 0.8 })
    );
    hair.position.y = 1.02;
    maidGroup.add(hair);
    const tray = new THREE.Mesh(
      new THREE.CylinderGeometry(0.15, 0.15, 0.012, 20),
      new THREE.MeshStandardMaterial({ color: 0xd8c7a6, roughness: 0.35, metalness: 0.5 })
    );
    tray.position.set(0, 0.86, 0.3);
    tray.castShadow = true;
    maidGroup.add(tray);
    const cake = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.055, 0.06, 16),
      new THREE.MeshStandardMaterial({ color: 0xf9e0e6, roughness: 0.6 })
    );
    cake.position.set(-0.03, 0.9, 0.3);
    maidGroup.add(cake);
    const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.03, 0.055, 16), white);
    cup.position.set(0.06, 0.895, 0.3);
    maidGroup.add(cup);
    this.scene.add(maidGroup);
    this.placeholderMaid = maidGroup;

    this._placeholderMats = { creamWall, wood, darkWood, marble, brass, white, glow };
  }

  /* ─────────────────────────── GLB 加载 ─────────────────────────── */
  /**
   * 加载 GLB。带两层容错：
   *   1) 预检 GLB 头，找出「空 texture 槽」（既无 source 也无 EXT_texture_webp.source）。
   *      这类槽会让 GLTFLoader 在 assignTexture 时抛 "undefined.uri"，**整包**失败。
   *      发现后把坏槽指向一张内嵌的 1×1 占位 PNG，再交给 GLTFLoader。
   *   2) 若仍失败，退回占位场景（页面不崩）。
   */
  async loadGLB(url) {
    const loader = new GLTFLoader();
    this.onProgress && this.onProgress(0.02, 'loading glb');
    const tLoad = performance.now();
    try {
      // 流式读取：按 Content-Length 上报真实下载进度（用户要求"写清楚要多久"）
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const total = Number(res.headers.get('content-length')) || 0;
      let buf;
      if (res.body && total > 0 && typeof res.body.getReader === 'function') {
        const reader = res.body.getReader();
        const chunks = [];
        let got = 0;
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
          got += value.length;
          // 下载阶段占进度 2% → 55%
          const frac = 0.02 + 0.53 * (got / total);
          this.onProgress && this.onProgress(frac, 'loading glb');
        }
        buf = new Uint8Array(got);
        let off = 0;
        for (const c of chunks) { buf.set(c, off); off += c.length; }
        buf = buf.buffer;
      } else {
        buf = await res.arrayBuffer();
      }
      this.glbBytes = buf.byteLength;
      this.glbFetchMs = Math.round(performance.now() - tLoad);

      this.onProgress && this.onProgress(0.56, 'parsing glb');
      const patched = this._preflightPatchGLB(buf);
      this.glbPreflight = patched.report;

      const tParse = performance.now();
      const gltf = await new Promise((resolve, reject) => {
        loader.parse(patched.buffer, '', resolve, (err) => reject(err));
      });
      this.glbParseMs = Math.round(performance.now() - tParse);
      this.onProgress && this.onProgress(0.72, 'ingesting');
      this._ingestGLTF(gltf);
      this.loadedFromGlb = true;
      this.glbTotalMs = Math.round(performance.now() - tLoad);
      this.onProgress && this.onProgress(0.88, 'ready');
      return true;
    } catch (err) {
      this.glbError = err && (err.message || String(err));
      this.warnings.push(`GLB 加载失败：${this.glbError}（已降级为占位场景）`);
      this.onProgress && this.onProgress(1, 'fallback');
      return false;
    }
  }

  /** GLB 预检 + 修补：把「空 texture 槽」替换成占位 1×1 PNG（返回新 buffer） */
  _preflightPatchGLB(buf) {
    const report = { patched: false, badTextures: [], images: 0, materials: 0, extensionsRequired: [] };
    try {
      const dv = new DataView(buf);
      if (dv.getUint32(0, true) !== 0x46546c67) throw new Error('不是 GLB（magic 不对）');
      const jsonLen = dv.getUint32(12, true);
      const jsonStart = 20;
      const json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, jsonStart, jsonLen)));
      report.images = (json.images || []).length;
      report.materials = (json.materials || []).length;
      report.extensionsRequired = json.extensionsRequired || [];

      const bad = [];
      (json.textures || []).forEach((t, i) => {
        const viaExt = t.extensions && t.extensions.EXT_texture_webp && t.extensions.EXT_texture_webp.source != null;
        const viaBasis = t.extensions && t.extensions.KHR_texture_basisu && t.extensions.KHR_texture_basisu.source != null;
        if (t.source == null && !viaExt && !viaBasis) bad.push(i);
      });
      report.badTextures = bad;
      if (!bad.length) return { buffer: buf, report };

      const png = onePixelPng();
      const binOff = jsonStart + jsonLen;
      const binLen = dv.getUint32(binOff, true);
      const binStart = binOff + 8;
      const oldBin = new Uint8Array(buf, binStart, binLen);

      // 追加 PNG 到 BIN 末尾，登记 bufferView / image
      json.bufferViews = json.bufferViews || [];
      const pngOffset = oldBin.length;
      json.bufferViews.push({ buffer: 0, byteOffset: pngOffset, byteLength: png.byteLength });
      const pngBv = json.bufferViews.length - 1;
      json.images = json.images || [];
      const imgIdx = json.images.length;
      json.images.push({ bufferView: pngBv, mimeType: 'image/png', name: 'WEB_PLACEHOLDER_1px' });

      for (const i of bad) {
        const t = json.textures[i];
        if (t.extensions) delete t.extensions;
        t.source = imgIdx;
      }
      if (json.buffers && json.buffers[0]) json.buffers[0].byteLength = oldBin.length + png.byteLength;

      // 重新拼 GLB：header + JSON chunk + BIN chunk（4 字节对齐）
      const newJson = new TextEncoder().encode(JSON.stringify(json));
      const jsonPad = (4 - (newJson.length % 4)) % 4;
      const binRawLen = oldBin.length + png.byteLength;
      const binPad = (4 - (binRawLen % 4)) % 4;
      const newBin = new Uint8Array(binRawLen + binPad);
      newBin.set(oldBin, 0);
      newBin.set(png, oldBin.length);
      const totalLen = 12 + 8 + newJson.length + jsonPad + 8 + newBin.length;
      const out = new Uint8Array(totalLen);
      const o = new DataView(out.buffer);
      o.setUint32(0, 0x46546c67, true); // 'glTF'
      o.setUint32(4, 2, true);
      o.setUint32(8, totalLen, true);
      o.setUint32(12, newJson.length + jsonPad, true);
      o.setUint32(16, 0x4e4f534a, true); // 'JSON'
      out.set(newJson, 20);
      for (let i = 0; i < jsonPad; i++) out[20 + newJson.length + i] = 0x20; // 空格填充
      const binChunkOff = 20 + newJson.length + jsonPad;
      o.setUint32(binChunkOff, newBin.length, true);
      o.setUint32(binChunkOff + 4, 0x004e4942, true); // 'BIN\0'
      out.set(newBin, binChunkOff + 8);

      report.patched = true;
      report.patchNote = `已把 ${bad.length} 个空 texture 槽替换为 1×1 占位图（原 GLB 会让 GLTFLoader 整包失败）`;
      this.warnings.push(`GLB 预修补：${report.patchNote}`);
      console.warn(`[scene] GLB 预修补：${report.patchNote} idx=${bad.join(',')}`);
      return { buffer: out.buffer, report };
    } catch (e) {
      this.warnings.push(`GLB 预检异常（已原样加载）：${e && e.message}`);
      return { buffer: buf, report };
    }
  }

  _ingestGLTF(gltf) {
    const t0 = performance.now();
    const root = gltf.scene || gltf.scenes[0];
    root.name = 'MAID_CAFE_GLB';
    this.glb = gltf;
    this.glbRoot = root;

    // manifest 声明的不投影物体（玻璃 29 个）→ castShadow=false，否则室内被玻璃影糊黑
    const noShadow = new Set((this._noShadowObjects || []).map((s) => String(s)));
    const isNoShadowName = (n) => {
      if (!n) return false;
      const s = String(n);
      if (noShadow.has(s)) return true;
      return noShadow.has(s.replace(/_\d+$/, '')); // RM_WinGlass_0_0 → RM_WinGlass_0
    };

    let meshes = 0;
    let shadowCasters = 0;
    let noShadowHits = 0;
    let tris = 0;
    let vertexColorMeshes = 0;
    const matSet = new Map();
    root.traverse((o) => {
      if (!o.isMesh) return;
      meshes++;
      o.receiveShadow = true;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      const matNames = mats.map((m) => (m && m.name) || '');
      const glassy = matNames.some((n) => /glass/i.test(n));
      const declared = isNoShadowName(o.name) || matNames.some(isNoShadowName);
      if (glassy || declared) {
        o.castShadow = false;
        noShadowHits++;
      } else {
        o.castShadow = true;
        shadowCasters++;
      }
      if (o.geometry && o.geometry.attributes && o.geometry.attributes.color) vertexColorMeshes++;
      const hasVCol = !!(o.geometry && o.geometry.attributes && o.geometry.attributes.color);
      for (const m of mats) {
        if (!m) continue;
        if (!matSet.has(m.uuid)) matSet.set(m.uuid, m);
        // 顶点色（COLOR_0）：只要几何体带 color 属性就强制开启——
        // 实测 GLTFLoader 在某些材质（M_Hair 带 sheen/anisotropy）会 clone 出新材质实例，
        // 顶点色标记可能没跟过来，导致女仆头发渲染成白色。这里兜底强制。
        if (hasVCol && m.vertexColors !== true) {
          m.vertexColors = true;
          m.needsUpdate = true;
        }
      }
      const geo = o.geometry;
      if (geo && geo.index) tris += geo.index.count / 3;
      else if (geo && geo.attributes.position) tris += geo.attributes.position.count / 3;
    });
    // ── 静态优化：冻结矩阵 + 阴影投射收窄 ──────────────
    let freezeStats = { frozenMatrices: 0, shadowSkipped: 0 };
    // 场景里绝大多数网格是静态的（墙、地板、家具）。每帧更新 matrixWorld
    // 对 1100+ 对象是纯浪费，冻结后 three 会跳过它们。
    // 同时把「不需要投影」的对象（户外 334 个、贴墙装饰等）的 castShadow 关掉，
    // 阴影 pass 的 draw call 能砍掉一半以上。
    {
      const NO_SHADOW_RE = /^(OD_|RM_Wall|RM_Ceil|RM_Skirting|RM_Wain|RM_Cove|RM_ChairRail|DC_Cove|DC_WinLeaf|DC_StringLights|BA_ShelfLED|MAT_)/;
      let frozen = 0, shadowOff = 0;
      root.traverse((o) => {
        if (!o.isMesh) return;
        // 静态冻结：非粒子、非动画对象
        if (o.isMesh) {
          o.matrixAutoUpdate = false;
          o.updateMatrix();
          frozen++;
        }
        if (NO_SHADOW_RE.test(o.name || '')) {
          o.castShadow = false;
          o.receiveShadow = false;
          shadowOff++;
        }
      });
      // 注意：此处 this.glbStats 尚未创建（下面才赋值），
      // 所以先存到局部变量，等 glbStats 建好后再合并。见下方 freezeStats。
      freezeStats = { frozenMatrices: frozen, shadowSkipped: shadowOff };
    }
    this.scene.add(root);
    this.glbStats = {
      meshes,
      tris: Math.round(tris),
      materials: matSet.size,
      shadowCasters,
      noShadowMeshes: noShadowHits,
      vertexColorMeshes,
      ingestMs: Math.round(performance.now() - t0),
      ...freezeStats,
    };

    const mats = Array.from(matSet.values());
    const byName = (n) => mats.filter((m) => m.name === n || (m.name || '').includes(n));
    this.glbMaterials = mats;

    // ── 网页端材质修正（2026-10-22） ─────────────────────────────
    // 1) GLB 导出的所有材质都是 doubleSided=true。对于**闭合几何体**（标签圆柱、
    //    书本、瓶体等），双面渲染时内表面会和外表面重叠，背面法线翻转过光照计算
    //    后接近 0，表现就是一片黑块（用户截图的 syrup 标签黑面即此）。
    //    标签/封闭体不需要双面，改成 FrontSide。
    // 2) 金属材质（metallic ≥ 0.9 且无 metallicRoughness 贴图）完全依赖环境反射。
    //    夜晚环境被压暗时会渲染成纯黑；给它一个最低 envMapIntensity 保底。
    {
      const CLOSED_MATS = /^(MAT_Paper|MAT_Paper_Menu|MAT_Paper_MenuCard|MAT_ChimePaper|MAT_Porcelain|MAT_Ceramic_Glaze|MAT_Terracotta|MAT_Cake_|MAT_Book_|MAT_Syrup_[0-9]|MAT_Tray_Cloth|potted_plant_|planter_box_|fern_02)/;
      let frontFixed = 0;
      let metalFixed = 0;
      for (const m of mats) {
        const n = m.name || '';
        // 闭合体 → FrontSide
        if (m.side === THREE.DoubleSide && CLOSED_MATS.test(n)) {
          m.side = THREE.FrontSide;
          m.needsUpdate = true;
          frontFixed++;
        }
        // 金属保底
        if (m.metalness != null && m.metalness >= 0.9 && !m.metalnessMap) {
          if (m.userData.webEnvCap == null) m.userData.webEnvCap = 0.9;
          metalFixed++;
        }
        // 纸/陶瓷类给一点自发光保底，夜间不至于纯黑
        if (/^(MAT_Paper|MAT_Porcelain)/.test(n) && m.emissive) {
          m.emissive.setHex(0x0a0a0a);
          m.emissiveIntensity = 1.0;
        }
      }
      this._reflCache = null;   // 材质属性变了，反射材质缓存失效
      this.glbStats.sideFixed = frontFixed;
      this.glbStats.metalGuard = metalFixed;
    }

    // 湿地面材质
    const wetNames = this.fx.wet_materials || DEFAULT_FX.wet_materials;
    const wet = [];
    for (const n of wetNames) wet.push(...byName(n));
    if (!wet.length) {
      for (const m of mats) {
        if (!m.name) continue;
        if (/Wood_Herringbone|Marble|Out_Concrete|Street/i.test(m.name)) wet.push(m);
      }
    }
    this.wetMaterialList = Array.from(new Set(wet));

    // 灯罩发光材质
    const lampNames = this.fx.lamp_materials || DEFAULT_FX.lamp_materials;
    const lamps = [];
    for (const n of lampNames) lamps.push(...byName(n));
    if (!lamps.length) {
      for (const m of mats) {
        if (m.emissive && m.emissive.getHex() !== 0 && /Emissive|Shade|Lamp|Bulb|LED/i.test(m.name || '')) lamps.push(m);
      }
    }
    this.lampMaterialList = Array.from(new Set(lamps));

    // 窗玻璃
    const glassName = this.fx.window_glass_material || DEFAULT_FX.window_glass_material;
    this.windowGlassList = byName(glassName);
    this.glbWindowGlass = this.windowGlassList.slice();
    root.traverse((o) => {
      if (o.isMesh && /win/i.test(o.name || '') && o.material && /glass/i.test(o.material.name || '')) {
        this.glbWindowGlass.push(o.material);
      }
    });

    // 对街建筑亮窗（OD_WindowLit_*）：只在黄昏/夜晚亮
    this.litWindowMeshes = [];
    if (this._litWindowObjects.length) {
      const names = new Set(this._litWindowObjects);
      root.traverse((o) => {
        if (!o.isMesh) return;
        const n = o.name || '';
        if (names.has(n) || names.has(n.replace(/_\d+$/, ''))) {
          o.userData.webLitWindow = true;
          o.userData.webLitBaseEmissive = o.material && o.material.emissive ? o.material.emissive.clone() : null;
          o.userData.webLitBaseIntensity =
            o.material && o.material.emissiveIntensity != null ? o.material.emissiveIntensity : 1;
          this.litWindowMeshes.push(o);
        }
      });
    }
    this.glbStats.litWindowMeshes = this.litWindowMeshes.length;

    // 蒸汽锚点：manifest fx_nodes.steam_node
    const steamName = this.fx.steam_node || 'MD_Steam_0';
    let steamObj = null;
    root.traverse((o) => {
      if (!steamObj && (o.name === steamName || (o.name || '').startsWith(steamName))) steamObj = o;
    });
    if (steamObj) {
      const wp = new THREE.Vector3();
      steamObj.getWorldPosition(wp);
      this.steamBaseThree = wp;
      if (steamObj.isMesh) steamObj.visible = false; // 用粒子替代
    }
    // 用户反复要求：删掉地上那团"冒烟"的东西。
    // 把所有名字带 steam 的网格一律隐藏（MD_Steam_0/1/2 及同族），
    // 且粒子侧已通过 _steamDisabled 永久关闭。
    root.traverse((o) => {
      if (o.isMesh && /steam/i.test(o.name || '')) {
        o.visible = false;
        o.castShadow = false;
        o.receiveShadow = false;
      }
    });

    // 占位物隐藏
    if (this.placeholder) this.placeholder.visible = false;
    if (this.placeholderMaid) this.placeholderMaid.visible = false;

    // ── 女仆/浅色材质的「发白」修正 ──
    // 根因（已由 GLB 侧实证）：M_Hair / M_White / M_Satin / M_Navy 在 GLB 里带
    //   KHR_materials_sheen: sheenColorFactor=[1,1,1] + sheenRoughness≈0.5，
    //   外加 KHR_materials_clearcoat 与 KHR_materials_anisotropy。
    //   three.js 会把 sheenColor 解析成纯白 → 在深色头发上叠一层白色绒光，
    //   实测女仆头发整体渲染成白色（皮肤/虹膜无 sheen，所以颜色正常）。
    // 处理：把 sheen 强度与 sheenColor 都压掉，并清零 clearcoat / anisotropy，
    //       让颜色回到 baseColor × COLOR_0 顶点色。
    this._maidMatTweak = {};
    const tweak = (name, cfg) => {
      const ms = mats.filter((m) => m.name === name);
      for (const m of ms) {
        if (cfg.sheen != null && 'sheen' in m) m.sheen = cfg.sheen;
        // 关键：sheenColor 是白色时即使 sheen 很小也会在深色基材上泛白
        if ('sheenColor' in m && m.sheenColor && m.sheenColor.isColor) {
          m.sheenColor.setRGB(
            cfg.sheen > 0 ? 1.0 : 0.0,
            cfg.sheen > 0 ? 1.0 : 0.0,
            cfg.sheen > 0 ? 1.0 : 0.0
          );
        }
        if ('sheenRoughness' in m && cfg.sheenRoughness != null) m.sheenRoughness = cfg.sheenRoughness;
        if (cfg.clearcoat != null && 'clearcoat' in m) m.clearcoat = cfg.clearcoat;
        if ('anisotropy' in m && cfg.anisotropy != null) m.anisotropy = cfg.anisotropy;
        if (cfg.roughness != null && m.roughness != null) m.roughness = Math.max(m.roughness, cfg.roughness);
        if (cfg.envMapIntensity != null) {
          m.userData.webEnvCap = cfg.envMapIntensity;
          if (m.envMapIntensity != null) m.envMapIntensity = Math.min(m.envMapIntensity, cfg.envMapIntensity);
        }
        m.needsUpdate = true;
        this._maidMatTweak[name] = {
          sheen: m.sheen,
          sheenColor: m.sheenColor && m.sheenColor.getHexString ? '#' + m.sheenColor.getHexString() : null,
          clearcoat: m.clearcoat,
          anisotropy: m.anisotropy,
          roughness: m.roughness,
          vertexColors: m.vertexColors,
          color: m.color ? '#' + m.color.getHexString() : null,
        };
      }
    };
    // 皮肤：去掉 clearcoat 与 sheen，粗糙度抬高（布料化）
    tweak('M_Skin', { sheen: 0.0, clearcoat: 0.0, roughness: 0.55, envMapIntensity: 0.3 });
    // 头发：sheen/clearcoat/anisotropy 全清零（这是头发变白的根因）
    tweak('M_Hair', { sheen: 0.0, sheenRoughness: 1.0, clearcoat: 0.0, anisotropy: 0.0, roughness: 0.5, envMapIntensity: 0.3 });
    // 虹膜：不要环境反射冲淡颜色
    tweak('M_Iris', { sheen: 0.0, clearcoat: 0.0, envMapIntensity: 0.15 });
    tweak('M_EyeLight', { sheen: 0.0, clearcoat: 0.0, envMapIntensity: 0.15 });
    tweak('M_EyeRed', { sheen: 0.0, clearcoat: 0.0, envMapIntensity: 0.15 });
    // 白色布料（围裙/袖口/袜）：sheen 清零，否则整片泛白
    tweak('M_White', { sheen: 0.0, clearcoat: 0.0, envMapIntensity: 0.28 });
    tweak('M_Satin', { sheen: 0.0, clearcoat: 0.0, envMapIntensity: 0.3 });
    // 深蓝裙/con- 也带白 sheen，压掉避免发灰
    tweak('M_Navy', { sheen: 0.0, clearcoat: 0.0, envMapIntensity: 0.3 });
    tweak('M_Sclera', { sheen: 0.0, clearcoat: 0.0, envMapIntensity: 0.12 });

    // ── 天空球：GLB 自带 OD_SkyDome（80m, doubleSided）会把相机包在里面，
    //    双面渲染时内壁会挡住整个画面（实测门洞机位被它切成棕色大面）。
    //    处理：关掉 doubleSided 造成的遮挡 —— 设 backSide 并隐藏，交给 weather.js 的程序化穹顶/HDRI 当背景。
    const skyMeshes = [];
    root.traverse((o) => {
      if (o.isMesh && /sky/i.test(o.name || '')) skyMeshes.push(o);
    });
    for (const s of skyMeshes) {
      s.visible = false;
      s.castShadow = false;
      s.receiveShadow = false;
      if (s.material) {
        s.material.side = THREE.BackSide;
        s.material.depthWrite = false;
      }
    }
    this.glbSkyMeshes = skyMeshes;
    this.glbStats.skyMeshesHidden = skyMeshes.length;
  }

  /* ── 近距几何淡出（相机贴近门叶/吧台时不要糊屏） ── */
  /**
   * 判定用**包围盒最近点距离**（门叶/吧台这类大板用中心距离会永远不触发）。
   * 只对相机 1.35m 内的物体生效；墙/天花/地板级超大件（对角线 > 6.5m）跳过。
   */
  _updateNearCameraFade() {
    // ★ 已停用：用户要求「不要相机靠近物体逐渐透明」的效果。
    //   而且它每帧改 m.transparent + m.needsUpdate = true，会触发 shader 重编译，
    //   是「某些视角贴图闪烁 / 光影出错」的主要原因之一。
    return;
  }

  /* ── 每帧：环境（st = 平滑后的 weather state，target = 目标 state） ── */
  applyWeatherState(st, dt, target) {
    if (!st) return;
    this._lastState = st;
    if (target) this._rainTargetLevel = target.rainLevel;

    // 雨量分档 0 / 3000 / 6000 / 12000。st.rainLevel 是平滑后的小数，
    // 不能直接取整（过渡期会长时间停在 0），档位按**目标**取。
    const lvlTarget = Math.round(this._rainTargetLevel != null ? this._rainTargetLevel : st.rainLevel);
    const baseCap = lvlTarget <= 0 ? 0 : lvlTarget === 1 ? 3000 : lvlTarget === 2 ? 6000 : RAIN_MAX;
    // 画质档位缩放（由 app.js 的 setFxBudget 设置；默认 1.0 不缩放）
    const cap = Math.round(baseCap * (this._fxRainScale != null ? this._fxRainScale : 1));
    this.rainTargetCount = cap;
    this.rainCount = cap;
    this.rain.geometry.setDrawRange(0, cap);
    this.rainMat.uniforms.uOpacity.value = lerp(0.3, 0.72, Math.min(1, (st.rainLevel || 0) / 3));
    this.rainMat.uniforms.uWind.value = st.windStrength || 0.2;
    this.rain.visible = cap > 0;

    // 雨区：**固定 x=0**（不跟相机），整柱放在前墙外。
    // 旧代码 this.rain.position.x = camera.position.x 是 bug：
    // 相机走进室内后雨的 x 也跟着进室内，看起来就像室内在下雨。
    // shader 里的室内盒（uRoomMin/uRoomMax）负责把落到房间体积内的雨滴裁掉，
    // 所以从窗内往外看仍然是「窗外在下雨」，从街上回看也是。
    const frontZ = this.room.z[1];
    this.rain.position.set(0, 0, frontZ + 4.0);
    this.rainMat.uniforms.uRoomMin.value.set(
      this.room.x[0] - 0.15, this.room.y[0], this.room.z[0] - 0.15);
    this.rainMat.uniforms.uRoomMax.value.set(
      this.room.x[1] + 0.15, this.room.y[1] + 0.5, frontZ + 0.30);
    if (this.rainMat.uniforms.uWallZ) this.rainMat.uniforms.uWallZ.value = frontZ + 0.02;

    // 窗上水帘 / 窗外雨幕
    this.windowDropsMat.opacity = lerp(0.0, 0.9, st.windowDropsOpacity);
    this.windowDrops.visible = st.windowDropsOpacity > 0.01;
    this.rainVeilMat.opacity = lerp(0.0, 0.22, Math.min(1, st.rainLevel / 3));
    this.rainVeil.visible = st.rainLevel > 0;

    // 蒸汽（冷/暗天更明显）
    this.steamMat.opacity = 0.2 + 0.14 * (1 - (st.sunIntensity || 0) / 3.5);
    if (!this._steamDisabled) this.steam.position.copy(this.steamBaseThree);

    // 尘埃（晴天要淡：350 粒子会像下雪）
    this.dustMat.opacity = (st.dustOpacity || 0) * 0.28;

    // 室外路灯 / 对街亮窗（程序化室外才有）
    const night = 1 - Math.min(1, (st.sunIntensity || 0) / 2.4);
    const lampOn = Math.max(night, st.lightning ? 0.6 : 0);
    for (const sl of this.streetLights || []) {
      sl.light.intensity = 1.6 * lampOn;
      sl.head.material.color.setHex(0xffe0a8).multiplyScalar(0.5 + 0.8 * lampOn);
    }
    if (this.buildingWinMat) {
      const b = 0.25 + 0.9 * lampOn;
      this.buildingWinMat.color.setRGB(b, b * 0.78, b * 0.5);
    }

    // GLB 里的对街亮窗：白天必须关掉，否则白得发假
    if (this.litWindowMeshes && this.litWindowMeshes.length) {
      const dayFactor = Math.min(1, Math.max(0, ((st.sunIntensity || 0) - 0.35) / 1.2));
      const visible = dayFactor < 0.85;
      const litK = Math.max(0, 1 - dayFactor) + (st.lightning ? 0.15 : 0);
      for (const o of this.litWindowMeshes) {
        o.visible = visible;
        const m = o.material;
        if (m && m.emissive) {
          if (o.userData.webLitBaseEmissive) m.emissive.copy(o.userData.webLitBaseEmissive);
          m.emissiveIntensity = o.userData.webLitBaseIntensity * litK;
        }
      }
    }

    // 闪电白光遮罩
    const flash = this._flashLevel || 0;
    this.flashMat.opacity = Math.min(0.85, flash * 0.5);
    this.flashSprite.visible = flash > 0.001;
  }

  setFlashLevel(v) {
    this._flashLevel = v;
  }

  /** 给 weather.js 提供需要联动的材质 */
  collectMaterialsForWeather() {
    const wet = new Set(this.wetMaterialList || []);
    if (!this.loadedFromGlb) {
      if (this.streetMat) wet.add(this.streetMat);
      if (this.roadMat) wet.add(this.roadMat);
      if (this._placeholderMats) {
        wet.add(this._placeholderMats.marble);
        wet.add(this._placeholderMats.wood);
      }
    }
    const lamps = new Set(this.lampMaterialList || []);
    if (!this.loadedFromGlb && this.placeholderLampMatList) {
      for (const m of this.placeholderLampMatList) lamps.add(m);
    }
    return { wet: Array.from(wet).filter(Boolean), lamps: Array.from(lamps).filter(Boolean) };
  }

  /** 反射组：只给玻璃/金属/大理石/湿路面挂 envMap（避免全屋 IBL 发白） */
  collectReflectiveMaterials() {
    // 缓存：材质集合在 GLB 载入后不再变化，没必要每次 applyEnvironmentMap 都重建
    if (this._reflCache) return this._reflCache;
    const list = new Set();
    const add = (m) => {
      if (m && 'envMap' in m) list.add(m);
    };
    if (!this.loadedFromGlb) {
      if (this._placeholderMats) {
        add(this._placeholderMats.marble);
        add(this._placeholderMats.brass);
        add(this.placeholderWindowGlass);
      }
      add(this.streetMat);
      add(this.roadMat);
    } else if (this.glbMaterials) {
      for (const m of this.glbMaterials) {
        const n = m.name || '';
        const metal = m.metalness != null && m.metalness > 0.35;
        const glassy = (m.transmission != null && m.transmission > 0.2) || /Glass/i.test(n);
        const smooth = m.roughness != null && m.roughness < 0.35;
        if (metal || glassy || (/Marble|Brass|Metal|Window/i.test(n) && smooth)) add(m);
      }
    }
    for (const m of this.wetMaterialList || []) add(m);
    const out = Array.from(list);
    this._reflCache = out;
    return out;
  }

  /** weather.js 烘好程序化环境贴图后调用（HDRI 未就绪时的兜底） */
  applyEnvironmentMap(tex, intensity = 0.9) {
    if (!tex) return;
    for (const m of this.collectReflectiveMaterials()) {
      const first = m.envMap == null;
      m.envMap = tex;
      if (m.envMapIntensity != null) m.envMapIntensity = intensity;
      if (first) m.needsUpdate = true;
    }
  }

  /* ── 每帧 ── */
  /**
   * 画质档位控制（app.js 的自适应画质调用）
   * @param {number} rainScale 雨粒子缩放（0..1）
   * @param {boolean} fxOn    是否保留蒸汽/尘埃/水花等小特效
   */
  setFxBudget(rainScale, fxOn) {
    this._fxRainScale = Math.max(0, Math.min(1, rainScale == null ? 1 : rainScale));
    this._fxEnabled = fxOn !== false;
    // 立即把当前雨量套用新预算（不必等下一帧）
    if (this.rainL1 != null || this._rainTargetLevel != null) {
      const lvl = Math.round(this._rainTargetLevel != null ? this._rainTargetLevel : 0);
      const baseCap = lvl <= 0 ? 0 : lvl === 1 ? 3000 : lvl === 2 ? 6000 : RAIN_MAX;
      const cap = Math.round(baseCap * this._fxRainScale);
      this.rainTargetCount = cap;
      this.rainCount = cap;
      if (this.rain && this.rain.geometry) this.rain.geometry.setDrawRange(0, cap);
      if (this.rain) this.rain.visible = cap > 0;
    }
    // 小特效开关
    for (const nm of ['dust', 'splash']) {
      const o = this[nm];
      if (o) o.visible = this._fxEnabled;
    }
    if (this.steam) this.steam.visible = false;   // 蒸汽永久关闭
    if (this.steamMat && this.steamMat.uniforms) {
      const u = this.steamMat.uniforms.uOpacity;
      if (u) u.value = this._fxEnabled ? (u.value || 0.4) : 0;
    }
  }

  tick(dt) {
    // freecam 启用时由它自己调 controls.update()，这里不重复（避免阻尼被算两遍）
    if (!this._freecamActive) this.controls.update();
    const pos = this.camera.position;
    // 自由飞行模式下：
    //   - 不 clamp 目标、不做相机碰撞（允许走出室外）
    //   - **绝对不能** lookAt(controls.target)：那会每帧把飞行控制器的朝向覆盖掉，
    //     表现就是"拖动转头后立刻被弹回去"（用户反馈的手感极差就是这个）
    if (!this._freeRoam) {
      this._clampTarget(this.controls.target);
      this.resolveCollision(pos);
      this.camera.lookAt(this.controls.target);
    }

    // 雨时间
    this.rainMat.uniforms.uTime.value += dt;

    // 水花：按雨量生成
    const st = this._lastState;
    if (st && st.rainLevel > 0.2) {
      const lvl = Math.max(1, Math.round(st.rainLevel));
      const spawnRate = lvl === 1 ? 60 : lvl === 2 ? 150 : 300;
      this._splashAcc += dt * spawnRate;
      const n = Math.min(40, Math.floor(this._splashAcc));
      this._splashAcc -= n;
      for (let i = 0; i < n; i++) this._spawnSplash();
    }
    this._updateSplash(dt);
    this._updateSteam(dt);
    this._updateDust(dt);
  }

  _spawnSplash() {
    const pool = this.splashPool;
    const p = pool[this.splashHead];
    this.splashHead = (this.splashHead + 1) % pool.length;
    // 落点在室外（前墙之外的人行道 / 马路），横向跟随相机
    const camX = this.camera.position.x;
    const frontZ = this.room.z[1];
    p.x = camX + (Math.random() - 0.5) * 20;
    p.z = frontZ + 0.5 + Math.random() * 13.0;
    const roadZ0 = this._roadZ0 || 5.2;
    p.y = p.z > roadZ0 ? -0.155 : 0.02;
    p.life = 0;
    p.max = 0.26 + Math.random() * 0.24;
    p.size = 0.1 + Math.random() * 0.1;
  }

  _updateSplash(dt) {
    const geo = this.splash.geometry;
    const posAttr = geo.getAttribute('position');
    const alphaAttr = geo.getAttribute('aAlpha');
    const sizeAttr = geo.getAttribute('aSize');
    const arr = posAttr.array;
    const al = alphaAttr.array;
    const sz = sizeAttr.array;
    let n = 0;
    for (let i = 0; i < this.splashPool.length; i++) {
      const p = this.splashPool[i];
      if (p.life >= p.max) continue;
      p.life += dt;
      if (p.life >= p.max) continue;
      const t = p.life / p.max;
      arr[n * 3] = p.x;
      arr[n * 3 + 1] = p.y + 0.005;
      arr[n * 3 + 2] = p.z;
      al[n] = (1 - t) * (1 - t) * 0.9;
      sz[n] = p.size * (0.7 + 1.3 * t); // 水环扩散
      n++;
    }
    geo.setDrawRange(0, n);
    this.splashLive = n;
    posAttr.needsUpdate = true;
    alphaAttr.needsUpdate = true;
    sizeAttr.needsUpdate = true;
  }

  _updateSteam(dt) {
    if (this._steamDisabled) return;   // 已按用户要求关闭蒸汽
    const geo = this.steam.geometry;
    const arr = geo.getAttribute('position').array;
    const seed = geo.getAttribute('aSeed').array;
    this._steamT = (this._steamT || 0) + dt;
    const t = this._steamT;
    for (let i = 0; i < seed.length; i++) {
      const s = seed[i];
      const y = ((s * 0.35 + t * 0.16) % 0.35) / 0.35;
      arr[i * 3] = Math.sin(t * 0.9 + s * 6.28) * 0.025 * y;
      arr[i * 3 + 1] = y * 0.42;
      arr[i * 3 + 2] = Math.cos(t * 0.7 + s * 5.2) * 0.025 * y;
    }
    geo.getAttribute('position').needsUpdate = true;
  }

  _updateDust(dt) {
    this.dustTime += dt;
    const geo = this.dust.geometry;
    const arr = geo.getAttribute('position').array;
    const base = this.dustBase;
    for (let i = 0; i < base.length / 3; i++) {
      const s = i * 0.37;
      arr[i * 3] = base[i * 3] + Math.sin(this.dustTime * 0.18 + s) * 0.22;
      arr[i * 3 + 1] = base[i * 3 + 1] + Math.sin(this.dustTime * 0.12 + s * 1.7) * 0.14;
      arr[i * 3 + 2] = base[i * 3 + 2] + Math.cos(this.dustTime * 0.15 + s * 1.3) * 0.22;
    }
    geo.getAttribute('position').needsUpdate = true;
  }

  /* ── 视图 ── */
  resize() {
    // 防呆：全屏切换的瞬间容器可能还是 0 尺寸。
    // 若直接用 0 去算 aspect，画面会被压成一条、其余区域清成纯黑
    //（用户反馈的"按 H 下半屏全黑"）。
    let w = this.container ? this.container.clientWidth : 0;
    let h = this.container ? this.container.clientHeight : 0;
    if (!w || w < 32) w = window.innerWidth || 1280;
    if (!h || h < 32) h = window.innerHeight || 720;

    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(w, h, false);

    // aspect 夹在合理范围，杜绝极端值
    const aspect = Math.max(0.1, Math.min(10, w / Math.max(h, 1)));
    this.camera.aspect = aspect;
    this.camera.updateProjectionMatrix();

    if (this.splashMat) {
      this.splashMat.uniforms.uPixelRatio.value = Math.min(window.devicePixelRatio || 1, 2);
    }
    this._lastW = w;
    this._lastH = h;
  }

  render() {
    this.renderer.render(this.scene, this.camera);
  }

  resetCamera() {
    const safe = this._resolveSafeCamera();
    this.camera.position.copy(safe.pos);
    this.controls.target.copy(safe.target);
    this.controls.update();
    this._clampTarget(this.controls.target);
    this._lastSafeCam = safe;
  }

  /**
   * 机位避障：manifest 的 cam_default 可能正好卡在门洞/门扇/吧台旁（本工程实测就在门洞里，
   * 两片门叶把画面切成棕色大斜面）。这里按优先顺序试候选机位，取第一个「视线通畅」的：
   *   1) manifest.anchors.cam_default
   *   2) Lead 建议的 (2.55,-2.30,1.60) → three (2.55,1.60,2.30)
   *   3) 房间中轴靠后 (0,1.55,-2.4) 看向吧台与女仆
   * 「通畅」判定：相机周围 0.45m 内没有网格，且相机→目标连线上 0.9m 内没有遮挡。
   */
  _resolveSafeCamera() {
    const base = { pos: this.camDefault.pos.clone(), target: this.camDefault.target.clone() };
    const candidates = [
      base,
      { pos: toThree(2.55, -2.3, 1.6), target: toThree(-1.1, 0.55, 1.0) },
      { pos: toThree(0.0, -2.35, 1.6), target: toThree(1.6, 1.0, 1.1) },
      { pos: toThree(-2.6, -2.3, 1.62), target: toThree(1.2, 1.0, 1.2) },
    ];
    for (const c of candidates) {
      if (!this.loadedFromGlb) return c;
      const ok = this._isViewClear(c.pos, c.target);
      if (ok.ok) return c;
    }
    // 全都被挡：退到房间中轴高点，至少能看到室内
    return { pos: toThree(0, -2.3, 1.7), target: toThree(0.6, 0.9, 1.4) };
  }

  /** 视线通畅检测（逐 mesh 射线，避开 Sphere/Light 之类无 layers 的对象） */
  _isViewClear(pos, target) {
    if (!this._raycaster) this._raycaster = new THREE.Raycaster();
    const rc = this._raycaster;
    const dir = target.clone().sub(pos);
    const dist = dir.length();
    if (dist < 0.2) return { ok: true, minD: Infinity };
    dir.normalize();
    rc.set(pos, dir);
    rc.near = 0.02;
    rc.far = Math.max(0.9, dist);
    let minD = Infinity;
    let hitName = null;
    const sph = new THREE.Sphere();
    const meshes = this._occluderMeshes || (this._occluderMeshes = (() => {
      const list = [];
      this.glbRoot.traverse((o) => {
        if (!o.isMesh) return;
        const n = o.name || '';
        if (/sky|steam/i.test(n)) return; // 天空球/蒸汽不挡视线
        list.push(o);
      });
      return list;
    })());

    for (const m of meshes) {
      const geo = m.geometry;
      if (!geo) continue;
      if (!geo.boundingSphere) geo.computeBoundingSphere();
      sph.copy(geo.boundingSphere).applyMatrix4(m.matrixWorld);
      // 相机贴着它自己也算遮挡（半径内）
      const dCenter = sph.center.distanceTo(pos);
      if (dCenter - sph.radius > rc.far) continue;
      try {
        const hits = rc.intersectObject(m, false);
        for (const h of hits) {
          if (h.distance < minD) {
            minD = h.distance;
            hitName = m.name;
          }
        }
      } catch (e) {
        /* 某些 mesh 的自定义 raycast 可能抛错，跳过即可 */
      }
      // 相机在包围球内且球半径很小 → 视为贴脸
      if (dCenter < sph.radius * 0.55 && sph.radius < 1.2) {
        if (minD > 0.4) {
          minD = Math.min(minD, 0.2);
          hitName = hitName || m.name;
        }
      }
    }
    const nearOk = minD > 0.55;
    return { ok: nearOk, minD: +minD.toFixed(3), hit: hitName };
  }

  /** 调试：返回当前机位与视线检测结果（给 verify/联调用） */
  cameraDiagnostics() {
    const pos = this.camera.position;
    const target = this.controls.target;
    return {
      pos: pos.toArray().map((v) => +v.toFixed(3)),
      target: target.toArray().map((v) => +v.toFixed(3)),
      safe: this._lastSafeCam
        ? {
            pos: this._lastSafeCam.pos.toArray().map((v) => +v.toFixed(3)),
            target: this._lastSafeCam.target.toArray().map((v) => +v.toFixed(3)),
          }
        : null,
      view: this._isViewClear(pos, target),
      clamp: this.clamp,
      insideRoom:
        pos.x >= this.room.x[0] &&
        pos.x <= this.room.x[1] &&
        pos.y >= this.room.y[0] &&
        pos.y <= this.room.y[1] &&
        pos.z >= this.room.z[0] &&
        pos.z <= this.room.z[1],
    };
  }

  stats() {
    const info = this.renderer.info;
    return {
      source: this.loadedFromGlb ? 'glb' : 'placeholder',
      glbError: this.glbError,
      glbBytes: this.glbBytes || 0,
      glbFetchMs: this.glbFetchMs || 0,
      glbParseMs: this.glbParseMs || 0,
      glbTotalMs: this.glbTotalMs || 0,
      glbPreflight: this.glbPreflight || null,
      triangles: info.render.triangles,
      drawCalls: info.render.calls,
      points: info.render.points,
      geometries: info.memory.geometries,
      textures: info.memory.textures,
      programs: info.programs ? info.programs.length : null,
      rainParticles: this.rainCount,
      splashParticles: this.splashLive || 0,
      colliders: this.colliders.length,
      glbStats: this.glbStats || null,
      warnings: this.warnings,
      missingAssets: this.missingAssets,
    };
  }
}

export default CafeScene;
