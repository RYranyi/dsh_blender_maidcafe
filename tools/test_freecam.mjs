/**
 * test_freecam.mjs —— 在 Node 里真实模拟 FreeCam 的输入与运动
 *
 * 目的：浏览器在这个沙箱起不来，但 FreeCam 不 import three（它全程用
 *       camera.position.constructor 拿构造函数），所以可以用 mock 相机在 Node 里
 *       真跑一遍「按键 → 位移」「滚轮 → FOV」「拖拽 → 朝向」，验证不是靠看代码猜。
 *
 * 断言：
 *   1. ArrowUp/W  → 相机向前（沿视线方向）移动
 *   2. ArrowLeft  → 相机向左平移
 *   3. ArrowDown  → 相机向后移动
 *   4. 焦点在 <input> 里时按方向键，依然能移动（之前的核心 bug）
 *   5. 滚轮上滚 deltaY<0 → targetFov 变小（放大）
 *   6. 鼠标向下拖 dy>0 → pitch 变小（低头）—— 之前符号写反
 */

/* ── 最小 THREE mock ───────────────────────────────────────────── */
class V3 {
  constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z; }
  set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; }
  copy(v) { this.x = v.x; this.y = v.y; this.z = v.z; return this; }
  clone() { return new V3(this.x, this.y, this.z); }
  add(v) { this.x += v.x; this.y += v.y; this.z += v.z; return this; }
  addScaledVector(v, s) {
    this.x += v.x * s; this.y += v.y * s; this.z += v.z * s; return this;
  }
  multiplyScalar(s) { this.x *= s; this.y *= s; this.z *= s; return this; }
  lengthSq() { return this.x * this.x + this.y * this.y + this.z * this.z; }
  lerp(v, a) {
    this.x += (v.x - this.x) * a;
    this.y += (v.y - this.y) * a;
    this.z += (v.z - this.z) * a;
    return this;
  }
  normalize() {
    const l = Math.hypot(this.x, this.y, this.z) || 1;
    this.x /= l; this.y /= l; this.z /= l; return this;
  }
}

class Euler {
  constructor(x = 0, y = 0, z = 0, order = 'XYZ') {
    this.x = x; this.y = y; this.z = z; this.order = order;
  }
}

class Quat {
  constructor() { this.x = 0; this.y = 0; this.z = 0; this.w = 1; }
  setFromEuler(e) { this._e = { x: e.x, y: e.y, z: e.z, order: e.order }; return this; }
}

class MockCamera {
  constructor() {
    this.position = new V3(0, 1.6, 0);
    this.rotation = new Euler(0, 0, 0, 'XYZ');
    this.quaternion = new Quat();
    this.fov = 58;
    this.dir = new V3(0, 0, -1);   // 朝向：默认看 -Z
  }
  updateProjectionMatrix() {}
  getWorldDirection(out) {
    // 由 yaw/pitch 推导朝向：与 dirFrom 一致
    return out.copy(this.dir);
  }
}

/* ── 全局 stub ─────────────────────────────────────────────────── */
const listeners = { window: {}, dom: {} };
class MockTarget {
  constructor(bag) { this.bag = bag; }
  addEventListener(t, fn) { (this.bag[t] = this.bag[t] || []).push(fn); }
  removeEventListener(t, fn) {
    const a = this.bag[t] || [];
    const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1);
  }
  dispatch(t, ev) { (this.bag[t] || []).forEach((fn) => fn(ev)); }
  setPointerCapture() {}
  releasePointerCapture() {}
}
const win = new MockTarget(listeners.window);
const dom = new MockTarget(listeners.dom);

globalThis.window = win;
globalThis.performance = { now: () => Date.now() };
globalThis.requestAnimationFrame = () => 1;
globalThis.cancelAnimationFrame = () => {};
globalThis.document = {
  activeElement: null,
  getElementById: () => null,
  querySelector: () => null,
  addEventListener: () => {},
};
globalThis.localStorage = {
  _d: {}, getItem(k) { return this._d[k] ?? null; },
  setItem(k, v) { this._d[k] = v; },
};

/* ── 载入被测类 ────────────────────────────────────────────────── */
const { FreeCam } = await import('file:///E:/dsh/maid_cafe/js/freecam.js');

let pass = 0, fail = 0;
function ok(cond, name, extra = '') {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (extra ? '   ' + extra : '')); }
}

function makeCam() {
  const cam = new MockCamera();
  const app = { camera: cam, controls: null, renderer: { domElement: dom }, _freeRoam: false };
  const fc = new FreeCam(app, { camera: cam, controls: null, dom });
  return { cam, app, fc };
}

function key(fc, k, down = true, target = { tagName: 'BODY', blur() {} }) {
  const ev = {
    key: k, target, preventDefault() {}, stopPropagation() {},
    clientX: 0, clientY: 0, button: 0, shiftKey: false,
  };
  if (down) fc._onKeyDown(ev); else fc._onKeyUp(ev);
}

function step(fc, n = 30) {
  // 走真实生产路径：app.js 主循环调用的是 freecam.update(dt)
  for (let i = 0; i < n; i++) fc.update(0.016);
}

console.log('═'.repeat(64));
console.log('FreeCam 真实行为测试（Node 模拟输入）');
console.log('═'.repeat(64));

/* 1. ArrowUp 前进 */
{
  const { cam, fc } = makeCam();
  fc.enable();
  fc.fly.pos.set(0, 1.6, 2.0);
  fc.fly.yaw = 0; fc.fly.pitch = 0;      // 朝 -Z
  fc.fly.vel.set(0, 0, 0);
  const z0 = fc.fly.pos.z;
  key(fc, 'ArrowUp');
  step(fc, 40);
  const dz = fc.fly.pos.z - z0;
  ok(dz < -0.05, 'ArrowUp 让相机向 -Z 前进', `Δz=${dz.toFixed(3)}`);
}

/* 2. ArrowLeft 左移 */
{
  const { fc } = makeCam();
  fc.enable();
  fc.fly.pos.set(0, 1.6, 2.0);
  fc.fly.yaw = 0; fc.fly.pitch = 0;
  fc.fly.vel.set(0, 0, 0);
  const x0 = fc.fly.pos.x;
  key(fc, 'ArrowLeft');
  step(fc, 40);
  const dx = fc.fly.pos.x - x0;
  ok(dx < -0.05, 'ArrowLeft 让相机向左(-X)平移', `Δx=${dx.toFixed(3)}`);
}

/* 3. ArrowDown 后退 */
{
  const { fc } = makeCam();
  fc.enable();
  fc.fly.pos.set(0, 1.6, 0.0);
  fc.fly.yaw = 0; fc.fly.pitch = 0;
  fc.fly.vel.set(0, 0, 0);
  const z0 = fc.fly.pos.z;
  key(fc, 'ArrowDown');
  step(fc, 40);
  const dz = fc.fly.pos.z - z0;
  ok(dz > 0.05, 'ArrowDown 让相机向 +Z 后退', `Δz=${dz.toFixed(3)}`);
}

/* 4. 焦点在 input 里时方向键仍生效（核心 bug） */
{
  const { fc } = makeCam();
  fc.enable();
  fc.fly.pos.set(0, 1.6, 2.0);
  fc.fly.yaw = 0; fc.fly.pitch = 0;
  fc.fly.vel.set(0, 0, 0);
  const z0 = fc.fly.pos.z;
  let blurred = false;
  const inp = { tagName: 'INPUT', blur() { blurred = true; } };
  key(fc, 'ArrowUp', true, inp);
  step(fc, 40);
  const dz = fc.fly.pos.z - z0;
  ok(dz < -0.05, '焦点在 <input> 时方向键仍能移动', `Δz=${dz.toFixed(3)}`);
  ok(blurred, '按下方向键时主动 blur 掉输入框');
}

/* 5. 滚轮放大 */
{
  const { fc } = makeCam();
  fc.enable();
  const f0 = fc.targetFov;
  fc._onWheel({ deltaY: -120, target: { closest: () => null }, preventDefault() {} });
  ok(fc.targetFov < f0, '滚轮上滚 deltaY<0 → FOV 变小（放大）',
     `${f0} → ${fc.targetFov.toFixed(1)}`);
  fc._onWheel({ deltaY: 400, target: { closest: () => null }, preventDefault() {} });
  ok(fc.targetFov <= 80, 'FOV 上限被夹在 80', `fov=${fc.targetFov.toFixed(1)}`);
}

/* 6. 拖拽方向：向下拖 → 低头（pitch 减小） */
{
  const { fc } = makeCam();
  fc.enable();
  fc.fly.pitch = 0;
  fc._onPointerDown({ button: 0, clientX: 100, clientY: 100,
                      target: { closest: () => null }, pointerId: 1 });
  fc._onPointerMove({ clientX: 100, clientY: 140, shiftKey: false,
                      target: { closest: () => null } });
  ok(fc.fly.pitch < 0, '鼠标向下拖 → pitch 减小（低头，非抬头）',
     `pitch=${fc.fly.pitch.toFixed(3)}`);
  fc._onPointerUp();
}

/* 7. 拖拽方向：向右拖 → yaw 减小（视角右转） */
{
  const { fc } = makeCam();
  fc.enable();
  fc.fly.yaw = 0;
  fc._onPointerDown({ button: 0, clientX: 100, clientY: 100,
                      target: { closest: () => null }, pointerId: 1 });
  fc._onPointerMove({ clientX: 160, clientY: 100, shiftKey: false,
                      target: { closest: () => null } });
  ok(fc.fly.yaw < 0, '鼠标向右拖 → yaw 减小（视角右转）',
     `yaw=${fc.fly.yaw.toFixed(3)}`);
  fc._onPointerUp();
}

/* 8. UI 上的滚轮不应改 FOV */
{
  const { fc } = makeCam();
  fc.enable();
  const f0 = fc.targetFov;
  fc._onWheel({
    deltaY: -120,
    target: { closest: (sel) => (sel.indexOf('.view-bar') >= 0 ? {} : null) },
    preventDefault() {},
  });
  ok(Math.abs(fc.targetFov - f0) < 1e-6, '在 .view-bar 上滚轮不改 FOV（交给面板自己）',
     `${f0} → ${fc.targetFov}`);
}

/* 9. 速度量级（bedroom: 0.95*dt*1.7） */
{
  const { fc } = makeCam();
  fc.enable();
  fc.fly.pos.set(0, 1.6, 2.0);
  fc.fly.yaw = 0; fc.fly.pitch = 0;
  fc.fly.vel.set(0, 0, 0);
  key(fc, 'w');
  // 1 秒 = 62.5 帧 × 0.016
  step(fc, 63);
  const dist = Math.hypot(fc.fly.pos.x, fc.fly.pos.z - 2.0);
  ok(dist > 1.2 && dist < 3.2, '按住 W 1 秒的位移在合理区间(1.2–3.2m)',
     `${dist.toFixed(2)}m`);
}

/* 10. 松键后速度衰减到 0 */
{
  const { fc } = makeCam();
  fc.enable();
  fc.fly.pos.set(0, 1.6, 2.0);
  fc.fly.vel.set(0, 0, 0);
  key(fc, 'w');
  step(fc, 20);
  key(fc, 'w', false);
  step(fc, 120);
  ok(fc.fly.vel.lengthSq() < 1e-6, '松键后速度衰减为 0',
     `|v|²=${fc.fly.vel.lengthSq().toExponential(2)}`);
}

console.log('─'.repeat(64));
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
