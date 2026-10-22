// 支持 HTTP Range 的下载器：大 WAV 只取前 N 秒（用 ffprobe 读 header 判断是否大文件）
// 用法: node download_range.mjs
import fs from 'node:fs';
import path from 'node:path';

const DL = 'E:\\dsh\\maid_cafe\\.scratch\\audio-dev\\dl';
fs.mkdirSync(DL, { recursive: true });
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36';
const OGA = 'https://opengameart.org/sites/default/files/';

// 同一批源；大文件用 byte 范围截断（WAV 头部 44 字节 + 立体声 48k 16bit 每秒 192KB）
const sources = [
  { file: 'park_birds.wav', url: OGA + 'park_ambience_birds.wav', lic: 'CC0', author: 'Thimras', src: 'https://opengameart.org/content/park-ambiences', maxBytes: 12000000 },
  { file: 'park_wind.wav', url: OGA + 'park_ambience_wind.wav', lic: 'CC0', author: 'Thimras', src: 'https://opengameart.org/content/park-ambiences', maxBytes: 12000000 },
  { file: 'park_river.wav', url: OGA + 'park_ambience_river.wav', lic: 'CC0', author: 'Thimras', src: 'https://opengameart.org/content/park-ambiences', maxBytes: 8000000 },
  { file: 'birds_wind_synth.ogg', url: OGA + 'Birds%20and%20Wind%20-%20Ambient_1.ogg', lic: 'CC0', author: 'Spring Spring', src: 'https://opengameart.org/content/birds-and-wind-ambient-birds-wind-and-synth' },
  { file: 'crickets.mp3', url: OGA + 'crickets_1.mp3', lic: 'CC0', author: 'Wolfgang_', src: 'https://opengameart.org/content/crickets-ambient-noise-loopable' },
  { file: 'fridge_loop.ogg', url: OGA + 'amb_fridge_loop_1.ogg', lic: 'CC0', author: 'Kresiek The Furry', src: 'https://opengameart.org/content/fridge-loop-1' },
  { file: 'bell_ding1.wav', url: OGA + 'bell_ding1.wav', lic: 'CC0', author: 'PWL', src: 'https://opengameart.org/content/bell-dingschimes' },
  { file: 'bell_ding2.wav', url: OGA + 'bell_ding2.wav', lic: 'CC0', author: 'PWL', src: 'https://opengameart.org/content/bell-dingschimes' },
  { file: 'bell_ding3.wav', url: OGA + 'bell_ding3.wav', lic: 'CC0', author: 'PWL', src: 'https://opengameart.org/content/bell-dingschimes' },
  { file: 'bell_ding4.wav', url: OGA + 'bell_ding4.wav', lic: 'CC0', author: 'PWL', src: 'https://opengameart.org/content/bell-dingschimes' },
  { file: 'doorbell.wav', url: OGA + 'doorbell.wav', lic: 'CC0', author: 'frosty ham', src: 'https://opengameart.org/content/doorbell' },
  { file: 'doorbell_tring.ogg', url: OGA + 'doorbell-old-tring.ogg', lic: 'CC0', author: 'Dub', src: 'https://opengameart.org/content/doorbell-ring' },
  { file: 'music_urban_shop.ogg', url: OGA + 'urban_shop_bpm92_0.ogg', lic: 'CC0', author: 'MintoDog', src: 'https://opengameart.org/content/urban-shop' },
  { file: 'music_cozy_puzzle.ogg', url: OGA + 'cozy_puzzle_in-game_1_bpm118_0.ogg', lic: 'CC0', author: 'MintoDog', src: 'https://opengameart.org/content/cozy-puzzle-in-game-1' },
  { file: 'music_catchy_swing.ogg', url: OGA + 'catchyswing.ogg', lic: 'CC0', author: 'Doge', src: 'https://opengameart.org/content/catchy-swing' },
  { file: 'music_cool_city.ogg', url: OGA + 'cool_city_bpm124_0.ogg', lic: 'CC0', author: 'MintoDog', src: 'https://opengameart.org/content/cool-city' },
  { file: 'music_jazzy_battle.ogg', url: OGA + 'jazzy_battle_theme_bpm130_0.ogg', lic: 'CC0', author: 'MintoDog', src: 'https://opengameart.org/content/jazzy-battle-theme' },
  { file: 'music_blues.mp3', url: OGA + 'blues_0.mp3', lic: 'CC0', author: 'LushoGames', src: 'https://opengameart.org/content/jazzy-blues' },
  { file: 'music_bird_night.ogg', url: OGA + 'bird_in_hand_night_0.ogg', lic: 'CC0', author: 'Fupi', src: 'https://opengameart.org/content/bird-in-hand-night' },
  { file: 'music_freejazz.flac', url: OGA + 'freejazz_medley.flac', lic: 'CC0', author: 'Anonymous', src: 'https://opengameart.org/content/freejazz-medley-loop', maxBytes: 8000000 },
];

const only = process.argv.slice(2);
const list = only.length ? sources.filter((s) => only.some((o) => s.file.includes(o))) : sources;

const man = [];
for (const s of list) {
  const out = path.join(DL, s.file);
  if (fs.existsSync(out) && fs.statSync(out).size > 2048) {
    console.log(`SKIP  ${s.file} (${(fs.statSync(out).size / 1024).toFixed(0)}KB)`);
    man.push({ ...s, bytes: fs.statSync(out).size, local: out, cached: true });
    continue;
  }
  const t0 = Date.now();
  try {
    const headers = { 'user-agent': UA };
    if (s.maxBytes) headers['range'] = `bytes=0-${s.maxBytes}`;
    const res = await fetch(s.url, { headers, redirect: 'follow' });
    if (!res.ok && res.status !== 206) throw new Error('HTTP ' + res.status);
    const buf = Buffer.from(await res.arrayBuffer());
    // 若用了 range，WAV 头里的 RIFF/data 长度会与实际不符；交给 ffmpeg 容错处理
    fs.writeFileSync(out, buf);
    console.log(`OK    ${s.file.padEnd(30)} ${(buf.length / 1024).toFixed(0).padStart(7)}KB ${String(Date.now() - t0).padStart(6)}ms  ${s.maxBytes ? '[ranged]' : ''}`);
    man.push({ ...s, bytes: buf.length, local: out });
  } catch (e) {
    console.log(`FAIL  ${s.file.padEnd(30)} ${e.message}`);
  }
}
fs.writeFileSync('E:\\dsh\\maid_cafe\\.scratch\\audio-dev\\dl_manifest2.json', JSON.stringify(man, null, 2));
console.log(`\n${man.length} files`);
