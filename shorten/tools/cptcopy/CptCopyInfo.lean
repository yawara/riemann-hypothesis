import Lean
import Formalism.HermitianCurvature.HermitianCurvatureProofs.CutCptCopy
open Lean Formalism.FourierDecayAlt.P.CptCopy

/-!
# 配布物の自作コマンド `cpt_copy_thms` が作る写しを調べる

`cpt_copy_thms`(`Formalism.HermitianCurvature.HermitianCurvatureProofs.CutCptCopy` で定義し、
`…CutMainCpt` の末尾で実行)は、根の定理(`roots`)から依存を辿り、`manual`・`special` の定数に
依存する宣言(tainted)ごとに、名前に `Cpt` を付けた写しを、定数を置き換えた項で環境に足す。
写しはカーネルの項の外で作られるので、写しが使われていても、写しの元の宣言は「使われていない」と
判定される。元を消すと写しが作られなくなる(段階 1a の 2 回目の全体ビルドで `…FinalS` が失敗した原因)。

配布物のビルド結果を読むだけ。根ごとに、写しの元と写しの名前・モジュール、辿った宣言を出す。

    COPY  根  元  写し  写しのモジュール  元のモジュール
    SEEN  根  辿った宣言  モジュール

使い方(配布物のビルド結果を LEAN_PATH に入れて):
    lean +leanprover/lean4:v4.33.1 --run shorten/tools/cptcopy/CptCopyInfo.lean
-/

def modOf (env : Environment) (c : Name) : String :=
  match env.getModuleIdxFor? c with
  | some i => env.header.moduleNames[i.toNat]!.toString
  | none => "?"

def main : IO Unit := do
  initSearchPath (← findSysroot)
  let env ← importModules #[{ module := `Formalism.HermitianCurvature.HermitianCurvatureProofs.CutMainCpt }] {} 0
    (loadExts := false)
  let (tainted, order) := toCopy env
  IO.println s!"INFO\ttainted={tainted.toList.length}\torder={order.size}"
  for r in roots do
    let (s, t, o) := go env r ({}, {}, #[])
    for n in o do
      let n' := mapName t n
      IO.println s!"COPY\t{r}\t{n}\t{n'}\t{modOf env n'}\t{modOf env n}"
    -- 根から辿った宣言すべて(消したり、中の参照を書き換えたりすると、写しの作られ方が変わる)
    for n in s.toList do
      IO.println s!"SEEN\t{r}\t{n}\t{modOf env n}"
