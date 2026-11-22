#!/usr/bin/env bash
# 短縮版(scripts/shorten_stage1a.py などが作った Lake プロジェクト)をビルドする。
#
# * 依存ライブラリ(Mathlib など)は、検証で使ったもの(/var/tmp/riemann-hypothesis-ywr/lake/packages)を
#   reflink で写して使う(XFS の reflink なので、写すのは一瞬で、書き換えても元には影響しない)。
#   検証用の lean/.lake は共有しない(Lake が書き換えると、検証の照合に響くため)。
# * 配布物のビルド結果(lean/.lake/build)も reflink で写しておく。ソースも import も変わっていない
#   モジュールは、Lake が再利用する。
# * Lake には並列数の指定が無いので、LEAN_NUM_THREADS(Lean のランタイムのスレッド数)で絞る。
#   検証の常駐プロセスと並行するときは小さくし、nice で優先度を下げる。
# * build.sh と同じく、Lake が書き出す巨大な setup.json を setup_json_reaper.sh で随時消す。
#
# 使い方: JOBS=16 scripts/shorten_build_stage.sh <短縮版のディレクトリ> [ビルドする対象 ...]
set -uo pipefail
export LC_ALL=C.UTF-8

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(realpath "${1:?usage: shorten_build_stage.sh <stage-dir> [targets...]}")"
shift
JOBS="${JOBS:-16}"
BASE=/var/tmp/riemann-hypothesis-ywr/lake
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$STAGE/builds/build-$TS"
mkdir -p "$LOG" "$STAGE/.lake"

if [ ! -d "$STAGE/.lake/packages" ]; then
  cp -a --reflink=always "$BASE/packages" "$STAGE/.lake/packages"
fi
if [ ! -d "$STAGE/.lake/build" ] && [ "${REUSE_BUILD:-1}" = "1" ]; then
  cp -a --reflink=always "$BASE/build" "$STAGE/.lake/build"
fi

cd "$STAGE"
{
  echo "stage: $STAGE"
  echo "started_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "targets: ${*:-<default targets>}"
  echo "jobs(LEAN_NUM_THREADS): $JOBS"
  echo "lake: $(lake --version 2>&1)"
} > "$LOG/meta.txt"

mkdir -p "$STAGE/.lake/build/ir"
bash "$ROOT/scripts/setup_json_reaper.sh" "$STAGE/.lake/build/ir" 30 5 &
REAPER_PID=$!
trap 'kill "$REAPER_PID" 2>/dev/null' EXIT

LEAN_NUM_THREADS="$JOBS" nice -n 10 /usr/bin/time -v -o "$LOG/time.txt" lake build "$@" > "$LOG/build.log" 2>&1
rc=$?
{
  echo "finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "exit_code: $rc"
  echo "error_lines: $(grep -c '^error' "$LOG/build.log")"
  grep -E 'Elapsed|Maximum resident' "$LOG/time.txt" | sed 's/^\s*/time: /'
} >> "$LOG/meta.txt"
ln -sfn "$LOG" "$STAGE/builds/latest"
cat "$LOG/meta.txt"
exit "$rc"
