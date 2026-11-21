#!/usr/bin/env bash
# 配布された Lean ソース全体を、Lean を実行せずに文字列検索で調べる(ripgrep 使用)。
#
# 目的は 2 つ:
#   (a) 「証明済み」に見せかける抜け道(sorry / 独自 axiom / native_decide / カーネル検査の
#       スキップ / 環境の直接書き換え など)がソースに書かれていないか
#   (b) ビルド時に任意コードを実行しうる構文(#eval / run_cmd / IO / initialize など)が
#       どこにどれだけあるか(ビルド前の安全確認)
#
# 注意: これは補助的な検査であり、最終判断は Lean カーネルによる検査
#       (ビルド成功 + `#print axioms` + leanchecker)で行う。
#
# 使い方: scripts/static_scan.sh            # verification/static-scan/ に結果を書き出す
set -uo pipefail
export LC_ALL=C.UTF-8

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/lean/src"
OUT="$ROOT/verification/static-scan"
mkdir -p "$OUT"
SUMMARY="$OUT/summary.tsv"
HITS="$OUT/notable-hits.txt"

cd "$ROOT/lean"

printf 'category\tlabel\tfiles\tmatching_lines\tripgrep_args\n' > "$SUMMARY"
: > "$HITS"

# scan <category> <label> <rg args...>  — ファイル数と一致行数を数える
scan() {
  local cat="$1" label="$2"; shift 2
  local res
  res="$(rg -c --no-messages "$@" src | awk -F: '{f++; m+=$NF} END{printf "%d\t%d", f+0, m+0}')"
  printf '%s\t%s\t%s\t%s\n' "$cat" "$label" "$res" "$*" >> "$SUMMARY"
}
# show <label> <rg args...> — 一致行そのものを記録する(件数が少ないもの用)
show() {
  local label="$1"; shift
  { echo "=== $label  (rg $*)"; rg -n --no-messages "$@" src | cut -c1-240; echo; } >> "$HITS"
}

# ---- (a) 健全性に関わるもの ----
scan soundness 'sorry (単語)'                       -w 'sorry'
scan soundness 'sorry (大文字小文字無視・部分一致)'  -i 'sorry'
scan soundness 'admit (単語)'                       -w 'admit'
scan soundness 'axiom (単語)'                       -w 'axiom'
scan soundness 'native_decide'                      'native_decide'
scan soundness 'decide +native'                     'decide\s*\+native'
scan soundness 'ofReduceBool / reduceBool / trustCompiler' 'ofReduceBool|reduceBool|trustCompiler'
scan soundness 'implemented_by'                     'implemented_by'
scan soundness 'extern (単語)'                      -w 'extern'
scan soundness 'unsafe (単語)'                      -w 'unsafe'
scan soundness 'csimp (単語)'                       -w 'csimp'
scan soundness 'opaque (単語)'                      -w 'opaque'
scan soundness 'debug.skipKernelTC'                 'skipKernelTC'
scan soundness 'set_option debug.*'                 'set_option\s+debug'
scan soundness 'byAsSorry'                          -i 'byAsSorry'
scan soundness '#guard_msgs'                        'guard_msgs'
scan soundness 'stop (単語)'                        -w 'stop'
scan soundness 'admitGoal / elabSorry / mkSorry'    'admitGoal|elabSorry|mkSorry'
scan soundness 'axiomDecl / axiomInfo / mkAxiom'    'axiomDecl|axiomInfo|AxiomVal|mkAxiom'
scan soundness 'unsafeCast / lcProof / lcUnreachable' 'unsafeCast|lcProof|lcUnreachable|ptrAddrUnsafe'
scan soundness 'addDecl / addAndCompile'            'addDecl|addAndCompile'
scan soundness 'modifyEnv / setEnv'                 'modifyEnv|setEnv'

# ---- (b) メタプログラミング・ビルド時コード実行 ----
scan meta 'run_cmd'                                 'run_cmd'
scan meta 'run_elab / run_meta'                     'run_elab|run_meta'
scan meta '#eval'                                   '#eval'
scan meta '#exit'                                   '#exit'
scan meta 'initialize / builtin_initialize'         -w 'initialize|builtin_initialize'
scan meta 'elab / elab_rules'                       -w 'elab|elab_rules'
scan meta 'macro / macro_rules'                     -w 'macro|macro_rules'
scan meta 'syntax / declare_syntax_cat'             -w 'syntax|declare_syntax_cat'
scan meta 'notation 類(local/scoped 含む)'          -w 'notation|notation3|infix|infixl|infixr|prefix|postfix'
scan meta 'notation 類(行頭 = 大域)'               '^\s*(notation3?|infix|infixl|infixr|prefix|postfix)\b'
scan meta 'IO.Process / IO.FS / System / socket'    'IO\.(Process|FS|getEnv|println|eprintln|mkRef|sleep|appPath)|\bSocket\b|\bcurl\b|\bwget\b'
scan meta 'import Lean*'                            '^import Lean'
scan meta 'open Lean'                               'open Lean'
scan meta 'partial (単語)'                          -w 'partial'
scan meta '#print / #check'                         '#print|#check'
scan meta 'prelude / module 宣言'                   '^(prelude|module)\s*$'

# ---- (c) 参考: 規模の目安 ----
scan info 'import Mathlib(全体 import の行)'       '^import Mathlib$'
scan info 'set_option maxHeartbeats'                'set_option\s+maxHeartbeats'
scan info 'attribute [local instance] 等'           'local instance|attribute \[local instance|attribute \[-instance'
scan info 'noncomputable (単語)'                    -w 'noncomputable'
scan info 'theorem / lemma(行頭)'                  '^\s*(@\[[^\]]*\]\s*)?((private|protected|nonrec|noncomputable)\s+)*(theorem|lemma)\s'
scan info 'def / abbrev / instance / structure / class / inductive(行頭)' '^\s*(@\[[^\]]*\]\s*)?((private|protected|nonrec|noncomputable|scoped|local)\s+)*(def|abbrev|instance|structure|class|inductive)\s'

# ---- 件数が少なく、人間が読むべきもの ----
show 'addDecl / addAndCompile'       'addDecl|addAndCompile'
show 'modifyEnv / setEnv'            'modifyEnv|setEnv'
show 'run_cmd'                       'run_cmd'
show 'elab / elab_rules'             -w 'elab|elab_rules'
show 'import Lean*'                  '^import Lean'
show 'open Lean'                     'open Lean'
show 'partial'                       -w 'partial'
show '#print / #check'               '#print|#check'
show 'stop (単語)'                   -w 'stop'
show 'macro / macro_rules(全件)'    -w 'macro|macro_rules'

# ---- set_option の全種類 ----
rg --no-messages -N --no-filename -o 'set_option\s+[A-Za-z_][A-Za-z0-9_.]*' src \
  | awk '{print $2}' | sort | uniq -c | sort -rn > "$OUT/set-option-names.txt"

# ---- notation 類の種別 ----
rg --no-messages -N --no-filename -o -w '(local |scoped |scoped\[[^\]]*\] )?(notation3?|infix|infixl|infixr|prefix|postfix)' src \
  | sort | uniq -c | sort -rn > "$OUT/notation-kinds.txt"

echo "ripgrep: $(rg --version | head -1)" > "$OUT/tool-version.txt"
date -u +"scanned_at_utc: %Y-%m-%dT%H:%M:%SZ" >> "$OUT/tool-version.txt"

column -t -s $'\t' "$SUMMARY" | cut -c1-150
