#!/usr/bin/env python3
"""domtree.tsv(domtree の出力)から、証明の骨組みと「大きな部分木を支配する定理」を書き出す。

* 骨組み: 根から、支配木を部分木の行数の大きい子へたどる(全体の pct% 以上の子だけ、depth 段まで)
* 候補: 証明の節点(定理の証明)を、支配する部分木の行数で並べる。その定理の主張(ソースの宣言の頭から `:=` まで)も添える

使い方: python3 -I report.py <domtree.tsv> <出力ディレクトリ> [--pct 0.5] [--depth 12] [--top 300]
ソースは lean/src(元の配布物。行範囲は元のソースのもの)を読む。
"""
import argparse
import collections
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SRC = os.path.join(ROOT, "lean", "src")


def statement(module, decl, start_line=None):
    path = os.path.join(SRC, *module.split(".")) + ".lean"
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return "?"
    short = decl.split(".")[-1]
    idx = None
    if start_line:
        idx = start_line - 1
    else:
        for i, l in enumerate(lines):
            if re.search(r"\b(theorem|lemma|def|structure|class|instance|abbrev|inductive)\s+(_root_\.)?\S*" + re.escape(short) + r"\b", l):
                idx = i
                break
    if idx is None:
        return "?"
    out = []
    for l in lines[idx: idx + 40]:
        out.append(l)
        if ":=" in l or re.search(r"\bwhere\s*$", l):
            break
    s = " ".join(x.strip() for x in out)
    s = re.sub(r":=.*$", ":=", s)
    return s[:600]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domtree")
    ap.add_argument("out")
    ap.add_argument("--pct", type=float, default=0.5)
    ap.add_argument("--depth", type=int, default=12)
    ap.add_argument("--top", type=int, default=300)
    ap.add_argument("--ids", default=None, help="decl-ids.tsv(主張の行を正しく取るため)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    starts = {}
    if a.ids:
        for l in list(open(a.ids, encoding="utf-8"))[1:]:
            f = l.rstrip("\n").split("\t")
            starts[f[0]] = int(f[3])
    rows = []
    for l in list(open(a.domtree, encoding="utf-8"))[1:]:
        f = l.rstrip("\n").split("\t")
        rows.append(dict(id=f[0], decl=f[1], node=f[2], kind=f[3], module=f[4], own=int(f[5]), sub=int(f[6]),
                         subn=int(f[7]), idom=f[8], idom_node=f[9]))
    key = {(r["decl"], r["node"]): r for r in rows}
    children = collections.defaultdict(list)
    tops = []
    for r in rows:
        if r["idom"] == "(root)":
            tops.append(r)
        else:
            children[(r["idom"], r["idom_node"])].append(r)
    total = sum(r["sub"] for r in tops)
    with open(os.path.join(a.out, "spine.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"# 主定理から到達する宣言の行: {total:,}\n")
        fh.write(f"# 支配木を、部分木が全体の {a.pct}% 以上の子だけたどる(行数、宣言の数、種類、名前)\n")

        def walk(r, d):
            fh.write(f"{'  ' * d}{r['sub']:>10,} {r['subn']:>8,} {r['node']:5} {r['kind']:8} {r['decl']}  [{r['module']}]\n")
            if d >= a.depth:
                return
            for c in sorted(children[(r["decl"], r["node"])], key=lambda x: -x["sub"]):
                if c["sub"] * 100 >= a.pct * total:
                    walk(c, d + 1)
        for r in sorted(tops, key=lambda x: -x["sub"]):
            walk(r, 0)
    # 候補: 証明の節点(主定理そのものは除く)
    cands = [r for r in rows if r["node"] == "proof"]
    cands.sort(key=lambda x: -x["sub"])
    with open(os.path.join(a.out, "proof-candidates.tsv"), "w", encoding="utf-8") as fh:
        fh.write("sub_lines\tsub_decls\town_lines\tdecl\tmodule\tidom\tstatement\n")
        for r in cands[: a.top]:
            st = statement(r["module"], r["decl"], starts.get(r["id"]))
            fh.write(f"{r['sub']}\t{r['subn']}\t{r['own']}\t{r['decl']}\t{r['module']}\t{r['idom']}\t{st}\n")
    # 分布
    with open(os.path.join(a.out, "distribution.txt"), "w", encoding="utf-8") as fh:
        for th in (1_000_000, 300_000, 100_000, 30_000, 10_000, 3_000, 1_000):
            n = sum(1 for r in cands if r["sub"] >= th)
            fh.write(f"証明が {th:>9,} 行以上を支配する定理: {n}\n")
    print(open(os.path.join(a.out, "distribution.txt"), encoding="utf-8").read())


if __name__ == "__main__":
    main()
