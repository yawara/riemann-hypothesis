#!/usr/bin/env python3
"""段階 1a の下ごしらえ: カーネルの項で使われる宣言に、ソースで参照される宣言を足した閉包を求める。

rhshrink の解析(カーネルの項の上での到達可能性)では、証明項に痕跡を残さない参照、たとえば
`simp [X]` で結局使われなかった `X` や、失敗した分岐の中の名前は数えない。こうした宣言を消すと、
ソースをビルドし直したときにエラーになりうる。そこで、Lean がビルドのたびに書き出す `.ilean`
(エディタ用の参照情報。参照ごとに、それを含む宣言の名前がつく)から、ソース上の参照のグラフを作り、
「カーネルの項で使われる宣言」から出発して、ソースで参照される宣言を推移的に足す。

マクロ(`macro`・`macro_rules`・`elab`・`elab_rules`)の本文に書かれた名前は、定義の時点では解決されず、
展開した先の参照も .ilean に残らない(位置が合成されたものになる)。`simp only [X]` の X が rfl の補題なら証明項にも
現れない。そこで、マクロの本文の識別子を、定義の位置の名前空間と open を踏まえて配布物の宣言に解決し、
マクロのキーワードが現れる宣言(local のマクロは同じモジュールの定義より後ろ、それ以外は定義したモジュールを
import するモジュールも含む)からの参照とみなす。マクロの中で別のマクロを使っていれば、その参照も含める。

足した宣言自身の証明項が使う定数(カーネルの辺)は、この閉包には入らない。足した宣言を起点に
rhshrink をもう一度走らせ(--roots)、両方の辺で閉じるまで繰り返す。

入力: rhshrink の decls.tsv.zst(既定は runs/shorten/latest-analysis)、配布物のビルド結果の .ilean
出力: <出力先>/source-closure.json(集計)、added-decls.tsv(足した宣言と、最初に参照した宣言)、
      added-roots.txt(rhshrink に渡す起点)、kept-decls.tsv(残す宣言)、
      module-refs.tsv(宣言の外からの参照の位置。shorten_stage1a.py が attribute・open の名前を外すのに使う)、
      macro-refs.tsv(マクロの本文の識別子と、解決した宣言)、macro-uses.tsv(マクロを使う場所と、その持ち主)

使い方: python3 -I scripts/shorten_source_closure.py [--analysis DIR] [--extra-live FILE] [--out DIR]
  --extra-live: 前回までに残すと決めた宣言の一覧(kept-decls.tsv。モジュール\t名前)
"""
import argparse
import collections
import json
import multiprocessing as mp
import os
import re
import subprocess

RUN_ROOT = os.environ.get("RH_RUN_ROOT", "/var/tmp/riemann-hypothesis-ywr/runs")
ILEAN_ROOT = "/var/tmp/riemann-hypothesis-ywr/lake/build/lib/lean"
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lean", "src")
MACRO_PAT = r"^(@\[[^]]*\] *)?(private |protected )?(local |scoped )?(macro_rules|macro|elab_rules|elab)\b"
MACRO_RE = re.compile(r"^(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+)?(local\s+|scoped\s+)?(macro_rules|macro|elab_rules|elab)\b")
IMPORT_RE = re.compile(r"^import\s+(\S+)\s*$")
STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
COMMENT_RE = re.compile(r"--.*$", re.M)
NS_RE = re.compile(r"^\s*(?:noncomputable\s+)?(namespace|section|end)\b\s*(\S*)")
OPEN_HEAD_RE = re.compile(r"^\s*open\s")
MACRO_KW_RE = re.compile(r'(?:macro|elab)(?::\w+)?\s+"([^"]+)"')
ANTIQUOT_RE = re.compile(r"\$[^\s()\[\]{},;]+")
TOKEN_RE = re.compile(r"[^\s()\[\]{},:;`\"$|⟨⟩←→↦=<>+*/\\^&%#@~·]+")
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
    modrefs = []  # 宣言の外からの参照: (行, 列, 終わりの行, 終わりの列, 参照先モジュール, 参照先の名前)。行・列は 0 始まり
    for key, v in d.get("references", {}).items():
        if not key.startswith('{"c":'):
            continue
        c = json.loads(key)["c"]
        m, n = c["m"], c["n"]
        for u in v.get("usages", []):
            if len(u) < 5:
                modrefs.append((u[0], u[1], u[2], u[3], m, n))
            if is_project(m):
                edges.add((u[4] if len(u) >= 5 else None, m, n))
    return module, sorted(edges, key=lambda e: (e[0] or "", e[1], e[2])), sorted(modrefs)


def module_lines(module):
    with open(os.path.join(SRC, *module.split(".")) + ".lean", encoding="utf-8") as fh:
        return fh.read().split("\n")


def import_graph():
    """配布物のモジュールの import(順方向)を、ソースの import 行から読む"""
    p = subprocess.run(["grep", "-rE", r"^import\s", SRC, "--include=*.lean"], capture_output=True, text=True)
    fwd = collections.defaultdict(list)
    for line in p.stdout.splitlines():
        path, _, rest = line.partition(":")
        mm = IMPORT_RE.match(rest)
        if mm and is_project(mm.group(1)):
            fwd[os.path.relpath(path, SRC)[:-5].replace(os.sep, ".")].append(mm.group(1))
    return fwd


def macro_table(decl_keys, fwd):
    """マクロ(macro・elab)ごとに、キーワードと、本文の識別子が指す配布物の宣言を求める。

    構文の引用の中の名前は、マクロを定義した位置で解決される(展開した先ではそれを使う)ので、定義の位置の
    名前空間(とその接頭辞)と、それより前の open で開いた名前空間を前に付けた名前を候補にし、import の閉包
    (自身を含む)にある宣言と完全に一致するものを取る。private の宣言は同じモジュールのものだけ。
    `$x` の形の反引用は識別子ではないので外す。
    返り値: [{"mod", "line", "end"(1 始まり、両端を含む), "kw", "local", "refs": [(識別子, (モジュール, 名前))]}]"""
    p = subprocess.run(["grep", "-rlE", MACRO_PAT, SRC, "--include=*.lean"], capture_output=True, text=True)
    mods = sorted(os.path.relpath(f, SRC)[:-5].replace(os.sep, ".") for f in p.stdout.split())
    by_name = collections.defaultdict(list)
    for m, n in decl_keys:
        if n.startswith("_private."):
            k = n.find(".0.")
            by_name[n[k + 3:] if k >= 0 else n].append((m, n, True))
        else:
            by_name[n].append((m, n, False))
    out = []
    for mod in mods:
        lines = module_lines(mod)
        seen = {mod}
        todo = [mod]
        while todo:
            for y in fwd.get(todo.pop(), ()):
                if y not in seen:
                    seen.add(y)
                    todo.append(y)
        stack = []      # 名前空間の成分(section は None)
        opened = set()  # ここまでの open で開いた名前空間の候補(section の終わりで閉じるのは無視して多めに取る。
                        # 開いた名前空間からの相対名は数えない)
        for i, l in enumerate(lines):
            mm = NS_RE.match(l)
            if mm and mm.group(1) == "namespace" and mm.group(2):
                stack.extend(mm.group(2).split("."))
            elif mm and mm.group(1) == "section":
                stack.append(None)
            elif mm and mm.group(1) == "end":
                if stack and stack[-1] is None:
                    stack.pop()
                else:
                    for _ in (mm.group(2).split(".") if mm.group(2) else [""]):
                        if stack and stack[-1] is not None:
                            stack.pop()
            cur = [x for x in stack if x]
            bases = [".".join(cur[:k]) for k in range(1, len(cur) + 1)]
            om = OPEN_HEAD_RE.match(l)
            if om:
                j = i + 1
                while j < len(lines) and lines[j].strip() != "" and lines[j][0] in " \t":
                    j += 1
                for tok in TOKEN_RE.findall(" ".join(lines[i:j])[om.end():]):
                    if tok in ("scoped", "in", "hiding", "renaming", "open"):
                        continue
                    opened.update([tok] + [f"{b}.{tok}" for b in bases])
                continue
            mm = MACRO_RE.match(l)
            if not mm:
                continue
            j = i + 1
            while j < len(lines) and (lines[j].strip() == "" or lines[j][0] in " \t"):
                j += 1
            while j > i + 1 and lines[j - 1].strip() == "":
                j -= 1
            km = MACRO_KW_RE.search(l)
            body = "\n".join(lines[i:j])
            body = ANTIQUOT_RE.sub(" ", COMMENT_RE.sub("", STRING_RE.sub(" ", body)))
            pre = bases + sorted(opened)
            refs = []
            for tok in sorted(set(TOKEN_RE.findall(body))):
                tok = tok.strip(".")
                if not tok or not any(ch.isalpha() for ch in tok):
                    continue
                cands = [tok[len("_root_."):]] if tok.startswith("_root_.") else [tok] + [f"{b}.{tok}" for b in pre]
                for c in cands:
                    for (m2, n2, priv) in by_name.get(c, ()):
                        if (m2 == mod) if priv else (m2 in seen):
                            refs.append((tok, (m2, n2)))
            out.append({"mod": mod, "line": i + 1, "end": j, "kw": km.group(1).strip() if km else None,
                        "local": (mm.group(1) or "").strip() == "local", "refs": refs})
    return out


def macro_uses(macros, fwd, decl_ranges):
    """マクロを使う場所を、キーワードの出現で探す。返り値: [(使うモジュール, 行, マクロの番号, 持ち主)]
    持ち主は ("decl", (モジュール, 名前))・("macro", 番号)・("module", モジュール) のどれか。
    local のマクロは同じモジュールの定義より後ろ、それ以外は同じモジュールの後ろと、定義したモジュールを
    (推移的に)import するモジュール(scoped でも open の有無は見ず、多めに取る)"""
    kws = sorted({mc["kw"] for mc in macros if mc["kw"]})
    if not kws:
        return []
    by_kw = collections.defaultdict(list)
    for k, mc in enumerate(macros):
        if mc["kw"]:
            by_kw[mc["kw"]].append(k)
    rev = collections.defaultdict(list)
    for a, bs in fwd.items():
        for b in bs:
            rev[b].append(a)
    importers = {}

    def importers_of(m):
        if m not in importers:
            seen = set()
            todo = [m]
            while todo:
                for y in rev.get(todo.pop(), ()):
                    if y not in seen:
                        seen.add(y)
                        todo.append(y)
            importers[m] = seen
        return importers[m]

    def kw_re(k):
        a = r"(?<![\w.'!?])" if (k[0].isalnum() or k[0] == "_") else ""
        b = r"(?![\w'!?])" if (k[-1].isalnum() or k[-1] in "_'!?") else ""
        return re.compile(a + re.escape(k) + b)

    kre = {k: kw_re(k) for k in kws}
    p = subprocess.run(["grep", "-rnF", *sum((["-e", k] for k in kws), []), SRC, "--include=*.lean"],
                       capture_output=True, text=True)
    macros_by_mod = collections.defaultdict(list)
    for k, mc in enumerate(macros):
        macros_by_mod[mc["mod"]].append(k)
    out = []
    for line in p.stdout.splitlines():
        path, _, rest = line.partition(":")
        ln, _, txt = rest.partition(":")
        mod = os.path.relpath(path, SRC)[:-5].replace(os.sep, ".")
        ln = int(ln)
        txt = COMMENT_RE.sub("", txt)
        inner = [k2 for k2 in macros_by_mod.get(mod, ()) if macros[k2]["line"] <= ln <= macros[k2]["end"]]
        for kw in kws:
            if kw not in txt or not kre[kw].search(txt):
                continue
            for k in by_kw[kw]:
                mc = macros[k]
                if k in inner:
                    continue   # 定義そのもの
                if mod == mc["mod"]:
                    if ln <= mc["end"]:
                        continue
                elif mc["local"] or mod not in importers_of(mc["mod"]):
                    continue
                if inner:
                    out.extend((mod, ln, k, ("macro", k2)) for k2 in inner)
                    continue
                owners = [d for d, (s_, e_) in decl_ranges.get(mod, {}).items() if s_ <= ln <= e_]
                if owners:
                    out.extend((mod, ln, k, ("decl", d)) for d in owners)
                else:
                    out.append((mod, ln, k, ("module", mod)))
    return out


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
    unresolved_list = collections.Counter()
    modrefs_fh = open(os.path.join(out, "module-refs.tsv"), "w", encoding="utf-8")
    modrefs_fh.write("module\tline\tcol\tend_line\tend_col\tref_module\tref_name\n")
    with mp.Pool(args.jobs) as pool:
        for i, (mod, es, mrs) in enumerate(pool.imap_unordered(parse_ilean, modules, chunksize=64)):
            for a, b, c, e, m, n in mrs:
                modrefs_fh.write(f"{mod}\t{a}\t{b}\t{c}\t{e}\t{m}\t{n}\n")
            for src, m, n in es:
                d = owner(m, n)
                if d is None:
                    unresolved += 1
                    unresolved_list[(m, n)] += 1
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
    modrefs_fh.close()
    print(f"edges from {len(edges)} decls, module-level refs in {len(module_refs)} modules, unresolved refs {unresolved}", flush=True)

    # マクロ: 本文の識別子が指す宣言を、マクロを使う宣言(マクロの中で使われていればその先を辿る)からの参照とみなす
    fwd = import_graph()
    macros = macro_table(decls.keys(), fwd)
    decl_ranges = collections.defaultdict(dict)
    for (m, n), (_, s_, e_, _) in decls.items():
        decl_ranges[m][(m, n)] = (s_, e_)
    uses = macro_uses(macros, fwd, decl_ranges)
    inner_uses = collections.defaultdict(set)
    for _, _, k, (kind, who) in uses:
        if kind == "macro":
            inner_uses[who].add(k)
    full_refs = {}

    def refs_of(k, path=()):
        if k in full_refs:
            return full_refs[k]
        r = {d for _, d in macros[k]["refs"]}
        for k2 in inner_uses.get(k, ()):
            if k2 not in path and k2 != k:
                r |= refs_of(k2, path + (k,))
        full_refs[k] = r
        return r

    n_macro_edges = 0
    for _, _, k, (kind, who) in uses:
        if kind == "decl":
            for d in refs_of(k):
                if d != who and d not in edges[who]:
                    edges[who].add(d)
                    n_macro_edges += 1
        elif kind == "module":
            module_refs[who] |= refs_of(k)
    with open(os.path.join(out, "macro-refs.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tline\tkeyword\tlocal\ttoken\tref_module\tref_name\n")
        for mc in macros:
            for tok, d in mc["refs"]:
                fh.write(f"{mc['mod']}\t{mc['line']}\t{mc['kw']}\t{int(mc['local'])}\t{tok}\t{d[0]}\t{d[1]}\n")
    with open(os.path.join(out, "macro-uses.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tline\tkeyword\tmacro_module\tmacro_line\towner_kind\towner\n")
        for mod, ln, k, (kind, who) in uses:
            w = who[1] if kind == "decl" else (f"{macros[who]['mod']}:{macros[who]['line']}" if kind == "macro" else who)
            fh.write(f"{mod}\t{ln}\t{macros[k]['kw']}\t{macros[k]['mod']}\t{macros[k]['line']}\t{kind}\t{w}\n")
    print(f"macros: {len(macros)}, body refs {sum(len(mc['refs']) for mc in macros)}, uses {len(uses)}, "
          f"new edges {n_macro_edges}", flush=True)

    # 閉包: カーネルで使われる宣言から出発し、ソースの参照を辿る。宣言が 1 つでも残るモジュールでは、宣言の外の参照も辿る
    kept = set(live)
    added = {}  # 足した宣言 -> 最初に参照した宣言(または "module:<モジュール>")
    kept_modules = {k[0] for k in kept}
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
        "macros": len(macros),
        "macro_body_refs": sum(len(mc["refs"]) for mc in macros),
        "macro_uses": len(uses),
        "macro_edges_added": n_macro_edges,
    }
    with open(os.path.join(out, "source-closure.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    with open(os.path.join(out, "unresolved-refs.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tconstant\tcount\n")
        fh.write("".join(f"{m}\t{n}\t{c}\n" for (m, n), c in unresolved_list.most_common()))
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
