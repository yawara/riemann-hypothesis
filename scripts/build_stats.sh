#!/usr/bin/env bash
# ビルドログ(build.log)から統計を取り出して、テキストで出力する。
#
# 使い方: scripts/build_stats.sh [RUN_DIR]   (省略時は最新のビルド)
set -uo pipefail
export LC_ALL=C.UTF-8
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="${1:-${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}/latest-build}"
LOG="$RUN/build.log"

echo "run_dir: $(readlink -f "$RUN")"
cat "$RUN/build.meta.txt"
echo
echo "## /usr/bin/time -v (lake プロセスとその子孫の合計)"
grep -E 'Elapsed \(wall clock\)|User time|System time|Maximum resident|Exit status' "$RUN/build.time.txt" 2>/dev/null | sed 's/^\s*//'
echo
echo "## ログ集計"
echo "log_bytes: $(stat -c %s "$LOG")"
echo "built_lines(✔ 警告なしで完了): $(grep -c -E '^✔ \[[0-9]+/[0-9]+\] Built ' "$LOG")"
echo "built_lines(⚠ 警告つきで完了): $(grep -c -E '^⚠ \[[0-9]+/[0-9]+\] Built ' "$LOG")"
echo "replayed_lines(前回の成果物を再利用): $(grep -c -E '^(✔|⚠) \[[0-9]+/[0-9]+\] Replayed ' "$LOG")"
echo "failed_lines(✖): $(grep -c -E '^✖ \[[0-9]+/[0-9]+\] ' "$LOG")"
echo "error_lines(error:): $(grep -c -E '^error: ' "$LOG")"
echo "warning_lines(warning:): $(grep -c -E '^warning: ' "$LOG")"
echo "last_line: $(tail -1 "$LOG" | cut -c1-200)"
echo
echo "## 成果物"
echo "olean_files: $(find "$ROOT/lean/.lake/build/lib/lean/" -name '*.olean' | wc -l)"
echo "build_lib_size: $(du -sh "$ROOT/lean/.lake/build/lib" | cut -f1)"
echo
echo "## モジュールごとの所要時間(Lake の表示値の合計。並列実行なので実時間ではない)"
grep -o -E '(Built|Replayed) [^ ]+ \([0-9.]+(ms|s|m)\)' "$LOG" | grep '^Built' \
  | awk '{t=$3; gsub(/[()]/,"",t); if (t ~ /ms$/) v=t/1000.0; else if (t ~ /m$/) v=t*60; else v=t+0; s+=v; n++; print v, $2}' \
  | sort -rn > "$RUN/module-times.txt"
awk '{s+=$1; n++} END{printf "modules_with_time: %d\nsum_seconds: %.0f (= %.1f 時間)\nmean_seconds: %.1f\n", n, s, s/3600, (n? s/n : 0)}' "$RUN/module-times.txt"
echo "slowest 15:"
head -15 "$RUN/module-times.txt" | awk '{printf "  %8.0f s  %s\n", $1, $2}'
echo
echo "## 警告の種類(上位)"
grep -E '^warning: ' "$LOG" | sed -E 's/^warning: [^ ]+ //' | cut -c1-70 | sort | uniq -c | sort -rn | head -15
if [ "$(grep -c -E '^(✖|error: )' "$LOG")" != "0" ]; then
  echo
  echo "## 失敗・エラー(先頭 60 行)"
  grep -n -E '^(✖|error: )' "$LOG" | head -60 | cut -c1-400
fi
