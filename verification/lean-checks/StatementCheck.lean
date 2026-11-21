import RHReference
import Main

/-!
# 主定理の型が参照ステートメントと一致することの確認

`RHReference`(Mathlib のみを import したファイル)で定義した命題を、配布物の主定理で
そのまま証明できるか(= 型が定義的に等しいか)を Lean のカーネルに判定させる。
続けて、ここで得た定理が依存する公理を表示する。
-/

theorem check_RH : RHReference.RH := riemannHypothesis

theorem check_RH_mathlib : RiemannHypothesis := riemannHypothesis

theorem check_RH_statements : RHReference.RH := riemannZeta_eq_zero_re

theorem check_GRH_halfPlane : RHReference.GRH_halfPlane := LFunction_ne_zero_of_half_lt_re

theorem check_GRH_strip : RHReference.GRH_strip := LFunction_eq_zero_re

theorem check_GRH_strip_primitive : RHReference.GRH_strip_primitive :=
  LFunction_eq_zero_re_of_isPrimitive

#print axioms check_RH
#print axioms check_RH_mathlib
#print axioms check_RH_statements
#print axioms check_GRH_halfPlane
#print axioms check_GRH_strip
#print axioms check_GRH_strip_primitive
