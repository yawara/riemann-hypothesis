#!/usr/bin/env python3
"""leanchecker に渡す対象(モジュール名の前方一致)を、走査の回数が少なくなるようにまとめる。

leanchecker(ツールチェーン同梱、src/lean/LeanChecker.lean)は、引数の名前 1 つごとに
検索パス全体(約 18.6 万個の .olean)を走査し直して、前方一致するモジュールを探す。
モジュール名を 1 つずつ渡すと、名前の解決だけで膨大な時間がかかる(1 回の走査に 20 秒〜数分)。
そこで、モジュール名の木を前方一致でまとめた「グループ」を作り、1 プロセスに 1 グループ
(= 走査 1 回)だけを渡す。

グループの作り方: 名前の木を根から辿り、配下のモジュール数が MAX 以下になった節点を 1 グループにする。
節点そのものがモジュールで、さらに配下にもモジュールがある場合(例: Foo.Bar と Foo.Bar.Baz)は、
前方一致で Foo.Bar だけを指定できないので、その節点の配下全体を 1 グループにする。

SCOPE=deps では、名前に `.` を含まないルートモジュール(`Mathlib` など。配下を import するだけの
集約ファイル)は、配下の全体と一緒にしか指定できないので対象から外す(従来の run_leanchecker.sh と同じ扱い)。
ただし、小さなパッケージで、グループの名前がルートと一致するときは、ルートも一緒に検査される。

出力(OUT ディレクトリ):
  modules.txt       検査しなければならないモジュール(この一覧が結果の照合の基準)
  excluded.txt      対象から外したモジュール
  targets.tsv       グループ: 番号 \t 前方一致の名前 \t モジュール数 \t 見積もりの重さ(重い順)
  groups/NNNN.txt   各グループで leanchecker が再生するはずのモジュール(検索パス上の全 .olean から計算)

使い方: python3 -I scripts/leanchecker_targets.py <project|deps> <OUT> [MAX=300]
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAKE = os.path.realpath(os.path.join(ROOT, "lean", ".lake"))
TOOLCHAIN_LIB = os.path.expanduser("~/.elan/toolchains/leanprover--lean4---v4.33.1/lib/lean")
CLOSURE = os.environ.get("RH_CLOSURE_JSON", "")  # 任意: {"size": {モジュール: 推移的 import 数}}


def oleans(root):
    out = []
    for d, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".olean"):
                rel = os.path.relpath(os.path.join(d, f), root)[: -len(".olean")]
                out.append(rel.replace(os.sep, "."))
    return out


def roots():
    project = os.path.join(LAKE, "build", "lib", "lean")
    deps = []
    pkgs = os.path.join(LAKE, "packages")
    for p in sorted(os.listdir(pkgs)):
        d = os.path.join(pkgs, p, ".lake", "build", "lib", "lean")
        if os.path.isdir(d):
            deps.append(d)
    return project, deps


def is_prefix(a, b):
    """Lean の Name.isPrefixOf と同じ(成分ごとの前方一致。等しい場合を含む)"""
    return b == a or b.startswith(a + ".")


def main():
    scope, out = sys.argv[1], sys.argv[2]
    max_size = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    project_root, dep_roots = roots()

    # 検索パス上の全モジュール(重複が無いことも確かめる。LEAN_PATH の順序を入れ替えても結果が変わらないため)
    owner = {}
    for r in [project_root, *dep_roots, TOOLCHAIN_LIB]:
        for m in oleans(r):
            assert m not in owner, f"モジュール名が重複: {m} ({owner[m]} と {r})"
            owner[m] = r
    if scope == "project":
        in_scope = [m for m, r in owner.items() if r == project_root]
        excluded = []
    elif scope == "deps":
        all_deps = [m for m, r in owner.items() if r in dep_roots]
        excluded = sorted(m for m in all_deps if "." not in m)
        in_scope = [m for m in all_deps if "." in m]
    else:
        raise SystemExit("scope は project か deps")
    in_scope.sort()
    all_names = sorted(owner)

    # 名前の木
    tree = {"children": {}, "module": False, "count": 0}
    for m in in_scope:
        node = tree
        for part in m.split("."):
            node = node["children"].setdefault(part, {"children": {}, "module": False, "count": 0})
        node["module"] = True

    def count(node):
        node["count"] = int(node["module"]) + sum(count(c) for c in node["children"].values())
        return node["count"]

    count(tree)
    groups = []

    def assign(node, prefix):
        if node["count"] == 0:
            return
        if prefix and (node["count"] <= max_size or (node["module"] and node["children"])):
            groups.append(".".join(prefix))
            return
        for name in sorted(node["children"]):
            assign(node["children"][name], prefix + [name])

    assign(tree, [])

    # 各グループで再生されるはずのモジュール(検索パス上の全 .olean に対する前方一致)
    size = {}
    if CLOSURE and os.path.isfile(CLOSURE):
        with open(CLOSURE, encoding="utf-8") as fh:
            size = json.load(fh).get("size", {})
    # 名前の成分ごとの前方一致を、名前側から引く(グループ数 × モジュール数の総当たりを避ける)
    group_set = set(groups)
    members = {g: [] for g in groups}
    for m in all_names:
        parts = m.split(".")
        hits = [p for p in (".".join(parts[:k]) for k in range(1, len(parts) + 1)) if p in group_set]
        assert len(hits) <= 1, f"複数のグループに入るモジュールがある: {m} {hits}"
        if hits:
            members[hits[0]].append(m)
    for g in groups:
        assert all(is_prefix(g, m) for m in members[g])
    covered = {m for g in groups for m in members[g]}
    missing = [m for m in in_scope if m not in covered]
    assert not missing, f"どのグループにも入らないモジュールがある: {missing[:5]}"

    def weight(g):
        # 重さの目安: 1 モジュールあたり「1 + 推移的 import 数 / 1000」(import の読み込みが主な手間)
        return sum(1 + size.get(m, 0) / 1000 for m in members[g])

    groups.sort(key=weight, reverse=True)
    os.makedirs(os.path.join(out, "groups"), exist_ok=True)
    with open(os.path.join(out, "modules.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(m + "\n" for m in in_scope))
    with open(os.path.join(out, "excluded.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(f"{m}\troot aggregator (prefix of the whole package)\n" for m in excluded))
    with open(os.path.join(out, "targets.tsv"), "w", encoding="utf-8") as fh:
        for i, g in enumerate(groups):
            fh.write(f"{i:04d}\t{g}\t{len(members[g])}\t{weight(g):.1f}\n")
            with open(os.path.join(out, "groups", f"{i:04d}.txt"), "w", encoding="utf-8") as gf:
                gf.write("".join(m + "\n" for m in members[g]))
    sizes = sorted((len(members[g]) for g in groups), reverse=True)
    print(f"scope={scope} modules={len(in_scope)} excluded={len(excluded)} groups={len(groups)} "
          f"max_group={sizes[0]} median_group={sizes[len(sizes) // 2]} min_group={sizes[-1]} "
          f"big(>{max_size})={sum(1 for s in sizes if s > max_size)}")


if __name__ == "__main__":
    main()
