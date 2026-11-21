// 見出し用の書体(解星 特ミン ExtraBold)を、紙面で実際に使う文字だけに絞り込む。
//
//   入力: ビルド済みの dist/index.html。class に font-display を含む要素の中の文字を集める
//   出力: src/assets/fonts/display-subset.woff2(リポジトリに含めるので、この道具が無くてもサイトはビルドできる)
//
// 元の書体は npm の @expo-google-fonts/kaisei-tokumin(SIL Open Font License 1.1)。全体で約 4.5 MB あるため、
// 見出しに使う数十字だけを取り出して数十 KB にする。絞り込みは subset-font(HarfBuzz の WebAssembly 版)。
//
// 使い方: node scripts/subset-display-font.mjs   (site/ で実行。内容が変わったら終了コード 10 を返す)
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import subsetFont from 'subset-font';
import { ELEMENT_NODE, TEXT_NODE, parse } from 'ultrahtml';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const pkgDir = dirname(require.resolve('@expo-google-fonts/kaisei-tokumin/package.json'));
const source = join(pkgDir, '800ExtraBold', 'KaiseiTokumin_800ExtraBold.ttf');
const outDir = join(root, 'src', 'assets', 'fonts');
const out = join(outDir, 'display-subset.woff2');
const html = join(root, 'dist', 'index.html');

// いつも入れておく文字(数字・約物)。閲覧時に差し替わる数値などに備える
const chars = new Set(' 0123456789.,:;/%+-−()()、。・「」ー');
// 状態の印に使う文字(判定が出たあとの分も含む)
for (const c of '検証中済未否合格独立之記録印') chars.add(c);

if (existsSync(html)) {
  const visit = (node, inside) => {
    if (node.type === ELEMENT_NODE) {
      const cls = ` ${node.attributes?.class ?? ''} `;
      inside ||= cls.includes(' font-display ');
    } else if (node.type === TEXT_NODE && inside) {
      for (const c of node.value) chars.add(c);
    }
    for (const child of node.children ?? []) visit(child, inside);
  };
  visit(parse(await readFile(html, 'utf8')), false);
} else {
  console.warn('dist/index.html が無いので、基本の文字だけで作ります(先に astro build を実行してください)');
}
chars.delete('\n');
chars.delete('\t');

const text = [...chars].sort().join('');
const subset = await subsetFont(await readFile(source), text, { targetFormat: 'woff2' });
const before = existsSync(out) ? createHash('sha256').update(await readFile(out)).digest('hex') : '';
const after = createHash('sha256').update(subset).digest('hex');
await mkdir(outDir, { recursive: true });
await copyFile(join(pkgDir, 'LICENSE_FONT'), join(outDir, 'KaiseiTokumin-OFL.txt'));
if (before === after) {
  console.log(`display-subset.woff2: 変更なし(${chars.size} 字、${subset.length} バイト)`);
} else {
  await writeFile(out, subset);
  await writeFile(join(outDir, 'display-subset.txt'), text + '\n');
  console.log(`display-subset.woff2: 更新(${chars.size} 字、${subset.length} バイト)`);
  process.exitCode = 10;
}
