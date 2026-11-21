#!/usr/bin/env python3
"""配布された Lean ソースツリーの import グラフを静的に解析する。

Lean を一切実行せず、各 .lean ファイル冒頭の `import` 行だけを読んで
  * モジュール数・内部 import 辺数
  * 存在しないプロジェクト内モジュールへの import(= ビルド不能の兆候)
  * 循環 import
  * Main からの推移閉包(主定理が実際に依存するファイル集合)
  * lakefile.toml の各 lean_lib の glob に属さないファイル
  * import 連鎖の最大深さ(ビルドの直列ボトルネックの目安)
を求め、JSON とテキスト一覧を出力する。

使い方:  python3 -I scripts/import_graph.py <lean/src> <出力ディレクトリ>
"""
import json
import os
import re
import sys
from collections import defaultdict, deque

IMPORT_RE = re.compile(r"^import\s+(runtime\s+)?(\S+)\s*$")

# lakefile.toml の lean_lib 定義(原本 lakefile.toml を目視で転記。glob "X.+" は
# 「X 配下の全サブモジュール(X 自身は含まない)」を意味する)
LIB_GLOBS = {
    "BuildAid": ["BuildAid"],
    "CompanionTheory": ["CompanionTheory"],
    "Development": ["Development"],
    "Formalism": ["Formalism"],
    "GroundTheory": [
        "GroundTheory.ArithmeticGeometry", "GroundTheory.AutomorphicForms",
        "GroundTheory.Brauer", "GroundTheory.FunctionField",
        "GroundTheory.HeightsAndTheta", "GroundTheory.IdeleRoots",
        "GroundTheory.PAdicHodge", "GroundTheory.PowerSubgroups",
        "GroundTheory.ProfiniteCohomology", "GroundTheory.TateCohomology",
    ],
    "GroundTheoryFields": ["GroundTheory.LocalFields", "GroundTheory.GlobalFields"],
    "Lemmata": ["Lemmata"],
    "PositivityTheory": ["PositivityTheory"],
    "ReciprocityTheory": ["ReciprocityTheory"],
    "Supplements": ["Supplements"],
}
LIB_ROOTS = {"Main": ["Statements", "Main"]}


def read_imports(path):
    """ファイル冒頭の import 群を返す。コメントと空行は読み飛ばす。"""
    imports = []
    in_block = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if in_block:
                in_block += s.count("/-") - s.count("-/")
                if in_block < 0:
                    in_block = 0
                continue
            if not s or s.startswith("--"):
                continue
            if s.startswith("/-"):
                in_block = s.count("/-") - s.count("-/")
                if in_block < 0:
                    in_block = 0
                continue
            m = IMPORT_RE.match(s)
            if m:
                imports.append(m.group(2))
                continue
            break  # 最初の非 import 行でヘッダ終了
    return imports


def lib_of(mod):
    for lib, roots in LIB_ROOTS.items():
        if mod in roots:
            return lib
    for lib, prefixes in LIB_GLOBS.items():
        for p in prefixes:
            if mod.startswith(p + "."):
                return lib
    return None


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)

    modules = {}
    for root, _dirs, files in os.walk(src):
        for f in files:
            if f.endswith(".lean"):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, src)
                modules[rel[:-5].replace(os.sep, ".")] = p
    project_roots = {m.split(".")[0] for m in modules}

    deps = {}
    external = defaultdict(int)
    missing = []
    dup_imports = 0
    n_edges = 0
    for mod, path in modules.items():
        imps = read_imports(path)
        if len(imps) != len(set(imps)):
            dup_imports += 1
        internal = []
        for i in dict.fromkeys(imps):
            if i in modules:
                internal.append(i)
            elif i.split(".")[0] in project_roots:
                missing.append((mod, i))
            else:
                external[i.split(".")[0]] += 1
        deps[mod] = internal
        n_edges += len(internal)

    # 循環検出 + トポロジカル順 + 最大深さ (Kahn)
    indeg = {m: 0 for m in modules}
    rdeps = defaultdict(list)
    for m, ds in deps.items():
        for d in ds:
            rdeps[d].append(m)
        indeg[m] = len(ds)
    depth = {m: 1 for m in modules}
    q = deque(m for m, k in indeg.items() if k == 0)
    order = []
    while q:
        m = q.popleft()
        order.append(m)
        for r in rdeps[m]:
            if depth[m] + 1 > depth[r]:
                depth[r] = depth[m] + 1
            indeg[r] -= 1
            if indeg[r] == 0:
                q.append(r)
    cyclic = sorted(m for m, k in indeg.items() if k > 0)

    def closure(start):
        seen = set()
        stack = [s for s in start if s in modules]
        while stack:
            m = stack.pop()
            if m in seen:
                continue
            seen.add(m)
            stack.extend(deps[m])
        return seen

    main_cone = closure(["Main"])
    statements_cone = closure(["Statements"])
    not_in_cone = sorted(set(modules) - main_cone)

    no_lib = sorted(m for m in modules if lib_of(m) is None)

    def by_top(mods):
        c = defaultdict(int)
        for m in mods:
            c[m.split(".")[0]] += 1
        return dict(sorted(c.items()))

    leaves_never_imported = sorted(m for m in modules if not rdeps[m])

    summary = {
        "modules_total": len(modules),
        "internal_import_edges": n_edges,
        "files_with_duplicate_import_lines": dup_imports,
        "external_import_roots": dict(sorted(external.items())),
        "missing_internal_imports": len(missing),
        "modules_in_cycles": len(cyclic),
        "max_import_chain_depth": max(depth.values()) if depth else 0,
        "main_cone_modules": len(main_cone),
        "main_cone_by_top_dir": by_top(main_cone),
        "statements_cone_modules": len(statements_cone),
        "outside_main_cone_modules": len(not_in_cone),
        "outside_main_cone_by_top_dir": by_top(not_in_cone),
        "modules_total_by_top_dir": by_top(modules),
        "modules_not_matched_by_any_lean_lib": len(no_lib),
        "modules_never_imported_by_others": len(leaves_never_imported),
    }
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    with open(os.path.join(out, "main-cone-modules.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(main_cone)) + "\n")
    with open(os.path.join(out, "outside-main-cone-modules.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(not_in_cone) + ("\n" if not_in_cone else ""))
    with open(os.path.join(out, "missing-internal-imports.txt"), "w", encoding="utf-8") as fh:
        for mod, imp in sorted(missing):
            fh.write(f"{mod}\t{imp}\n")
    with open(os.path.join(out, "modules-in-cycles.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(cyclic) + ("\n" if cyclic else ""))
    with open(os.path.join(out, "modules-without-lean-lib.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(no_lib) + ("\n" if no_lib else ""))
    # Main への最長 import 連鎖を 1 本、具体例として書き出す
    chain = []
    if "Main" in modules:
        cur = "Main"
        while True:
            chain.append(cur)
            if not deps[cur]:
                break
            cur = max(deps[cur], key=lambda d: depth[d])
    with open(os.path.join(out, "longest-chain-to-main.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(chain) + "\n")
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
