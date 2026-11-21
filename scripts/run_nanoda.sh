#!/usr/bin/env bash
# 主定理とその依存(定義・定理・公理のすべて)を lean4export で書き出し、
# Rust 製の独立カーネル nanoda で検査する。
#
#   1. lean4export Main -- <主定理 5 件>   … 主定理が推移的に依存する全宣言を NDJSON に出力
#   2. nanoda_bin                          … その全宣言を Lean 本体とは別実装で型検査
#
# 許可する公理は propext / Classical.choice / Quot.sound の 3 つだけ。
# それ以外の公理に依存する宣言があれば nanoda はエラーで止まる
# ("unpermitted_axiom_hard_error": false は「使われていない公理宣言は無視する」設定で、
#  使われた場合はエラーになる)。
#
# 出力は巨大になりうるので zstd で圧縮して保存し、nanoda には標準入力で流し込む。
#
# 使い方: THREADS=64 scripts/run_nanoda.sh
set -uo pipefail
export LC_ALL=C.UTF-8

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="${RH_TOOLS:-/var/tmp/riemann-hypothesis-ywr/tools}"
RUN_ROOT="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$RUN_ROOT/nanoda-$TS"
THREADS="${THREADS:-64}"
mkdir -p "$OUT"
ln -sfn "$OUT" "$RUN_ROOT/latest-nanoda"

THEOREMS=(riemannHypothesis riemannZeta_eq_zero_re LFunction_ne_zero_of_half_lt_re
          LFunction_eq_zero_re LFunction_eq_zero_re_of_isPrimitive)

cd "$ROOT/lean"

{
  echo "started_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "lean4export: $(git -C "$TOOLS/lean4export" rev-parse HEAD)"
  echo "nanoda_lib: $(git -C "$TOOLS/nanoda_lib" rev-parse HEAD)"
  echo "theorems: ${THEOREMS[*]}"
  echo "threads: $THREADS"
} > "$OUT/meta.txt"

echo "[1/2] export"
/usr/bin/time -v -o "$OUT/export.time.txt" \
  lake env "$TOOLS/lean4export/.lake/build/bin/lean4export" Main -- "${THEOREMS[@]}" 2> "$OUT/export.stderr.txt" \
  | tee >(wc -c > "$OUT/export.bytes") >(wc -l > "$OUT/export.lines") \
  | zstd -T16 -3 -q -o "$OUT/export.ndjson.zst"
rc_export=${PIPESTATUS[0]}
echo "export_exit_code: $rc_export" >> "$OUT/meta.txt"
echo "export_finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUT/meta.txt"
[ "$rc_export" = "0" ] || { echo "export failed"; tail -5 "$OUT/export.stderr.txt"; exit 1; }

cat > "$OUT/config.json" <<EOF
{
  "use_stdin": true,
  "num_threads": $THREADS,
  "stack_size_bytes": 4294967296,
  "permitted_axioms": ["propext", "Classical.choice", "Quot.sound"],
  "unpermitted_axiom_hard_error": false,
  "nat_extension": true,
  "string_extension": true,
  "pp_declars": ["riemannHypothesis", "RiemannHypothesis", "riemannZeta_eq_zero_re",
                 "LFunction_ne_zero_of_half_lt_re", "LFunction_eq_zero_re",
                 "LFunction_eq_zero_re_of_isPrimitive",
                 "RiemannZetaZerosOnLine", "DirichletLNonvanishingRightOfHalf",
                 "DirichletLZerosOnLine", "PrimitiveDirichletLZerosOnLine"],
  "pp_to_stdout": true,
  "print_success_message": true
}
EOF

echo "[2/2] nanoda"
zstd -dc "$OUT/export.ndjson.zst" \
  | /usr/bin/time -v -o "$OUT/nanoda.time.txt" "$TOOLS/nanoda_lib/target/release/nanoda_bin" "$OUT/config.json" \
      > "$OUT/nanoda.out.txt" 2> "$OUT/nanoda.stderr.txt"
rc=${PIPESTATUS[1]}
{
  echo "nanoda_exit_code: $rc"
  echo "finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "export_bytes: $(cat "$OUT/export.bytes")"
  echo "export_lines: $(cat "$OUT/export.lines")"
} >> "$OUT/meta.txt"
cat "$OUT/meta.txt"
tail -5 "$OUT/nanoda.out.txt"
exit "$rc"
