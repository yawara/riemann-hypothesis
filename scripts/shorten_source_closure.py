#!/usr/bin/env python3
"""段階 1a の下ごしらえ: カーネルの項で使われる宣言に、ソースで参照される宣言を足した閉包を求める。

rhshrink の解析(カーネルの項の上での到達可能性)では、証明項に痕跡を残さない参照、たとえば
`simp [X]` で結局使われなかった `X` や、失敗した分岐の中の名前は数えない。こうした宣言を消すと、
ソースをビルドし直したときにエラーになりうる。そこで、Lean がビルドのたびに書き出す `.ilean`
(エディタ用の参照情報。参照ごとに、それを含む宣言の名前がつく)から、ソース上の参照のグラフを作り、
「カーネルの項で使われる宣言」から出発して、ソースで参照される宣言を推移的に足す。

足した宣言自身の証明項が使う定数(カーネルの辺)は、この閉包には入らない。足した宣言を起点に
rhshrink をもう一度走らせ(--roots)、両方の辺で閉じるまで繰り返す。

入力: rhshrink の decls.tsv.zst(既定は runs/shorten/latest-analysis)、配布物のビルド結果の .ilean
出力: <出力先>/source-closure.json(集計)、added-decls.tsv(足した宣言と、最初に参照した宣言)、
      added-roots.txt(rhshrink に渡す起点)

使い方: python3 -I scripts/shorten_source_closure.py [--analysis DIR] [--extra-live FILE] [--out DIR]
  --extra-live: 前回までに残すと決めた宣言の一覧(kept-decls.tsv。モジュール\t名前)
"""
import argparse
import collections
import json
import multiprocessing as mp
import os
import subprocess

RUN_ROOT = os.environ.get("RH_RUN_ROOT", "/var/tmp/riemann-hypothesis-ywr/runs")
ILEAN_ROOT = "/var/tmp/riemann-hypothesis-ywr/lake/build/lib/lean"
PROJECT_ROOTS = {"BuildAid", "CompanionTheory", "Development", "Formalism", "GroundTheory", "Lemmata",
                 "PositivityTheory", "ReciprocityTheory", "Supplements", "Main", "Statements"}


def is_project(module):
    return module.split(".", 1)[0] in PROJECT_ROOTS


def parse_ilean(module):
    """1 モジュールの .ilean から、配布物の定数への参照を (含む宣言 or None, 参照先モジュール, 参照先の名前) で返す"""
    path = os.path.join(ILEAN_ROOT, *module.split(".")) + ".ilean"
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    edges = set()
    for key, v in d.get("references", {}).items():
        if not key.startswith('{"c":'):
            continue
        c = json.loads(key)["c"]
        m, n = c["m"], c["n"]
        if not is_project(m):
            continue
        for u in v.get("usages", []):
            edges.add((u[4] if len(u) >= 5 else None, m, n))
    return module, sorted(edges, key=lambda e: (e[0] or "", e[1], e[2]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", default=os.path.join(RUN_ROOT, "shorten", "latest-analysis"))
    ap.add_argument("--extra-live", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--jobs", type=int, default=24)
    args = ap.parse_args()
    ana = os.path.realpath(args.analysis)
    out = args.out or os.path.join(ana, "source-closure")
    os.makedirs(out, exist_ok=True)

    # rhshrink の宣言ごとの状態。同じ名前で型も同じ定理は 2 つのモジュールにありうる(Lean は import 時に重複を許す)
    # ので、宣言は (モジュール, 名前) で区別する
    decls = {}            # (モジュール, 宣言) -> (種類, 開始行, 終了行, 状態)
    by_module = collections.defaultdict(set)
    p = subprocess.Popen(["zstd", "-dc", os.path.join(ana, "decls.tsv.zst")], stdout=subprocess.PIPE, text=True)
    next(p.stdout)
    for line in p.stdout:
        mod, name, kind, s, e, state, _, _ = line.rstrip("\n").split("\t")
        decls[(mod, name)] = (kind, int(s), int(e), state)
        by_module[mod].add(name)
    p.wait()
    live = {k for k, v in decls.items() if v[3] == "live"}
    if args.extra_live:
        with open(args.extra_live, encoding="utf-8") as fh:
            extra = {tuple(l.rstrip("\n").split("\t", 1)) for l in fh if l.strip()}
        live |= extra & decls.keys()
    print(f"decls={len(decls)} live(kernel)={len(live)}", flush=True)

    def owner(m, n):
        names = by_module.get(m)
        if not names:
            return None
        while n:
            if n in names:
                return (m, n)
            if "." not in n:
                return None
            n = n.rsplit(".", 1)[0]
        return None

    # .ilean を並列に読む
    modules = sorted(by_module)
    # 宣言を持たないモジュール(import だけ)も .ilean はあるが、参照は無いので読まなくてよい
    edges = collections.defaultdict(set)   # 宣言 -> 参照先の宣言
    module_refs = collections.defaultdict(set)  # モジュール -> 宣言の外から参照される宣言
    unresolved = 0
    with mp.Pool(args.jobs) as pool:
        for i, (mod, es) in enumerate(pool.imap_unordered(parse_ilean, modules, chunksize=64)):
            for src, m, n in es:
                d = owner(m, n)
                if d is None:
                    unresolved += 1
                    continue
                if src is None:
                    module_refs[mod].add(d)
                else:
                    s = owner(mod, src)
                    if s is None:
                        module_refs[mod].add(d)
                    elif s != d:
                        edges[s].add(d)
            if (i + 1) % 20000 == 0:
                print(f"  ilean {i + 1}/{len(modules)}", flush=True)
    print(f"edges from {len(edges)} decls, module-level refs in {len(module_refs)} modules, unresolved refs {unresolved}", flush=True)

    # 閉包: カーネルで使われる宣言から出発し、ソースの参照を辿る。宣言が 1 つでも残るモジュールでは、宣言の外の参照も辿る
    kept = set(live)
    kept_modules = {k[0] for k in kept}
    added = {}  # 足した宣言 -> 最初に参照した宣言(または "module:<モジュール>")
    stack = list(kept)
    for m in kept_modules:
        for d in module_refs.get(m, ()):
            if d not in kept:
                kept.add(d)
                added[d] = f"module:{m}"
                stack.append(d)
    while stack:
        s = stack.pop()
        m = s[0]
        if m not in kept_modules:
            kept_modules.add(m)
            for d in module_refs.get(m, ()):
                if d not in kept:
                    kept.add(d)
                    added[d] = f"module:{m}"
                    stack.append(d)
        for d in edges.get(s, ()):
            if d not in kept:
                kept.add(d)
                added[d] = s
                stack.append(d)

    newly_alive_modules = {d[0] for d in added} - {k[0] for k in live}
    lines_added = sum(decls[d][2] - decls[d][1] + 1 for d in added)
    by_state = collections.Counter(decls[d][3] for d in added)
    summary = {
        "analysis": ana,
        "decls": len(decls),
        "kernel_live_decls": len(live),
        "added_by_source_refs": len(added),
        "added_by_state": dict(by_state),
        "added_decl_lines": lines_added,
        "kept_decls": len(kept),
        "modules_with_kept_decls": len(kept_modules),
        "modules_revived_by_source_refs": len(newly_alive_modules),
        "unresolved_refs": unresolved,
    }
    with open(os.path.join(out, "source-closure.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    with open(os.path.join(out, "added-decls.tsv"), "w", encoding="utf-8") as fh:
        fh.write("decl\tmodule\tkind\tstart_line\tend_line\tkernel_state\treferenced_by\n")
        for d in sorted(added):
            kind, s, e, state = decls[d]
            by = added[d] if isinstance(added[d], str) else f"{added[d][1]} ({added[d][0]})"
            fh.write(f"{d[1]}\t{d[0]}\t{kind}\t{s}\t{e}\t{state}\t{by}\n")
    # rhshrink に渡す起点(名前だけ。重複名の宣言はどちらか一方の定数しか環境に無い)
    with open(os.path.join(out, "added-roots.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(n + "\n" for n in sorted({d[1] for d in added if decls[d][3] != "live"})))
    # 次の回の --extra-live に渡す、これまでに残すと決めた宣言(モジュール\t名前)
    with open(os.path.join(out, "kept-decls.tsv"), "w", encoding="utf-8") as fh:
        fh.write("".join(f"{m}\t{n}\n" for m, n in sorted(kept)))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
