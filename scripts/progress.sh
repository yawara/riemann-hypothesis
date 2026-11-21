#!/usr/bin/env bash
# ビルドの進捗を 1 回表示する(.olean の数、ログ中の成功/失敗数、メモリ、ディスク)。
set -u
export LC_ALL=C
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}/latest-build"
LIB="$ROOT/lean/.lake/build/lib/lean"
TOTAL=175187

echo "now_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
[ -f "$RUN/build.meta.txt" ] && grep -E '^(started_at_utc|finished_at_utc|exit_code)' "$RUN/build.meta.txt"
oleans="$(find "$LIB/" -name '*.olean' 2>/dev/null | wc -l)"
echo "olean: $oleans / $TOTAL ($(awk -v a="$oleans" -v b="$TOTAL" 'BEGIN{printf "%.2f", 100*a/b}')%)"
if [ -f "$RUN/build.log" ]; then
  echo "log_bytes: $(stat -c %s "$RUN/build.log")"
  echo "log_built_ok: $(grep -c -E '^(✔|⚠) \[[0-9]+/[0-9]+\] Built ' "$RUN/build.log")"
  echo "log_failed: $(grep -c -E '^✖ \[[0-9]+/[0-9]+\] ' "$RUN/build.log")"
  echo "log_error_lines: $(grep -c -E '^error: ' "$RUN/build.log")"
  echo "log_last_progress: $(grep -E '^(✔|⚠|✖) \[[0-9]+/[0-9]+\] ' "$RUN/build.log" | tail -1 | cut -c1-160)"
fi
echo "lean_procs: $(pgrep -c -x lean 2>/dev/null || echo 0)"
echo "loadavg: $(cut -d' ' -f1-3 /proc/loadavg)"
free -g | awk 'NR==2{printf "mem_used_gib: %s  mem_avail_gib: %s\n", $3, $7}'
echo "setup_json_now: $(find "$ROOT/lean/.lake/build/ir/" -name '*.setup.json' 2>/dev/null | wc -l) files, $(find "$ROOT/lean/.lake/build/ir/" -name '*.setup.json' -printf '%s\n' 2>/dev/null | awk '{s+=$1} END{printf "%.1f GiB", s/1073741824}')"
echo "build_dir: $(du -sh "$ROOT/lean/.lake/build/" 2>/dev/null | cut -f1)"
df -h / /home | awk 'NR>1{printf "disk %s: avail %s (%s used)\n", $6, $4, $5}'
