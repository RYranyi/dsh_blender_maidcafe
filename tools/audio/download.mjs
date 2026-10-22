// 批量下载素材（Node fetch，走系统 TLS；PowerShell IWR 会被拦）
// 用法: node download.mjs   （读同目录 sources.json，输出到 .scratch/audio-dev/dl）
import fs from 'node:fs';
import path from 'node:path';

const DL = 'E:\\dsh\\maid_cafe\\.scratch\\audio-dev\\dl';
fs.mkdirSync(DL, { recursive: true });
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36';

const OGA = 'https://opengameart.org/sites/default/files/';

const sources = [
  // ---- ZIP 音效包（CC0, rubberduck / StarNinjas / laleksic / Ylmir）----
  { file: 'pack_rubberduck_100_v1.zip', url: OGA + '100-CC0-SFX_0.zip', lic: 'CC0', author: 'rubberduck', src: 'https://opengameart.org/content/100-cc0-sfx' },
  { file: 'pack_rubberduck_100_v2.zip', url: OGA + 'sfx_100_v2.zip', lic: 'CC0', author: 'rubberduck', src: 'https://opengameart.org/content/100-cc0-sfx-2' },
  { file: 'pack_rubberduck_loops.zip', url: OGA + 'sfx_loops.zip', lic: 'CC0', author: 'rubberduck', src: 'https://opengameart.org/content/30-cc0-sfx-loops' },
  { file: 'pack_starninjas_pages.zip', url: OGA + 'book_flips_-_starninjas.zip', lic: 'CC0', author: 'StarNinjas', src: 'https://opengameart.org/content/10-book-page-flips' },
  { file: 'pack_laleksic_sfx.zip', url: OGA + 'sounds_8.zip', lic: 'CC0', author: 'laleksic', src: 'https://opengameart.org/content/various-sound-effects' },
  { file: 'pack_ylmir_rain.zip', url: OGA + 'Rain%20OGG.zip', lic: 'CC0', author: 'Ylmir', src: 'https://opengameart.org/content/rain-loopable' },

  // ---- 雨 / 风暴 / 风 ----
  { file: 'rain_loop_1.ogg', url: OGA + 'amb_rain_loop_1.ogg', lic: 'CC0', author: 'Kresiek The Furry', src: 'https://opengameart.org/content/amb-rain-loop-1' },
  { file: 'rain_loop_2.ogg', url: OGA + 'amb_rain2.ogg', lic: 'CC0', author: 'Kresiek The Furry', src: 'https://opengameart.org/content/amb-rain-loop-2' },
  { file: 'rain_gutter.mp3', url: OGA + 'rain-gutter-loop_0.mp3', lic: 'CC0', author: 'Ogrebane', src: 'https://opengameart.org/content/rain-gutter-loop' },
  { file: 'rain_thunder.ogg', url: OGA + 'rain-thunder.ogg', lic: 'CC0', author: 'WuxiaScrub', src: 'https://opengameart.org/content/rain-long-thunder' },
  { file: 'dark_rainy_night.ogg', url: OGA + 'Dark_Rainy_Night%28ambience%29.ogg', lic: 'CC0', author: 'kindland', src: 'https://opengameart.org/content/rain-and-thunders' },
  { file: 'storm_siren.ogg', url: OGA + 'storm_3_siren.ogg', lic: 'CC0', author: 'TinyWorlds', src: 'https://opengameart.org/content/storm-siren' },
  { file: 'wind_whoosh_loop.ogg', url: OGA + 'wind%20woosh%20loop.ogg', lic: 'CC0', author: 'SketchMan3', src: 'https://opengameart.org/content/wind-whoosh-loop' },
  { file: 'rain_window_loop.wav', url: OGA + 'rain_on_window_loop.wav', lic: 'CC-BY 4.0', author: 'alxl', src: 'https://opengameart.org/content/rain-on-window-loop' },

  // ---- 环境：鸟 / 公园 / 夜虫 / 冰箱 ----
  { file: 'park_birds.wav', url: OGA + 'park_ambience_birds.wav', lic: 'CC0', author: 'Thimras', src: 'https://opengameart.org/content/park-ambiences' },
  { file: 'park_wind.wav', url: OGA + 'park_ambience_wind.wav', lic: 'CC0', author: 'Thimras', src: 'https://opengameart.org/content/park-ambiences' },
  { file: 'park_river.wav', url: OGA + 'park_ambience_river.wav', lic: 'CC0', author: 'Thimras', src: 'https://opengameart.org/content/park-ambiences' },
  { file: 'birds_wind_synth.ogg', url: OGA + 'Birds%20and%20Wind%20-%20Ambient_1.ogg', lic: 'CC0', author: 'Spring Spring', src: 'https://opengameart.org/content/birds-and-wind-ambient-birds-wind-and-synth' },
  { file: 'crickets.mp3', url: OGA + 'crickets_1.mp3', lic: 'CC0', author: 'Wolfgang_', src: 'https://opengameart.org/content/crickets-ambient-noise-loopable' },
  { file: 'fridge_loop.ogg', url: OGA + 'amb_fridge_loop_1.ogg', lic: 'CC0', author: 'Kresiek The Furry', src: 'https://opengameart.org/content/fridge-loop-1' },

  // ---- 铃 / 门铃 ----
  { file: 'bell_ding1.wav', url: OGA + 'bell_ding1.wav', lic: 'CC0', author: 'PWL', src: 'https://opengameart.org/content/bell-dingschimes' },
  { file: 'bell_ding2.wav', url: OGA + 'bell_ding2.wav', lic: 'CC0', author: 'PWL', src: 'https://opengameart.org/content/bell-dingschimes' },
  { file: 'bell_ding3.wav', url: OGA + 'bell_ding3.wav', lic: 'CC0', author: 'PWL', src: 'https://opengameart.org/content/bell-dingschimes' },
  { file: 'bell_ding4.wav', url: OGA + 'bell_ding4.wav', lic: 'CC0', author: 'PWL', src: 'https://opengameart.org/content/bell-dingschimes' },
  { file: 'doorbell.wav', url: OGA + 'doorbell.wav', lic: 'CC0', author: 'frosty ham', src: 'https://opengameart.org/content/doorbell' },
  { file: 'doorbell_tring.ogg', url: OGA + 'doorbell-old-tring.ogg', lic: 'CC0', author: 'Dub', src: 'https://opengameart.org/content/doorbell-ring' },

  // ---- 音乐铺底（CC0）----
  { file: 'music_urban_shop.ogg', url: OGA + 'urban_shop_bpm92_0.ogg', lic: 'CC0', author: 'MintoDog', src: 'https://opengameart.org/content/urban-shop' },
  { file: 'music_cozy_puzzle.ogg', url: OGA + 'cozy_puzzle_in-game_1_bpm118_0.ogg', lic: 'CC0', author: 'MintoDog', src: 'https://opengameart.org/content/cozy-puzzle-in-game-1' },
  { file: 'music_catchy_swing.ogg', url: OGA + 'catchyswing.ogg', lic: 'CC0', author: 'Doge', src: 'https://opengameart.org/content/catchy-swing' },
  { file: 'music_cool_city.ogg', url: OGA + 'cool_city_bpm124_0.ogg', lic: 'CC0', author: 'MintoDog', src: 'https://opengameart.org/content/cool-city' },
  { file: 'music_jazzy_battle.ogg', url: OGA + 'jazzy_battle_theme_bpm130_0.ogg', lic: 'CC0', author: 'MintoDog', src: 'https://opengameart.org/content/jazzy-battle-theme' },
  { file: 'music_blues.mp3', url: OGA + 'blues_0.mp3', lic: 'CC0', author: 'LushoGames', src: 'https://opengameart.org/content/jazzy-blues' },
  { file: 'music_freejazz.flac', url: OGA + 'freejazz_medley.flac', lic: 'CC0', author: 'Anonymous', src: 'https://opengameart.org/content/freejazz-medley-loop' },
  { file: 'music_bird_night.ogg', url: OGA + 'bird_in_hand_night_0.ogg', lic: 'CC0', author: 'Fupi', src: 'https://opengameart.org/content/bird-in-hand-night' },
];

const only = process.argv.slice(2);
const list = only.length ? sources.filter((s) => only.some((o) => s.file.includes(o))) : sources;

const manifest = [];
for (const s of list) {
  const out = path.join(DL, s.file);
  if (fs.existsSync(out) && fs.statSync(out).size > 0) {
    const sz = fs.statSync(out).size;
    console.log(`SKIP ${s.file} (${(sz / 1024).toFixed(0)}KB)`);
    manifest.push({ ...s, bytes: sz, local: out, cached: true });
    continue;
  }
  const t0 = Date.now();
  try {
    const res = await fetch(s.url, { headers: { 'user-agent': UA }, redirect: 'follow' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const buf = Buffer.from(await res.arrayBuffer());
    fs.writeFileSync(out, buf);
    console.log(`OK   ${s.file.padEnd(34)} ${(buf.length / 1024).toFixed(0).padStart(6)}KB ${String(Date.now() - t0).padStart(6)}ms`);
    manifest.push({ ...s, bytes: buf.length, local: out });
  } catch (e) {
    console.log(`FAIL ${s.file.padEnd(34)} ${e.message}`);
  }
}
fs.writeFileSync('E:\\dsh\\maid_cafe\\.scratch\\audio-dev\\dl_manifest.json', JSON.stringify(manifest, null, 2));
console.log(`\n${manifest.length} files, ${(manifest.reduce((a, b) => a + (b.bytes || 0), 0) / 1048576).toFixed(1)} MB`);
