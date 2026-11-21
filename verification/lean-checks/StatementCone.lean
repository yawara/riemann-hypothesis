import Main

/-!
# 主定理の「主張」が何に依存しているかの機械的な確認

定理の **型(= 主張)** に現れる定数を、定義の中身まで推移的に辿って集め、それぞれが
どのモジュールで定義されているかを調べる。

* 定義 (`def`) は型と値の両方を辿る(値が主張の意味を決めるため)
* 定理 (`theorem`) は型だけを辿る(証明は主張の意味に影響しない)
* 帰納型はコンストラクタも辿る

`riemannHypothesis` の主張が配布プロジェクト側のモジュールで定義された定数に一切
依存していなければ、「主張は Mathlib(と Lean 本体)の定義だけで書かれている」ことが
機械的に確認できる。配布物が notation やマクロで `RiemannHypothesis` 等の識別子を
すり替えていた場合、ここでプロジェクト側の定数が現れる。
-/

open Lean

namespace RHVerify

/-- 配布プロジェクトのトップレベル名前空間(モジュール名の先頭要素)。 -/
def projectRoots : List Name :=
  [`BuildAid, `CompanionTheory, `Development, `Formalism, `GroundTheory, `Lemmata,
   `PositivityTheory, `ReciprocityTheory, `Supplements, `Main, `Statements]

partial def cone (env : Environment) (stack : Array Name) (seen : NameSet) : NameSet :=
  if h : 0 < stack.size then
    let n := stack[stack.size - 1]
    let stack := stack.pop
    if seen.contains n then cone env stack seen else
    let seen := seen.insert n
    match env.find? n with
    | none => cone env stack seen
    | some ci =>
      let used := ci.type.getUsedConstants
      let used := match ci with
        | .defnInfo d => used ++ d.value.getUsedConstants
        | .opaqueInfo o => used ++ o.value.getUsedConstants
        | .inductInfo i => used ++ i.ctors.toArray
        | _ => used
      cone env (used.foldl (fun s u => if seen.contains u then s else s.push u) stack) seen
  else seen

def moduleOf (env : Environment) (n : Name) : Name :=
  match env.getModuleIdxFor? n with
  | some idx => env.header.moduleNames[idx.toNat]!
  | none => `«(current file)»

def report (thm : Name) : CoreM Unit := do
  let env ← getEnv
  let some ci := env.find? thm | throwError "not found: {thm}"
  let s := cone env ci.type.getUsedConstants {}
  let mut byRoot : Std.HashMap Name Nat := {}
  let mut fromProject : Array (Name × Name) := #[]
  for n in s do
    let m := moduleOf env n
    let r := m.getRoot
    byRoot := byRoot.insert r (byRoot.getD r 0 + 1)
    if projectRoots.contains r then fromProject := fromProject.push (n, m)
  let roots := byRoot.toArray.qsort (fun a b => a.1.toString < b.1.toString)
  logInfo m!"[{thm}]\n  defined in module: {moduleOf env thm}\n  type: {ci.type}\n  statement cone: {s.size} constants\n  by module root: {roots}\n  constants defined in the distributed project: {fromProject}"

run_cmd Lean.Elab.Command.liftCoreM do
  let env ← getEnv
  logInfo m!"RiemannHypothesis is defined in module: {moduleOf env ``RiemannHypothesis}"
  logInfo m!"riemannZeta is defined in module: {moduleOf env ``riemannZeta}"
  logInfo m!"DirichletCharacter.LFunction is defined in module: {moduleOf env ``DirichletCharacter.LFunction}"
  logInfo m!"number of imported modules: {env.header.moduleNames.size}"
  for thm in [`riemannHypothesis, `riemannZeta_eq_zero_re, `LFunction_ne_zero_of_half_lt_re,
              `LFunction_eq_zero_re, `LFunction_eq_zero_re_of_isPrimitive] do
    report thm

end RHVerify

set_option pp.fullNames true in
#print RiemannHypothesis
