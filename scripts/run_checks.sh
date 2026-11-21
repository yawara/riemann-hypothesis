#!/usr/bin/env bash
# ビルド完了後に実行する検査一式。結果は verification/results/ に保存する。
#
#   1. AxiomsCheck   … 配布物の主定理 5 件が依存する公理の一覧
#   2. StatementCheck … 検証者が Mathlib だけで書いた参照ステートメントと型が一致するか
#   3. StatementCone … 主定理の「主張」が配布プロジェクト側の定義に依存していないか
#
# いずれも Lake を介さず `lake env lean` で直接コンパイルする(検査用ファイルを配布物の
# ビルド設定に混ぜないため)。配布物のビルドと同じスレッドスタック設定を使う。
#
# 使い方: scripts/run_checks.sh
set -uo pipefail
export LC_ALL=C.UTF-8

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHK="$ROOT/verification/lean-checks"
RES="$ROOT/verification/results"
TMP="${RH_CHECK_DIR:-/var/tmp/riemann-hypothesis-ywr/checks}"
mkdir -p "$RES" "$TMP"

cd "$ROOT/lean"
BASE_PATH="$(lake env printenv LEAN_PATH)"
TSTACK="--tstack=4000000"

run() {  # run <name> <extra LEAN_PATH or empty> <lean args...>
  local name="$1" extra="$2"; shift 2
  local out="$RES/$name.out.txt"
  {
    echo "# $name"
    echo "# started_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "# lean: $(lean --version 2>&1)"
    echo "# command: lean $*"
    echo
  } > "$out"
  LEAN_PATH="$BASE_PATH${extra:+:$extra}" /usr/bin/time -f '# wall=%es user=%Us sys=%Ss maxrss=%MKB' \
    lean "$@" >> "$out" 2>&1
  local rc=$?
  echo "# exit_code: $rc" >> "$out"
  echo "# finished_at_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$out"
  echo "[$name] exit=$rc -> $out"
  return $rc
}

rc_all=0
run 01-axioms "" $TSTACK --root="$CHK" "$CHK/AxiomsCheck.lean" || rc_all=1

# 参照ステートメントは Mathlib だけを import してコンパイルし、その .olean を別ディレクトリに置く
run 02a-reference "" --root="$CHK" -o "$TMP/RHReference.olean" -i "$TMP/RHReference.ilean" "$CHK/RHReference.lean" || rc_all=1
run 02b-statement-check "$TMP" $TSTACK --root="$CHK" "$CHK/StatementCheck.lean" || rc_all=1

run 03-statement-cone "" $TSTACK --root="$CHK" "$CHK/StatementCone.lean" || rc_all=1

exit $rc_all
