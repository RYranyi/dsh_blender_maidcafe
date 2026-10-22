#!/usr/bin/env node
/**
 * check-glb.mjs —— GLB 结构体检（不依赖 Blender / three，纯二进制 + JSON 解析）。
 *
 * 用法：
 *   node tools/web/check-glb.mjs                          # 默认查 scene/maid_cafe.glb
 *   node tools/web/check-glb.mjs --file scene/xxx.glb
 *   node tools/web/check-glb.mjs --json                   # 只输出 JSON
 *
 * 检查项：
 *   1. GLB 容器：magic / version / 长度 / chunk 结构
 *   2. extensionsUsed / extensionsRequired 与 known-loader 支持表比对（不支持 → FAIL，会被 GLTFLoader 拒绝）
 *   3. texture → source / EXT_texture_webp.source 引用完整性（**这是本次事故的直接原因**）
 *   4. image → bufferView / uri 至少有一个
 *   5. material 里所有 xxxTexture.index 必须落在 textures 范围内，且该槽非空
 *   6. 三角面总数 / 材质数 / 节点数 / 内嵌贴图字节数
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');

const argv = process.argv.slice(2);
const arg = (n, d) => {
  const i = argv.indexOf(`--${n}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
};
const FILE = path.resolve(ROOT, arg('file', 'scene/maid_cafe.glb'));
const JSON_ONLY = argv.includes('--json');

/** three r160 GLTFLoader 实际支持的扩展（unsupported 会 warn 或 throw） */
const SUPPORTED_EXT = new Set([
  'KHR_materials_clearcoat',
  'KHR_materials_emissive_strength',
  'KHR_materials_ior',
  'KHR_materials_pbrSpecularGlossiness',
  'KHR_materials_sheen',
  'KHR_materials_specular',
  'KHR_materials_transmission',
  'KHR_materials_unlit',
  'KHR_materials_volume',
  'KHR_materials_iridescence',
  'KHR_materials_anisotropy',
  'KHR_materials_dispersion',
  'KHR_texture_basisu',
  'KHR_texture_transform',
  'KHR_draco_mesh_compression',
  'KHR_mesh_quantization',
  'KHR_lights_punctual',
  'EXT_texture_webp',
  'EXT_meshopt_compression',
  'EXT_mesh_gpu_instancing',
  'KHR_materials_variants',
  'KHR_materials_emissive_strength',
  'KHR_animation_pointer',
  'KHR_xmp_json_ld',
  'KHR_materials_diffuse_transmission',
  'KHR_materials_anisotropy',
  'MSFT_texture_dds',
]);
/** 必须有专门扩展支持、否则读不出来的（出现在 extensionsRequired 才致命） */
const CRITICAL_IF_REQUIRED = new Set(['KHR_draco_mesh_compression', 'KHR_texture_basisu', 'EXT_meshopt_compression']);

function fail(msg) {
  errors.push(msg);
}
function warn(msg) {
  warnings.push(msg);
}

const errors = [];
const warnings = [];

function main() {
  if (!fs.existsSync(FILE)) {
    console.error(`找不到文件: ${FILE}`);
    process.exit(1);
  }
  const buf = fs.readFileSync(FILE);
  const stat = { file: path.relative(ROOT, FILE).replace(/\\/g, '/'), bytes: buf.length, bytesHuman: (buf.length / 1048576).toFixed(2) + ' MB' };

  // 1) 容器
  if (buf.toString('utf8', 0, 4) !== 'glTF') {
    console.error('不是 GLB（magic 不是 glTF）');
    process.exit(1);
  }
  const version = buf.readUInt32LE(4);
  const total = buf.readUInt32LE(8);
  stat.version = version;
  stat.declaredLength = total;
  if (version !== 2) fail(`glTF 版本是 ${version}，期望 2`);
  if (total !== buf.length) warn(`header 声明长度 ${total} ≠ 实际 ${buf.length}（可能是流式写盘，通常无害）`);

  const jsonLen = buf.readUInt32LE(12);
  const jsonType = buf.toString('utf8', 16, 20);
  if (jsonType !== 'JSON') fail(`第一个 chunk 不是 JSON（是 ${JSON.stringify(jsonType)}）`);
  let j;
  try {
    j = JSON.parse(buf.toString('utf8', 20, 20 + jsonLen));
  } catch (e) {
    console.error('JSON chunk 解析失败:', e.message);
    process.exit(1);
  }
  // BIN chunk
  const binOff = 20 + jsonLen;
  let binLen = 0;
  if (binOff + 8 <= buf.length) {
    binLen = buf.readUInt32LE(binOff);
    stat.binBytes = binLen;
    stat.binHuman = (binLen / 1048576).toFixed(2) + ' MB';
  }

  // 2) extensions
  const used = j.extensionsUsed || [];
  const required = j.extensionsRequired || [];
  stat.extensionsUsed = used;
  stat.extensionsRequired = required;
  for (const e of required) {
    if (!SUPPORTED_EXT.has(e)) fail(`extensionsRequired 含 three r160 不支持的扩展：${e} → GLTFLoader 会直接失败`);
    else if (CRITICAL_IF_REQUIRED.has(e)) warn(`extensionsRequired 含 ${e}（需要对应 loader 插件，确认已注册）`);
  }
  for (const e of used) if (!SUPPORTED_EXT.has(e)) warn(`extensionsUsed 含未知扩展 ${e}（不影响加载）`);

  const images = j.images || [];
  const textures = j.textures || [];
  const materials = j.materials || [];
  const meshes = j.meshes || [];
  const nodes = j.nodes || [];
  stat.counts = {
    nodes: nodes.length,
    meshes: meshes.length,
    materials: materials.length,
    textures: textures.length,
    images: images.length,
    accessors: (j.accessors || []).length,
    bufferViews: (j.bufferViews || []).length,
  };

  // 3) texture.source 完整性
  const badTextures = [];
  textures.forEach((t, i) => {
    const viaExt = t.extensions && t.extensions.EXT_texture_webp && t.extensions.EXT_texture_webp.source != null;
    const viaBasis = t.extensions && t.extensions.KHR_texture_basisu && t.extensions.KHR_texture_basisu.source != null;
    if (t.source == null && !viaExt && !viaBasis) badTextures.push(i);
    const src = t.source != null ? t.source : viaExt ? t.extensions.EXT_texture_webp.source : viaBasis ? t.extensions.KHR_texture_basisu.source : null;
    if (src != null && (src < 0 || src >= images.length)) fail(`textures[${i}] 指向不存在的 image ${src}`);
  });
  stat.badTextures = badTextures;
  for (const i of badTextures) fail(`textures[${i}] 没有 source / EXT_texture_webp.source —— GLTFLoader 会抛 "undefined.uri"，**整包加载失败**`);

  // 4) image 完整性
  images.forEach((im, i) => {
    if (im.bufferView == null && !im.uri) fail(`images[${i}] 既无 bufferView 也无 uri`);
    if (im.bufferView != null && im.bufferView >= (j.bufferViews || []).length) fail(`images[${i}].bufferView=${im.bufferView} 越界`);
    if (im.mimeType && !/^image\/(png|jpeg|jpg|webp|ktx2|avif)$/i.test(im.mimeType)) warn(`images[${i}] mimeType=${im.mimeType} 不常见`);
  });
  const webpCount = images.filter((im) => im.mimeType === 'image/webp').length;
  stat.webpImages = webpCount;
  stat.imageMimes = [...new Set(images.map((im) => im.mimeType))];

  // 5) material 里的 texture 引用
  const TEX_SLOTS = [
    'baseColorTexture',
    'metallicRoughnessTexture',
    'normalTexture',
    'occlusionTexture',
    'emissiveTexture',
    'clearcoatTexture',
    'clearcoatRoughnessTexture',
    'clearcoatNormalTexture',
    'sheenColorTexture',
    'sheenRoughnessTexture',
    'transmissionTexture',
    'thicknessTexture',
    'specularTexture',
    'specularColorTexture',
    'iridescenceTexture',
    'iridescenceThicknessTexture',
    'anisotropyTexture',
    'diffuseTransmissionTexture',
    'diffuseTransmissionColorTexture',
  ];
  const matProblems = [];
  materials.forEach((m, mi) => {
    const name = m.name || `#${mi}`;
    const buckets = [
      ['pbrMetallicRoughness', m.pbrMetallicRoughness],
      ['', m],
      ['extensions.KHR_materials_clearcoat', m.extensions && m.extensions.KHR_materials_clearcoat],
      ['extensions.KHR_materials_sheen', m.extensions && m.extensions.KHR_materials_sheen],
      ['extensions.KHR_materials_transmission', m.extensions && m.extensions.KHR_materials_transmission],
      ['extensions.KHR_materials_specular', m.extensions && m.extensions.KHR_materials_specular],
      ['extensions.KHR_materials_anisotropy', m.extensions && m.extensions.KHR_materials_anisotropy],
      ['extensions.KHR_materials_iridescence', m.extensions && m.extensions.KHR_materials_iridescence],
    ];
    for (const [prefix, obj] of buckets) {
      if (!obj || typeof obj !== 'object') continue;
      for (const slot of TEX_SLOTS) {
        const t = obj[slot];
        if (!t || typeof t !== 'object') continue;
        if (typeof t.index !== 'number') continue;
        const p = `${prefix ? prefix + '.' : ''}${slot}`;
        if (t.index < 0 || t.index >= textures.length) {
          matProblems.push(`${name}.${p} → textures[${t.index}] 越界`);
        } else if (badTextures.includes(t.index)) {
          matProblems.push(`${name}.${p} → textures[${t.index}] 是空槽（会导致整包加载失败）`);
        }
      }
    }
  });
  stat.materialTextureProblems = matProblems;
  if (matProblems.length) fail(`材质引用了坏纹理槽：${matProblems.slice(0, 6).join('; ')}${matProblems.length > 6 ? ` …共 ${matProblems.length} 处` : ''}`);

  // 6) 三角面
  let tris = 0;
  const posAccessors = new Set();
  meshes.forEach((mesh) => {
    for (const prim of mesh.primitives || []) {
      const mode = prim.mode == null ? 4 : prim.mode;
      if (mode !== 4) continue; // 只看三角形
      const idxAcc = prim.indices != null ? j.accessors && j.accessors[prim.indices] : null;
      if (idxAcc && typeof idxAcc.count === 'number') tris += idxAcc.count / 3;
      else if (prim.attributes && prim.attributes.POSITION != null) {
        const pa = j.accessors && j.accessors[prim.attributes.POSITION];
        if (pa && typeof pa.count === 'number') tris += pa.count / 3;
      }
      if (prim.attributes && prim.attributes.POSITION != null) posAccessors.add(prim.attributes.POSITION);
      if (prim.extensions && prim.extensions.KHR_draco_mesh_compression) warn('有 Draco 压缩 primitive（需 DRACOLoader）');
    }
  });
  stat.tris = Math.round(tris);
  stat.vertexColorPrimitives = meshes.reduce(
    (n, mesh) => n + (mesh.primitives || []).filter((p) => p.attributes && p.attributes.COLOR_0 != null).length,
    0
  );
  stat.alphaBlendMaterials = materials.filter((m) => m.alphaMode === 'BLEND').length;
  stat.transmissionMaterials = materials.filter((m) => m.extensions && m.extensions.KHR_materials_transmission).length;

  const result = { ok: errors.length === 0, errors, warnings, stat };
  if (JSON_ONLY) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.log(`GLB 体检：${stat.file}  ${stat.bytesHuman}`);
    console.log(`  glTF v${stat.version}  bin=${stat.binHuman}  nodes=${stat.counts.nodes} mesh=${stat.counts.meshes}`);
    console.log(`  tris=${stat.tris.toLocaleString()}  materials=${stat.counts.materials}  textures=${stat.counts.textures}  images=${stat.counts.images} (webp ${stat.webpImages})`);
    console.log(`  COLOR_0 primitives=${stat.vertexColorPrimitives}  alphaBlend=${stat.alphaBlendMaterials}  transmission=${stat.transmissionMaterials}`);
    console.log(`  extensionsRequired=${JSON.stringify(stat.extensionsRequired)}`);
    if (warnings.length) {
      console.log(`\n⚠ ${warnings.length} 个警告：`);
      for (const w of warnings) console.log(`   - ${w}`);
    }
    if (errors.length) {
      console.log(`\n✗ ${errors.length} 个错误：`);
      for (const e of errors) console.log(`   - ${e}`);
      console.log('\nFAIL');
    } else {
      console.log('\nPASS ✓');
    }
  }
  process.exitCode = errors.length ? 1 : 0;
}

main();
