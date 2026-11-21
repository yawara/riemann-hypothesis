#!/usr/bin/env python3
"""各モジュールの推移的 import 閉包の大きさを数える(プロジェクト内モジュールのみ)。

Lake 5 は各モジュールについて、推移的に import する全モジュールの成果物パスを
列挙した <Module>.setup.json を書き出す。閉包が大きいとこのファイルだけで
ディスクを圧迫しうるので、ビルド前に見積もるために使う。

使い方: python3 -I scripts/closure_stats.py <lean/src> [出力JSON]
"""
import json
import os
import re
import sys
from collections import defaultdict, deque

IMPORT_RE = re.compile(r"^import\s+(runtime\s+)?(\S+)\s*$")


def read_imports(path):
    imports = []
    in_block = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if in_block:
                in_block = max(0, in_block + s.count("/-") - s.count("-/"))
                continue
            if not s or s.startswith("--"):
                continue
            if s.startswith("/-"):
                in_block = max(0, s.count("/-") - s.count("-/"))
                continue
            m = IMPORT_RE.match(s)
            if m:
                imports.append(m.group(2))
                continue
            break
    return imports


def main():
    src = sys.argv[1]
    modules = {}
    for root, _dirs, files in os.walk(src):
        for f in files:
            if f.endswith(".lean"):
                p = os.path.join(root, f)
                modules[os.path.relpath(p, src)[:-5].replace(os.sep, ".")] = p
    deps = {}
    imports_mathlib = {}
    for mod, path in modules.items():
        imps = read_imports(path)
        deps[mod] = [i for i in dict.fromkeys(imps) if i in modules]
        imports_mathlib[mod] = any(i.split(".")[0] in ("Mathlib", "Batteries", "Lean") for i in imps)

    indeg = {m: len(ds) for m, ds in deps.items()}
    rdeps = defaultdict(list)
    for m, ds in deps.items():
        for d in ds:
            rdeps[d].append(m)
    q = deque(m for m, k in indeg.items() if k == 0)
    order = []
    while q:
        m = q.popleft()
        order.append(m)
        for r in rdeps[m]:
            indeg[r] -= 1
            if indeg[r] == 0:
                q.append(r)
    assert len(order) == len(modules), "cycle detected"
    idx = {m: i for i, m in enumerate(order)}

    bits = [0] * len(order)
    sizes = [0] * len(order)
    path_bytes = [len(m) for m in order]  # モジュール名の長さ(パス長の代用)
    remaining_users = [len(rdeps[m]) for m in order]
    total = 0
    for i, m in enumerate(order):
        b = 0
        for d in deps[m]:
            j = idx[d]
            b |= bits[j] | (1 << j)
            remaining_users[j] -= 1
            if remaining_users[j] == 0:
                bits[j] = 0  # もう参照されないので解放
        bits[i] = b
        sizes[i] = b.bit_count()
        total += sizes[i]

    s = sorted(sizes)
    n = len(s)
    summary = {
        "modules": n,
        "sum_of_transitive_project_imports": total,
        "mean": total / n,
        "p50": s[n // 2],
        "p90": s[int(n * 0.9)],
        "p99": s[int(n * 0.99)],
        "max": s[-1],
        "modules_with_zero_project_imports": sum(1 for x in s if x == 0),
    }
    json.dump(summary, sys.stdout, indent=2)
    print()
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w") as fh:
            json.dump(summary, fh, indent=2)
            fh.write("\n")


if __name__ == "__main__":
    main()
