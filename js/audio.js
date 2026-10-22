/**
 * audio.js —— 女仆咖啡馆 · 背景音乐引擎（Web Audio API 版）
 *
 * 【为什么重写】
 *   上一版用 <audio> 元素 + setInterval 淡变，问题：
 *     1) 音乐文件里混进了 theora 视频流（封面图），<audio> 播不了 → 没声音
 *     2) <audio loop> 有微小间隙；雨声 30 秒一段，每到接缝就"停一下" → 用户听到断续
 *     3) 每次 setWeather 都 new Audio() → 多个实例打架
 *
 * 【这一版】
 *   - 全部走 Web Audio API：decodeAudioData 一次解码，AudioBufferSourceNode.loop = true
 *     → 采样级无缝循环，绝不会断
 *   - 音乐/雨声各一条常驻 source + GainNode，交叉淡化用 gain.gain.setValueAtTime 自动化
 *   - 5 首曲目预加载成 AudioBuffer 缓存在内存
 *   - 切歌：新 source 从 0 音量起、旧 source 淡出后停 → 等功率交叉 1.2 秒
 *
 * 【对外接口保持不变】（app.js 依赖）
 *   await init() / setMasterVolume(v) / setTimePhase(p) / setWeather(k)
 *   setPaused(b) / playOnce(n) / notifyLightning() / on(evt, cb)
 *   新增：switchTo(i) / nextTrack() / prevTrack() / randomNext() / tracks / currentTrack
 */

const MUSIC_TRACKS = [
  { id: 'creamydream',   file: '01_creamydream.ogg',   title: 'creamydream',   artist: 'flap+frog' },
  { id: 'lazy_red_sans', file: '02_lazy_red_sans.ogg', title: 'lazy red sans', artist: 'flap+frog' },
  { id: 'mental_sketch', file: '03_mental_sketch.ogg', title: 'mental sketch', artist: 'flap+frog' },
  { id: 'starry_sky',    file: '04_starry_sky.ogg',    title: 'starry sky',    artist: 'flap+frog' },
  { id: 'un_fiore_rosa', file: '05_un_fiore_rosa.ogg', title: 'Un Fiore Rosa', artist: 'flap+frog' },
];

const MUSIC_BASE = './assets/music/';
const RAIN_BASE = './assets/audio/';
const RAIN_FILE = 'amb_rain_med.ogg';
const CROSSFADE = 1.2;
const RAIN_WEATHERS = new Set(['rain_light', 'rain_med', 'rain_heavy', 'storm']);

class Emitter {
  constructor() { this._map = new Map(); }
  on(evt, cb) {
    if (typeof cb !== 'function') return () => {};
    if (!this._map.has(evt)) this._map.set(evt, new Set());
    this._map.get(evt).add(cb);
    return () => this.off(evt, cb);
  }
  off(evt, cb) { const s = this._map.get(evt); if (s) s.delete(cb); }
  emit(evt, payload) {
    const s = this._map.get(evt);
    if (!s) return;
    for (const cb of Array.from(s)) {
      try { cb(payload); } catch (e) { /* 单个回调异常不影响引擎 */ }
    }
  }
}

export class AudioEngine extends Emitter {
  constructor(basePath = MUSIC_BASE, options = {}) {
    super();
    this.musicBase = basePath || MUSIC_BASE;
    this.rainBase = (options && options.rainBase) || RAIN_BASE;
    this.tracks = MUSIC_TRACKS;

    this.ctx = null;
    this.master = null;         // 总音量 GainNode
    this.musicBus = null;       // 音乐总线
    this.rainBus = null;        // 雨声总线

    this.buffers = new Map();   // id -> AudioBuffer
    this.rainBuffer = null;

    this.curSrc = null;         // 当前音乐 source
    this.curGain = null;
    this.cur = -1;
    this.pendSrc = null;        // 交叉中的新曲
    this.pendGain = null;
    this.pendIndex = -1;
    this.crossEnd = 0;

    this.rainSrc = null;
    this.rainLoopGain = null;
    this.rainOn = false;

    this.masterVolume = 0.45;
    this.musicVolume = 1.0;
    this.rainVolume = 0.55;

    this.unlocked = false;
    this.paused = false;
    this.ready = false;
    this.lastWeather = 'clear';
    this.lastPhase = 'noon';
    this.onTrackChange = null;
    this._decodePromise = null;
  }

  /* ────────────────────────── 初始化 ────────────────────────── */
  async init() {
    if (this.unlocked && this.ready) return true;
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) throw new Error('浏览器不支持 Web Audio API');
      if (!this.ctx) {
        this.ctx = new AC();
        this.master = this.ctx.createGain();
        this.master.gain.value = this.masterVolume;
        this.master.connect(this.ctx.destination);
        this.musicBus = this.ctx.createGain();
        this.musicBus.gain.value = this.musicVolume;
        this.musicBus.connect(this.master);
        this.rainBus = this.ctx.createGain();
        this.rainBus.gain.value = this.rainVolume;
        this.rainBus.connect(this.master);
      }
      // 关键：必须在用户手势里 resume（浏览器自动播放策略）
      if (this.ctx.state === 'suspended') await this.ctx.resume();

      // 预解码曲目（只解当前 + 下一首，省内存）
      if (!this.ready) {
        const first = Math.floor(Math.random() * this.tracks.length);
        await this._ensureDecoded(first);
        this.cur = first;
        this._startMusic(first, 0);
        this.ready = true;
        // 后台慢慢解其余
        this._preloadRest();
      }
      this.unlocked = true;
      this.emit('ready', { index: this.cur });
      return true;
    } catch (e) {
      console.warn('[audio] init failed', e);
      return false;
    }
  }

  async _ensureDecoded(idx) {
    const t = this.tracks[idx];
    if (!t) return null;
    if (this.buffers.has(t.id)) return this.buffers.get(t.id);
    const url = this.musicBase + t.file;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const ab = await res.arrayBuffer();
      const buf = await this.ctx.decodeAudioData(ab);
      this.buffers.set(t.id, buf);
      return buf;
    } catch (e) {
      console.warn('[audio] 解码失败:', t.file, e && e.message);
      return null;
    }
  }

  _preloadRest() {
    if (this._preloadPromise) return this._preloadPromise;
    this._preloadPromise = (async () => {
      for (let i = 0; i < this.tracks.length; i++) {
        if (this.buffers.has(this.tracks[i].id)) continue;
        await this._ensureDecoded(i);
        await new Promise((r) => setTimeout(r, 350));   // 让主线程喘口气
      }
      // 顺便解雨声
      try {
        const res = await fetch(this.rainBase + RAIN_FILE);
        if (res.ok) {
          const ab = await res.arrayBuffer();
          this.rainBuffer = await this.ctx.decodeAudioData(ab);
        }
      } catch (e) { /* 雨声缺失不影响音乐 */ }
    })();
    return this._preloadPromise;
  }

  /* ────────────────────────── 音乐 ────────────────────────── */
  _startMusic(idx, fadeIn) {
    const buf = this.buffers.get(this.tracks[idx].id);
    if (!buf || !this.ctx) return;
    if (this.curSrc) {
      try { this.curSrc.stop(); } catch (e) { /* ignore */ }
      try { this.curSrc.disconnect(); } catch (e) { /* ignore */ }
    }
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;                    // ★ 采样级无缝循环，不会断
    const g = this.ctx.createGain();
    g.gain.value = fadeIn > 0 ? 0 : 1;
    src.connect(g);
    g.connect(this.musicBus);
    src.start(0);
    if (fadeIn > 0) {
      g.gain.linearRampToValueAtTime(1, this.ctx.currentTime + fadeIn);
    }
    this.curSrc = src;
    this.curGain = g;
    this.cur = idx;
    // 记录播放起点与曲目时长，供「播完再切」判断
    this.trackStartedAt = this.ctx.currentTime;
    this.trackDuration = buf.duration || 0;
    if (this.onTrackChange) this.onTrackChange(idx, this.tracks[idx]);
    this.emit('trackchange', { index: idx, track: this.tracks[idx] });
  }

  /** 平滑切歌（等功率交叉淡化） */
  async switchTo(index, opts = {}) {
    if (index < 0 || index >= this.tracks.length) return;
    if (!this.ctx) return;
    if (index === this.cur && this.curSrc) return;

    await this._ensureDecoded(index);
    const buf = this.buffers.get(this.tracks[index].id);
    if (!buf) { console.warn('[audio] 曲目未就绪:', index); return; }

    const instant = !!opts.instant || !this.curSrc;
    if (instant) {
      this._startMusic(index, 0);
      return;
    }

    // 新曲淡入
    if (this.pendSrc) { try { this.pendSrc.stop(); } catch (e) {} }
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    const g = this.ctx.createGain();
    g.gain.value = 0;
    src.connect(g);
    g.connect(this.musicBus);
    src.start(0);

    const t0 = this.ctx.currentTime;
    const T = CROSSFADE;
    // 等功率：旧曲 cos 衰减，新曲 sin 上升
    this._eqFade(this.curGain.gain, t0, T, 1, 0);
    this._eqFade(g.gain, t0, T, 0, 1);

    const oldSrc = this.curSrc, oldGain = this.curGain;
    this.curSrc = src;
    this.curGain = g;
    this.cur = index;
    this.trackStartedAt = this.ctx.currentTime;
    this.trackDuration = buf.duration || 0;
    this.crossing = true;
    setTimeout(() => { this.crossing = false; }, (CROSSFADE + 0.2) * 1000);
    if (this.onTrackChange) this.onTrackChange(index, this.tracks[index]);
    this.emit('trackchange', { index, track: this.tracks[index] });

    // 交叉结束后停掉旧曲
    setTimeout(() => {
      try { oldSrc.stop(); oldSrc.disconnect(); oldGain.disconnect(); } catch (e) {}
    }, (T + 0.15) * 1000);
  }

  _eqFade(param, t0, dur, from, to) {
    // 用 8 段线性逼近等功率曲线（避免大量 API 调用）
    const N = 8;
    param.cancelScheduledValues(t0);
    param.setValueAtTime(from, t0);
    for (let i = 1; i <= N; i++) {
      const k = i / N;
      const v = to > from
        ? Math.sin(k * Math.PI / 2)      // 淡入
        : Math.cos(k * Math.PI / 2);     // 淡出
      param.linearRampToValueAtTime(Math.max(0.0001, v), t0 + dur * k);
    }
    param.linearRampToValueAtTime(to, t0 + dur + 0.02);
  }

  /** 当前曲目已播放秒数（基于 Web Audio 时钟） */
  get playedSeconds() {
    if (!this.ctx || this.trackStartedAt == null) return 0;
    return Math.max(0, this.ctx.currentTime - this.trackStartedAt);
  }

  /** 当前曲目总时长（秒）；未解码时为 0 */
  get totalSeconds() { return this.trackDuration || 0; }

  /** 当前曲目是否已播完一遍 */
  get currentFinished() {
    const d = this.totalSeconds;
    return d > 0 && this.playedSeconds >= d;
  }

  nextTrack() { this.switchTo((Math.max(0, this.cur) + 1) % this.tracks.length); }
  prevTrack() { this.switchTo((Math.max(0, this.cur) - 1 + this.tracks.length) % this.tracks.length); }
  randomNext() {
    if (this.tracks.length <= 1) return;
    let n = this.cur, guard = 0;
    while (n === this.cur && guard++ < 20) n = Math.floor(Math.random() * this.tracks.length);
    this.switchTo(n);
  }

  /* ────────────────────────── 音量 ────────────────────────── */
  setMasterVolume(v) {
    this.masterVolume = Math.max(0, Math.min(1, Number(v) || 0));
    if (this.master) this.master.gain.setTargetAtTime(this.masterVolume, this.ctx.currentTime, 0.05);
  }
  setMusicVolume(v) {
    this.musicVolume = Math.max(0, Math.min(1, Number(v) || 0));
    if (this.musicBus) this.musicBus.gain.setTargetAtTime(this.musicVolume, this.ctx.currentTime, 0.05);
  }
  setRainVolume(v) {
    this.rainVolume = Math.max(0, Math.min(1, Number(v) || 0));
    if (this.rainBus) this.rainBus.gain.setTargetAtTime(this.rainVolume, this.ctx.currentTime, 0.05);
  }

  setPaused(p) {
    this.paused = !!p;
    if (!this.ctx) return;
    if (this.paused) this.ctx.suspend().catch(() => {});
    else this.ctx.resume().catch(() => {});
  }

  /* ──────────────────────── 天气 / 时段 ──────────────────────── */
  setTimePhase(phase) { this.lastPhase = phase; }

  setWeather(key) {
    this.lastWeather = key;
    this.setRainOn(RAIN_WEATHERS.has(key));
  }

  /** 雨声：常驻 loop source，只改 gain —— 绝不会有"停了再播" */
  async setRainOn(on) {
    if (on === this.rainOn) return;
    this.rainOn = on;
    if (!this.ctx) return;

    if (on) {
      if (!this.rainBuffer) {
        await this._ensureRain();
      }
      if (this.rainBuffer && !this.rainSrc) {
        const src = this.ctx.createBufferSource();
        src.buffer = this.rainBuffer;
        src.loop = true;                // ★ 无缝
        const g = this.ctx.createGain();
        g.gain.value = 0;
        src.connect(g);
        g.connect(this.rainBus);
        src.start(0);
        this.rainSrc = src;
        this.rainLoopGain = g;
      }
      if (this.rainLoopGain) {
        const t = this.ctx.currentTime;
        this.rainLoopGain.gain.cancelScheduledValues(t);
        this.rainLoopGain.gain.setValueAtTime(this.rainLoopGain.gain.value, t);
        this.rainLoopGain.gain.linearRampToValueAtTime(1, t + 0.8);
      }
    } else if (this.rainLoopGain) {
      const t = this.ctx.currentTime;
      this.rainLoopGain.gain.cancelScheduledValues(t);
      this.rainLoopGain.gain.setValueAtTime(this.rainLoopGain.gain.value, t);
      this.rainLoopGain.gain.linearRampToValueAtTime(0, t + 0.8);
      // source 不 stop —— 留着，下次再来雨直接抬 gain，零延迟
    }
  }

  async _ensureRain() {
    if (this.rainBuffer) return;
    try {
      const res = await fetch(this.rainBase + RAIN_FILE);
      if (!res.ok) return;
      const ab = await res.arrayBuffer();
      this.rainBuffer = await this.ctx.decodeAudioData(ab);
    } catch (e) { console.warn('[audio] 雨声加载失败', e && e.message); }
  }

  playOnce() { /* 事件音已全部删除，保留空实现 */ }

  notifyLightning() {
    // 闪电时雨声短暂加重（不动 source，只推 gain）
    if (this.rainLoopGain && this.rainOn && this.ctx) {
      const t = this.ctx.currentTime;
      const g = this.rainLoopGain.gain;
      g.cancelScheduledValues(t);
      g.setValueAtTime(g.value, t);
      g.linearRampToValueAtTime(1.6, t + 0.12);
      g.linearRampToValueAtTime(1.0, t + 1.1);
    }
    this.emit('lightning', null);
  }

  /* ────────────────────────── 状态 ────────────────────────── */
  get currentIndex() { return this.cur; }
  get currentTrack() { return this.cur >= 0 ? this.tracks[this.cur] : null; }
  isReady() { return this.ready; }

  getState() {
    return {
      unlocked: this.unlocked,
      ready: this.ready,
      paused: this.paused,
      index: this.cur,
      track: this.currentTrack,
      tracks: this.tracks,
      masterVolume: this.masterVolume,
      musicVolume: this.musicVolume,
      rainVolume: this.rainVolume,
      rainOn: this.rainOn,
      weather: this.lastWeather,
      phase: this.lastPhase,
      decoded: this.buffers.size,
      ctxState: this.ctx ? this.ctx.state : 'none',
    };
  }

  dispose() {
    try {
      if (this.curSrc) this.curSrc.stop();
      if (this.rainSrc) this.rainSrc.stop();
      if (this.ctx) this.ctx.close();
    } catch (e) { /* ignore */ }
  }
}

/** 降级壳：任何构造失败都不拖垮 boot */
export function createAudio(basePath) {
  try {
    return new AudioEngine(basePath);
  } catch (e) {
    console.warn('[audio] engine init failed', e);
    return {
      init: async () => false, setMasterVolume() {}, setMusicVolume() {},
      setRainVolume() {}, setTimePhase() {}, setWeather() {}, setPaused() {},
      get playedSeconds() { return 0; }, get totalSeconds() { return 0; },
  get currentFinished() { return false; },
  switchTo() {}, nextTrack() {}, prevTrack() {}, randomNext() {},
      playOnce() {}, notifyLightning() {}, on: () => () => {}, off() {},
      dispose() {}, tracks: MUSIC_TRACKS,
      get currentIndex() { return -1; }, get currentTrack() { return null; },
      isReady: () => false,
      getState: () => ({ unlocked: false, tracks: MUSIC_TRACKS }),
      onTrackChange: null,
    };
  }
}

export { MUSIC_TRACKS };
export default AudioEngine;
