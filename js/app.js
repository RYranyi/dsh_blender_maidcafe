/**
 * js/app.js — 主入口 module：初始化、UI 绑定、时间/天气状态机、动画循环。
 *
 * 依赖：
 *   ./scene.js   场景（GLB / 相机 / 碰撞 / 粒子 / 室外）
 *   ./weather.js 时间 4 档 × 天气 6 态 → 光照/天空/雾/材质
 *   ./audio.js   （audio-dev 交付，可能还不存在 → 动态 import 失败即降级，不阻塞页面）
 *
 * 对外调试句柄：window.__CAFE__（验证脚本工具/web/verify.mjs 用它取状态与数字）。
 */

import { CafeScene, DEFAULT_ROOM_BLENDER } from './scene.js';
import { WeatherSystem, phaseLabel, nearestPhase, formatHour, PHASE_ANCHORS } from './weather.js';

const MANIFEST_URL = './scene/scene_manifest.json';
const GLB_URL = './scene/maid_cafe.glb';
const AUDIO_URL = './assets/audio/';

const $ = (sel) => document.querySelector(sel);

const app = {
  ready: false,
  failed: false,
  errors: [],
  scene: null,
  weather: null,
  audio: null,
  audioReady: false,
  manifest: null,
  hour: 18,
  weatherKey: 'clear',
  volume: 0.45,
  entered: false,
  transitioning: false,
  lastTimePhase: null,
  lastAudioWeather: null,
  debug: new URLSearchParams(location.search).has('debug'),
  fps: 0,
};

window.__CAFE__ = app;

/* ───────────────────────── 错误捕获（验证脚本读 app.errors） ───────────────────────── */
function captureError(kind, err) {
  const msg = err && (err.stack || err.message || String(err));
  if (app.errors.length < 60) app.errors.push({ kind, msg, at: Date.now() });
  console.error(`[cafe:${kind}]`, msg);
}
window.addEventListener('error', (e) => captureError('error', e.error || e.message));
window.addEventListener('unhandledrejection', (e) => captureError('unhandledrejection', e.reason && e.reason.reason ? e.reason.reason : e.reason));

/* ───────────────────────── manifest 读取 ───────────────────────── */
async function loadManifest() {
  try {
    const res = await fetch(MANIFEST_URL, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    app.manifest = json;
    app.manifestSource = 'file';
    return json;
  } catch (err) {
    app.manifest = null;
    app.manifestSource = 'fallback';
    app.manifestError = err && err.message;
    console.warn('[cafe] manifest 不可用，使用 CONTRACT 兜底值：', app.manifestError);
    return null;
  }
}

/* ───────────────────────── UI ───────────────────────── */
const ui = {};

function uiInit() {
  ui.stage = $('#stage');
  ui.loader = $('#loader');
  ui.loadbar = $('#loadbar-fill');
  ui.loadlabel = $('#loadlabel');
  ui.enter = $('#enter');
  ui.enterBtn = $('#enter-btn');
  ui.hud = $('#hud');
  ui.timeSlider = $('#time-slider');
  ui.timeLabel = $('#time-label');
  ui.weatherLabel = $('#weather-label');
  ui.weatherMain = document.querySelector('.weather-main');
  ui.rainSub = $('#rain-sub');
  ui.rainToggle = document.querySelector('[data-rain-toggle]');
  ui.musicVolSlider = $('#music-vol');
  ui.musicVolLabel = $('#music-vol-label');
  ui.rainVolSlider = $('#rain-vol');
  ui.rainVolLabel = $('#rain-vol-label');
  ui.audioNote = $('#audio-note');
  ui.statusTag = $('#status-tag');
  ui.fps = $('#fps');
  // 背景音乐 UI（新增）
  ui.musicTitle = $('#music-title');
  ui.musicSelect = $('#music-select');
  ui.btnMusicPrev = $('#btn-music-prev');
  ui.btnMusicNext = $('#btn-music-next');
  ui.btnMusicRandom = $('#btn-music-random');
  // 加载进度 UI
  ui.loadpct = $('#loadpct');
}

const _loadT0 = (typeof performance !== 'undefined' ? performance.now() : Date.now());

/**
 * 更新加载进度：bar 宽度 + 百分比 + 预计剩余时间
 * @param {number} p 0..1
 * @param {string} label 阶段名
 */
let _loaderShown = false;
let _loaderTimer = 0;

function progress(p, label) {
  const v = Math.max(0.02, Math.min(1, Number(p) || 0));
  // 秒进时不要闪：进度条延迟 260ms 才出现
  if (ui.loader && !_loaderShown) {
    if (!_loaderTimer) {
      _loaderTimer = setTimeout(() => {
        if (ui.loader && !ui.loader.classList.contains('done')) {
          ui.loader.classList.add('is-visible');
          _loaderShown = true;
        }
      }, 260);
    }
  }
  if (ui.loadbar) ui.loadbar.style.width = `${Math.round(v * 100)}%`;
  if (ui.loadlabel && label) ui.loadlabel.textContent = label;
  if (ui.loadpct) ui.loadpct.textContent = `${Math.round(v * 100)}%`;

  // ── 同时驱动「进入页」上的进度条（用户真正看得到的那条）──
  const elLoad = document.getElementById('enter-load');
  const elFill = document.getElementById('enter-load-fill');
  const elPct = document.getElementById('enter-load-pct');
  const elLabel = document.getElementById('enter-load-label');
  const elBtn = document.getElementById('enter-btn');
  if (elLoad) elLoad.hidden = false;
  if (elFill) elFill.style.width = `${Math.max(2, Math.round(v * 100))}%`;
  if (elPct) elPct.textContent = `${Math.round(v * 100)}%`;
  if (elLabel && label) elLabel.textContent = label;
  // 加载完 → 点亮进入按钮
  if (elBtn) {
    if (v >= 0.999) {
      elBtn.disabled = false;
      elBtn.textContent = '点击进入';
      if (elLoad) elLoad.hidden = true;
    } else {
      elBtn.disabled = true;
      elBtn.textContent = `加载中 ${Math.round(v * 100)}%`;
    }
  }
}

/* ───────────────────────── 音频（可选依赖） ───────────────────────── */

/**
 * 音频模块与 AudioEngine 实例的**模块级缓存**。
 * 目的：boot 阶段就把 audio.js import 好，用户点「进入」时不必再 await import，
 * 从而保住"用户手势"上下文 —— 这是浏览器允许播放音频的唯一条件。
 */
let _audioMod = null;
let _audioEngine = null;

/** boot 阶段调用：只 import 模块，不创建 AudioContext */
async function preloadAudioModule() {
  if (_audioMod) return _audioMod;
  try {
    _audioMod = await import('./audio.js');
  } catch (e) {
    console.warn('[cafe] audio.js 预加载失败:', e && e.message);
    _audioMod = null;
  }
  return _audioMod;
}

/**
 * 在**用户手势的同步路径里**调用：立刻 new AudioContext + resume。
 * 返回的 engine 可能还没解码完 buffer，但 ctx 已经是 running 状态。
 */
function unlockAudioSync() {
  if (_audioEngine) {
    // 已有实例：再 resume 一次（从暂停恢复也走这里）
    try { _audioEngine.init && _audioEngine.init(); } catch (e) { /* ignore */ }
    return _audioEngine;
  }
  const mod = _audioMod;
  if (!mod) return null;
  const Engine = mod.AudioEngine || mod.default;
  if (!Engine) return null;
  try {
    _audioEngine = new Engine();
  } catch (e) {
    console.warn('[cafe] AudioEngine 构造失败:', e && e.message);
    return null;
  }
  // 关键：这一步必须在当前同步调用栈里完成
  try {
    if (typeof _audioEngine.init === 'function') {
      _audioEngine.init().catch((e) => console.warn('[cafe] audio init:', e && e.message));
    }
  } catch (e) {
    console.warn('[cafe] audio init 同步部分失败:', e && e.message);
  }
  return _audioEngine;
}

async function initAudio() {
  if (app.audio) return app.audio;
  try {
    const mod = _audioMod || (await preloadAudioModule());
    const Engine = mod.AudioEngine || mod.default;
    if (!Engine) throw new Error('audio.js 未导出 AudioEngine');
    // 复用同步解锁时创建的实例；没有就现建一个并立刻 init
    if (_audioEngine) {
      app.audio = _audioEngine;
      app.audioReady = true;
      if (ui.audioNote) ui.audioNote.classList.add('hidden');
      initVolumesFromStorage();
      syncAudio();
      bindMusicUI(_audioEngine);
      return _audioEngine;
    }
    const engine = new Engine(AUDIO_URL);
    if (engine && typeof engine.init === 'function') await engine.init();
    app.audio = engine;
    app.audioReady = true;
    if (ui.audioNote) ui.audioNote.classList.add('hidden');
    initVolumesFromStorage();
    if (engine && typeof engine.on === 'function') {
      engine.on('lightning', () => triggerLightningVisuals('audio-event'));
    }
    if (typeof engine.startEventScheduler === 'function') {
      try {
        engine.startEventScheduler();
      } catch (e) {
        console.warn('[cafe] startEventScheduler 失败:', e && e.message);
      }
    }
    syncAudio();
    bindMusicUI(engine);
    return engine;
  } catch (err) {
    // 音频模块还没交付 → 静默降级，UI 照常可用
    app.audioReady = false;
    console.warn('[cafe] 音频模块不可用（页面继续运行）：', err && err.message);
    if (ui.audioNote) ui.audioNote.classList.remove('hidden');
    return null;
  }
}

/* ───────────────── 自适应画质（解决"移动有点卡"）─────────────────
 * 策略：
 *   L0（最高）：pixelRatio = min(dpr,2) · 阴影 PCFSoft · 全部特效
 *   L1：pixelRatio = min(dpr,1.5) · 阴影 PCF
 *   L2：pixelRatio = 1.0 · 阴影 PCF · 雨粒子/水花减半
 *   L3：pixelRatio = 0.8 · 关闭阴影 · 雨粒子再减
 *   L4：pixelRatio = 0.7 · 关阴影 · 关蒸汽/尘埃/水花
 * 判定：连续 90 帧平均 FPS < 45 → 降一档；连续 300 帧 > 57 → 升一档（上限 L1，不来回抖）
 * 用户拖动相机/移动时允许短暂掉帧，不计入（避免"一动就降"）
 */


/**
 * 环境亮度滑条：0.6–1.6 倍率，实时乘到 renderer.toneMappingExposure。
 * 存 localStorage，刷新后保留。
 */
/* ─────── 面板眼睛开关：收起 / 显示 ───────
   两态循环：
     1) 展开 → 收起（只留标题行）
     2) 收起 → 完全隐藏
     3) 完全隐藏 → 展开
   状态存 localStorage，刷新后保持。
*/
const PANEL_IDS = ['panel-time', 'panel-bright', 'panel-weather', 'panel-audio'];
const PANEL_STATE_KEY = 'cafe.panelState';

function loadPanelState() {
  try {
    return JSON.parse(localStorage.getItem(PANEL_STATE_KEY) || '{}') || {};
  } catch (e) { return {}; }
}

function savePanelState(st) {
  try { localStorage.setItem(PANEL_STATE_KEY, JSON.stringify(st)); } catch (e) { /* ignore */ }
}

function applyPanelState(el, st) {
  el.classList.remove('collapsed', 'docked-hidden');
  if (st === 'collapsed') el.classList.add('collapsed');
  const btn = el.querySelector('.panel-eye');
  if (btn) {
    const t = st === 'collapsed' ? '展开面板' : '收起面板';
    btn.title = t;
    btn.setAttribute('aria-label', t);
    btn.classList.toggle('is-collapsed', st === 'collapsed');
  }
}

/** 循环切换一个面板的状态 */
function cyclePanel(panelId) {
  const el = document.getElementById(panelId);
  if (!el) return;
  const st = loadPanelState();
  const cur = st[panelId] || 'open';
  // 只有两态：收起 ↔ 展开。不会「消失找不回」。
  const next = cur === 'open' ? 'collapsed' : 'open';
  st[panelId] = next;
  savePanelState(st);
  applyPanelState(el, next);
  console.log('[cafe] 面板 ' + panelId + ' → ' + next);
}

function bindPanelEyes() {
  document.querySelectorAll('.panel-eye').forEach((btn) => {
    const pid = btn.dataset.panel;
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      cyclePanel(pid);
    });
  });
  // 恢复上次状态
  const st = loadPanelState();
  for (const pid of PANEL_IDS) {
    const el = document.getElementById(pid);
    if (!el) continue;
    // 若完全隐藏了，眼睛按钮也跟着元素一起消失 → 需要额外提供一个恢复入口
    applyPanelState(el, st[pid] || 'open');
  }
  // 若某面板被完全隐藏，在 dock 底部显示一个「恢复」小按钮
  console.log('[cafe] 面板眼睛按钮已绑定');
}


function bindBrightnessUI() {
  const el = document.getElementById('brightness');
  const lab = document.getElementById('brightness-val');
  if (!el) return;

  // 范围 0.15 – 2.0（15% – 200%），默认 1.0
  const MIN = 0.15, MAX = 2.0, DEF = 1.0;
  el.min = String(MIN);
  el.max = String(MAX);
  el.step = '0.01';

  // 读上次保存
  let saved = DEF;
  try {
    const v = parseFloat(localStorage.getItem('cafe.brightness'));
    if (isFinite(v) && v >= MIN && v <= MAX) saved = v;
  } catch (e) { /* ignore */ }

  /** 把 0.15–2.0 映射成环境亮度系数。
   *  线性映射会让低端区间太钝（0.15 和 0.4 差别不明显），
   *  这里用 pow 让低端更细腻：0.15→0.06, 0.5→0.42, 1.0→1.0, 1.5→1.68, 2.0→2.4
   */
  const toFactor = (raw) => {
    const v = Math.max(MIN, Math.min(MAX, raw));
    // 以 1.0 为基准，向两端做幂次拉伸
    return v <= 1 ? Math.pow(v, 1.35) : Math.pow(v, 1.15);
  };

  const apply = (silent) => {
    const raw = parseFloat(el.value) || DEF;
    const factor = toFactor(raw);
    app.brightnessMul = /* 兼容旧字段 */ factor;
    app.brightnessRaw = raw;
    if (lab) lab.textContent = Math.round(raw * 100) + '%';
    try { localStorage.setItem('cafe.brightness', String(raw)); } catch (e) { /* ignore */ }
    try {
      if (app.weather) {
        app.weather.overrides = app.weather.overrides || {};
        app.weather.overrides.exposure = factor;
      }
      // 立即重算一帧，滑块拖动时所见即所得
      if (!silent && app.weather && typeof app.weather.update === 'function') {
        app.weather.update(0.016);
      }
    } catch (e) { /* ignore */ }
  };

  // 初始化
  el.value = String(saved);
  apply(true);

  el.addEventListener('input', () => apply(false));
  el.addEventListener('change', () => apply(false));

  // 双击标签回到 100%
  if (lab) {
    lab.style.cursor = 'pointer';
    lab.title = '双击回到 100%';
    lab.addEventListener('dblclick', () => {
      el.value = String(DEF);
      apply(false);
    });
  }
  console.log('[cafe] 亮度滑块已绑定（15%–200%，双击标签复位）');
}

function buildViewUI(fc) {
  const box = $('#view-presets');
  const hint = $('#view-mode-hint');
  if (!box) return;

  const setHint = (mode) => {
    if (!hint) return;
    hint.textContent = mode === 'fly'
      ? '拖动看 · WASD 走 · 滚轮缩放 · 空格/C 升降'
      : '拖拽环绕 · 滚轮缩放 · 右键平移';
  };

  box.innerHTML = '';

  // ① 飞行 / 环绕 切换
  const modeBtn = document.createElement('button');
  modeBtn.className = 'btn small ghost preset-btn';
  modeBtn.type = 'button';
  const syncMode = () => {
    const m = (fc.getInfo ? fc.getInfo().mode : fc.mode) || 'fly';
    modeBtn.textContent = m === 'fly' ? '✈ 飞行中' : '◎ 环绕中';
    modeBtn.title = '按 V 或 F 切换飞行 / 环绕';
    modeBtn.classList.toggle('active', m === 'fly');
    setHint(m);
  };
  modeBtn.addEventListener('click', () => { fc.toggleMode(); syncMode(); });
  box.appendChild(modeBtn);

  // ② 沉浸观看
  const imBtn = document.createElement('button');
  imBtn.id = 'btn-immersive';
  imBtn.className = 'btn small ghost preset-btn';
  imBtn.type = 'button';
  imBtn.textContent = '⛶ 沉浸观看';
  imBtn.title = '隐藏所有界面，只看场景（Esc 退出）';
  imBtn.addEventListener('click', () => setImmersive(!app.immersive));
  box.appendChild(imBtn);

  window.addEventListener('keydown', (e) => {
    const k = (e.key || '').toLowerCase();
    if (k === 'v' || k === 'f') setTimeout(syncMode, 0);   // Esc 不参与任何切换
  });
  if (fc.onModeChange) fc.onModeChange = () => syncMode();

  syncMode();
}

/** 沉浸观看：隐藏全部 UI + 进入全屏 + 重算渲染尺寸 */
function setImmersive(on) {
  app.immersive = !!on;
  document.body.classList.toggle('immersive', app.immersive);

  const btn = document.getElementById('btn-immersive');
  if (btn) btn.textContent = app.immersive ? '⛶ 退出沉浸' : '⛶ 沉浸观看';
  const ex = document.getElementById('immersive-exit');
  if (ex) ex.hidden = !app.immersive;

  // ① 真正进/出全屏（浏览器不支持或用户拒绝时静默降级）
  try {
    if (app.immersive) {
      const el = document.documentElement;
      const req = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
      if (req && !document.fullscreenElement) {
        const p = req.call(el);
        if (p && p.catch) p.catch(() => {});
      }
    } else if (document.fullscreenElement) {
      const exit = document.exitFullscreen || document.webkitExitFullscreen;
      if (exit) {
        const p = exit.call(document);
        if (p && p.catch) p.catch(() => {});
      }
    }
  } catch (e) { /* ignore */ }

  // ② 关键：视口变了必须重算 renderer 尺寸，否则 canvas 覆盖不到的区域会变黑
  const doResize = () => {
    try { if (app.scene && app.scene.resize) app.scene.resize(); } catch (e) {}
  };
  requestAnimationFrame(doResize);
  setTimeout(doResize, 120);
  setTimeout(doResize, 420);
}

// 绑定沉浸退出按钮（HTML 里存在但之前漏了 click handler）
(function bindImmersiveExit() {
  const bind = () => {
    const btn = document.getElementById('immersive-exit');
    if (!btn || btn.__cafeBound) return;
    btn.__cafeBound = true;
    btn.addEventListener('click', () => setImmersive(false));
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  } else {
    bind();
  }
  // 兜底：boot 晚于 DOM 时也能绑上
  setTimeout(bind, 0);
  setTimeout(bind, 800);
})();

// 退出全屏（用户按 Esc / F11 由浏览器处理）时同步退出沉浸状态
document.addEventListener('fullscreenchange', () => {
  if (!document.fullscreenElement && app.immersive) {
    app.immersive = false;
    document.body.classList.remove('immersive');
    const btn = document.getElementById('btn-immersive');
    if (btn) btn.textContent = '⛶ 沉浸观看';
    const ex = document.getElementById('immersive-exit');
    if (ex) ex.hidden = true;
    try { if (app.scene && app.scene.resize) app.scene.resize(); } catch (e) {}
  }
});

// 窗口尺寸变化也补一次（全屏切换可能不触发 resize）
window.addEventListener('resize', () => {
  if (app.immersive) {
    try { if (app.scene && app.scene.resize) app.scene.resize(); } catch (e) {}
  }
});

// 全局：H 键切换沉浸，Esc 退出
window.addEventListener('keydown', (e) => {
  const k = (e.key || '').toLowerCase();
  if (k === 'h') { setImmersive(!app.immersive); e.preventDefault(); }
  // 注意：Esc 故意**不绑定任何功能**（用户要求）。
  // 退出沉浸：再按一次 H，或点右上角「✕ 退出沉浸」。
});


function bindMusicUI(engine) {
  if (!engine) return;
  const tracks = engine.tracks || [];
  const sel = ui.musicSelect;

  // 填下拉选项
  if (sel && tracks.length) {
    sel.innerHTML = '<option value="">选择曲目…</option>' +
      tracks.map((t, i) => `<option value="${i}">${t.title} — ${t.artist}</option>`).join('');
    sel.addEventListener('change', () => {
      const v = sel.value;
      if (v === '') return;
      const idx = Number(v);
      if (Number.isFinite(idx) && typeof engine.switchTo === 'function') {
        engine.switchTo(idx);       // 平滑交叉淡入淡出
      }
      sel.value = '';               // 回到占位项
    });
  }

  const showTitle = (idx, track) => {
    const t = track || (tracks[idx] || null);
    if (ui.musicTitle) ui.musicTitle.textContent = t ? `${t.title}` : '—';
    if (sel && t) sel.title = `${t.title} — ${t.artist}`;
  };
  showTitle(engine.currentIndex, engine.currentTrack);

  // 引擎切歌完成（含交叉结束、随机切）都同步 UI
  app.audioEngine = engine;
  engine.onTrackChange = (idx, track) => showTitle(idx, track);
  if (typeof engine.on === 'function') {
    engine.on('trackchange', (p) => showTitle(p && p.index, p && p.track));
  }

  if (ui.btnMusicPrev) {
    ui.btnMusicPrev.addEventListener('click', () => {
      if (typeof engine.prevTrack === 'function') engine.prevTrack();
    });
  }
  if (ui.btnMusicNext) {
    ui.btnMusicNext.addEventListener('click', () => {
      if (typeof engine.nextTrack === 'function') engine.nextTrack();
    });
  }
  if (ui.btnMusicRandom) {
    ui.btnMusicRandom.addEventListener('click', () => {
      if (typeof engine.randomNext === 'function') engine.randomNext();
    });
  }

  // ── 自动切歌：等当前曲目**自然播完**再换下一首 ──────────────
  // 旧实现是「空闲 90 秒随机换一首」，90 秒远短于一首歌（2–4 分钟），
  // 所以用户听到的总是"没播完就被切走"。更糟的是判断里引用了不存在的
  // engine.crossing，条件恒成立。
  //
  // 现在：每 1 秒轮询一次，当前曲目播放进度 >= 时长才切（crossfade 由引擎做）；
  // 若用户手动切歌，计时点由引擎侧 trackStartedAt 自动重置。
  let autoTimer = 0;
  const armAuto = () => {
    clearTimeout(autoTimer);
    autoTimer = setTimeout(() => {
      try {
        const eng = app.audioEngine || engine;
        const playing = eng && !eng.paused;
        const finished = eng && typeof eng.currentFinished === 'boolean' && eng.currentFinished;
        if (playing && finished) {
          if (typeof eng.randomNext === 'function') eng.randomNext();
        }
      } catch (e) { /* ignore */ }
      armAuto();                         // 继续轮询（下次切歌由引擎状态驱动）
    }, 1000);
  };
  armAuto();
  // 手动切歌后不必重置计时（trackStartedAt 由引擎负责），但要保证轮询还在跑
  for (const b of [ui.btnMusicPrev, ui.btnMusicNext, ui.btnMusicRandom]) {
    if (b) b.addEventListener('click', armAuto);
  }
  if (sel) sel.addEventListener('change', armAuto);
}

function setMusicVolume(v, opts = {}) {
  app.musicVol = Math.max(0, Math.min(1, Number(v) || 0));
  if (ui.musicVolSlider) ui.musicVolSlider.value = String(Math.round(app.musicVol * 100));
  if (ui.musicVolLabel) ui.musicVolLabel.textContent = `${Math.round(app.musicVol * 100)}%`;
  try {
    if (app.audio && typeof app.audio.setMusicVolume === 'function') {
      app.audio.setMusicVolume(app.musicVol);
    }
  } catch (e) { captureError('audio.setMusicVolume', e); }
  try { localStorage.setItem('cafe.musicVol', String(app.musicVol)); } catch (e) {}
  if (!opts.silent) app.lastVolumeChange = Date.now();
}

function setRainVolume(v, opts = {}) {
  app.rainVol = Math.max(0, Math.min(1, Number(v) || 0));
  if (ui.rainVolSlider) ui.rainVolSlider.value = String(Math.round(app.rainVol * 100));
  if (ui.rainVolLabel) ui.rainVolLabel.textContent = `${Math.round(app.rainVol * 100)}%`;
  try {
    if (app.audio && typeof app.audio.setRainVolume === 'function') {
      app.audio.setRainVolume(app.rainVol);
    }
  } catch (e) { captureError('audio.setRainVolume', e); }
  try { localStorage.setItem('cafe.rainVol', String(app.rainVol)); } catch (e) {}
  if (!opts.silent) app.lastVolumeChange = Date.now();
}

/** 从 localStorage 恢复音乐/雨声音量（音频就绪后调用一次） */
function initVolumesFromStorage() {
  let mv = 0.45, rv = 0.60;
  try {
    const a1 = parseFloat(localStorage.getItem('cafe.musicVol'));
    const a2 = parseFloat(localStorage.getItem('cafe.rainVol'));
    if (isFinite(a1)) mv = a1;
    if (isFinite(a2)) rv = a2;
  } catch (e) { /* ignore */ }
  setMusicVolume(mv, { silent: true });
  setRainVolume(rv, { silent: true });
}

/** 兼容旧调用点：总音量恒为 1，音乐/雨声各自独立 */
function setVolume(v, opts = {}) {
  app.musicVol = Math.max(0, Math.min(1, Number(v) || 0));
  app.rainVol = app.musicVol;
  if (!opts.silent) app.lastVolumeChange = Date.now();
}

function syncAudio() {
  if (!app.audio) return;
  const phase = nearestPhase(app.hour).key;
  if (phase !== app.lastTimePhase && typeof app.audio.setTimePhase === 'function') {
    app.lastTimePhase = phase;
    try {
      app.audio.setTimePhase(phase, { fadeMs: 1200 });
    } catch (e) {
      captureError('audio.setTimePhase', e);
    }
  }
  if (app.weatherKey !== app.lastAudioWeather && typeof app.audio.setWeather === 'function') {
    app.lastAudioWeather = app.weatherKey;
    try {
      app.audio.setWeather(app.weatherKey, { fadeMs: 1500 });
    } catch (e) {
      captureError('audio.setWeather', e);
    }
  }
}

/* ───────────────────────── 时间 & 天气状态机 ───────────────────────── */
let timeDebounce = null;

function applyHour(hour, opts = {}) {
  app.hour = ((hour % 24) + 24) % 24;
  if (ui.timeSlider && document.activeElement !== ui.timeSlider) {
    ui.timeSlider.value = String(app.hour);
  }
  const label = phaseLabel(app.hour);
  if (ui.timeLabel) ui.timeLabel.textContent = label;

  if (app.weather) app.weather.setHour(app.hour);

  // 拖动中不切音频；松手 220ms 后调 setTimePhase（避免高频切换）
  if (!opts.silent) {
    clearTimeout(timeDebounce);
    timeDebounce = setTimeout(() => syncAudio(), 220);
  }
}

const WEATHER_LABELS = {
  clear: '晴天',
  cloudy: '多云',
  rain_light: '小雨',
  rain_med: '中雨',
  rain_heavy: '大雨',
  storm: '雷阵雨',
};

const RAIN_KEYS = new Set(['rain_light', 'rain_med', 'rain_heavy', 'storm']);

function applyWeather(key, opts = {}) {
  if (!WEATHER_LABELS[key]) return;
  app.weatherKey = key;
  const label = WEATHER_LABELS[key];
  if (ui.weatherLabel) ui.weatherLabel.textContent = label;
  if (app.weather) app.weather.setWeather(key);

  // 一级按钮选中态
  const primary = RAIN_KEYS.has(key) ? 'rain' : key;
  document.querySelectorAll('#panel-weather [data-weather]').forEach((b) => {
    const k = b.getAttribute('data-weather');
    b.setAttribute('aria-pressed', String(k === key));
    b.classList.toggle('active', k === key);
  });
  const rainBtn = ui.rainToggle;
  if (rainBtn) {
    const on = RAIN_KEYS.has(key);
    rainBtn.setAttribute('aria-pressed', String(on));
    rainBtn.classList.toggle('active', on);
    if (on && ui.rainSub) ui.rainSub.classList.remove('hidden');
  }
  if (ui.rainSub) {
    if (RAIN_KEYS.has(key)) {
      ui.rainSub.classList.remove('hidden');
    } else if (!opts.keepSub) {
      ui.rainSub.classList.add('hidden');
    }
  }
  clearTimeout(timeDebounce);
  syncAudio();
}

/* ── 闪电视觉：天空白光爆闪 + 方向光脉冲 + 路灯闪烁 ── */
let lightningTimer = null;
let lightningNextAt = 0;
const lightning = { count: 0, lastAt: 0, history: [] };

function triggerLightningVisuals(source = 'timer') {
  if (!app.weather) return;
  const t = performance.now();
  // 双闪：一道主闪 + 一次回闪，更像真实雷暴
  app.weather.flash(1.0);
  app.scene && app.scene.setFlashLevel(1.0);
  setTimeout(() => {
    app.weather && app.weather.flash(0.75);
    app.scene && app.scene.setFlashLevel(0.85);
  }, 120);
  setTimeout(() => {
    app.weather && app.weather.flash(0.4);
  }, 260);
  lightning.count++;
  lightning.lastAt = Date.now();
  lightning.history.push({ at: lightning.lastAt, source });
  if (lightning.history.length > 20) lightning.history.shift();

  // 音频侧：由 app 主动通知（雷声延迟由 audio 内部按 manifest 处理）
  if (app.audio && typeof app.audio.notifyLightning === 'function') {
    try {
      app.audio.notifyLightning();
    } catch (e) {
      captureError('audio.notifyLightning', e);
    }
  }
  return t;
}

function scheduleLightning() {
  clearTimeout(lightningTimer);
  const isStorm = app.weatherKey === 'storm';
  app.lightningActive = isStorm;
  if (!isStorm) {
    lightningNextAt = 0;
    return;
  }
  const delay = 3000 + Math.random() * 7000; // 契约：随机 3–10s 一次
  lightningNextAt = Date.now() + delay;
  lightningTimer = setTimeout(() => {
    triggerLightningVisuals('timer');
    scheduleLightning();
  }, delay);
}

/** 外部（验证脚本）可直接调用 */
app.triggerLightning = () => triggerLightningVisuals('external');
app.lightningState = lightning;

/* ───────────────────────── 动画循环 ───────────────────────── */
let rafId = 0;
let lastFrame = 0;
let fpsAccum = 0;
let fpsFrames = 0;
let envRefreshTimer = 0;

function loop(now) {
  rafId = requestAnimationFrame(loop);
  const dt = Math.min(0.1, lastFrame ? (now - lastFrame) / 1000 : 0.016);
  lastFrame = now;

  // ── 自适应画质：连续掉帧就降档（用户反馈"网页端移动有点卡"）──

  if (app.weather) app.weather.update(dt);
  const st = app.weather ? app.weather.state : null;
  const tgt = app.weather ? app.weather.targetState : null;

  if (app.scene) {
    app.scene.applyWeatherState(st, dt, tgt);
    // ★ 相机更新放在渲染前、同一个循环里（与 bedroom_scene 一致）
    if (app.freecam && app.freecam.enabled) app.freecam.update(dt);
    app.scene.tick(dt);
    app.scene.render();
  }

  // 状态稳定后再重烘环境贴图（避免每帧 PMREM）
  if (app.weather) {
    envRefreshTimer += dt;
    if (envRefreshTimer > 0.6) {
      envRefreshTimer = 0;
      if (app.weather._skyEnvUpdate && !app.weather._envBusy) {
        app.weather._skyEnvUpdate = false;
        // 放到下一个空闲帧
        setTimeout(() => {
          try {
            app.weather.refreshEnvironment();
            app.scene && app.scene.windowDrops && (app.scene.windowDropsMat.needsUpdate = true);
          } catch (e) {
            console.warn('[cafe] env 重烘失败:', e && e.message);
          }
        }, 0);
      }
    }
  }

  // FPS / debug 面板
  fpsAccum += dt;
  fpsFrames++;
  if (fpsAccum >= 0.5) {
    app.fps = Math.round(fpsFrames / fpsAccum);
    fpsAccum = 0;
    fpsFrames = 0;
    updateDebugPanel();
  }

  if (app.scene && app.scene._flashLevel > 0) {
    const decay = Math.exp(-dt * 6.5);
    app.scene.setFlashLevel(app.scene._flashLevel * decay);
    if (app.scene._flashLevel < 0.002) app.scene.setFlashLevel(0);
  }
}

function updateDebugPanel() {
  if (!app.debug || !ui.fps || !app.scene) return;
  const s = app.scene.stats();
  const w = app.weather ? app.weather.info() : {};
  ui.fps.textContent =
    `${app.fps} fps\n` +
    `tri ${s.triangles}\n` +
    `draw ${s.drawCalls}  pts ${s.points}\n` +
    `rain ${s.rainParticles}\n` +
    `sun ${w.sunIntensity}  exp ${w.exposure}\n` +
    `fog ${w.fogDensity}`;
}

/* ───────────────────────── 启动 ───────────────────────── */
async function boot() {
  uiInit();
  const isDebug = app.debug;
  if (isDebug && ui.fps) ui.fps.classList.remove('hidden');
  if (ui.statusTag && isDebug) ui.statusTag.classList.remove('hidden');

  progress(0.02, '读取场景清单');
  const manifest = await loadManifest();

  app.scene = new CafeScene({
    container: ui.stage,
    manifest,
    debug: isDebug,
    glbUrl: GLB_URL,
    onProgress: (p, label) => progress(p, label === 'loading glb' ? '加载三维场景…' : label === 'ready' ? '就绪' : label === 'fallback' ? '模型未就绪 · 使用占位场景' : '读取场景清单'),
  });

  app.weather = new WeatherSystem(app.scene.scene, app.scene.renderer, {
    manifest,
    roomThree: app.scene.room,
  });
  // 环境贴图只在反射材质上生效（r160 无 scene.environmentIntensity，全屋 IBL 会把奶油墙洗白）
  app.weather.onEnvChanged = (tex) => {
    // ★ 全屋 IBL 强度 0.85 → 0.30：r160 没有 environmentIntensity，
    //   0.85 的 IBL 会把奶油墙/地板整体提亮成灰白（室内永远亮的主因之一）
    if (app.scene) app.scene.applyEnvironmentMap(tex, 0.30);
  };
  app.weather.onHdriChanged = (rec) => {
    app.appliedHdri = { phase: app.weather.hdriUsedPhase, url: rec.url, loadMs: rec.loadMs, bytes: rec.bytes };
  };
  // 预载全部 4 张 HDRI（本地 1k，总共约 5.8MB；后台串行，不阻塞首帧）
  if (typeof app.weather.loadHdriForPhase === 'function') {
    const order = ['morning', 'noon', 'dusk', 'night'];
    app.hdriReadyPromise = (async () => {
      const out = {};
      for (const ph of order) out[ph] = await app.weather.loadHdriForPhase(ph);
      return out;
    })();
  }

  // 时间/天气初值（可被 URL 参数覆盖，便于验证脚本对拍）
  const qs = new URLSearchParams(location.search);
  const hourParam = qs.has('hour') ? Number(qs.get('hour')) : 18;
  const weatherParam = qs.get('weather');
  applyHour(Number.isFinite(hourParam) ? hourParam : 18, { silent: true });
  applyWeather(WEATHER_LABELS[weatherParam] ? weatherParam : 'clear', { silent: true });
  app.weather.snap();

  // 材质联动（GLB 到位后才有意义；占位场景用占位材质）
  bindMaterialLinks();

  // 先把音频模块 import 好（只加载代码，不建 AudioContext）
  try { await preloadAudioModule(); } catch (e) { /* ignore */ }

  progress(0.08, '加载三维场景…');
  const tLoad0 = performance.now();
  const ok = await app.scene.loadGLB(GLB_URL);
  app.loadMs = Math.round(performance.now() - tLoad0);
  app.glbLoaded = !!ok;
  if (!ok) {
    app.scene._buildPlaceholder();
    if (ui.statusTag) ui.statusTag.classList.remove('hidden');
  } else {
    if (ui.statusTag) ui.statusTag.classList.add('hidden');
    bindMaterialLinks();
  }
  app.scene.resetCamera();
  app.scene.resize();


  // ── 自由视角（WASD 漫游 + 室外 + 固定视角预设）──────────────
  try {
    const fcMod = await import('./freecam.js');
    const FreeCam = fcMod.FreeCam || fcMod.default;
    app.freecam = new FreeCam(app.scene, {
      camera: app.scene.camera,
      controls: app.scene.controls,
      dom: app.scene.renderer && app.scene.renderer.domElement,
    });
    app.freecam.enable();
    app.freecam.widenLimits();      // 先放开远距/极角限制，允许走到室外
    buildViewUI(app.freecam);
    app.freecamBound = true;
  } catch (e) {
    console.warn('[cafe] freecam 不可用:', e && e.message);
    captureError('freecam', e);
  }

  // 亮度滑块独立于 freecam（用户要求能在网页自己挑亮度）
  // ── F11 全屏兜底：浏览器原生全屏不触发 fullscreenchange，
  //    但视口尺寸会变。这里轮询 window 尺寸，变了就 resize。
  //    这是修「F11 后画面显示不全」的关键（H 键走 Fullscreen API 本来就有事件）。
  try {
    let _lastVW = window.innerWidth;
    let _lastVH = window.innerHeight;
    let _f11Stable = 0;
    const watchViewport = () => {
      const w = window.innerWidth, h = window.innerHeight;
      if (w !== _lastVW || h !== _lastVH) {
        _lastVW = w; _lastVH = h;
        // 连续 3 次检测（F11 动画期间尺寸可能抖动）
        _f11Stable = 0;
        if (app.scene && typeof app.scene.resize === 'function') app.scene.resize();
        setTimeout(() => { if (app.scene) app.scene.resize(); }, 120);
        setTimeout(() => { if (app.scene) app.scene.resize(); }, 420);
        setTimeout(() => { if (app.scene) app.scene.resize(); }, 900);
      }
      requestAnimationFrame(watchViewport);
    };
    // 用 rAF 轮询太耗，改成每 400ms 检查一次（足够快且省）
    setInterval(() => {
      const w = window.innerWidth, h = window.innerHeight;
      if (w !== _lastVW || h !== _lastVH) {
        _lastVW = w; _lastVH = h;
        if (app.scene && typeof app.scene.resize === 'function') app.scene.resize();
        setTimeout(() => { if (app.scene) app.scene.resize(); }, 150);
        setTimeout(() => { if (app.scene) app.scene.resize(); }, 500);
      }
    }, 400);
    // 标准 resize 事件也接（部分浏览器 F11 会触发）
    window.addEventListener('resize', () => {
      if (!app.scene) return;
      app.scene.resize();
      setTimeout(() => app.scene && app.scene.resize(), 150);
      setTimeout(() => app.scene && app.scene.resize(), 500);
    });
    console.log('[cafe] F11 视口监听已启用');
  } catch (e) {
    console.warn('[cafe] F11 视口监听挂载失败', e && e.message);
  }

  try { bindPanelEyes(); } catch (e) {
    console.warn('[cafe] 面板眼睛绑定失败', e && e.message);
  }

  try { bindBrightnessUI(); } catch (e) {
    console.warn('[cafe] 亮度滑块绑定失败', e && e.message);
  }

  // 音量初始化独立于 freecam（不放上面的 try 里，避免 freecam 失败时被跳过）
  try {
    const mv = parseFloat(localStorage.getItem('cafe.musicVol'));
    const rv = parseFloat(localStorage.getItem('cafe.rainVol'));
    setMusicVolume(isFinite(mv) ? mv : 0.45, { silent: true });
    setRainVolume(isFinite(rv) ? rv : 0.60, { silent: true });
  } catch (e) { /* ignore */ }

  progress(1, '就绪');
  setTimeout(() => ui.loader && ui.loader.classList.add('done'), 260);

  // 首帧
  const tFirst = performance.now();
  app.weather.snap();
  app.scene.applyWeatherState(app.weather.state, 1, app.weather.targetState);
  app.scene.render();
  app.firstFrameMs = Math.round(performance.now() - tFirst);
  app.firstFrameAt = Date.now();
  lastFrame = 0;
  rafId = requestAnimationFrame(loop);

  app.ready = true;
  app.readyAt = Date.now();

  // 进入遮罩：点击后 init 音频（自动播放策略）；允许直接进入（音频降级）
  if (ui.enterBtn) {
    ui.enterBtn.addEventListener('click', onEnter);
    ui.enterBtn.focus({ preventScroll: true });
  }
  // 兜底：若音频模块缺失，用户点进入依然可以看场景
  document.addEventListener('keydown', (e) => {
    if (!app.entered && (e.key === 'Enter' || e.key === ' ')) onEnter();
  });

  bindUI();
  window.addEventListener('resize', () => {
    app.scene && app.scene.resize();
  });
  syncAudio();
  bootQuery();
}

/**
 * URL 参数开机引导（自动化验收用，不影响正常访问）：
 *   ?auto=1                  自动进入（跳过「点击进入」，音频降级为静音）
 *   ?time=12.5               初始时间（小时，小数可）
 *   ?weather=rain_med        初始天气（clear/cloudy/rain_light/rain_med/rain_heavy/storm）
 * 用法示例：
 *   index.html?debug=1&auto=1&time=21.5&weather=storm
 */
function bootQuery() {
  let q;
  try {
    q = new URLSearchParams(location.search);
  } catch (e) {
    return;
  }
  const t = q.get('time');
  if (t != null && t !== '' && Number.isFinite(Number(t))) {
    app.hour = ((Number(t) % 24) + 24) % 24;
    if (ui.timeSlider) ui.timeSlider.value = String(app.hour);
    if (ui.timeLabel) ui.timeLabel.textContent = phaseLabel(app.hour);
    if (app.weather) app.weather.setHour(app.hour);
  }
  const w = q.get('weather');
  if (w && WEATHER_LABELS[w]) applyWeather(w);
  if (q.has('auto')) setTimeout(() => { onEnter().catch(() => {}); }, 80);
}

function bindMaterialLinks() {
  if (!app.scene || !app.weather) return;
  const { wet, lamps } = app.scene.collectMaterialsForWeather();
  app.weather.setWetMaterials(wet);
  app.weather.setLampMaterials(lamps);
  // 参与 IBL 的材质：GLB 全部 PBR 材质（r160 靠 envMapIntensity 缩放强度）
  const envMats = app.scene.collectReflectiveMaterials ? app.scene.collectReflectiveMaterials() : [];
  const allMats = app.scene.glbMaterials || [];
  app.weather.setEnvMaterials([...envMats, ...allMats, ...wet, ...lamps]);
  if (app.weather.lamps) {
    for (const l of app.weather.lamps) l.castShadow = false;
  }
}

async function onEnter() {
  if (app.entered) return;
  app.entered = true;
  if (ui.enter) ui.enter.classList.add('gone');
  if (ui.hud) ui.hud.classList.remove('hidden');
  // 视角条（自由漫游 + 固定视角预设）
  const vb = document.getElementById('view-bar');
  if (vb) vb.classList.remove('hidden');
  // ★ 关键：在点击事件的**同步**路径里创建并 resume AudioContext
  //   （任何 await 之后再创建都会被浏览器判为"非手势"，导致静音）
  try { unlockAudioSync(); } catch (e) { console.warn('[cafe] unlockAudioSync', e); }
  await initAudio();
  syncAudio();
  scheduleLightning();
  app.enteredAt = Date.now();
}

/* ───────────────────────── UI 绑定 ───────────────────────── */
function bindUI() {
  // 时间滑块：input 实时（阻尼过渡由 weather 负责），change 时立即同步音频
  if (ui.timeSlider) {
    ui.timeSlider.addEventListener('input', () => {
      const v = Number(ui.timeSlider.value);
      app.hour = ((v % 24) + 24) % 24;
      if (ui.timeLabel) ui.timeLabel.textContent = phaseLabel(app.hour);
      if (app.weather) app.weather.setHour(app.hour);
      app.lastUserTimeAt = Date.now();
      clearTimeout(timeDebounce);
      timeDebounce = setTimeout(() => syncAudio(), 260);
    });
    ui.timeSlider.addEventListener('change', () => {
      const v = Number(ui.timeSlider.value);
      applyHour(v);
    });
    // 键盘微调
    ui.timeSlider.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const delta = e.key === 'ArrowLeft' ? -0.25 : 0.25;
        applyHour(Number(ui.timeSlider.value) + delta);
        e.preventDefault();
      }
    });
  }

  // 天气一级按钮
  document.querySelectorAll('#panel-weather [data-weather]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-weather');
      applyWeather(key);
      scheduleLightning();
      flashPanel(btn);
    });
  });

  // 雨天二级展开
  if (ui.rainToggle) {
    ui.rainToggle.addEventListener('click', () => {
      if (!ui.rainSub) return;
      const opening = ui.rainSub.classList.contains('hidden');
      if (opening) {
        ui.rainSub.classList.remove('hidden');
        // 首次展开选中当前雨势或小雨
        const cur = app.weatherKey;
        if (!RAIN_KEYS.has(cur)) applyWeather('rain_light', { keepSub: true });
        else applyWeather(cur, { keepSub: true });
        flashPanel(ui.rainToggle);
      } else {
        ui.rainSub.classList.add('hidden');
        ui.rainToggle.setAttribute('aria-pressed', 'false');
        ui.rainToggle.classList.remove('active');
      }
    });
  }

  // 音量
  if (ui.musicVolSlider) {
    ui.musicVolSlider.addEventListener('input', () => {
      setMusicVolume(Number(ui.musicVolSlider.value) / 100);
    });
  }
  if (ui.rainVolSlider) {
    ui.rainVolSlider.addEventListener('input', () => {
      setRainVolume(Number(ui.rainVolSlider.value) / 100);
    });
  }

  // 默认机位
  if (ui.btnResetCam) {
    ui.btnResetCam.addEventListener('click', () => {
      app.scene && app.scene.resetCamera();
      flashPanel(ui.btnResetCam);
    });
  }

  // 快捷键：空格切换雨天/晴天，R 复位
  document.addEventListener('keydown', (e) => {
    if (!app.entered) return;
    if (e.target && /input|select|textarea/i.test(e.target.tagName)) return;
    if (e.key === 'r' || e.key === 'R') app.scene && app.scene.resetCamera();
    if (e.key === '1') applyWeather('clear');
    if (e.key === '2') applyWeather('cloudy');
    if (e.key === '3') applyWeather('rain_med');
    if (e.key === '4') applyWeather('storm');
  });

  // 初始按钮态
  applyWeather(app.weatherKey, { silent: true });
  if (ui.timeLabel) ui.timeLabel.textContent = phaseLabel(app.hour);

  // 记录器：给验证脚本 / 控制台用
  app.setState = (opts = {}) => {
    if (opts.hour != null) applyHour(Number(opts.hour));
    if (opts.weather) {
      applyWeather(opts.weather);
      scheduleLightning();
    }
    return app.snapshot();
  };
  app.snapshot = () => {
    const w = app.weather ? app.weather.info() : null;
    const s = app.scene ? app.scene.stats() : null;
    return {
      ready: app.ready,
      entered: app.entered,
      manifestSource: app.manifestSource,
      glbLoaded: app.glbLoaded,
      hour: app.hour,
      hourLabel: ui.timeLabel ? ui.timeLabel.textContent : null,
      weather: app.weatherKey,
      weatherLabel: ui.weatherLabel ? ui.weatherLabel.textContent : null,
      weatherButtons: Array.from(document.querySelectorAll('#panel-weather [data-weather]')).map((b) => ({
        key: b.getAttribute('data-weather'),
        pressed: b.getAttribute('aria-pressed'),
      })),
      musicVol: app.musicVol,
      rainVol: app.rainVol,
      volumeLabel: ui.volumeLabel ? ui.volumeLabel.textContent : null,
      audioReady: app.audioReady,
      lightningActive: !!app.lightningActive,
      lightningCount: lightning.count,
      lights: w,
      render: s,
      errors: app.errors.length,
      fps: app.fps,
      enterHidden: ui.enter ? ui.enter.classList.contains('gone') : null,
    };
  };
  // 24 组状态批量对拍（验证脚本用，也方便人工在控制台跑）
  app.matrix = (faster = true) => {
    const hours = [7, 12.5, 18, 21.5];
    const out = [];
    const prev = app.weather ? app.weather._timeScale : 1;
    if (app.weather) app.weather._timeScale = 0.02;
    for (const h of hours) {
      for (const key of Object.keys(WEATHER_LABELS)) {
        applyHour(h, { silent: true });
        applyWeather(key, { silent: true, keepSub: true });
        app.weather.snap();
        app.scene.applyWeatherState(app.weather.state, 1, app.weather.targetState);
        app.scene.render();
        const info = app.weather.info();
        out.push({
          hour: h,
          phase: info.phase,
          phaseLabel: info.phaseLabel,
          weather: key,
          weatherLabel: WEATHER_LABELS[key],
          sunIntensity: info.sunIntensity,
          sunElevation: info.sunElevation,
          exposure: info.exposure,
          fogDensity: info.fogDensity,
          lampIntensity: info.lampIntensity,
          rainLevel: info.rainLevel,
          rainParticles: app.scene.rainCount,
          skyTop: info.skyTop,
          skyHorizon: info.skyHorizon,
        });
      }
    }
    if (app.weather) app.weather._timeScale = prev;
    // 恢复原状
    applyHour(app.hour, { silent: true });
    applyWeather(app.weatherKey, { silent: true, keepSub: true });
    if (app.weather) app.weather.snap();
    return out;
  };
  app.PHASE_ANCHORS = PHASE_ANCHORS;
}

function flashPanel(el) {
  if (!el) return;
  el.style.transition = 'none';
  el.style.transform = 'scale(0.96)';
  requestAnimationFrame(() => {
    el.style.transition = '';
    el.style.transform = '';
  });
}

/* ───────────────────────── 自启动 ───────────────────────── */
boot().catch((err) => {
  app.failed = true;
  captureError('boot', err);
  const label = $('#loadlabel');
  if (label) label.textContent = `启动失败：${err && err.message}`;
});
