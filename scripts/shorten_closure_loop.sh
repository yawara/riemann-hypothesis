#!/usr/bin/env bash
# 残す宣言の閉包を、カーネルの辺(rhshrink。scripts/shorten_analyze.sh)とソースの辺(scripts/shorten_source_closure.py)を
# 交互に回して、足す宣言が 0 になるまで求める。段階 1b では、まとめる定理の付け替え表を両方に渡す。
#
# 使い方: scripts/shorten_closure_loop.sh <名前> <起点の一覧> [merge.tsv(rhshrink 用)] [redirect.tsv(ソースの辺用)]
#   出力: $RUN_ROOT/shorten/analysis-<名前>-<k>-<時刻>/(最後のものの source-closure/kept-decls.tsv が残す宣言)
#         $RUN_ROOT/shorten/<名前>-roots-<k>.txt(各回の起点)、<名前>-loop.log
#   RH_CLOSURE_ARGS に shorten_source_closure.py への追加の引数(--drop-open-list-refs など)を渡せる
set -uo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}"
NAME="${1:?usage: shorten_closure_loop.sh <name> <roots> [merge.tsv] [redirect.tsv]}"
ROOTS="${2:?roots file}"
MERGE="${3:-}"
REDIR="${4:-}"
S="$RUN_ROOT/shorten"
LOG="$S/$NAME-loop.log"
MAIN_THMS="riemannHypothesis riemannZeta_eq_zero_re LFunction_ne_zero_of_half_lt_re LFunction_eq_zero_re LFunction_eq_zero_re_of_isPrimitive"

cur="$S/$NAME-roots-0.txt"
sort -u "$ROOTS" > "$cur"
echo "$(date -u +%FT%TZ) start: roots=$(wc -l < "$cur") merge=${MERGE:-none} redirect=${REDIR:-none} closure_args=${RH_CLOSURE_ARGS:-none}" >> "$LOG"
cd "$ROOT"
for k in 1 2 3 4 5 6 7 8 9 10; do
  if [ -n "$MERGE" ]; then
    RH_ANALYSIS_TAG="$NAME-$k" RHSHRINK_SKIP_DUPS=1 RHSHRINK_REDIRECT="$MERGE" \
      scripts/shorten_analyze.sh Main $MAIN_THMS "@$cur" > "$S/$NAME-$k-analyze.out" 2>&1
  else
    RH_ANALYSIS_TAG="$NAME-$k" RHSHRINK_SKIP_DUPS=1 \
      scripts/shorten_analyze.sh Main $MAIN_THMS "@$cur" > "$S/$NAME-$k-analyze.out" 2>&1
  fi
  D="$(ls -d "$S"/analysis-"$NAME-$k"-2* | tail -1)"
  grep -q '^exit_code: 0' "$D/meta.txt" || { echo "$(date -u +%FT%TZ) rhshrink failed: $D" >> "$LOG"; exit 1; }
  # shellcheck disable=SC2086
  nice -n 10 python3 -I scripts/shorten_source_closure.py --analysis "$D" ${REDIR:+--redirect "$REDIR"} ${RH_CLOSURE_ARGS:-} \
    > "$S/$NAME-$k-source.out" 2>&1 || { echo "$(date -u +%FT%TZ) source closure failed: $D" >> "$LOG"; exit 1; }
  added="$(grep -c . "$D/source-closure/added-roots.txt" || true)"
  live="$(python3 -c "import json; print(json.load(open('$D/source-closure/source-closure.json'))['kernel_live_decls'])")"
  echo "$(date -u +%FT%TZ) iteration $k: $D roots=$(wc -l < "$cur") kernel_live=$live added=$added" >> "$LOG"
  if [ "$added" = "0" ]; then
    echo "$(date -u +%FT%TZ) closed: $D" >> "$LOG"
    exit 0
  fi
  nxt="$S/$NAME-roots-$k.txt"
  cat "$cur" "$D/source-closure/added-roots.txt" | sort -u > "$nxt"
  cur="$nxt"
done
echo "$(date -u +%FT%TZ) not closed after 10 iterations" >> "$LOG"
exit 1
