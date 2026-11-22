#!/usr/bin/env bash
# ビルドの終了を待ち、成功していればビルド後の検査を順に実行する。
# 端末やセッションが切れても進むよう、setsid/nohup で切り離して起動する想定。
#
#   0. ビルドが失敗していた場合は 1 回だけ `lake build` をやり直す
#      (OOM など環境要因の失敗を拾うため。成功済みモジュールは再利用される)
#   1. run_checks.sh      … 公理の一覧 / 主張の一致 / 主張の依存解析     ┐ 並行
#   2. run_leanchecker.sh … 全モジュールのカーネル再検査                 ┘
#   3. run_leanchecker.sh (SCOPE=deps) … Mathlib など依存ライブラリのカーネル再検査
#   4. run_nanoda.sh      … 主定理の依存一式を別実装カーネルで検査
#   5. reconstruct.sh --verify … ソースが原本のままであることの再照合
#
# 各段の終了コードと時刻を $RUN_ROOT/pipeline/status.txt に追記する。
#
# 使い方: scripts/post_build_pipeline.sh <build.sh の PID>
#         scripts/post_build_pipeline.sh --from-leanchecker   # 2. から再開(1. は済んでいるとき)
#
# 2026-11-22: 1 回目の実行では 2. の leanchecker が名前の解決だけで何日もかかる見込みになったため止め、
# run_leanchecker.sh を作り直して --from-leanchecker で再開した(経緯は run_leanchecker.sh の冒頭)。
set -uo pipefail
export LC_ALL=C.UTF-8

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}"
P="$RUN_ROOT/pipeline"
mkdir -p "$P"
STATUS="$P/status.txt"
BUILD_PID="${1:-}"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$STATUS"; }

FROM_LEANCHECKER=0
if [ "$BUILD_PID" = "--from-leanchecker" ]; then
  FROM_LEANCHECKER=1
  BUILD_PID=""
fi

if [ "$FROM_LEANCHECKER" = "1" ]; then
  log "pipeline resume from leanchecker"
else
log "pipeline start (waiting for build pid=${BUILD_PID:-none})"
if [ -n "$BUILD_PID" ]; then
  tail --pid="$BUILD_PID" -f /dev/null
fi

rc="$(cat "$RUN_ROOT/latest-build/exit_code" 2>/dev/null || echo missing)"
log "build finished: exit_code=$rc run=$(readlink -f "$RUN_ROOT/latest-build")"
bash "$ROOT/scripts/build_stats.sh" > "$P/build-stats-first.txt" 2>&1

if [ "$rc" != "0" ]; then
  log "build failed; retrying once"
  bash "$ROOT/scripts/build.sh" > "$P/build-retry.launch.out" 2>&1
  rc="$(cat "$RUN_ROOT/latest-build/exit_code" 2>/dev/null || echo missing)"
  log "retry finished: exit_code=$rc run=$(readlink -f "$RUN_ROOT/latest-build")"
  bash "$ROOT/scripts/build_stats.sh" > "$P/build-stats-retry.txt" 2>&1
fi

if [ "$rc" != "0" ]; then
  log "BUILD FAILED after retry; stopping pipeline"
  echo "build_failed" > "$P/result"
  exit 1
fi

log "checks: start"
bash "$ROOT/scripts/run_checks.sh" > "$P/run_checks.out" 2>&1 &
CHECKS_PID=$!
fi

log "leanchecker: start"
JOBS="${LEANCHECKER_JOBS:-100}" bash "$ROOT/scripts/run_leanchecker.sh" > "$P/run_leanchecker.out" 2>&1
log "leanchecker: exit_code=$?"

if [ "$FROM_LEANCHECKER" = "0" ]; then
  wait "$CHECKS_PID"
  log "checks: exit_code=$?"
fi

log "leanchecker(deps): start"
SCOPE=deps JOBS="${LEANCHECKER_JOBS:-100}" bash "$ROOT/scripts/run_leanchecker.sh" > "$P/run_leanchecker_deps.out" 2>&1
log "leanchecker(deps): exit_code=$?"

log "nanoda: start"
THREADS="${NANODA_THREADS:-96}" bash "$ROOT/scripts/run_nanoda.sh" > "$P/run_nanoda.out" 2>&1
log "nanoda: exit_code=$?"

log "source verify: start"
bash "$ROOT/scripts/reconstruct.sh" --verify > "$P/reconstruct-verify.out" 2>&1
log "source verify: exit_code=$?"

log "pipeline done"
echo "done" > "$P/result"
