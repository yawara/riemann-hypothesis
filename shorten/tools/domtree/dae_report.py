#!/usr/bin/env python3
"""使われない引数の削除の見積もり(rhshrink の RHSHRINK_DAE)で要らなくなる宣言を、支配木(domtree.tsv)の上でまとめる。

要らなくなる宣言 d が支配する宣言は、すべて要らなくなる(d を通らなければ主定理から辿り着けないため)。そこで、
要らなくなる宣言のうち、支配木の親が要るまま残る宣言(「消える部分木の根」)を集め、その親(= 使われない引数の位置に
証明を渡している定理の証明など)ごとに、消える行を合計する。

使い方: python3 -I dae_report.py <domtree.tsv> <dae-dropped-decls.tsv> <dae-dead-args.tsv> <出力ディレクトリ>
"""
import collections
import os
import sys


def main():
    dom, dropped_path, dead_path, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    node = {}
    for l in list(open(dom, encoding="utf-8"))[1:]:
        f = l.rstrip("\n").split("\t")
        node[(f[1], f[2])] = dict(decl=f[1], node=f[2], kind=f[3], module=f[4], own=int(f[5]), sub=int(f[6]),
                                  subn=int(f[7]), idom=(f[8], f[9]))
    dropped = set()
    lines = {}
    for l in list(open(dropped_path, encoding="utf-8"))[1:]:
        m, d, s, e = l.rstrip("\n").split("\t")
        dropped.add(d)
        lines[d] = int(e) - int(s) + 1
    # 消える部分木の根: 要らなくなる宣言のうち、支配木の親(の宣言)が残るもの
    roots = []
    for d in dropped:
        n = node.get((d, "decl"))
        if n is None:
            continue
        p = n["idom"]
        if p[0] == "(root)" or p[0] not in dropped:
            roots.append(n)
    by_parent = collections.defaultdict(list)
    for n in roots:
        by_parent[n["idom"]].append(n)
    tot = sum(lines.values())
    covered = sum(n["sub"] for n in roots)
    dead_by_thm = collections.defaultdict(list)
    for l in list(open(dead_path, encoding="utf-8"))[1:]:
        t, pos, b, ow, m = l.rstrip("\n").split("\t")
        dead_by_thm[ow].append(f"{pos}:{b}")
    with open(os.path.join(out, "dae-by-parent.tsv"), "w", encoding="utf-8") as fh:
        fh.write("lines\troots\tparent\tparent_node\ttop_roots\n")
        rows = []
        for p, ns in by_parent.items():
            s = sum(n["sub"] for n in ns)
            ns.sort(key=lambda n: -n["sub"])
            rows.append((s, len(ns), p, ", ".join(f"{n['decl']}({n['sub']})" for n in ns[:5])))
        rows.sort(key=lambda r: -r[0])
        for s, k, p, top in rows:
            fh.write(f"{s}\t{k}\t{p[0]}\t{p[1]}\t{top}\n")
    with open(os.path.join(out, "dae-summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"要らなくなる宣言: {len(dropped):,} 個・{tot:,} 行\n")
        fh.write(f"消える部分木の根: {len(roots):,} 個(その部分木の行の合計 {covered:,})\n")
        fh.write(f"使われない引数を持つ定理(辿り直したあとも到達するもの): {len(dead_by_thm):,} 個\n\n")
        fh.write("# 親ごとの消える行(上位 40)\n")
        for s, k, p, top in rows[:40]:
            fh.write(f"{s:>10,} {k:>5}  {p[1]:5} {p[0]}\n             {top[:300]}\n")
    print(open(os.path.join(out, "dae-summary.txt"), encoding="utf-8").read())


if __name__ == "__main__":
    main()
