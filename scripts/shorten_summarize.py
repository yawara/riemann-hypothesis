#!/usr/bin/env python3
"""短縮の下調べ(rhshrink の出力)を、ソースファイルの行数・バイト数と突き合わせて集計する。

入力: rhshrink の出力ディレクトリ(既定は runs/shorten/latest-analysis)と、配布物のソース lean/src。
出力: shorten/results/01-analysis/ に
  summary.json     集計(モジュール・行・バイト・宣言の数、重複・外部との一致・別名)
  summary.txt      同じ内容を人が読む形で
  dead-modules.txt.zst   証明に使われている宣言を 1 つも持たないモジュールの一覧(段階 1a の入力)
  modules.tsv.zst  モジュールごとの集計(rhshrink の modules.tsv に行数・バイト数を足したもの)
  duplicates.tsv.zst / external-matches.tsv.zst / aliases.tsv.zst  rhshrink の一覧をそのまま圧縮したもの

使い方: python3 -I scripts/shorten_summarize.py [解析の出力ディレクトリ]
"""
import collections
import csv
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_ROOT = os.environ.get("RH_RUN_ROOT", "/var/tmp/riemann-hypothesis-ywr/runs")
SRC = os.path.join(ROOT, "lean", "src")
OUT = os.environ.get("RH_SHORTEN_OUT") or os.path.join(ROOT, "shorten", "results", "01-analysis")
FIXED = {"Main", "Statements"}  # 主張を担うので、どの段階でも残すモジュール


def read_tsv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))


def file_stats(module):
    path = os.path.join(SRC, *module.split(".")) + ".lean"
    with open(path, "rb") as fh:
        data = fh.read()
    return data.count(b"\n"), len(data)


def zst(src, dst):
    subprocess.run(["zstd", "-q", "-19", "-f", src, "-o", dst], check=True)


def main():
    ana = os.path.realpath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(RUN_ROOT, "shorten", "latest-analysis"))
    with open(os.path.join(ana, "summary.json"), encoding="utf-8") as fh:
        raw = json.load(fh)
    mods = read_tsv(os.path.join(ana, "modules.tsv"))
    os.makedirs(OUT, exist_ok=True)

    cat = collections.Counter()
    by_top = collections.defaultdict(collections.Counter)
    dead_modules = []
    rows = []
    for m in mods:
        name = m["module"]
        lines, size = file_stats(name)
        live, aux, decls = int(m["live_decls"]), int(m["aux_decls"]), int(m["decls"])
        if name in FIXED:
            kind = "fixed"
        elif decls == 0:
            kind = "no_decls"  # import だけのモジュール(import の中継)
        elif live == 0 and aux == 0:
            kind = "dead"
        elif live == 0:
            kind = "aux_only"
        else:
            kind = "live"
        if kind == "dead":
            dead_modules.append(name)
        top = name.split(".")[0]
        for key, val in (("modules", 1), ("lines", lines), ("bytes", size)):
            cat[f"{kind}_{key}"] += val
            by_top[top][f"{kind}_{key}"] += val
            cat[f"all_{key}"] += val
            by_top[top][f"all_{key}"] += val
        if kind == "live":
            # 生きているモジュールの中の、使われていない宣言の行
            cat["dead_lines_in_live_modules"] += int(m["dead_lines"])
            cat["aux_lines_in_live_modules"] += int(m["aux_lines"])
            cat["live_decl_lines"] += int(m["live_lines"])
        rows.append({**m, "kind": kind, "file_lines": lines, "file_bytes": size})

    def dup_stats(path):
        groups = collections.defaultdict(list)
        for r in read_tsv(path):
            groups[(r["kind"], r["group"])].append(r)
        out = collections.Counter()
        for (kind, _), rs in groups.items():
            spans = sorted((int(r["end_line"]) - int(r["start_line"]) + 1) if r["start_line"] != "-" else 0 for r in rs)
            out[f"{kind}_groups"] += 1
            out[f"{kind}_extra_copies"] += len(rs) - 1
            out[f"{kind}_extra_copy_lines"] += sum(spans[:-1])  # 最も長い 1 つを残す見積もり
        return out

    dups = dup_stats(os.path.join(ana, "duplicates.tsv"))
    ext = read_tsv(os.path.join(ana, "external-matches.tsv"))
    ext_lines = sum(int(r["end_line"]) - int(r["start_line"]) + 1 for r in ext if r["start_line"] != "-")
    aliases = read_tsv(os.path.join(ana, "aliases.tsv"))
    pure = [a for a in aliases if a["non_bvar_args"] == "0"]
    pure_proj = [a for a in pure if a["target_in_project"] == "true"]

    summary = {
        "analysis_dir": ana,
        "rhshrink": raw,
        "files": {k: v for k, v in sorted(cat.items())},
        "by_top_dir": {t: dict(sorted(c.items())) for t, c in sorted(by_top.items())},
        "duplicates": dict(dups),
        "external_matches": {"theorems": len(ext), "lines": ext_lines},
        "aliases": {"candidates": len(aliases), "pure": len(pure), "pure_to_project": len(pure_proj),
                    "pure_theorems": sum(1 for a in pure if a["kind"] == "theorem"),
                    "pure_defs": sum(1 for a in pure if a["kind"] == "def")},
    }
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    with open(os.path.join(OUT, "dead-modules.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(n + "\n" for n in sorted(dead_modules)))
    zst(os.path.join(OUT, "dead-modules.txt"), os.path.join(OUT, "dead-modules.txt.zst"))
    os.remove(os.path.join(OUT, "dead-modules.txt"))
    tmp = os.path.join(OUT, "modules.tsv")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    zst(tmp, tmp + ".zst")
    os.remove(tmp)
    for f in ("duplicates.tsv", "external-matches.tsv", "aliases.tsv"):
        zst(os.path.join(ana, f), os.path.join(OUT, f + ".zst"))
    for f in ("meta.txt", "log.txt"):
        if not os.path.exists(os.path.join(ana, f)):
            continue
        with open(os.path.join(ana, f), encoding="utf-8") as src, open(os.path.join(OUT, f), "w", encoding="utf-8") as dst:
            dst.write(src.read())

    def pct(a, b):
        return f"{100 * a / b:.1f}%" if b else "-"

    c = cat
    lines = [
        f"解析: {ana}",
        f"配布物のモジュール: {c['all_modules']:,}(行 {c['all_lines']:,}、{c['all_bytes']:,} バイト)",
        f"  live(使われている宣言がある): {c['live_modules']:,} モジュール、{c['live_lines']:,} 行({pct(c['live_lines'], c['all_lines'])})",
        f"  dead(使われている宣言が 1 つもない): {c['dead_modules']:,} モジュール、{c['dead_lines']:,} 行({pct(c['dead_lines'], c['all_lines'])})、{c['dead_bytes']:,} バイト",
        f"  aux だけ: {c['aux_only_modules']:,} モジュール、{c['aux_only_lines']:,} 行",
        f"  宣言なし(import だけ): {c['no_decls_modules']:,} モジュール、{c['no_decls_lines']:,} 行",
        f"  主張(Main・Statements): {c['fixed_modules']:,} モジュール、{c['fixed_lines']:,} 行",
        f"live モジュールの中の行: 使われている宣言 {c['live_decl_lines']:,} 行、使われていない宣言 {c['dead_lines_in_live_modules']:,} 行、aux {c['aux_lines_in_live_modules']:,} 行",
        f"宣言: {raw.get('decls', 0):,}(live {raw.get('live_decls', 0):,}、aux {raw.get('aux_decls', 0):,}、dead {raw.get('dead_decls', 0):,})",
        f"到達可能な配布物の定数: {raw['reachable_project_consts']:,} / {raw.get('project_consts', 0):,}、直接使う外部の定数: {raw['external_consts_used_directly']:,}",
        f"重複: 定理 {dups['theorem_groups']:,} 組(余分 {dups['theorem_extra_copies']:,} 個、{dups['theorem_extra_copy_lines']:,} 行)、"
        f"定義 {dups['def_groups']:,} 組(余分 {dups['def_extra_copies']:,} 個、{dups['def_extra_copy_lines']:,} 行)",
        f"外部と同じ型の定理: {len(ext):,} 個({ext_lines:,} 行)",
        f"純粋な別名: {len(pure):,} 個(定理 {summary['aliases']['pure_theorems']:,}、定義 {summary['aliases']['pure_defs']:,}。配布物の定数を指すもの {len(pure_proj):,})",
        "",
        "トップレベルのディレクトリ別(dead モジュール数 / 全モジュール数、dead の行 / 全行):",
    ]
    for t, cc in sorted(by_top.items(), key=lambda kv: -kv[1]["all_lines"]):
        lines.append(f"  {t}: {cc['dead_modules']:,} / {cc['all_modules']:,} モジュール、{cc['dead_lines']:,} / {cc['all_lines']:,} 行({pct(cc['dead_lines'], cc['all_lines'])})")
    text = "\n".join(lines) + "\n"
    with open(os.path.join(OUT, "summary.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
