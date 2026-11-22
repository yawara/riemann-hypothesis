#!/usr/bin/env python3
"""段階 1a: 主定理の証明に使われていない宣言を消した短縮版のソースを作る。

入力
  lean/src                         配布物のソース(読むだけ)
  --decls  rhshrink の decls.tsv.zst(全宣言の行範囲。既定は runs/shorten/latest-analysis)
  --kept   残す宣言の一覧(モジュール\\t名前)。shorten_source_closure.py の kept-decls.tsv を、
           rhshrink と交互に閉じるまで回した最後のもの
出力(--out。既定は /var/tmp/riemann-hypothesis-ywr/shorten/stage-1a)
  src/、lakefile.toml、lake-manifest.json、lean-toolchain   短縮版の Lake プロジェクト
  stage1a/report.json            変換前後の規模(モジュール・行・空行を除く行・バイト・宣言)
  stage1a/deleted-modules.txt    丸ごと消したモジュール
  stage1a/deleted-decls.tsv      消した宣言(モジュール、名前、行範囲)
  stage1a/protected-decls.tsv    使われていないが残した宣言と理由
  stage1a/open-fixes.tsv         open の行から外した名前空間・名前

規則(1 版目。保守的に)
  * 宣言: --kept に無いものは消す。ただし次は残す
      - `@[… simp …]` の付いたもの(rfl 補題は dsimp が証明項に痕跡を残さず使うことがある)
      - mutual ブロックを含むモジュールの宣言
    消す宣言の直前にある `set_option … in` / `open … in` / `omit … in` / `include … in` / `variable … in` も消す
  * `example` と `#check` などの命令は消す(環境に何も残さない)。範囲は、次に行頭から始まる行の手前まで
  * モジュール: 残る宣言が無く、大域的なメタ命令(行頭の run_cmd・macro・syntax・notation・scoped、local でない
    attribute 命令など)も無ければ丸ごと消す。Main・Statements と、Main が直接 import するモジュールは残す
  * 消したモジュールを import していたモジュールは、そのモジュールの import を(推移的に)引き継ぐ。重複した import は 1 つにする
  * open: 残すモジュールの open で、短縮版で存在しなくなる配布物の名前空間・名前を外す(外すと空になる行は消す)
"""
import argparse
import collections
import json
import multiprocessing as mp
import os
import re
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "lean", "src")
RUN_ROOT = os.environ.get("RH_RUN_ROOT", "/var/tmp/riemann-hypothesis-ywr/runs")
LAKE = "/var/tmp/riemann-hypothesis-ywr/lake"
TOOLCHAIN_LIB = os.path.expanduser("~/.elan/toolchains/leanprover--lean4---v4.33.1/lib/lean")
PROJECT_ROOTS = {"BuildAid", "CompanionTheory", "Development", "Formalism", "GroundTheory", "Lemmata",
                 "PositivityTheory", "ReciprocityTheory", "Supplements", "Main", "Statements"}
FIXED = {"Main", "Statements"}

META_RE = re.compile(r"^(run_cmd|run_elab|run_meta|initialize|builtin_initialize|scoped|notation|notation3|infix|infixl|"
                     r"infixr|prefix|postfix|macro|macro_rules|syntax|elab|elab_rules|declare_syntax_cat|export)\b"
                     r"|^attribute \[(?!local )")
WRAPPER_RE = re.compile(r"^\s*(set_option|open|omit|include|variable)\s.*\sin\s*$")
DROP_CMD_RE = re.compile(r"^(example\b|#(check|eval|print|reduce|guard|exit)\b)")
IMPORT_RE = re.compile(r"^import\s+(\S+)\s*$")
SIMP_RE = re.compile(r"@\[[^\]]*\bsimp\b")
MUTUAL_RE = re.compile(r"^\s*mutual\s*$")
NS_RE = re.compile(r"^\s*(?:noncomputable\s+)?(namespace|section|end)\b\s*(\S*)")
OPEN_RE = re.compile(r"^(\s*)open\s+(.*?)(\s+in)?\s*$")
IDENT = r"[^\s()\[\]{},:;←→]+"
OPEN_SIMPLE_RE = re.compile(rf"^(scoped\s+)?{IDENT}(\s+{IDENT})*$")
OPEN_LIST_RE = re.compile(rf"^(scoped\s+)?{IDENT}\s*(\(.*\)|\s+(renaming|hiding)\s+.*)$")
KEYWORDS = {"in", "private", "protected", "theorem", "lemma", "def", "instance", "example", "from", "noncomputable",
            "abbrev", "structure", "class", "inductive", "where", "with", "at", "by", "fun", "have", "show", "then", "else"}


def is_project_module(m):
    return m.split(".", 1)[0] in PROJECT_ROOTS


def module_path(m):
    return os.path.join(SRC, *m.split(".")) + ".lean"


def prefixes(name):
    parts = name.split(".")
    return [".".join(parts[:k]) for k in range(1, len(parts))]


def ilean_decl_names(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return list(json.load(fh).get("decls", {}).keys())
    except (OSError, ValueError):
        return []


def external_namespaces(jobs):
    """外部(Mathlib・Batteries・Lean 本体など)の宣言名の接頭辞の集合(.ilean の decls から)"""
    roots = [TOOLCHAIN_LIB] + [os.path.join(LAKE, "packages", p, ".lake", "build", "lib", "lean")
                               for p in sorted(os.listdir(os.path.join(LAKE, "packages")))]
    paths = []
    for r in roots:
        for d, _, fs in os.walk(r):
            paths.extend(os.path.join(d, f) for f in fs if f.endswith(".ilean"))
    ns = set()
    with mp.Pool(jobs) as pool:
        for names in pool.imap_unordered(ilean_decl_names, paths, chunksize=64):
            for n in names:
                ns.update(prefixes(n))
    return ns, len(paths)


def drop_span(lines, i):
    """行 i(0 始まり)から始まる命令の範囲 [i, j): 次に行頭から始まる空でない行の手前まで(末尾の空行は含めない)"""
    j = i + 1
    while j < len(lines) and (lines[j].strip() == "" or lines[j][0] in " \t"):
        j += 1
    while j > i + 1 and lines[j - 1].strip() == "":
        j -= 1
    return j


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decls", default=os.path.join(RUN_ROOT, "shorten", "latest-analysis", "decls.tsv.zst"))
    ap.add_argument("--kept", required=True)
    ap.add_argument("--protected", default=None, help="shorten_protect.py の protected.tsv(念のため、ここにある宣言は残す)")
    ap.add_argument("--out", default="/var/tmp/riemann-hypothesis-ywr/shorten/stage-1a")
    ap.add_argument("--jobs", type=int, default=24)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 全モジュール(ソースの一覧から)
    modules = []
    for d, _, fs in os.walk(SRC):
        for f in fs:
            if f.endswith(".lean"):
                modules.append(os.path.relpath(os.path.join(d, f), SRC)[:-5].replace(os.sep, "."))
    modules.sort()
    decls = collections.defaultdict(list)  # モジュール -> [(名前, 種類, 開始行, 終了行)](1 始まり、両端を含む)
    p = subprocess.Popen(["zstd", "-dc", args.decls], stdout=subprocess.PIPE, text=True)
    next(p.stdout)
    for line in p.stdout:
        mod, name, kind, s, e = line.rstrip("\n").split("\t")[:5]
        decls[mod].append((name, kind, int(s), int(e)))
    p.wait()
    with open(args.kept, encoding="utf-8") as fh:
        kept = {tuple(l.rstrip("\n").split("\t", 1)) for l in fh if l.strip()}
    protected_set = {}
    if args.protected:
        with open(args.protected, encoding="utf-8") as fh:
            next(fh)
            for l in fh:
                a, b, r = l.rstrip("\n").split("\t")
                protected_set[(a, b)] = r
    print(f"modules={len(modules)} decls={sum(len(v) for v in decls.values())} kept={len(kept)}", flush=True)

    text = {}
    for m in modules:
        with open(module_path(m), encoding="utf-8") as fh:
            text[m] = fh.read().split("\n")  # 末尾の改行は最後の空要素として残る

    # Main が直接 import するモジュールも残す(Main.lean を書き換えないため)
    fixed = set(FIXED)
    for l in text["Main"]:
        mm = IMPORT_RE.match(l)
        if mm and is_project_module(mm.group(1)):
            fixed.add(mm.group(1))

    # 1. 宣言と命令の削除を行ごとに決める
    deleted_lines = {}       # モジュール -> 消す行(0 始まり)の集合
    deleted_decls = []       # (モジュール, 名前, 開始, 終了)
    protected = []           # (モジュール, 名前, 理由)
    kept_decl_names = set()
    deleted_decl_names = set()
    module_has_kept = {}
    for m in modules:
        lines = text[m]
        n = len(lines)
        has_mutual = any(MUTUAL_RE.match(l) for l in lines)
        cover = [0] * (n + 1)   # 残す宣言が覆う行
        to_delete = []
        any_kept = False
        for name, kind, s, e in decls.get(m, []):
            keep = (m, name) in kept or m in fixed
            if not keep:
                if (m, name) in protected_set:
                    protected.append((m, name, protected_set[(m, name)]))
                    keep = True
                elif has_mutual:
                    protected.append((m, name, "mutual を含むモジュール"))
                    keep = True
            if keep:
                any_kept = True
                kept_decl_names.add(name)
                for i in range(s - 1, e):
                    cover[i] = 1
            else:
                to_delete.append((name, s, e))
        dl = set()
        for name, s, e in to_delete:
            for i in range(s - 1, e):
                if not cover[i]:
                    dl.add(i)
            deleted_decls.append((m, name, s, e))
            deleted_decl_names.add(name)
        for i, l in enumerate(lines):
            if not cover[i] and DROP_CMD_RE.match(l):
                j = drop_span(lines, i)
                dl.update(range(i, j))
        # `… in` の前置きは次の命令に掛かる。次の空でない行が消える命令なら、前置きも消す(下から順に、連なりも)
        nxt = None  # 下から見て、直前に見た空でない行の番号
        for i in range(n - 1, -1, -1):
            if lines[i].strip() == "":
                continue
            if not cover[i] and i not in dl and WRAPPER_RE.match(lines[i]) and (nxt is None or nxt in dl):
                dl.add(i)
            nxt = i
        deleted_lines[m] = dl
        module_has_kept[m] = any_kept

    # 2. 丸ごと消すモジュール
    deleted_modules = set()
    for m in modules:
        if m in fixed or module_has_kept[m]:
            continue
        if any(META_RE.match(l) for l in text[m]):
            continue
        deleted_modules.add(m)
    print(f"deleted modules: {len(deleted_modules)}", flush=True)

    # 3. import のつなぎ直し
    orig_imports = {m: [mm.group(1) for l in text[m] if (mm := IMPORT_RE.match(l))] for m in modules}
    memo = {}

    def expand(m):
        if m in memo:
            return memo[m]
        out = []
        for i in orig_imports[m]:
            if is_project_module(i) and i in deleted_modules:
                out.extend(expand(i))
            else:
                out.append(i)
        res = list(dict.fromkeys(out))
        memo[m] = res
        return res

    # 3b. import の推移簡約: 消したモジュールの import を引き継いだモジュールでは、ほかの import から
    #     推移的に入るものを外す(import の閉包は変わらない)
    import sys
    sys.setrecursionlimit(1_000_000)
    kept_modules = [m for m in modules if m not in deleted_modules]
    idx = {m: k for k, m in enumerate(kept_modules)}
    closure = {}

    def clos(m):
        if m in closure:
            return closure[m]
        c = 0
        for y in expand(m):
            if y in idx:
                c |= (1 << idx[y]) | clos(y)
        closure[m] = c
        return c

    reduced = {}
    for m in kept_modules:
        ex = expand(m)
        if ex == orig_imports[m]:
            continue
        proj = [y for y in ex if y in idx]
        u = 0
        for y in proj:
            u |= clos(y)
        reduced[m] = [y for y in ex if y not in idx or not (u >> idx[y]) & 1]
    print(f"import 推移簡約: {len(reduced)} モジュール", flush=True)

    def new_imports(m):
        return reduced.get(m, orig_imports[m] if expand(m) == orig_imports[m] else expand(m))

    # 4. open の修正: 短縮版で存在しなくなる配布物の名前空間・名前を外す
    ext_ns, n_ext = external_namespaces(args.jobs)
    print(f"external namespaces: {len(ext_ns)} (from {n_ext} .ilean)", flush=True)
    # 名前空間: 短縮版に残るもの(残す宣言の名前の接頭辞と、残すモジュールの namespace 命令)と、
    # 短縮前に配布物にあったもの(全宣言の接頭辞と、全モジュールの namespace 命令)
    ns_kept = set()
    for nm in kept_decl_names:
        ns_kept.update(prefixes(nm))
    ns_before = set()
    for v in decls.values():
        for name, *_ in v:
            ns_before.update(prefixes(name))
    for m in modules:
        stack = []
        for l in text[m]:
            mm = NS_RE.match(l)
            if mm and mm.group(1) == "namespace" and mm.group(2):
                full = ".".join([x for x in stack if x] + [mm.group(2)])
                ns_before.update(prefixes(full + ".x"))
                if m not in deleted_modules:
                    ns_kept.update(prefixes(full + ".x"))
                stack.append(mm.group(2))
            elif mm and mm.group(1) == "section":
                stack.append(None)
            elif mm and mm.group(1) == "end" and stack:
                stack.pop()
    exists = ns_kept | ext_ns
    open_fixes = []

    def vanished(tok, cur, opened):
        """tok が、短縮前は配布物の名前空間として解決でき、短縮版ではどの解決候補も存在しないとき True"""
        if tok.startswith("_root_."):
            return False
        bases = [".".join(cur[:k]) for k in range(1, len(cur) + 1)] + list(opened)
        cands = [tok] + [f"{b}.{tok}" for b in bases]
        if any(c in exists for c in cands):
            return False
        return any(c in ns_before for c in cands)

    new_text = {}
    changes = {}  # モジュール -> (消した行, open の修正, import を変えたか)
    for m in modules:
        if m in deleted_modules:
            continue
        n_fix_before = len(open_fixes)
        lines = text[m]
        dl = deleted_lines[m]
        out = []
        stack = []
        opened = set()
        imports_done = False
        del_since_text = False  # 最後に出した空でない行のあとで、行を消したか
        for i, l in enumerate(lines):
            if IMPORT_RE.match(l):
                if not imports_done:
                    out.extend(f"import {x}" for x in new_imports(m))
                    imports_done = True
                continue
            if i in dl:
                del_since_text = True
                continue
            if l.strip() == "":
                # 消した宣言の前後の空行が続くときは 1 行にまとめる(もともと続いていた空行はそのまま)
                if del_since_text and out and out[-1].strip() == "":
                    continue
                out.append(l)
                continue
            del_since_text = False
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
            om = OPEN_RE.match(l)
            if om and m not in fixed and ((not OPEN_SIMPLE_RE.match(om.group(2)) and not OPEN_LIST_RE.match(om.group(2)))
                                          or KEYWORDS & set(om.group(2).split("(")[0].split())):
                om = None  # 名前空間と名前の並び以外(`open X in theorem …` を 1 行に書いたものなど)は触らない
            if om and m not in fixed:
                indent, body, in_kw = om.group(1), om.group(2), om.group(3) or ""
                cur = [x for x in stack if x]
                if "(" in body or " renaming " in body or " hiding " in body:
                    ns = body.split()[1] if body.startswith("scoped ") else body.split()[0]
                    if vanished(ns, cur, opened):
                        open_fixes.append((m, i + 1, ns, "名前空間が無くなる(行ごと削除)"))
                        del_since_text = True
                        continue
                    for c in [ns] + [f"{b}.{ns}" for b in [".".join(cur[:k]) for k in range(1, len(cur) + 1)] + list(opened)]:
                        if c in exists or c in ns_before:
                            opened.add(c)
                    # 明示した名前のうち、消した宣言だけを指すものを外す
                    if "(" in body and ")" in body:
                        a, b = body.index("("), body.rindex(")")
                        names = body[a + 1:b].split()
                        keep_names = []
                        for x in names:
                            cands = [f"{ns}.{x}"] + [".".join(cur[:k] + [ns, x]) for k in range(1, len(cur) + 1)]
                            if any(c in deleted_decl_names for c in cands) and not any(c in kept_decl_names for c in cands):
                                open_fixes.append((m, i + 1, f"{ns}.{x}", "名前が無くなる"))
                            else:
                                keep_names.append(x)
                        if not keep_names:
                            del_since_text = True
                            continue
                        if len(keep_names) != len(names):
                            l = f"{indent}open {body[:a]}({' '.join(keep_names)}){body[b + 1:]}{in_kw}"
                else:
                    toks = body.split()
                    scoped = toks[:1] == ["scoped"]
                    names = toks[1:] if scoped else toks
                    keep_names = []
                    for x in names:
                        if vanished(x, cur, opened):
                            open_fixes.append((m, i + 1, x, "名前空間が無くなる"))
                        else:
                            keep_names.append(x)
                            # 相対名の候補に使う、開いた名前空間(実在するものだけを足す)
                            for c in [x] + [f"{b}.{x}" for b in [".".join(cur[:k]) for k in range(1, len(cur) + 1)] + list(opened)]:
                                if c in exists or c in ns_before:
                                    opened.add(c)
                    if not keep_names:
                        del_since_text = True
                        continue
                    if len(keep_names) != len(names):
                        l = f"{indent}open {'scoped ' if scoped else ''}{' '.join(keep_names)}{in_kw}"
            out.append(l)
        if not imports_done and new_imports(m):
            out = [f"import {x}" for x in new_imports(m)] + out
        new_text[m] = out
        changes[m] = (len(dl), len(open_fixes) - n_fix_before, new_imports(m) != orig_imports[m], out != lines)

    # 5. 集計
    def stats(texts):
        st = collections.Counter()
        for lines in texts:
            body = "\n".join(lines)
            st["modules"] += 1
            st["lines"] += body.count("\n")  # README の数え方(改行の数)と同じ
            st["nonblank_lines"] += sum(1 for x in lines if x.strip())
            st["bytes"] += len(body.encode("utf-8"))
        return st

    before = stats(text.values())
    after = stats(new_text.values())
    after["decls"] = len(kept_decl_names)
    before["decls"] = sum(len(v) for v in decls.values())
    report = {
        "kept_list": os.path.realpath(args.kept),
        "decls_source": os.path.realpath(args.decls),
        "before": dict(before), "after": dict(after),
        "deleted_modules": len(deleted_modules),
        "deleted_decls": len(deleted_decls),
        "protected_decls": collections.Counter(r for _, _, r in protected),
        "open_fixes": collections.Counter(r for *_, r in open_fixes),
        "open_fixes_top": collections.Counter(x for _, _, x, _ in open_fixes).most_common(25),
    }
    print(json.dumps(report, ensure_ascii=False, indent=1, default=dict), flush=True)
    if args.dry_run:
        return

    # 6. 書き出し
    out = args.out
    if os.path.exists(os.path.join(out, "src")):
        shutil.rmtree(os.path.join(out, "src"))
    os.makedirs(os.path.join(out, "stage1a"), exist_ok=True)
    for f in ("lakefile.toml", "lake-manifest.json", "lean-toolchain"):
        shutil.copy2(os.path.join(ROOT, "lean", f), os.path.join(out, f))
    for m, lines in new_text.items():
        path = os.path.join(out, "src", *m.split(".")) + ".lean"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    rec = os.path.join(out, "stage1a")
    with open(os.path.join(rec, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, default=dict)
        fh.write("\n")
    with open(os.path.join(rec, "deleted-modules.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(x + "\n" for x in sorted(deleted_modules)))
    with open(os.path.join(rec, "deleted-decls.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tdecl\tstart_line\tend_line\n")
        fh.write("".join(f"{a}\t{b}\t{c}\t{d}\n" for a, b, c, d in sorted(deleted_decls)))
    with open(os.path.join(rec, "protected-decls.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tdecl\treason\n")
        fh.write("".join(f"{a}\t{b}\t{c}\n" for a, b, c in sorted(protected)))
    with open(os.path.join(rec, "changes.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tdeleted_lines\topen_fixes\timports_changed\tchanged\n")
        fh.write("".join(f"{m}\t{a}\t{b}\t{int(c)}\t{int(d)}\n" for m, (a, b, c, d) in sorted(changes.items())))
    with open(os.path.join(rec, "open-fixes.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tline\tname\treason\n")
        fh.write("".join(f"{a}\t{b}\t{c}\t{d}\n" for a, b, c, d in open_fixes))
    print(f"wrote {out}", flush=True)



if __name__ == "__main__":
    main()
