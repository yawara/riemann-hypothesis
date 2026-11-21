#!/usr/bin/env bash
# 配布された Lean プロジェクト(lean/)を、配布物の lakefile.toml / lake-manifest.json /
# lean-toolchain のまま `lake build` する。ソースには一切手を加えない。
#
#   * 出力: $RUN_DIR/build.log(Lake の全出力)、build.time.txt(/usr/bin/time -v)、
#           build.meta.txt(開始・終了時刻、終了コード、ツール版数)
#   * ビルド中は setup_json_reaper.sh を並走させ、巨大な setup.json を随時削除する
#
# 使い方: scripts/build.sh [lake build に渡すターゲット...]   (省略時は既定ターゲット全部)
set -uo pipefail
export LC_ALL=C.UTF-8

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$RUN_ROOT/build-$TS"
mkdir -p "$RUN_DIR"
ln -sfn "$RUN_DIR" "$RUN_ROOT/latest-build"

cd "$ROOT/lean"

{
  echo "run_dir: $RUN_DIR"
  echo "started_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "targets: ${*:-<default targets>}"
  echo "lake: $(lake --version 2>&1)"
  echo "lean: $(lean --version 2>&1)"
  echo "nproc: $(nproc)"
  echo "sha256 lakefile.toml: $(sha256sum lakefile.toml | cut -d' ' -f1)"
  echo "sha256 lake-manifest.json: $(sha256sum lake-manifest.json | cut -d' ' -f1)"
  echo "sha256 lean-toolchain: $(sha256sum lean-toolchain | cut -d' ' -f1)"
} > "$RUN_DIR/build.meta.txt"

bash "$ROOT/scripts/setup_json_reaper.sh" "$ROOT/lean/.lake/build/ir" 30 5 &
REAPER_PID=$!
trap 'kill "$REAPER_PID" 2>/dev/null' EXIT

/usr/bin/time -v -o "$RUN_DIR/build.time.txt" lake build "$@" > "$RUN_DIR/build.log" 2>&1
rc=$?

{
  echo "finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "exit_code: $rc"
} >> "$RUN_DIR/build.meta.txt"
echo "$rc" > "$RUN_DIR/exit_code"
exit "$rc"
