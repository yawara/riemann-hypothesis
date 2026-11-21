import Mathlib

/-!
# 検証者による参照ステートメント(配布物から独立)

このファイルは `import Mathlib` **だけ** を行い、配布プロジェクトのモジュールを一切
import しない。したがって、配布物が定義する notation・マクロ・インスタンス等の影響を
受けない「きれいな」環境で elaborate される。

配布物の主定理の型が、ここに書いた命題と(カーネルの定義的等価性の意味で)一致するかを
`StatementCheck.lean` で確かめる。
-/

namespace RHReference

/-- リーマン予想。Mathlib の `RiemannHypothesis` を参照せず、中身を直接書き下したもの:
ζ(s) = 0 で、s が自明な零点 (-2, -4, …) でも s = 1 でもなければ Re s = 1/2。 -/
def RH : Prop :=
  ∀ s : ℂ, riemannZeta s = 0 → (¬ ∃ n : ℕ, s = -2 * ((n : ℂ) + 1)) → s ≠ 1 → s.re = 1 / 2

/-- 一般化リーマン予想(半平面形): 任意の法 N の Dirichlet 指標 χ について、
Re s > 1/2 で L(s, χ) ≠ 0(χ が自明指標のときの極 s = 1 は除く)。 -/
def GRH_halfPlane : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N) (s : ℂ),
    1 / 2 < s.re → (χ ≠ 1 ∨ s ≠ 1) → DirichletCharacter.LFunction χ s ≠ 0

/-- 一般化リーマン予想(臨界帯形): 0 < Re s < 1 にある L(s, χ) の零点は Re s = 1/2 上にある。 -/
def GRH_strip : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N) (s : ℂ),
    0 < s.re → s.re < 1 → DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2

/-- 上と同じ主張を原始指標に限ったもの。 -/
def GRH_strip_primitive : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N), χ.IsPrimitive →
    ∀ s : ℂ, 0 < s.re → s.re < 1 → DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2

/-- 自己確認: 上の `RH` は Mathlib の `RiemannHypothesis` と定義的に等しい。 -/
example : RH = RiemannHypothesis := rfl

end RHReference
