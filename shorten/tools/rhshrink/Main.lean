import Lean

/-!
# rhshrink: 主定理の証明に実際に使われている宣言を調べる(短縮の下調べ)

配布物の環境(既定では `import Main`)を読み込み、次を書き出す。

1. 到達可能性: 主定理 5 件から、型と値(証明項)に現れる定数を推移的に辿る。
   配布物の外(Mathlib・Batteries・Lean 本体)の定数は記録だけして、その先は辿らない
   (外のライブラリから配布物の定数へ戻ることはないため)。
2. 宣言ごとの生死: 配布物の各モジュールの宣言(ソース上の行範囲つき)を、
   - live: 宣言の定数そのものが到達可能
   - aux : 宣言の定数は到達不能だが、その補助定数(`foo.match_1` など)だけが別の宣言から使われている
   - dead: どれも到達不能
   に分ける。補助定数(`foo._proof_1`、`Foo.rec` など)は、名前の末尾を削って行範囲のある宣言に帰属させる。
3. 重複: 到達可能な配布物の定理のうち、型(宇宙レベルとメタデータを消したもの)が α 同値なものの組。
   定義は型と値の両方が α 同値なものの組。
4. 外部との一致: 到達可能な配布物の定理のうち、配布物の外に同じ型(同じ正規化)の定理があるもの。
5. 別名: 値が「ラムダの列のあとに定数を適用しただけ」の定理・定義。

これはカーネルの項の上での解析で、エラボレーションにだけ使われるもの(notation・マクロ・
証明項に痕跡を残さない `dsimp` 用の rfl 補題など)は数えない。実際に消せるかどうかは、
消したソースを再ビルドして確かめる。

使い方: rhshrink <出力ディレクトリ> [ルートのモジュール = Main] [起点の定理 ...]
(LEAN_PATH は配布物の `lake env` のものを渡す。)
-/

open Lean

namespace RHShrink

/-- 配布プロジェクトのモジュール名の先頭要素 -/
def projectRoots : Array Name :=
  #[`BuildAid, `CompanionTheory, `Development, `Formalism, `GroundTheory, `Lemmata,
    `PositivityTheory, `ReciprocityTheory, `Supplements, `Main, `Statements]

def mainTheorems : Array Name :=
  #[`riemannHypothesis, `riemannZeta_eq_zero_re, `LFunction_ne_zero_of_half_lt_re,
    `LFunction_eq_zero_re, `LFunction_eq_zero_re_of_isPrimitive]

def kindOf : ConstantInfo → String
  | .axiomInfo _ => "axiom"
  | .defnInfo _ => "def"
  | .thmInfo _ => "theorem"
  | .opaqueInfo _ => "opaque"
  | .quotInfo _ => "quot"
  | .inductInfo _ => "inductive"
  | .ctorInfo _ => "ctor"
  | .recInfo _ => "rec"

/-- 定数 `ci` をカーネルに追加するとき、先に環境にあるべき定数(型と値に現れるもの、帰納型の組) -/
def edges (ci : ConstantInfo) : Array Name :=
  let a := ci.type.getUsedConstants
  match ci with
  | .defnInfo v => a ++ v.value.getUsedConstants
  | .thmInfo v => a ++ v.value.getUsedConstants
  | .opaqueInfo v => a ++ v.value.getUsedConstants
  | .inductInfo v => a ++ v.ctors.toArray ++ v.all.toArray
  | .ctorInfo v => a.push v.induct
  | .recInfo v => v.rules.foldl (fun acc r => acc ++ r.rhs.getUsedConstants) (a ++ v.all.toArray)
  | _ => a

/-- 比較用の正規化: 宇宙レベルとメタデータを消す(束縛変数名・束縛の種類は `Expr` の `==` が無視する) -/
partial def norm (e : Expr) : Expr :=
  e.replace fun
    | .sort _ => some (.sort .zero)
    | .const n _ => some (.const n [])
    | .mdata _ b => some (norm b)
    | _ => none

partial def stripLams : Expr → Expr
  | .lam _ _ b _ => stripLams b
  | .mdata _ b => stripLams b
  | e => e

/-- メタデータを消す -/
partial def stripMData (e : Expr) : Expr :=
  e.replace fun
    | .mdata _ b => some (stripMData b)
    | _ => none

/-- 型の先頭の ∀ の並び(→ を含む)の、束縛の種類(d 明示・i 暗黙・s 強い暗黙・I instance)と束縛変数の名前 -/
partial def binderSig : Expr → String × String
  | .forallE n _ b bi =>
    let c := match bi with
      | .default => "d"
      | .implicit => "i"
      | .strictImplicit => "s"
      | .instImplicit => "I"
    let (is, ns) := binderSig b
    (c ++ is, n.toString ++ " " ++ ns)
  | .mdata _ b => binderSig b
  | _ => ("", "")

/-- 段階 1b 用の厳しい比較の鍵: 宇宙変数を位置で付け替えた型(メタデータだけ消す。`Expr` の `==` は束縛変数名と
    束縛の種類を無視するので、束縛の種類の並びと宇宙変数の数を別に持つ)。この鍵が同じ定理どうしは、ソース上の参照を
    付け替えても同じように引数が渡る(名前つき引数を除く) -/
def strictKey (lps : List Name) (ty : Expr) : Expr × String :=
  let canon := (List.range lps.length).map fun i => Level.param (Name.mkSimple s!"u_{i}")
  let t := stripMData (ty.instantiateLevelParams lps canon)
  (t, s!"{(binderSig t).1}|{lps.length}")

/-- 値が「ラムダの列のあとに定数を適用しただけ」なら (定数, 引数の数, 束縛変数でない引数の数) -/
def aliasTarget? (v : Expr) : Option (Name × Nat × Nat) :=
  let body := stripLams v
  match body.getAppFn.consumeMData with
  | .const c _ =>
    let args := body.getAppArgs
    some (c, args.size, (args.filter fun a => !a.consumeMData.isBVar).size)
  | _ => none

/-- 行範囲のある宣言への帰属: 名前の末尾を削りながら探す -/
partial def owner (rng : Std.HashMap Name (Nat × Nat)) (n : Name) : Option Name :=
  if rng.contains n then some n else
  match n with
  | .str p _ => owner rng p
  | .num p _ => owner rng p
  | .anonymous => none

def countTrue (a : Array Bool) : Nat := a.foldl (fun k b => if b then k + 1 else k) 0

/-- `Name.toString` で書き出した名前を読み戻す(`«…»` の中の `.` と、数字だけの成分 = `Name.num` を扱う) -/
def parseName (s : String) : Name := Id.run do
  let mut comps : Array (String × Bool) := #[]  -- (成分, «» で囲まれていたか)
  let mut cur := ""
  let mut quoted := false
  let mut wasQuoted := false
  for c in s.toList do
    if quoted then
      if c == '»' then quoted := false else cur := cur.push c
    else if c == '«' then
      quoted := true
      wasQuoted := true
    else if c == '.' then
      comps := comps.push (cur, wasQuoted)
      cur := ""
      wasQuoted := false
    else
      cur := cur.push c
  comps := comps.push (cur, wasQuoted)
  let mut n := Name.anonymous
  for (c, q) in comps do
    if !q && !c.isEmpty && c.all Char.isDigit then n := Name.mkNum n c.toNat!
    else n := Name.mkStr n c
  return n

end RHShrink

open RHShrink

def main (args : List String) : IO UInt32 := do
  let t0 ← IO.monoMsNow
  let log (s : String) : IO Unit := do
    let t ← IO.monoMsNow
    IO.eprintln s!"[{(t - t0) / 1000}s] {s}"
  let some (outStr : String) := args[0]?
    | throw <| IO.userError "usage: rhshrink <outdir> [root-module] [theorem ...]"
  let out : System.FilePath := ⟨outStr⟩
  IO.FS.createDirAll out
  let rootMod := (args[1]?.getD "Main").toName
  -- 起点: 引数の名前。`@ファイル` はファイルの各行を起点にする
  let mut roots : Array Name := #[]
  for a in args.drop 2 do
    if a.startsWith "@" then
      for l in (← IO.FS.lines ⟨a.drop 1 |>.toString⟩) do
        unless l.isEmpty do roots := roots.push (parseName l)
    else
      roots := roots.push (parseName a)
  if roots.isEmpty then roots := mainTheorems
  let skipDups := (← IO.getEnv "RHSHRINK_SKIP_DUPS").isSome
  initSearchPath (← findSysroot)
  log s!"import {rootMod}"
  let env ← importModules #[{ module := rootMod }] {} (trustLevel := 1024)
  let names := env.header.moduleNames
  let mods := env.header.moduleData
  let nMods := names.size
  let isProj : Array Bool := names.map fun m => projectRoots.contains m.getRoot
  log s!"imported {nMods} modules ({countTrue isProj} project)"
  let modOf? (n : Name) : Option Nat := (env.getModuleIdxFor? n).map (·.toNat)
  let isProjConst (n : Name) : Bool :=
    match modOf? n with
    | some i => isProj[i]!
    | none => false

  -- 1. 到達可能性(主定理が見つからなければ止める。追加の起点で定数でないものは数えて飛ばす)
  for r in mainTheorems do
    if roots.contains r then
      unless (env.find? r).isSome do throw <| IO.userError s!"not found: {r}"
  let missingRoots := roots.filter fun r => !(env.find? r).isSome
  unless missingRoots.isEmpty do
    log s!"{missingRoots.size} roots are not constants (skipped), e.g. {missingRoots.extract 0 3}"
  roots := roots.filter fun r => (env.find? r).isSome
  -- 段階 1b: RHSHRINK_REDIRECT=<ファイル>(1 行に「消す定理\t残す定理」)があれば、辿るときに参照を付け替える
  -- (消す定理は、起点でない限り辿られず dead になる)
  let mut redir : Std.HashMap Name Name := {}
  if let some f ← IO.getEnv "RHSHRINK_REDIRECT" then
    for l in (← IO.FS.lines ⟨f⟩) do
      match l.splitOn "\t" with
      | [a, b] => redir := redir.insert (parseName a) (parseName b)
      | _ => pure ()
    log s!"redirects: {redir.size}"
  let mut seen : Std.HashSet Name := {}
  let mut ext : Std.HashSet Name := {}
  let mut stack : Array Name := roots
  let mut noInfo : Array Name := #[]
  while !stack.isEmpty do
    let n := stack.back!
    stack := stack.pop
    if seen.contains n || ext.contains n then continue
    if !isProjConst n then
      ext := ext.insert n
      continue
    seen := seen.insert n
    match env.find? n with
    | none => noInfo := noInfo.push n
    | some ci =>
      for u0 in edges ci do
        let u := redir.getD u0 u0
        unless seen.contains u || ext.contains u do
          stack := stack.push u
    if seen.size % 250000 == 0 then log s!"reached {seen.size} project constants (stack {stack.size})"
  log s!"reachable: {seen.size} project constants; {ext.size} external constants used directly; {noInfo.size} without info"

  let reachH ← IO.FS.Handle.mk (out / "reachable.txt") .write
  for n in seen do reachH.putStrLn n.toString
  reachH.flush
  let extH ← IO.FS.Handle.mk (out / "external-used.tsv") .write
  extH.putStrLn "constant\tmodule\tkind"
  for n in ext do
    let m := match modOf? n with | some i => names[i]!.toString | none => "?"
    let k := match env.find? n with | some ci => kindOf ci | none => "?"
    extH.putStrLn s!"{n}\t{m}\t{k}"
  extH.flush

  let mut reachByMod : Array (Array Name) := Array.replicate nMods #[]
  for n in seen do
    if let some i := modOf? n then
      reachByMod := reachByMod.modify i (·.push n)

  -- 2. 宣言ごとの生死と行数
  let declsH ← IO.FS.Handle.mk (out / "decls.tsv") .write
  declsH.putStrLn "module\tdecl\tkind\tstart_line\tend_line\tstate\tconsts\treachable_consts"
  let modsH ← IO.FS.Handle.mk (out / "modules.tsv") .write
  modsH.putStrLn "module\tconsts\treachable_consts\tdecls\tlive_decls\taux_decls\tdead_decls\tlive_lines\taux_lines\tdead_lines\tunowned_consts\tunowned_reachable\tmax_decl_line"
  let mut declLoc : Std.HashMap Name (Nat × Nat × Nat) := {}
  let mut tot : Std.HashMap String Nat := {}
  let bump (m : Std.HashMap String Nat) (k : String) (d : Nat) := m.insert k (m.getD k 0 + d)
  for i in [0:nMods] do
    unless isProj[i]! do continue
    if i % 20000 == 0 then log s!"module index {i} / {nMods}"
    let entries := declRangeExt.getModuleEntries env i
    let mut rng : Std.HashMap Name (Nat × Nat) := {}
    for (n, r) in entries do
      rng := rng.insert n (r.range.pos.line, r.range.endPos.line)
      declLoc := declLoc.insert n (i, r.range.pos.line, r.range.endPos.line)
    let mut nConst : Std.HashMap Name Nat := {}
    let mut nReach : Std.HashMap Name Nat := {}
    let mut unowned := 0
    let mut unownedReach := 0
    let consts := mods[i]!.constNames
    for c in consts do
      match owner rng c with
      | some d => nConst := nConst.insert d (nConst.getD d 0 + 1)
      | none => unowned := unowned + 1
    for c in reachByMod[i]! do
      match owner rng c with
      | some d => nReach := nReach.insert d (nReach.getD d 0 + 1)
      | none => unownedReach := unownedReach + 1
    let state (n : Name) : String :=
      if seen.contains n then "live"
      else if nReach.getD n 0 > 0 then (if env.contains n then "aux" else "live")
      else "dead"
    let maxLine := entries.foldl (fun a (_, r) => max a r.range.endPos.line) 0
    let mut lineSt : Array Nat := Array.replicate (maxLine + 1) 0  -- 0 なし, 1 dead, 2 aux, 3 live
    let mut nLive := 0
    let mut nAux := 0
    let mut nDead := 0
    for (n, r) in entries do
      let s := state n
      let v := if s == "live" then 3 else if s == "aux" then 2 else 1
      if v == 3 then nLive := nLive + 1 else if v == 2 then nAux := nAux + 1 else nDead := nDead + 1
      for l in [r.range.pos.line : r.range.endPos.line + 1] do
        if lineSt[l]! < v then lineSt := lineSt.set! l v
      let k := match env.find? n with | some ci => kindOf ci | none => "-"
      declsH.putStrLn s!"{names[i]!}\t{n}\t{k}\t{r.range.pos.line}\t{r.range.endPos.line}\t{s}\t{nConst.getD n 0}\t{nReach.getD n 0}"
    let liveL := lineSt.foldl (fun a v => if v == 3 then a + 1 else a) 0
    let auxL := lineSt.foldl (fun a v => if v == 2 then a + 1 else a) 0
    let deadL := lineSt.foldl (fun a v => if v == 1 then a + 1 else a) 0
    modsH.putStrLn s!"{names[i]!}\t{consts.size}\t{reachByMod[i]!.size}\t{entries.size}\t{nLive}\t{nAux}\t{nDead}\t{liveL}\t{auxL}\t{deadL}\t{unowned}\t{unownedReach}\t{maxLine}"
    tot := bump tot "project_modules" 1
    tot := bump tot "project_consts" consts.size
    tot := bump tot "decls" entries.size
    tot := bump tot "live_decls" nLive
    tot := bump tot "aux_decls" nAux
    tot := bump tot "dead_decls" nDead
    tot := bump tot "live_lines" liveL
    tot := bump tot "aux_lines" auxL
    tot := bump tot "dead_lines" deadL
    tot := bump tot "unowned_consts" unowned
    tot := bump tot "unowned_reachable" unownedReach
    if nLive == 0 then tot := bump tot "modules_without_live_decls" 1
    if entries.size == 0 then tot := bump tot "modules_without_decls" 1
  declsH.flush
  modsH.flush
  log s!"declarations: {tot.getD "decls" 0} ({tot.getD "live_decls" 0} live, {tot.getD "aux_decls" 0} aux, {tot.getD "dead_decls" 0} dead)"

  -- 3, 4. 型の一致(配布物の中の重複と、外部の定理との一致)。RHSHRINK_SKIP_DUPS があれば省く
  let mut extIdx : Std.HashMap Expr (Array Name) := {}
  for i in [0:nMods] do
    if skipDups || isProj[i]! then continue
    for ci in mods[i]!.constants do
      if let .thmInfo v := ci then
        if !v.name.isInternal then
          let k := norm v.type
          extIdx := extIdx.insert k ((extIdx.getD k #[]).push v.name)
  log s!"indexed {extIdx.size} external theorem types"
  let mut thmIdx : Std.HashMap Expr (Array Name) := {}
  let mut defIdx : Std.HashMap (Expr × Expr) (Array Name) := {}
  let aliasH ← IO.FS.Handle.mk (out / "aliases.tsv") .write
  aliasH.putStrLn "decl\tkind\ttarget\ttarget_in_project\targs\tnon_bvar_args"
  -- 対象は、ソース上の行範囲を持つ宣言(人が書いた宣言)だけ。自動生成の補助定数(`foo.eq_def` など)は除く
  let mut nAliasThm := 0
  let mut nAliasDef := 0
  let mut nDeclThm := 0
  let mut nDeclDef := 0
  -- 段階 1b 用: RHSHRINK_STRICT_DUPS があれば、厳しい鍵(strictKey)で定理の組も作る(RHSHRINK_SKIP_DUPS と併用できる)
  let strictDups := (← IO.getEnv "RHSHRINK_STRICT_DUPS").isSome
  let mut strictIdx : Std.HashMap (Expr × String) (Array Name) := {}
  for n in seen do
    if skipDups && !strictDups then break
    unless declLoc.contains n do continue
    match env.find? n with
    | some (.thmInfo v) =>
      if strictDups then
        let sk := strictKey v.levelParams v.type
        strictIdx := strictIdx.insert sk ((strictIdx.getD sk #[]).push n)
      if skipDups then continue
      nDeclThm := nDeclThm + 1
      let k := norm v.type
      thmIdx := thmIdx.insert k ((thmIdx.getD k #[]).push n)
      if let some (c, na, nb) := aliasTarget? v.value then
        aliasH.putStrLn s!"{n}\ttheorem\t{c}\t{isProjConst c}\t{na}\t{nb}"
        if nb == 0 then nAliasThm := nAliasThm + 1
    | some (.defnInfo v) =>
      if skipDups then continue
      nDeclDef := nDeclDef + 1
      let k := (norm v.type, norm v.value)
      defIdx := defIdx.insert k ((defIdx.getD k #[]).push n)
      if let some (c, na, nb) := aliasTarget? v.value then
        aliasH.putStrLn s!"{n}\tdef\t{c}\t{isProjConst c}\t{na}\t{nb}"
        if nb == 0 then nAliasDef := nAliasDef + 1
    | _ => pure ()
  aliasH.flush
  let loc (n : Name) : String :=
    match declLoc.get? n with
    | some (i, s, e) => s!"{names[i]!}\t{s}\t{e}"
    | none => match modOf? n with
      | some i => s!"{names[i]!}\t-\t-"
      | none => "?\t-\t-"
  if strictDups then
    let sdupH ← IO.FS.Handle.mk (out / "duplicates-strict.tsv") .write
    sdupH.putStrLn "group\tsize\tdecl\tmodule\tstart_line\tend_line\tprivate\tbinders\tbinder_names"
    let mut sg := 0
    let mut sExtra := 0
    for ((_, sig), ns) in strictIdx do
      if ns.size ≥ 2 then
        sg := sg + 1
        sExtra := sExtra + (ns.size - 1)
        for n in ns do
          let bn := match env.find? n with
            | some ci => (binderSig (stripMData ci.type)).2
            | none => ""
          sdupH.putStrLn s!"{sg}\t{ns.size}\t{n}\t{loc n}\t{isPrivateName n}\t{sig}\t{bn}"
    sdupH.flush
    log s!"strict theorem duplicate groups: {sg} (+{sExtra} copies)"
  let dupH ← IO.FS.Handle.mk (out / "duplicates.tsv") .write
  dupH.putStrLn "group\tkind\tsize\tdecl\tmodule\tstart_line\tend_line"
  let mut g := 0
  let mut dupThmGroups := 0
  let mut dupThmExtra := 0
  for (_, ns) in thmIdx do
    if ns.size ≥ 2 then
      g := g + 1
      dupThmGroups := dupThmGroups + 1
      dupThmExtra := dupThmExtra + (ns.size - 1)
      for n in ns do dupH.putStrLn s!"{g}\ttheorem\t{ns.size}\t{n}\t{loc n}"
  let mut dupDefGroups := 0
  let mut dupDefExtra := 0
  for (_, ns) in defIdx do
    if ns.size ≥ 2 then
      g := g + 1
      dupDefGroups := dupDefGroups + 1
      dupDefExtra := dupDefExtra + (ns.size - 1)
      for n in ns do dupH.putStrLn s!"{g}\tdef\t{ns.size}\t{n}\t{loc n}"
  dupH.flush
  let extH2 ← IO.FS.Handle.mk (out / "external-matches.tsv") .write
  extH2.putStrLn "decl\tmodule\tstart_line\tend_line\texternal_matches\texamples"
  let mut nExtMatch := 0
  for (k, ns) in thmIdx do
    if let some es := extIdx.get? k then
      for n in ns do
        nExtMatch := nExtMatch + 1
        extH2.putStrLn s!"{n}\t{loc n}\t{es.size}\t{",".intercalate ((es.extract 0 5).toList.map toString)}"
  extH2.flush
  log s!"live theorems {nDeclThm}, defs {nDeclDef}; theorem duplicate groups: {dupThmGroups} (+{dupThmExtra} copies); def duplicate groups: {dupDefGroups} (+{dupDefExtra}); external matches: {nExtMatch}; pure aliases: {nAliasThm} theorems, {nAliasDef} defs"

  let t1 ← IO.monoMsNow
  let summary := Json.mkObj <|
    [("root_module", toJson rootMod.toString),
     ("roots", toJson (if roots.size > 20 then #[s!"{roots.size} roots"] else roots.map (·.toString))),
     ("roots_count", toJson roots.size),
     ("roots_not_constants", toJson missingRoots.size),
     ("duplicates_skipped", toJson skipDups),
     ("imported_modules", toJson nMods),
     ("reachable_project_consts", toJson seen.size),
     ("external_consts_used_directly", toJson ext.size),
     ("reachable_without_info", toJson noInfo.size),
     ("theorem_duplicate_groups", toJson dupThmGroups),
     ("theorem_duplicate_extra_copies", toJson dupThmExtra),
     ("def_duplicate_groups", toJson dupDefGroups),
     ("def_duplicate_extra_copies", toJson dupDefExtra),
     ("theorems_matching_external", toJson nExtMatch),
     ("live_source_theorems", toJson nDeclThm),
     ("live_source_defs", toJson nDeclDef),
     ("pure_alias_theorems", toJson nAliasThm),
     ("pure_alias_defs", toJson nAliasDef),
     ("seconds", toJson ((t1 - t0) / 1000))] ++
    (tot.toList.map fun (k, v) => (k, toJson v))
  IO.FS.writeFile (out / "summary.json") (summary.pretty ++ "\n")
  log "done"
  return 0
