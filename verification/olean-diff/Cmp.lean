/-
  2 つの .olean(モジュールシステムの 3 つの部分 .olean・.olean.server・.olean.private)を宣言ごとに読み比べる。
  Mathlib をソースから作り直した結果と公式キャッシュが違ったモジュールの、違いの中身を調べるのに使った
  (verification/results/08-mathlib-from-source/)。

  使い方: lean --run Cmp.lean <片方の拡張子なしのパス> <もう片方の拡張子なしのパス>
  出力: 部分ごとに、定数の数、import・定数名の並びが同じか、型・値が違う定数の名前(10 個まで)、
        拡張の項目数の違い
-/
import Lean
open Lean

def cmpData (a _b : System.FilePath) (ma mb : ModuleData) : IO Unit := do
  IO.println s!"== {a.fileName.getD ""}: constants {ma.constants.size} vs {mb.constants.size}, constNames {ma.constNames.size} vs {mb.constNames.size}, extraConstNames {ma.extraConstNames.size} vs {mb.extraConstNames.size}"
  IO.println s!"   imports equal: {ma.imports == mb.imports}; constNames equal (same order): {ma.constNames == mb.constNames}; extraConstNames equal: {ma.extraConstNames == mb.extraConstNames}"
  let mut mapB : Std.HashMap Name ConstantInfo := {}
  for c in mb.constants do
    mapB := mapB.insert c.name c
  let mut onlyA := 0
  let mut tyDiff := 0
  let mut valDiff := 0
  let mut kindDiff := 0
  for c in ma.constants do
    match mapB[c.name]? with
    | none =>
      onlyA := onlyA + 1
      if onlyA ≤ 10 then IO.println s!"   only in source-built: {c.name}"
    | some d =>
      if c.type != d.type then
        tyDiff := tyDiff + 1
        if tyDiff ≤ 10 then
          IO.println s!"   type differs: {c.name}"
          IO.println s!"     source-built: {c.type}"
          IO.println s!"     cache:        {d.type}"
      if (c.value? (allowOpaque := true)) != (d.value? (allowOpaque := true)) then
        valDiff := valDiff + 1
        if valDiff ≤ 10 then IO.println s!"   value differs: {c.name}"
      if c.isTheorem != d.isTheorem || c.isDefinition != d.isDefinition || c.levelParams != d.levelParams then
        kindDiff := kindDiff + 1
        if kindDiff ≤ 10 then IO.println s!"   kind/levelParams differ: {c.name}"
  let namesA : NameSet := ma.constants.foldl (fun s c => s.insert c.name) {}
  let mut onlyB := 0
  for c in mb.constants do
    unless namesA.contains c.name do
      onlyB := onlyB + 1
      if onlyB ≤ 10 then IO.println s!"   only in cache: {c.name}"
  IO.println s!"   only-in-source-built {onlyA}, only-in-cache {onlyB}, type differs {tyDiff}, value differs {valDiff}, kind differs {kindDiff}"
  -- environment extension entries: compare names and counts
  let mut entB : Std.HashMap Name Nat := {}
  for (n, es) in mb.entries do
    entB := entB.insert n es.size
  for (n, es) in ma.entries do
    let nb := entB.getD n 0
    if es.size != nb then IO.println s!"   ext {n}: {es.size} vs {nb} entries"
  IO.println s!"   extensions: {ma.entries.size} vs {mb.entries.size}"

def main (args : List String) : IO Unit := do
  match args with
  | [a, b] =>
    let exts := #["olean", "olean.server", "olean.private"]
    let pa ← readModuleDataParts (exts.map fun e => System.FilePath.mk (a ++ "." ++ e))
    let pb ← readModuleDataParts (exts.map fun e => System.FilePath.mk (b ++ "." ++ e))
    for ((e, x), y) in (exts.zip pa).zip pb do
      cmpData (System.FilePath.mk (a ++ "." ++ e)) (System.FilePath.mk (b ++ "." ++ e)) x.1 y.1
  | _ => IO.println "usage: Cmp <source-built base> <cache base>"
