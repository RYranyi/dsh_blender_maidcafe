/**
 * freecam.js —— 自由飞行视角（照搬 bedroom_scene 的成功方案）
 *
 * 设计来源：E:\dsh\bedroom_scene\website\app.js 的 fly 控制器
 *   之所以不用 OrbitControls 做主控：OrbitControls 是「绕目标转」，
 *   走动时相机跟着 target 飘，手感很差。bedroom_scene 那套是
 *   「自己维护 pos/yaw/pitch/roll + 速度阻尼」，WASD 是真的往前走，
 *   鼠标拖拽只改朝角，滚轮改 FOV —— 手感是飞行游戏的。
 *
 * 键位（与 bedroom_scene 一致）：
 *   W/A/S/D 或方向键 —— 前后左右
 *   空格 / R        —— 上升
 *   C               —— 下降
 *   Shift           —— 加速
 *   V 或 F          —— 切换「飞行 ↔ 环绕」
 *   鼠标左键拖拽     —— 转头（yaw/pitch）
 *   滚轮            —— 缩放 FOV（30–80°）
 *
 * 边界：室内限制在房间里；室外可走远（用于看外景）。
 */

const DEG = Math.PI / 180;

/* ── 默认机位（不再有固定视角预设，只保留 reset 用）── */
const DEFAULT_VIEW = { pos: [2.55, 1.62, 2.30], look: [-1.20, 1.05, -0.60] };


export class FreeCam {
  constructor(app, opts = {}) {
    this.app = app;
    this.camera = opts.camera || app.camera;
    this.controls = opts.controls || app.controls;
    this.dom = opts.dom || (app.renderer && app.renderer.domElement);

    this.enabled = false;
    this.mode = 'fly';                 // 'fly' | 'orbit'

    // 飞行状态（照搬 bedroom_scene 的 fly 结构）
    const V3 = this._vec3();
    this.fly = {
      pos: V3 ? new V3(2.55, 1.62, 2.30) : { x: 2.55, y: 1.62, z: 2.30 },
      yaw: 0, pitch: -0.10, roll: 0,
      vel: V3 ? new V3(0, 0, 0) : { x: 0, y: 0, z: 0 },
    };

    this.keys = Object.create(null);
    this.dragging = false;
    this.lastPointer = null;
    this.targetFov = 58;   // bedroom_scene 桌面默认 58
    this.smoothFov = 58;

    // 活动范围：室内 x[-3.9,3.9] z[-2.9,2.9] y[0.16,2.78]
    //          室外放宽到 x[-22,22] z[-6,20] y[-0.4,14]
    this.roomBox = { minX: -3.88, maxX: 3.88, minZ: -2.88, maxZ: 2.88, minY: 0.16, maxY: 2.76 };
    this.worldBox = { minX: -22, maxX: 22, minZ: -8, maxZ: 20, minY: -0.4, maxY: 14 };

    this._onKeyDown = this._onKeyDown.bind(this);
    this._onKeyUp = this._onKeyUp.bind(this);
    this._onPointerDown = this._onPointerDown.bind(this);
    this._onPointerMove = this._onPointerMove.bind(this);
    this._onPointerUp = this._onPointerUp.bind(this);
    this._onWheel = this._onWheel.bind(this);
    this._onBlur = this._onBlur.bind(this);
    this._onContextMenu = this._onContextMenu.bind(this);

    this.onModeChange = null;
  }

  _vec3() {
    try {
      if (this.camera && this.camera.position) {
        return this.camera.position.constructor;
      }
    } catch (e) { /* ignore */ }
    return null;
  }

  /* ────────────────────────── 生命周期 ────────────────────────── */
  enable() {
    if (this.enabled) return;
    this.enabled = true;
    // 告诉 scene.tick：controls 由我接管，别再重复 update（否则阻尼被算两遍）
    if (this.app) this.app._freecamActive = true;

    if (this.camera) {
      this.camera.rotation.order = 'YXZ';
      this.fly.pos.copy(this.camera.position);
      // 从当前朝向反推 yaw/pitch
      const d = new this.camera.position.constructor();
      this.camera.getWorldDirection(d);
      this.fly.yaw = Math.atan2(-d.x, -d.z);
      this.fly.pitch = Math.asin(Math.max(-1, Math.min(1, d.y)));
      this.fly.roll = 0;
    }

    window.addEventListener('keydown', this._onKeyDown, { passive: false });
    window.addEventListener('keyup', this._onKeyUp);
    window.addEventListener('blur', this._onBlur);

    // ★ 绑到 window：鼠标在 HUD 面板/滑条上时也能收到事件
    //   （只绑 canvas 会导致"滚轮在面板上就不放大"）
    window.addEventListener('pointerdown', this._onPointerDown);
    window.addEventListener('pointermove', this._onPointerMove);
    window.addEventListener('pointerup', this._onPointerUp);
    window.addEventListener('pointercancel', this._onPointerUp);
    window.addEventListener('wheel', this._onWheel, { passive: false });
    window.addEventListener('contextmenu', this._onContextMenu);

    this.setMode('fly');
    // ★ 不再自己起 rAF：由 app.js 的渲染循环调用 this.update(dt)
    //   （bedroom_scene 就是这样：loop 里 updateFly(dt) 之后立刻 render，
    //    两个循环并行会导致相机与渲染不同步 → 手感发飘）
  }

  disable() {
    this.enabled = false;
    if (this.app) this.app._freecamActive = false;
    window.removeEventListener('keydown', this._onKeyDown);
    window.removeEventListener('keyup', this._onKeyUp);
    window.removeEventListener('blur', this._onBlur);
    window.removeEventListener('pointerdown', this._onPointerDown);
    window.removeEventListener('pointermove', this._onPointerMove);
    window.removeEventListener('pointerup', this._onPointerUp);
    window.removeEventListener('pointercancel', this._onPointerUp);
    window.removeEventListener('wheel', this._onWheel);
    window.removeEventListener('contextmenu', this._onContextMenu);
    this.keys = Object.create(null);
  }

  /* ────────────────────────── 模式切换 ────────────────────────── */
  setMode(next) {
    this.mode = next === 'orbit' ? 'orbit' : 'fly';
    if (this.controls) this.controls.enabled = (this.mode === 'orbit');
    // 飞行模式下让 scene.js 别把相机往回拽，也别做碰撞
    if (this.app) this.app._freeRoam = (this.mode === 'fly');

    if (this.mode === 'orbit') {
      // 切到环绕：把当前相机位置交给 OrbitControls
      if (this.controls && this.camera) {
        // 目标点：当前视线前方 2.5m
        const d = new this.camera.position.constructor();
        this.camera.getWorldDirection(d);
        this.controls.target.copy(this.camera.position).addScaledVector(d, 2.5);
        this.controls.enabled = true;
        this.controls.update();
      }
    } else {
      // 切到飞行：从相机反推 yaw/pitch
      if (this.camera) {
        const d = new this.camera.position.constructor();
        this.camera.getWorldDirection(d);
        this.fly.yaw = Math.atan2(-d.x, -d.z);
        this.fly.pitch = Math.asin(Math.max(-1, Math.min(1, d.y)));
        this.fly.pos.copy(this.camera.position);
        this.fly.vel.set(0, 0, 0);
        this.applyFlyCamera();
      }
    }
    if (this.onModeChange) this.onModeChange(this.mode);
    return this.mode;
  }

  toggleMode() {
    return this.setMode(this.mode === 'fly' ? 'orbit' : 'fly');
  }

  /* ──────────────────────── 方向数学（照搬）─────────────────────── */
  dirFrom(yaw, pitch) {
    const cp = Math.cos(pitch);
    const V = this.camera ? this.camera.position.constructor : null;
    const v = V ? new V(-Math.sin(yaw) * cp, Math.sin(pitch), -Math.cos(yaw) * cp) : null;
    return v;
  }

  rightFrom(yaw) {
    const V = this.camera ? this.camera.position.constructor : null;
    return V ? new V(Math.cos(yaw), 0, -Math.sin(yaw)) : null;
  }

  yawPitchTo(from, look) {
    const lx = Array.isArray(look) ? look[0] : look.x;
    const ly = Array.isArray(look) ? look[1] : look.y;
    const lz = Array.isArray(look) ? look[2] : look.z;
    const V = this.camera.position.constructor;
    const d = new V(lx - from.x, ly - from.y, lz - from.z).normalize();
    return { yaw: Math.atan2(-d.x, -d.z), pitch: Math.asin(Math.max(-1, Math.min(1, d.y))) };
  }

  /* ────────────────────────── 相机应用 ────────────────────────── */
  applyFlyCamera() {
    if (!this.camera) return;
    this.camera.position.copy(this.fly.pos);
    this.smoothFov += (this.targetFov - this.smoothFov) * 0.15;
    if (Math.abs(this.camera.fov - this.smoothFov) > 0.01) {
      this.camera.fov = this.smoothFov;
      this.camera.updateProjectionMatrix();
    }
    // 用 Euler("YXZ") 设朝向 —— 与 bedroom_scene 完全一致
    const E = (this.camera.rotation && this.camera.rotation.constructor);
    if (E) {
      this.camera.quaternion.setFromEuler(new E(this.fly.pitch, this.fly.yaw, this.fly.roll, 'YXZ'));
    }
  }

  /* ─────────────────────── 边界（室内/室外）─────────────────────── */
  isInside(p) {
    return p.x > this.roomBox.minX && p.x < this.roomBox.maxX
        && p.z > this.roomBox.minZ && p.z < this.roomBox.maxZ;
  }

  clampPos(p) {
    // 判定：在室内用房间边界；踏出房间就切到世界边界（可以走到街上）
    if (this.isInside(p)) {
      p.x = Math.max(this.roomBox.minX, Math.min(this.roomBox.maxX, p.x));
      p.z = Math.max(this.roomBox.minZ, Math.min(this.roomBox.maxZ, p.z));
      p.y = Math.max(this.roomBox.minY, Math.min(this.roomBox.maxY, p.y));
    } else {
      p.x = Math.max(this.worldBox.minX, Math.min(this.worldBox.maxX, p.x));
      p.z = Math.max(this.worldBox.minZ, Math.min(this.worldBox.maxZ, p.z));
      p.y = Math.max(this.worldBox.minY, Math.min(this.worldBox.maxY, p.y));
    }
    return p;
  }

  /* ────────────── 每帧更新（由 app.js 主循环调用）────────────── */
  /**
   * 与 bedroom_scene 的 loop() 完全一致：
   *   const dt = Math.min(0.05, clock.getDelta());
   *   if (mode === "fly") updateFly(dt); else controls.update();
   * @param {number} dt 秒
   */
  update(dt) {
    if (!this.enabled) return;
    const d = Math.min(0.05, (dt == null || !isFinite(dt) || dt <= 0) ? 0.016 : dt);
    if (this.mode === 'fly') this.updateFly(d);
    else if (this.controls) this.controls.update();
  }

  updateFly(dt) {
    const k = this.keys;
    const V = this.camera.position.constructor;

    this.fly.roll = 0;   // Q/E 侧倾已移除
    let f = 0, r = 0, u = 0;
    if (k['w'] || k['arrowup']) f += 1;
    if (k['s'] || k['arrowdown']) f -= 1;
    if (k['d'] || k['arrowright']) r += 1;
    if (k['a'] || k['arrowleft']) r -= 1;
    if (k[' '] || k['r']) u += 1;
    if (k['c']) u -= 1;

    const len = Math.hypot(f, r, u);
    if (len > 0.001) {
      f /= Math.max(1, len);
      r /= Math.max(1, len);
      u /= Math.max(1, len);
      // ★ 与 bedroom_scene 完全一致：(shift?1.9:0.95) * dt * 1.7
      //   之前用的 2.4/1.15 * dt * 2.2 速度快了 63%，走一步就冲出去
      const speed = (k['shift'] ? 1.9 : 0.95) * dt * 1.7;
      const move = new V()
        .addScaledVector(this.dirFrom(this.fly.yaw, this.fly.pitch), f * speed)
        .addScaledVector(this.rightFrom(this.fly.yaw), r * speed)
        .addScaledVector(new V(0, 1, 0), u * speed);
      this.fly.vel.lerp(move, 0.5);      // bedroom: 0.5
    } else {
      this.fly.vel.multiplyScalar(0.85);   // bedroom: 0.85
      if (this.fly.vel.lengthSq() < 1e-7) this.fly.vel.set(0, 0, 0);
    }
    this.fly.pos.add(this.fly.vel);
    this.clampPos(this.fly.pos);
    this.applyFlyCamera();
  }

  /* ────────────── 平滑移到某个机位（仅 reset 内部用）────────────── */
  flyTo(pos, look, ms = 780) {
    if (!this.camera) return;
    const V = this.camera.position.constructor;

    if (this.mode === 'orbit') {
      // 环绕模式：平滑飞位置 + target
      const ctrl = this.controls;
      const fromP = this.camera.position.clone();
      const fromT = ctrl ? ctrl.target.clone() : new V();
      const toP = new V(pos[0], pos[1], pos[2]);
      const toT = new V(look[0], look[1], look[2]);
      const t0 = performance.now();
      const step = () => {
        const kk = Math.min(1, (performance.now() - t0) / ms);
        const e = kk * kk * (3 - 2 * kk);
        this.camera.position.lerpVectors(fromP, toP, e);
        if (ctrl) {
          ctrl.target.lerpVectors(fromT, toT, e);
          ctrl.update();
        }
        if (kk < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
      return;
    }

    // 飞行模式：位置 + yaw/pitch 插值
    const fromPos = this.fly.pos.clone();
    const toPos = new V(pos[0], pos[1], pos[2]);
    this.clampPos(toPos);
    const fromYaw = this.fly.yaw;
    const fromPitch = this.fly.pitch;
    const yp = this.yawPitchTo(toPos, look);
    // yaw 取最短路径
    let dy = yp.yaw - fromYaw;
    while (dy > Math.PI) dy -= Math.PI * 2;
    while (dy < -Math.PI) dy += Math.PI * 2;

    this.fly.vel.set(0, 0, 0);
    const t0 = performance.now();
    const step = () => {
      const kk = Math.min(1, (performance.now() - t0) / ms);
      const e = kk * kk * (3 - 2 * kk);
      this.fly.pos.lerpVectors(fromPos, toPos, e);
      this.fly.yaw = fromYaw + dy * e;
      this.fly.pitch = fromPitch + (yp.pitch - fromPitch) * e;
      this.applyFlyCamera();
      if (kk < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  /* ────────────────────────── 输入 ────────────────────────── */
  _onKeyDown(e) {
    const k = (e.key || '').toLowerCase();
    const NAV = ['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft',
                 'arrowright', ' ', 'c', 'r', 'shift'];

    // ★ 关键修复：不能因为焦点在 <input> 上就整体 return。
    //   用户拖过时间/音量滑条后，焦点会停在 input 里，导致方向键全被吃掉。
    //   NAV 键先把焦点移开，再照常处理。
    const tag = (e.target && e.target.tagName) || '';
    const inField = (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT');
    if (inField) {
      if (NAV.includes(k)) {
        if (e.target && e.target.blur) e.target.blur();
      } else {
        return;   // 在输入框里打字时不抢普通字符键
      }
    }

    if (NAV.includes(k)) e.preventDefault();
    this.keys[k] = true;

    if (k === 'v' || k === 'f') { this.toggleMode(); e.preventDefault(); }
    if (k === 'home') this.reset();
  }

  _onKeyUp(e) {
    this.keys[(e.key || '').toLowerCase()] = false;
  }

  _onBlur() { this.keys = Object.create(null); }

  _onPointerDown(e) {
    if (this.mode !== 'fly') return;
    if (this._isUiTarget(e)) return;        // 在面板/滑条上按下不接管
    this.dragging = true;
    this.lastPointer = { x: e.clientX, y: e.clientY, button: e.button };
    try {
      if (this.dom && this.dom.setPointerCapture) this.dom.setPointerCapture(e.pointerId);
    } catch (err) { /* ignore */ }
  }

  _onPointerMove(e) {
    if (!this.dragging || this.mode !== 'fly' || !this.lastPointer) return;
    const dx = e.clientX - this.lastPointer.x;
    const dy = e.clientY - this.lastPointer.y;
    this.lastPointer = { x: e.clientX, y: e.clientY, button: this.lastPointer.button };

    // 右键 / Shift+拖  = 平移相机（照搬 bedroom_scene）
    if (this.lastPointer.button === 2 || e.shiftKey) {
      this.fly.pos.addScaledVector(this.rightFrom(this.fly.yaw), -dx * 0.0042);
      this.fly.pos.y = Math.max(this.roomBox.minY - 3,
                       Math.min(this.worldBox.maxY, this.fly.pos.y + dy * 0.0042));
      this.clampPos(this.fly.pos);
      this.fly.vel.set(0, 0, 0);
      this.applyFlyCamera();
      return;
    }

    // 左键拖 = 转头。★ 符号与 bedroom_scene 完全一致：
    //   yaw -= dx*0.0032 ; pitch -= dy*0.0030
    // 之前写成 pitch += dy，导致"往下拖却往上看"，手感完全反了。
    this.fly.yaw -= dx * 0.0032;
    this.fly.pitch = Math.max(-1.45, Math.min(1.45, this.fly.pitch - dy * 0.0030));
    this.applyFlyCamera();
  }

  _onPointerUp() {
    this.dragging = false;
    this.lastPointer = null;
    try {
      if (this.dom && this.dom.releasePointerCapture) {
        // 释放所有可能被捕获的指针
      }
    } catch (err) { /* ignore */ }
  }

  _onWheel(e) {
    if (this.mode !== 'fly') return;
    if (this._isUiTarget(e)) return;      // 面板/滑条上的滚轮交给它们自己
    e.preventDefault();
    // 与 bedroom_scene 完全一致：targetFov += deltaY * 0.025，夹在 30–80
    this.targetFov = Math.max(30, Math.min(80, this.targetFov + e.deltaY * 0.025));
  }

  /** 判断事件是否发生在 UI 控件上（面板/滑条/按钮），这类区域不接管鼠标 */
  _isUiTarget(e) {
    const t = e.target;
    if (!t || !t.closest) return false;
    return !!t.closest('input, textarea, select, button, .panel, .view-bar, .loadbox, #hud .card');
  }

  _onContextMenu(e) {
    // 飞行模式下右键是"平移"，禁掉浏览器右键菜单
    if (this.mode === 'fly' && !this._isUiTarget(e)) e.preventDefault();
  }

  /**
   * 放宽活动边界到整个街区（允许走出室外看外景）。
   * 注意：早期版本用这个方法扩大范围，重写时漏掉了，但 app.js 仍在调用 ——
   * 一旦缺失会 TypeError，把后面的 buildViewPresetUI / bindBrightnessUI 一起吞掉。
   */
  widenLimits() {
    this.roomBox = { minX: -3.88, maxX: 3.88, minZ: -2.88, maxZ: 2.88,
                     minY: 0.16, maxY: 2.76 };
    this.worldBox = { minX: -24, maxX: 24, minZ: -10, maxZ: 22,
                      minY: -0.5, maxY: 15 };
    return this;
  }

  /* ────────────────────────── 对外信息 ────────────────────────── */
  getInfo() {
    const p = this.fly.pos;
    return {
      mode: this.mode,
      pos: [p.x, p.y, p.z],
      fov: Math.round(this.targetFov),
      inside: this.isInside(p),
      yaw: this.fly.yaw,
      pitch: this.fly.pitch,
    };
  }

  reset() {
    // 回到默认机位（无固定预设，只此一个）
    if (this.mode === 'fly') {
      const V = this.camera.position.constructor;
      this.fly.pos.set(DEFAULT_VIEW.pos[0], DEFAULT_VIEW.pos[1], DEFAULT_VIEW.pos[2]);
      const yp = this.yawPitchTo(this.fly.pos, DEFAULT_VIEW.look);
      this.fly.yaw = yp.yaw;
      this.fly.pitch = yp.pitch;
      this.fly.roll = 0;
      this.fly.vel.set(0, 0, 0);
      this.applyFlyCamera();
    } else {
      this.flyTo(DEFAULT_VIEW.pos, DEFAULT_VIEW.look, 500);
    }
  }
}



export default FreeCam;
