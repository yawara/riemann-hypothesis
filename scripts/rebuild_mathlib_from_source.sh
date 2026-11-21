#!/usr/bin/env bash
# Mathlib と依存ライブラリを、ビルド済みキャッシュを使わずにソースからコンパイルし直し、
# 本検証のビルドで使った .olean(公式キャッシュから取得したもの)とバイト単位で比較する。
#
# 本体のビルドでは Mathlib の .olean を公式キャッシュから取得している。主定理の「主張」は
# Mathlib の定義(riemannZeta など)で書かれているので、キャッシュの .olean が本当に
# Mathlib v4.33.1 のソースをコンパイルしたものかどうかを、ここで独立に確かめる。
#
#   * 一致すれば: キャッシュ由来の .olean は、同じツールチェーンでソースから作ったものと同一
#   * 不一致なら: どのモジュールが違うかを一覧にする(ビルドの非決定性の可能性も含め要調査)
#
# 使い方: scripts/rebuild_mathlib_from_source.sh
set -uo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
W="${RH_MATHLIB_SRC_DIR:-/var/tmp/riemann-hypothesis-ywr/mathlib-from-source}"
RUN_ROOT="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}"
OUT="$RUN_ROOT/mathlib-from-source"
REV="0df444a360eaa60ab8c11dca51a86af692955474"
mkdir -p "$W" "$OUT"

CACHED="$ROOT/lean/.lake/packages"

{
  echo "started_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "mathlib_rev: $REV"
} > "$OUT/meta.txt"

if [ ! -d "$W/mathlib4/.git" ]; then
  git clone -q https://github.com/leanprover-community/mathlib4 "$W/mathlib4"
fi
cd "$W/mathlib4"
git checkout -q -f "$REV"
[ "$(git rev-parse HEAD)" = "$REV" ] || { echo "checkout failed"; exit 1; }
echo "toolchain: $(cat lean-toolchain)" >> "$OUT/meta.txt"

# キャッシュは取得しない(`lake exe cache get` を実行しない)。依存は Mathlib 自身の
# lake-manifest.json に固定された版がソースから取得・ビルドされる。
/usr/bin/time -v -o "$OUT/build.time.txt" lake build Mathlib > "$OUT/build.log" 2>&1
rc=$?
echo "build_exit_code: $rc" >> "$OUT/meta.txt"
echo "build_finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/meta.txt"
[ "$rc" = "0" ] || { tail -20 "$OUT/build.log"; exit 1; }

# 比較: ソースからビルドした .olean と、キャッシュ由来の .olean
hash_tree() {  # hash_tree <lib dir> → "sha256  相対パス" を標準出力へ
  ( cd "$1" && find . -name '*.olean' -print0 | sort -z | xargs -0 -n 500 -P 32 sha256sum | sort -k2 )
}
: > "$OUT/compare-summary.txt"
total=0; same=0; diff=0; missing=0
for pkg in mathlib batteries aesop Qq proofwidgets importGraph LeanSearchClient plausible; do
  if [ "$pkg" = "mathlib" ]; then src_lib="$W/mathlib4/.lake/build/lib/lean"; else src_lib="$W/mathlib4/.lake/packages/$pkg/.lake/build/lib/lean"; fi
  cache_lib="$CACHED/$pkg/.lake/build/lib/lean"
  [ -d "$src_lib" ] || { echo "$pkg: source-built lib dir not found ($src_lib)" >> "$OUT/compare-summary.txt"; continue; }
  hash_tree "$src_lib" > "$OUT/$pkg.source-built.sha256"
  hash_tree "$cache_lib" > "$OUT/$pkg.cache.sha256"
  # ソースからビルドされたファイルを基準に突き合わせる(Cache.* など Mathlib 本体以外は対象外)
  join -1 2 -2 2 -a 1 -e MISSING -o '0,1.1,2.1' "$OUT/$pkg.source-built.sha256" "$OUT/$pkg.cache.sha256" > "$OUT/$pkg.joined.txt"
  t=$(wc -l < "$OUT/$pkg.joined.txt")
  s=$(awk '$2==$3' "$OUT/$pkg.joined.txt" | wc -l)
  m=$(awk '$3=="MISSING"' "$OUT/$pkg.joined.txt" | wc -l)
  d=$((t - s - m))
  awk '$2!=$3 {print $1}' "$OUT/$pkg.joined.txt" > "$OUT/$pkg.differing.txt"
  echo "$pkg: source-built=$t identical=$s different=$d missing-in-cache=$m" >> "$OUT/compare-summary.txt"
  total=$((total + t)); same=$((same + s)); diff=$((diff + d)); missing=$((missing + m))
done
echo "TOTAL: source-built=$total identical=$same different=$diff missing-in-cache=$missing" >> "$OUT/compare-summary.txt"
echo "finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/meta.txt"
cat "$OUT/meta.txt" "$OUT/compare-summary.txt"
[ "$diff" = "0" ] && [ "$missing" = "0" ]
