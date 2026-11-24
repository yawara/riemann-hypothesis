#!/usr/bin/env bash
# 短縮の下調べ: 主定理の証明に実際に使われている宣言を rhshrink(shorten/tools/rhshrink)で調べる。
#
# 配布物のビルド結果(.olean)を読み込むだけで、lean/ のソースやビルド結果には書き込まない
# (検査パイプラインの最後のソース不変確認に影響しない)。パイプラインと並行して走らせるので、
# nice で優先度を下げる。出力は $RUN_ROOT/shorten/analysis-<時刻>/(中身は shorten/README.md)。
#
# 使い方: setsid scripts/shorten_analyze.sh [ルートのモジュール = Main] [起点の定理 … | @起点の一覧ファイル] &
#   RH_ANALYSIS_TAG=<名前> を付けると analysis-<名前>-<時刻>/ に出力し、latest-analysis は動かさない
#   (段階 1a の閉包の繰り返しなどで使う)。RHSHRINK_SKIP_DUPS=1 で重複の集計を省く。
set -uo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ROOT="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
TAG="${RH_ANALYSIS_TAG:-}"
OUT="$RUN_ROOT/shorten/analysis-${TAG:+$TAG-}$TS"
TC="${RH_TOOLCHAIN:-$HOME/.elan/toolchains/leanprover--lean4---v4.33.1}"
TOOL_DIR="${RH_RHSHRINK_DIR:-$ROOT/shorten/tools/rhshrink}"  # 動いている解析の実行ファイルに触らないとき、別に写した道具を使う
TOOL="$TOOL_DIR/.lake/build/bin/rhshrink"
mkdir -p "$OUT"
[ -z "$TAG" ] && ln -sfn "$OUT" "$RUN_ROOT/shorten/latest-analysis"
echo $$ > "$RUN_ROOT/shorten/analysis${TAG:+-$TAG}.pid"

( cd "$TOOL_DIR" && lake build ) > "$OUT/tool-build.log" 2>&1 || { echo "rhshrink のビルドに失敗"; cat "$OUT/tool-build.log"; exit 1; }

cd "$ROOT/lean"
# 検索パスは run_leanchecker.sh と同じ(実パスにして、プロジェクトを先頭に置く)
LP="$(lake env printenv LEAN_PATH)"
LPR="$( { echo "$LP" | tr ':' '\n' | grep -v '/packages/'; echo "$LP" | tr ':' '\n' | grep '/packages/'; } \
  | while read -r d; do [ -n "$d" ] && [ -d "$d" ] && realpath "$d"; done | paste -sd: )"
export LEAN_PATH="$LPR" LEAN_SYSROOT="$TC"

{
  echo "started_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "tool: $TOOL ($(sha256sum "$TOOL" | cut -c1-16)…)"
  echo "source: $(sha256sum "$TOOL_DIR/Main.lean" | cut -c1-16)… (shorten/tools/rhshrink/Main.lean)"
  echo "args: ${*:-(Main と主定理 5 件)}"
  echo "lean: $("$TC/bin/lean" --version 2>&1)"
} > "$OUT/meta.txt"

nice -n 10 /usr/bin/time -v -o "$OUT/time.txt" "$TOOL" "$OUT" "$@" 2> "$OUT/log.txt"
rc=$?
{
  echo "exit_code: $rc"
  echo "finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  grep -E 'Elapsed|Maximum resident' "$OUT/time.txt" | sed 's/^\s*/time: /'
} >> "$OUT/meta.txt"
# 大きな一覧は圧縮して置く
for f in decls.tsv reachable.txt; do
  [ -f "$OUT/$f" ] && nice -n 10 zstd -q -9 -T8 --rm "$OUT/$f"
done
cat "$OUT/meta.txt"
exit "$rc"
