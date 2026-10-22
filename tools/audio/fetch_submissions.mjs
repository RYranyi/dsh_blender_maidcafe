// 抓 OGA 提交页，提取：可下载音频直链 / 许可证 / 作者 / 标题
// 用法: node fetch_submissions.mjs <slug1> <slug2> ...
import fs from 'node:fs';
import path from 'node:path';

const OUT = 'E:\\dsh\\maid_cafe\\.scratch\\audio-dev\\html';
fs.mkdirSync(OUT, { recursive: true });
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36';

const slugs = process.argv.slice(2);
const results = {};

for (const slug of slugs) {
  const url = `https://opengameart.org/content/${slug}`;
  try {
    const res = await fetch(url, { headers: { 'user-agent': UA }, redirect: 'follow' });
    const html = await res.text();
    fs.writeFileSync(path.join(OUT, `sub_${slug}.html`), html);

    // 音频直链（OGA 的文件在 /sites/default/files/ 下）
    const files = [...new Set(
      [...html.matchAll(/href="([^"]*\/sites\/default\/files\/[^"]*\.(?:ogg|mp3|wav|flac|m4a))"/gi)].map((m) => m[1])
    )];
    // 许可证块
    const licBlock = (html.match(/field-name-field-art-licenses[\s\S]{0,1200}?<\/div>\s*<\/div>/) || [])[0] || '';
    const lics = [...new Set([...licBlock.matchAll(/>([^<>]{3,60})</g)]
      .map((m) => m[1].trim())
      .filter((t) => /CC0|CC-BY|CC BY|OGA-BY|GPL|Public Domain|Attribution/i.test(t)))];
    // 作者
    const auth = (html.match(/field-name-author[\s\S]{0,600}?<a[^>]*>([^<]{2,60})<\/a>/) || [])[1]
      || (html.match(/Submitted by\s*<[^>]*>([^<]{2,60})</) || [])[1] || '?';
    // 标题
    const title = (html.match(/<title>([^<]*)<\/title>/) || [])[1] || slug;

    results[slug] = { url, files, lics, author: auth.trim(), title: title.trim() };
    console.log(`\n### ${slug}`);
    console.log(`    title: ${results[slug].title}`);
    console.log(`    author: ${results[slug].author}`);
    console.log(`    licenses: ${JSON.stringify(results[slug].lics)}`);
    files.forEach((f) => console.log(`    FILE ${f}`));
    if (!files.length) console.log('    (no audio files found)');
  } catch (e) {
    console.log(`\n### ${slug} FAIL ${e.message}`);
    results[slug] = { url, error: e.message };
  }
}

fs.writeFileSync('E:\\dsh\\maid_cafe\\.scratch\\audio-dev\\submissions.json', JSON.stringify(results, null, 2));
