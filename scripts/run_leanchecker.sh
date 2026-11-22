#!/usr/bin/env bash
# ビルド済みの全モジュールを、カーネルに再生(replay)させて再検査する。
#
# 再生とは、各モジュールの .olean に入っている宣言を、そのモジュールの import だけを読み込んだ環境へ
# 1 つずつカーネル経由で追加し直すこと。エラボレータやメタプログラムを経由せずにカーネルだけで
# 再検査するので、「カーネル検査を迂回して環境に宣言を押し込む」類の細工(environment hacking)があれば
# 検出できる。Lean ツールチェーン同梱の `leanchecker`(旧 lean4checker)と同じ処理。
#
# ■ leanchecker をそのまま使わない理由
#   leanchecker(src/lean/LeanChecker.lean)は、引数の名前 1 つごとに検索パス全体(約 18.6 万個の .olean)を
#   走査し直して前方一致するモジュールを探す。17.5 万個の名前を渡すと、この名前の解決だけで何日もかかる
#   (2026-11-22 の 1 回目の実行で判明。100 並列で 1 回の走査に約 6.5 分、1 プロセスに 1,752 個の名前)。
#   前方一致でまとめて渡す方法も、平らなディレクトリが多いため有効にまとめられなかった。
#   そこで、leanchecker の再生関数 `replayFromImports` を一字一句そのまま写し、名前の解決だけを省いた
#   小さな実行ファイル rhcheck(verification/leanchecker-driver/)にモジュール名を直接渡す。
#   最初に、いくつかのモジュールで公式の leanchecker と rhcheck の両方を走らせ、どちらも通ることを確かめる。
#
# ■ 並べ方
#   1 プロセス内で複数モジュールを同時に再生すると .olean の mmap が共有されずメモリを大量に消費するため、
#   LEAN_NUM_THREADS=1 のプロセスを JOBS 個並べる。モジュールは CHUNK 個ずつの小さな組に分け、
#   空いたプロセスから順に次の組を取る(xargs -P)。組は全体からとびとびに選び、重いモジュールが偏らないようにする。
#   (2 回目の実行では 100 個の大きな組を最初に固定で割り当てたため、組ごとの進み方に 2 倍以上の差が出た。)
#   検索パス(LEAN_PATH)は、シンボリックリンクを解決した実パスにして、プロジェクトを先頭に置く
#   (モジュール名は検索パスの中で重複しないので、順序を変えても読み込まれる .olean は同じ)。
#
# ■ 途中からの再開
#   PREV_RUNS に以前の実行のディレクトリ(空白区切り)を渡すと、そこで `ok` になったモジュールは再生し直さず、
#   その記録を batch.prev.log として引き継ぐ。最後の照合は、引き継いだ分と今回の分を合わせて全モジュールを数える。
#
# SCOPE=project(既定)は配布プロジェクトの全モジュール、SCOPE=deps は Mathlib など依存
# ライブラリ(公式キャッシュから取得した .olean)の全モジュール(ルートの集約ファイルも含む)。
#
# 使い方: JOBS=100 scripts/run_leanchecker.sh
#         SCOPE=deps JOBS=100 scripts/run_leanchecker.sh
#         PREV_RUNS=/var/tmp/.../leanchecker-project-XXXX VALIDATE=0 scripts/run_leanchecker.sh
set -uo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SCOPE="${SCOPE:-project}"
OUT="$RUN_ROOT/leanchecker-$SCOPE-$TS"
JOBS="${JOBS:-100}"
CHUNK="${CHUNK:-25}"
PREV_RUNS="${PREV_RUNS:-}"
TC="${RH_TOOLCHAIN:-$HOME/.elan/toolchains/leanprover--lean4---v4.33.1}"
DRIVER_DIR="$ROOT/verification/leanchecker-driver"
DRIVER="$DRIVER_DIR/.lake/build/bin/rhcheck"
mkdir -p "$OUT"
ln -sfn "$OUT" "$RUN_ROOT/latest-leanchecker-$SCOPE"

# rhcheck をビルドする(数秒)
( cd "$DRIVER_DIR" && lake build ) > "$OUT/driver-build.log" 2>&1 || { echo "rhcheck のビルドに失敗"; cat "$OUT/driver-build.log"; exit 1; }

cd "$ROOT/lean"
# 検索パス: lake env の LEAN_PATH を実パスにし、プロジェクトを先頭に置く(存在しない場所は除く)
LP="$(lake env printenv LEAN_PATH)"
LPR="$( { echo "$LP" | tr ':' '\n' | grep -v '/packages/'; echo "$LP" | tr ':' '\n' | grep '/packages/'; } \
  | while read -r d; do [ -n "$d" ] && [ -d "$d" ] && realpath "$d"; done | paste -sd: )"
export LEAN_PATH="$LPR" LEAN_SYSROOT="$TC" LEAN_NUM_THREADS=1

if [ -n "${MODULES_FILE:-}" ]; then
  # 動作試験用: 検査するモジュール名の一覧を直接与える
  sort -u "$MODULES_FILE" > "$OUT/modules.txt"
elif [ "$SCOPE" = "deps" ]; then
  for lib in .lake/packages/*/.lake/build/lib/lean; do
    ( cd "$lib" && find . -name '*.olean' | sed -e 's|^\./||' -e 's|\.olean$||' -e 's|/|.|g' )
  done | sort -u > "$OUT/modules.txt"
else
  find src -name '*.lean' | sed -e 's|^src/||' -e 's|\.lean$||' -e 's|/|.|g' | sort > "$OUT/modules.txt"
fi
N="$(wc -l < "$OUT/modules.txt")"

# 以前の実行で済んだモジュールを引き継ぐ
: > "$OUT/batch.prev.log"
if [ -n "$PREV_RUNS" ]; then
  for d in $PREV_RUNS; do
    cat "$d"/batch.*.log 2>/dev/null | grep '^ok ' | cut -d' ' -f2
  done | sort -u | comm -12 - "$OUT/modules.txt" | sed 's/^/ok /' > "$OUT/batch.prev.log"
fi
cut -d' ' -f2 "$OUT/batch.prev.log" | sort -u | comm -23 "$OUT/modules.txt" - > "$OUT/todo.txt"
T="$(wc -l < "$OUT/todo.txt")"
CHUNKS="$(( (T + CHUNK - 1) / CHUNK ))"
# 組 k には、残りのモジュールのうち k, k+CHUNKS, k+2*CHUNKS, … 番目を入れる(全体からとびとびに選ぶ)
if [ "$T" -gt 0 ]; then
  awk -v n="$CHUNKS" '{print > sprintf("%s/batch.%05d", dir, (NR-1) % n)}' dir="$OUT" "$OUT/todo.txt"
fi

{
  echo "started_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "scope: $SCOPE"
  echo "modules: $N"
  echo "carried_over_from_previous_runs: $(wc -l < "$OUT/batch.prev.log")${PREV_RUNS:+ ($PREV_RUNS)}"
  echo "to_replay_now: $T"
  echo "jobs: $JOBS"
  echo "chunk_size: $CHUNK"
  echo "chunks: $CHUNKS"
  echo "driver: $DRIVER ($(sha256sum "$DRIVER" | cut -c1-16)…)"
  echo "leanchecker: $TC/bin/leanchecker"
  echo "lean: $("$TC/bin/lean" --version 2>&1)"
  echo "LEAN_PATH: $LEAN_PATH"
} > "$OUT/meta.txt"

# 照合: 見本のモジュールを、公式の leanchecker と rhcheck の両方で再生する(project のときだけ)
if [ "$SCOPE" = "project" ] && [ -z "${MODULES_FILE:-}" ] && [ "${VALIDATE:-1}" = "1" ]; then
  mkdir -p "$OUT/validate"
  printf '%s\n' \
    Development.AbelianVarietyTheory.BlockTheory.AdelicCMFields.UnitaryHeckeCharacterIdele \
    Development.AbelianVarietyTheory.Proofs.TwistedOperators.GoodRowsPrincipalLevelAreRows \
    Supplements.Kernels.MainTheoremsAll > "$OUT/validate/modules.txt"
  /usr/bin/time -f '# wall=%es user=%Us sys=%Ss maxrss=%MKB' "$TC/bin/leanchecker" -v $(cat "$OUT/validate/modules.txt") \
    > "$OUT/validate/leanchecker.log" 2>&1
  v1=$?
  /usr/bin/time -f '# wall=%es user=%Us sys=%Ss maxrss=%MKB' "$DRIVER" "$OUT/validate/modules.txt" \
    > "$OUT/validate/rhcheck.log" 2>&1
  v2=$?
  echo "validate: leanchecker rc=$v1, rhcheck rc=$v2 (3 modules)" >> "$OUT/meta.txt"
  if [ "$v1" != "0" ] || [ "$v2" != "0" ]; then
    echo "照合に失敗。中止する"; cat "$OUT/meta.txt"; exit 1
  fi
fi

if [ "$T" -gt 0 ]; then
  ls "$OUT" | grep -E '^batch\.[0-9]{5}$' | sed "s|^|$OUT/|" | xargs -P "$JOBS" -I{} sh -c '
    start=$(date +%s)
    "$0" "{}" > "{}.log" 2>&1
    rc=$?
    echo "$rc $(( $(date +%s) - start ))" > "{}.rc"
  ' "$DRIVER"
fi

fail=0
for f in $(ls "$OUT" | grep -E '^batch\.[0-9]{5}$' | sed "s|^|$OUT/|"); do
  rc="$(cut -d" " -f1 "$f.rc" 2>/dev/null || echo missing)"
  [ "$rc" = "0" ] || { fail=$((fail + 1)); echo "FAILED chunk: $f (rc=$rc)"; grep '^FAILED' "$f.log" | head -3; tail -2 "$f.log"; }
done
# 照合: 全モジュールに `ok` の記録があるか(引き継いだ分と今回の分を合わせて数える)
cat "$OUT"/batch.*.log | grep '^ok ' | cut -d' ' -f2 | sort -u > "$OUT/ok-modules.txt"
comm -23 "$OUT/modules.txt" "$OUT/ok-modules.txt" > "$OUT/missing.txt"
ok="$(comm -12 "$OUT/modules.txt" "$OUT/ok-modules.txt" | wc -l)"
failed_modules="$(cat "$OUT"/batch.*.log | grep -c '^FAILED ')"
{
  echo "finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "failed_chunks: $fail"
  echo "ok_modules: $ok / $N"
  echo "missing_modules: $(wc -l < "$OUT/missing.txt")"
  echo "failed_modules: $failed_modules"
} >> "$OUT/meta.txt"
cat "$OUT/meta.txt"
[ "$fail" = "0" ] && [ "$ok" = "$N" ] && [ "$failed_modules" = "0" ]
