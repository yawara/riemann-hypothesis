#!/usr/bin/env bash
# ビルド済みの全プロジェクトモジュールを、Lean ツールチェーン同梱の `leanchecker`
# (旧 lean4checker)でカーネルに再生(replay)させる。
#
# leanchecker は各モジュールの .olean に入っている宣言を、そのモジュールの import だけを
# 読み込んだ環境へ 1 つずつカーネル経由で追加し直す。エラボレータやメタプログラムを
# 経由せずにカーネルだけで再検査するので、「カーネル検査を迂回して環境に宣言を押し込む」
# 類の細工(environment hacking)があれば検出できる。
#
# 1 プロセス内で複数モジュールを同時に再生すると .olean の mmap が共有されずメモリを
# 大量に消費するため、LEAN_NUM_THREADS=1 のプロセスを多数並べ、各プロセスには
# モジュールのバッチを順番に処理させる。
#
# SCOPE=project(既定)は配布プロジェクトの全モジュール、SCOPE=deps は Mathlib など依存
# ライブラリ(公式キャッシュから取得した .olean)の全モジュールを対象にする。
#
# 使い方: JOBS=100 scripts/run_leanchecker.sh
#         SCOPE=deps JOBS=100 scripts/run_leanchecker.sh
set -uo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SCOPE="${SCOPE:-project}"
OUT="$RUN_ROOT/leanchecker-$SCOPE-$TS"
JOBS="${JOBS:-100}"
mkdir -p "$OUT"
ln -sfn "$OUT" "$RUN_ROOT/latest-leanchecker-$SCOPE"

cd "$ROOT/lean"

if [ -n "${MODULES_FILE:-}" ]; then
  # 動作試験用: 検査するモジュール名の一覧を直接与える
  cp "$MODULES_FILE" "$OUT/modules.txt"
elif [ "$SCOPE" = "deps" ]; then
  for lib in .lake/packages/*/.lake/build/lib/lean; do
    ( cd "$lib" && find . -name '*.olean' | sed -e 's|^\./||' -e 's|\.olean$||' -e 's|/|.|g' )
  done | sort -u > "$OUT/modules.all.txt"
  # leanchecker は引数を「前方一致」で解釈するため、`Mathlib` のようなルートモジュール名を
  # 渡すとライブラリ全体が 1 プロセスで再検査されてしまう。ルート(名前に `.` を含まない
  # もの)は配下の全モジュールを import するだけの集約ファイルなので対象から外し、
  # 配下のモジュールを個別に検査する。
  grep -v '\.' "$OUT/modules.all.txt" > "$OUT/modules.excluded-roots.txt" || true
  grep '\.' "$OUT/modules.all.txt" > "$OUT/modules.txt"
else
  find src -name '*.lean' | sed -e 's|^src/||' -e 's|\.lean$||' -e 's|/|.|g' | sort > "$OUT/modules.txt"
fi
N="$(wc -l < "$OUT/modules.txt")"
BATCH="${BATCH:-$(( (N + JOBS - 1) / JOBS ))}"
# 重いモジュールが 1 バッチに偏らないよう、決定的な順序でばらしてから分割する
awk -v jobs="$(( (N + BATCH - 1) / BATCH ))" '{print > sprintf("%s/batch.%04d", dir, (NR-1) % jobs)}' dir="$OUT" "$OUT/modules.txt"

{
  echo "started_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "scope: $SCOPE"
  echo "modules: $N"
  echo "jobs: $JOBS"
  echo "batch_size: $BATCH"
  echo "batches: $(ls "$OUT"/batch.???? | wc -l)"
  echo "leanchecker: $(command -v leanchecker)"
  echo "lean: $(lean --version 2>&1)"
} > "$OUT/meta.txt"

ls "$OUT"/batch.???? | xargs -P "$JOBS" -I{} sh -c '
  start=$(date +%s)
  LEAN_NUM_THREADS=1 lake env leanchecker -v $(cat "{}") > "{}.log" 2>&1
  rc=$?
  echo "$rc $(( $(date +%s) - start ))" > "{}.rc"
'

fail=0
for f in "$OUT"/batch.????; do
  rc="$(cut -d" " -f1 "$f.rc" 2>/dev/null || echo missing)"
  [ "$rc" = "0" ] || { fail=$((fail + 1)); echo "FAILED batch: $f (rc=$rc)"; tail -3 "$f.log"; }
done
replayed="$(cat "$OUT"/batch.????.log | grep -c '^replaying ')"
{
  echo "finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "failed_batches: $fail"
  echo "replaying_lines: $replayed"
} >> "$OUT/meta.txt"
cat "$OUT/meta.txt"
[ "$fail" = "0" ]
