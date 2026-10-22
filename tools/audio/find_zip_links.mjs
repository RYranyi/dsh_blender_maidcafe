// 从已抓取的 OGA 提交页里找 .zip 打包直链（rubberduck 的 100/30 音效包）
import fs from 'node:fs';
const dir = 'E:\\dsh\\maid_cafe\\.scratch\\audio-dev\\html\\';
const files = fs.readdirSync(dir).filter((f) => f.startsWith('sub_'));
for (const f of files) {
  const h = fs.readFileSync(dir + f, 'utf8');
  const zips = [...new Set([...h.matchAll(/href="([^"]*\.zip)"/gi)].map((m) => m[1]))];
  const any = [...new Set([...h.matchAll(/href="([^"]*\/sites\/default\/files\/[^"]*)"/gi)].map((m) => m[1]))];
  if (zips.length) {
    console.log('### ' + f);
    zips.forEach((z) => console.log('   ZIP ' + z));
  }
  if (!any.length && !zips.length) console.log('### ' + f + '  (no downloadable link at all)');
  else if (any.length > 0 && !zips.length) {
    console.log('### ' + f + '  any=' + any.length);
    any.slice(0, 6).forEach((a) => console.log('   ANY ' + a));
  }
}
