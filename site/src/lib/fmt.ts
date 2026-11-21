// サーバ側(ビルド時)とブラウザ側の両方で使う整形関数。定点観測の表は、同じ関数でビルド時にも閲覧時にも組み立てる。

export const fmtInt = (n: number) => Number(n).toLocaleString('en-US');

const pad = (v: number) => String(v).padStart(2, '0');
/** UTC の時刻を、日本時間の Date(getUTC* で日本時間の各部が取れる)にずらす */
export const toJst = (iso: string | number) => new Date(new Date(iso).getTime() + 9 * 3600 * 1000);
export const jstHm = (iso: string | number) => {
  const d = toJst(iso);
  return `${d.getUTCHours()}:${pad(d.getUTCMinutes())}`;
};
export const jstMdHm = (iso: string | number) => {
  const d = toJst(iso);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${d.getUTCHours()}:${pad(d.getUTCMinutes())}`;
};
export const elapsed = (min: number) => `${Math.floor(min / 60)}:${pad(Math.round(min % 60))}`;

export const phaseLabel: Record<string, string> = {
  build: 'ビルド',
  'build-finished': 'ビルド終了',
  'build-retry': 'ビルド再実行',
  'post-build-checks': 'ビルド後の検査',
  'independent-kernel': '別実装カーネル',
  'mathlib-rebuild': 'Mathlib 再ビルド',
  finished: '終了',
};

export interface ObsPoint {
  seq: number;
  t_utc: string;
  elapsed_min: number;
  done: number;
  rate_per_min: number;
  error_lines: number | null;
  built_with_warnings: number | null;
  lean_procs: number | null;
  load1: number | null;
  mem_used_gib: number | null;
  disk_free_gib: number | null;
  phase: string;
  source: 'live' | 'mtime';
}
export interface Obs {
  t0_utc: string;
  interval_min: number;
  step_min: number;
  total: number;
  generated_at_utc: string;
  latest: { t_utc: string; done: number; error_lines: number | null; phase: string };
  projection: { window_min: number; rate_per_min: number; eta_utc: string } | null;
  series: number[];
  points: ObsPoint[];
}

const dash = '<span class="text-ink-3">—</span>';
const cell = (v: number | null, digits = 0) =>
  v === null || v === undefined ? dash : digits ? v.toFixed(digits) : fmtInt(v);

/** 表 2(定点観測の記録)の 1 行 */
export function obsRow(p: ObsPoint, total: number): string {
  const pct = ((p.done / total) * 100).toFixed(1);
  return (
    `<tr>` +
    `<td class="num">${p.seq}${p.source === 'mtime' ? '<sup class="font-sans text-[0.7em]">*</sup>' : ''}</td>` +
    `<td class="num">${jstHm(p.t_utc)}</td>` +
    `<td class="num">${elapsed(p.elapsed_min)}</td>` +
    `<td class="num">${fmtInt(p.done)}</td>` +
    `<td class="num">${pct}%</td>` +
    `<td class="num">${p.rate_per_min.toFixed(1)}</td>` +
    `<td class="num">${cell(p.load1, 1)}</td>` +
    `<td class="num">${cell(p.mem_used_gib, 1)}</td>` +
    `<td class="num">${cell(p.disk_free_gib, 1)}</td>` +
    `<td class="num">${cell(p.error_lines)}</td>` +
    `<td class="font-sans text-[0.8125rem] whitespace-nowrap">${phaseLabel[p.phase] ?? p.phase}</td>` +
    `</tr>`
  );
}
