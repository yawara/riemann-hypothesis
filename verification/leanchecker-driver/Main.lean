import Lean.CoreM
import Lean.Replay

/-!
# rhcheck: leanchecker と同じ再生処理を、モジュール名の一覧に対して直接実行する

Lean 4.33.1 同梱の leanchecker(`src/lean/LeanChecker.lean`)は、引数の名前 1 つごとに検索パス全体
(約 18.6 万個の .olean)を走査し直して、前方一致するモジュールを探す。17.5 万個のモジュールを指定すると、
名前の解決だけで何日もかかる。

このプログラムは、leanchecker の `replayFromImports` を一字一句そのまま写し、名前の解決だけを省いて、
一覧ファイルに書かれたモジュール名(完全一致)を 1 つずつ順に再生する。再生の中身(各モジュールの宣言を、
そのモジュールの import だけを読み込んだ環境へ、カーネルを通して追加し直す)は leanchecker と同じ。
leanchecker を LEAN_NUM_THREADS=1 で動かしたときと同じく、モジュールは 1 つずつ処理する。

使い方: rhcheck <モジュール名の一覧ファイル>
出力: モジュールごとに `replaying M` のあと `ok M`(または `FAILED M: …`)。1 つでも失敗すれば終了コード 1。
-/

open Lean

-- ここから、LeanChecker.lean(Lean 4.33.1)の replayFromImports をそのまま写したもの
unsafe def replayFromImports (module : Name) : IO Unit := do
  let mFile ← findOLean module
  unless (← mFile.pathExists) do
    throw <| IO.userError s!"object file '{mFile}' of module {module} does not exist"
  -- Load all module data parts (exported, server, private)
  let mut fnames := #[mFile]
  let sFile := OLeanLevel.server.adjustFileName mFile
  if (← sFile.pathExists) then
    fnames := fnames.push sFile
    let pFile := OLeanLevel.private.adjustFileName mFile
    if (← pFile.pathExists) then
      fnames := fnames.push pFile
  let parts ← readModuleDataParts fnames
  if h : parts.size = 0 then throw <| IO.userError "failed to read module data" else
  let (mod, _) := parts[0]
  let (_, s) ← importModulesCore mod.imports |>.run
  let env ← finalizeImport s mod.imports {} 0 false false (isModule := true)
  let mut newConstants := {}
  -- Collect constants from last ("most private") part, which subsumes all prior ones
  for name in parts[parts.size-1].1.constNames, ci in parts[parts.size-1].1.constants do
    newConstants := newConstants.insert name ci
  let env' ← env.replay newConstants
  env'.freeRegions
-- ここまで

unsafe def main (args : List String) : IO UInt32 := do
  initSearchPath (← findSysroot)
  let some file := args.head? | throw <| IO.userError "usage: rhcheck <modules-file>"
  let mods := (← IO.FS.lines file).toList.filter (fun l => !l.isEmpty) |>.map String.toName
  let out ← IO.getStdout
  let mut failed := 0
  for m in mods do
    out.putStrLn s!"replaying {m}"
    out.flush
    try
      replayFromImports m
      out.putStrLn s!"ok {m}"
    catch e =>
      failed := failed + 1
      out.putStrLn s!"FAILED {m}: {e}"
    out.flush
  out.putStrLn s!"done: {mods.length} modules, {failed} failed"
  out.flush
  return if failed == 0 then 0 else 1
