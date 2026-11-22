#!/usr/bin/env bash
# 短縮版のビルドを、検証の常駐プロセスより後回しにするためのメモリの見張り。
# 空きメモリ(MemAvailable)が下限を切ったら、短縮版のビルド(shorten_build_stage.sh のプロセスグループ)を止める。
# 止めたビルドは、空きが戻ってから同じコマンドで再開すればよい(Lake は済んだモジュールを再利用する)。
#
# 使い方: setsid scripts/shorten_memguard.sh <shorten_build_stage.sh の PID> [下限 GiB = 80] [間隔秒 = 30] &
set -u
PID="${1:?usage: shorten_memguard.sh <build-pid> [min-GiB] [interval]}"
MIN_GIB="${2:-80}"
INTERVAL="${3:-30}"
LOG="/var/tmp/riemann-hypothesis-ywr/shorten/memguard.log"
PGID="$(ps -o pgid= -p "$PID" | tr -d ' ')"
echo "$(date -u +%FT%TZ) start: build pid=$PID pgid=$PGID min=${MIN_GIB}GiB" >> "$LOG"
while kill -0 "$PID" 2>/dev/null; do
  avail_kb="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  if [ "$avail_kb" -lt $((MIN_GIB * 1024 * 1024)) ]; then
    echo "$(date -u +%FT%TZ) MemAvailable $((avail_kb / 1024 / 1024))GiB < ${MIN_GIB}GiB: stopping build pgid=$PGID" >> "$LOG"
    kill -TERM -- "-$PGID" 2>/dev/null
    sleep 20
    kill -KILL -- "-$PGID" 2>/dev/null
    exit 0
  fi
  sleep "$INTERVAL"
done
echo "$(date -u +%FT%TZ) build finished; guard exits" >> "$LOG"
