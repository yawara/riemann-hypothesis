#!/usr/bin/env bash
# 書き換えたモジュールを、ビルド済みの短縮版の環境(.olean)で 1 つずつコンパイルして試す。
# 全体をビルドし直す前に、書き換えが通るかを安く確かめるためのもの(import 先の .olean は環境の短縮版のものを使う。
# 段階 1b なら、消した定理はまだ環境に残っているが、書き換えたモジュールはそれを参照しないので確かめられる)。
# オプションは lean/lakefile.toml と同じ(--tstack、leanOptions)。
#
# 使い方: JOBS=32 scripts/shorten_try_compile.sh <環境の短縮版のディレクトリ> <試すソースの src> <モジュールの一覧> <出力ディレクトリ>
#   出力: <出力ディレクトリ>/rc.tsv(終了コード・秒・モジュール)、logs/<モジュール>.log
set -uo pipefail
export LC_ALL=C.UTF-8
ENV_STAGE="$(realpath "${1:?usage}")"
SRC="$(realpath "${2:?usage}")"
LIST="${3:?usage}"
OUT="${4:?usage}"
JOBS="${JOBS:-32}"
TC="${RH_TOOLCHAIN:-$HOME/.elan/toolchains/leanprover--lean4---v4.33.1}"
mkdir -p "$OUT/logs"
LP="$ENV_STAGE/.lake/build/lib/lean"
for p in "$ENV_STAGE"/.lake/packages/*/.lake/build/lib/lean; do LP="$LP:$p"; done
export LEAN_PATH="$LP" LEAN_SYSROOT="$TC" LEAN_NUM_THREADS=1 TC SRC OUT
: > "$OUT/rc.tsv"
xargs -P "$JOBS" -I{} sh -c '
  m="{}"; f="$SRC/$(echo "$m" | tr . /).lean"; s=$(date +%s)
  nice -n 10 timeout 3600 "$TC/bin/lean" --tstack=400000 -DautoImplicit=false -DrelaxedAutoImplicit=false \
    -DmaxSynthPendingDepth=3 -Dpp.unicode.fun=true -DmaxHeartbeats=4000000 "$f" > "$OUT/logs/$m.log" 2>&1
  rc=$?
  printf "%s\t%s\t%s\n" "$rc" "$(( $(date +%s) - s ))" "$m" >> "$OUT/rc.tsv"
' < "$LIST"
awk -F'\t' '{n++; if ($1 != 0) f++} END {printf "tried %d, failed %d\n", n, f}' "$OUT/rc.tsv"
