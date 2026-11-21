import Main

/-!
# 主定理が依存する公理の表示

配布物 `Main.lean` の 5 定理について、証明が(推移的に)依存する公理を Lean に列挙させる。
Lean 4 + Mathlib の標準は `propext`, `Classical.choice`, `Quot.sound` の 3 つ。
`sorryAx`(= sorry)、`Lean.ofReduceBool` / `Lean.trustCompiler`(= native_decide)、
その他の独自公理が出れば、その定理は「無条件に証明された」とは言えない。
-/

#print axioms riemannHypothesis
#print axioms riemannZeta_eq_zero_re
#print axioms LFunction_ne_zero_of_half_lt_re
#print axioms LFunction_eq_zero_re
#print axioms LFunction_eq_zero_re_of_isPrimitive
