#!/usr/bin/env python3
"""段階 1a: 主定理の証明に使われていない宣言を消した短縮版のソースを作る。

入力
  lean/src         配布物のソース(読むだけ)
  --decls          rhshrink の decls.tsv.zst(全宣言の行範囲)
  --kept           残す宣言の一覧(モジュール\\t名前)。shorten_source_closure.py の kept-decls.tsv を、
                   rhshrink と交互に閉じるまで回した最後のもの
  --protected      shorten_protect.py の protected.tsv(念のため、ここにある宣言も残す)
  --module-refs    shorten_source_closure.py の module-refs.tsv(宣言の外からの参照の位置。.ilean 由来)
出力(--out。既定は /var/tmp/riemann-hypothesis-ywr/shorten/stage-1a)
  src/、lakefile.toml、lake-manifest.json、lean-toolchain   短縮版の Lake プロジェクト
  stage1a/report.json            変換前後の規模(モジュール・行・空行を除く行・バイト・宣言)
  stage1a/deleted-modules.txt    丸ごと消したモジュール
  stage1a/deleted-decls.tsv      消した宣言(モジュール、名前、行範囲)
  stage1a/protected-decls.tsv    --kept に無いが残した宣言と理由(閉包が正しければ空)
  stage1a/edits.tsv              宣言の外の行に加えた修正(open・attribute から外した名前など)
  stage1a/changes.tsv            モジュールごとの変更の有無

規則
  * 宣言: --kept に無いものは消す(--protected にあるもの、mutual ブロックを含むモジュールのものは残す)。
  * 消す命令に掛かる前置き(`set_option … in` / `open … in` / `omit … in` / `include … in` / `variable … in` /
    `attribute […] … in` / `unseal … in` / `universe … in`。2 行以上にわたるもの、空行を挟むもの、連なったものを含む)も消す。
  * `example` と `#check` などの命令は消す(環境に何も残さない)。範囲は、次に行頭から始まる行の手前まで。
  * attribute 命令と `open X (名前 …)`・`export X (名前 …)` からは、消す宣言を指す名前を外す(位置は .ilean の参照で
    特定する。字下げで続く行も含む)。名前が残らなければ命令ごと消す(`attribute […] … in` の前置きも)。
  * モジュール: 残る宣言が無く、次のどれも無ければ丸ごと消す。Main・Statements と、Main が直接 import するモジュールは残す。
      - 宣言の外の大域的なメタ命令(run_cmd・macro_rules・initialize・export など)
      - local でない attribute 命令で、消さない定数(配布物の外の定数を含む)を指すもの
  * 消したモジュールを import していたモジュールは、その import を(推移的に)引き継ぎ、推移簡約する(閉包は変わらない)。
  * open・export: その位置から見えなくなる配布物の名前空間を外す(import の閉包の中に、その名前空間の宣言や
    namespace 命令が残っているか、同じモジュールのそれより前に namespace 命令か残す宣言があるかで判定する。
    字下げで続く行も含む)。外すと空になる行は消し、名前空間が 1 つも残らなければ命令ごと消す。
    ただし、同じモジュールの後ろで初めて現れる名前空間で、その名前空間の外から短い名前で参照される
    (.ilean の参照で判定)ものは open に残し、その前に `namespace X end X` の 1 行を入れて名前空間を作る。
  * 消した宣言や行の前後で続いた空行は 1 行にまとめる(もともと続いていた空行はそのまま)。
"""
import argparse
import collections
import json
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "lean", "src")
LAKE = "/var/tmp/riemann-hypothesis-ywr/lake"
TOOLCHAIN_LIB = os.path.expanduser("~/.elan/toolchains/leanprover--lean4---v4.33.1/lib/lean")
ILEAN_ROOT = os.path.join(LAKE, "build", "lib", "lean")   # 配布物のビルド結果の .ilean
PROJECT_ROOTS = {"BuildAid", "CompanionTheory", "Development", "Formalism", "GroundTheory", "Lemmata",
                 "PositivityTheory", "ReciprocityTheory", "Supplements", "Main", "Statements"}
FIXED = {"Main", "Statements"}

META_CMD_RE = re.compile(r"^(run_cmd|run_elab|run_meta|initialize|builtin_initialize|scoped|notation|notation3|infix|"
                         r"infixl|infixr|prefix|postfix|macro|macro_rules|syntax|elab|elab_rules|declare_syntax_cat|"
                         r"export|binder_predicate)\b")
ATTR_RE = re.compile(r"^(\s*)attribute\s+\[([^\]]*)\]")
WRAP_START_RE = re.compile(r"^\s*(set_option|open|omit|include|variable|attribute|unseal|universe)\b")
WRAP_END_RE = re.compile(r"\sin\s*$")
DROP_CMD_RE = re.compile(r"^(example\b|#(check|eval|print|reduce|guard|exit)\b)")
IMPORT_RE = re.compile(r"^import\s+(\S+)\s*$")
MUTUAL_RE = re.compile(r"^\s*mutual\s*$")
NS_RE = re.compile(r"^\s*(?:noncomputable\s+)?(namespace|section|end)\b\s*(\S*)")
OPEN_RE = re.compile(r"^(\s*)open\s+(.*?)(\s+in)?\s*$")
EXPORT_RE = re.compile(r"^(\s*)export\s+([^\s(]+)\s*\(")
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


def unpriv(n):
    """`_private.<モジュール>.0.<名前>` を <名前> に直す"""
    if n and n.startswith("_private."):
        k = n.find(".0.")
        return n[k + 3:] if k >= 0 else n
    return n


def module_ilean_refs(m):
    """配布物のモジュール m の .ilean から、配布物の定数への参照を (行, 列, 終わりの行, 終わりの列, 名前, 持ち主) で返す
    (行・列は 0 始まり、列は UTF-16。名前と持ち主は private の接頭辞を外したもの。持ち主は宣言の外なら None)"""
    try:
        with open(os.path.join(ILEAN_ROOT, *m.split(".")) + ".ilean", encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return []
    out = []
    for key, v in d.get("references", {}).items():
        if not key.startswith('{"c":'):
            continue
        c = json.loads(key)["c"]
        if not is_project_module(c["m"]):
            continue
        for u in v.get("usages", []):
            out.append((u[0], u[1], u[2], u[3], unpriv(c["n"]), unpriv(u[4]) if len(u) >= 5 else None))
    return out


def drop_span(lines, i):
    """行 i(0 始まり)から始まる命令の範囲 [i, j): 次に行頭から始まる空でない行の手前まで(末尾の空行は含めない)"""
    j = i + 1
    while j < len(lines) and (lines[j].strip() == "" or lines[j][0] in " \t"):
        j += 1
    while j > i + 1 and lines[j - 1].strip() == "":
        j -= 1
    return j


def cont_span(lines, i):
    """行 i から始まる命令が、字下げした続きの行を含めてどこまで続くか [i, j)"""
    j = i + 1
    while j < len(lines) and lines[j].strip() != "" and lines[j][0] in " \t":
        j += 1
    return j


def u16_to_idx(s, u16):
    """UTF-16 の位置(.ilean の列)を Python の文字位置に直す"""
    k = 0
    for idx, ch in enumerate(s):
        if k >= u16:
            return idx
        k += 2 if ord(ch) > 0xFFFF else 1
    return len(s)


def cut_spans(line, spans):
    """line から spans(文字位置の [a, b) の並び)を取り除き、取り除いた所の空白を詰める"""
    out = line
    for a, b in sorted(spans, reverse=True):
        left, right = out[:a], out[b:]
        if left.endswith(" ") and right.startswith(" "):
            right = right.lstrip(" ")
        elif left.endswith(" ") and (right.startswith(")") or right == ""):
            left = left.rstrip(" ")
        elif left.endswith("(") and right.startswith(" "):
            right = right.lstrip(" ")
        out = left + right
    return out.rstrip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decls", required=True)
    ap.add_argument("--kept", required=True)
    ap.add_argument("--protected", default=None)
    ap.add_argument("--module-refs", required=True)
    ap.add_argument("--out", default="/var/tmp/riemann-hypothesis-ywr/shorten/stage-1a")
    ap.add_argument("--jobs", type=int, default=24)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.setrecursionlimit(1_000_000)

    # ---- 読み込み
    modules = []
    for d, _, fs in os.walk(SRC):
        for f in fs:
            if f.endswith(".lean"):
                modules.append(os.path.relpath(os.path.join(d, f), SRC)[:-5].replace(os.sep, "."))
    modules.sort()
    decls = collections.defaultdict(list)  # モジュール -> [(名前, 開始行, 終了行)](1 始まり、両端を含む)
    p = subprocess.Popen(["zstd", "-dc", args.decls], stdout=subprocess.PIPE, text=True)
    next(p.stdout)
    for line in p.stdout:
        mod, name, kind, s, e = line.rstrip("\n").split("\t")[:5]
        decls[mod].append((name, int(s), int(e)))
    p.wait()
    with open(args.kept, encoding="utf-8") as fh:
        kept = {tuple(l.rstrip("\n").split("\t", 1)) for l in fh if l.strip()}
    protected_in = {}
    if args.protected:
        with open(args.protected, encoding="utf-8") as fh:
            next(fh)
            for l in fh:
                a, b, r = l.rstrip("\n").split("\t")
                protected_in[(a, b)] = r
    modrefs = collections.defaultdict(list)  # モジュール -> [(行, 列, 終わりの行, 終わりの列, 参照先モジュール, 名前)]
    with open(args.module_refs, encoding="utf-8") as fh:
        next(fh)
        for l in fh:
            m, a, b, c, e, rm, rn = l.rstrip("\n").split("\t")
            modrefs[m].append((int(a), int(b), int(c), int(e), rm, rn))
    text = {}
    for m in modules:
        with open(module_path(m), encoding="utf-8") as fh:
            text[m] = fh.read().split("\n")
    print(f"modules={len(modules)} decls={sum(len(v) for v in decls.values())} kept={len(kept)} "
          f"module-refs={sum(len(v) for v in modrefs.values())}", flush=True)

    fixed = set(FIXED)
    for l in text["Main"]:
        mm = IMPORT_RE.match(l)
        if mm and is_project_module(mm.group(1)):
            fixed.add(mm.group(1))

    # ---- 1. 宣言ごとの残す・消す
    keep_decl = {}             # (モジュール, 名前) -> bool
    protected = []
    for m in modules:
        has_mutual = any(MUTUAL_RE.match(l) for l in text[m])
        for name, s, e in decls.get(m, []):
            k = (m, name) in kept or m in fixed
            if not k and (m, name) in protected_in:
                protected.append((m, name, protected_in[(m, name)]))
                k = True
            elif not k and has_mutual:
                protected.append((m, name, "mutual を含むモジュール"))
                k = True
            keep_decl[(m, name)] = k
    names_by_module = {m: {n for n, _, _ in v} for m, v in decls.items()}

    def owner(m, n):
        names = names_by_module.get(m)
        while names and n:
            if n in names:
                return n
            if "." not in n:
                return None
            n = n.rsplit(".", 1)[0]
        return None

    def ref_deleted(rm, rn):
        """参照先の定数が、短縮版で消える宣言に属するか(配布物の外や、帰属できない定数は消えないとみなす)"""
        if not is_project_module(rm):
            return False
        o = owner(rm, rn)
        return o is not None and not keep_decl[(rm, o)]

    # ---- 2. 消す行(宣言、命令、前置き)
    deleted_lines = {}
    deleted_decls = []
    kept_names_by_module = collections.defaultdict(set)
    for m in modules:
        lines = text[m]
        n = len(lines)
        cover = [False] * (n + 1)
        to_delete = []
        for name, s, e in decls.get(m, []):
            if keep_decl[(m, name)]:
                kept_names_by_module[m].add(name)
                for i in range(s - 1, e):
                    cover[i] = True
            else:
                to_delete.append((name, s, e))
        dl = set()
        for name, s, e in to_delete:
            dl.update(i for i in range(s - 1, e) if not cover[i])
            deleted_decls.append((m, name, s, e))
        for i, l in enumerate(lines):
            if not cover[i] and DROP_CMD_RE.match(l):
                dl.update(range(i, drop_span(lines, i)))
        # 前置き(1 行または字下げで続く複数行で、` in` で終わるもの)は次の命令に掛かる。
        # 次の空でない行が消えるなら前置きも消す(下から順に見るので、連なった前置きも消える)
        nxt = None
        i = n - 1
        while i >= 0:
            if lines[i].strip() == "":
                i -= 1
                continue
            if not cover[i] and i not in dl and WRAP_END_RE.search(lines[i]):
                j = i
                while j > 0 and lines[j][:1] in (" ", "\t") and not cover[j - 1] and lines[j - 1].strip() != "":
                    j -= 1
                if WRAP_START_RE.match(lines[j]) and not any(cover[k] for k in range(j, i + 1)):
                    if nxt is None or nxt in dl:
                        dl.update(range(j, i + 1))
                    nxt = j
                    i = j - 1
                    continue
            nxt = i
            i -= 1
        deleted_lines[m] = dl

    # ---- 3. 丸ごと消すモジュール
    def attr_spans(m):
        lines = text[m]
        out = []
        for i, l in enumerate(lines):
            mm = ATTR_RE.match(l)
            if mm and not l[:1].isspace():
                out.append((i, cont_span(lines, i), mm.group(2).strip().startswith("local")))
        return out

    refs_by_line = {}

    def module_refs_by_line(m):
        if m not in refs_by_line:
            d = collections.defaultdict(list)
            for r in modrefs.get(m, ()):
                d[r[0]].append(r)
            refs_by_line[m] = d
        return refs_by_line[m]

    deleted_modules = set()
    keep_reason = collections.Counter()
    for m in modules:
        if m in fixed or kept_names_by_module[m]:
            continue
        lines = text[m]
        dl = deleted_lines[m]
        if any(META_CMD_RE.match(l) for i, l in enumerate(lines) if i not in dl):
            keep_reason["宣言の外のメタ命令"] += 1
            continue
        rbl = module_refs_by_line(m)
        live_global_attr = False
        for s, e, is_local in attr_spans(m):
            if is_local:
                continue
            for i in range(s, e):
                for r in rbl.get(i, ()):
                    if not ref_deleted(r[4], r[5]):
                        live_global_attr = True
        if live_global_attr:
            keep_reason["消さない定数を指す大域的な attribute"] += 1
            continue
        deleted_modules.add(m)
    print(f"deleted modules: {len(deleted_modules)}; kept without decls: {dict(keep_reason)}", flush=True)

    # ---- 4. import のつなぎ直しと推移簡約
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
        memo[m] = list(dict.fromkeys(out))
        return memo[m]

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

    new_imports = {}
    for m in kept_modules:
        ex = expand(m)
        if ex == orig_imports[m]:
            new_imports[m] = ex
            continue
        u = 0
        for y in ex:
            if y in idx:
                u |= clos(y)
        new_imports[m] = [y for y in ex if y not in idx or not (u >> idx[y]) & 1]
    print("imports rewired", flush=True)

    # ---- 5. 名前空間が見えるか(そのモジュールの import の閉包に、名前空間の宣言か namespace 命令が残るか)
    ext_ns, n_ext = external_namespaces(args.jobs)
    print(f"external namespaces: {len(ext_ns)} (from {n_ext} .ilean)", flush=True)
    ns_mods = collections.defaultdict(set)
    ns_before = set()
    for m in modules:
        for name, _, _ in decls.get(m, []):
            ps = prefixes(name)
            ns_before.update(ps)
            if m in idx and keep_decl[(m, name)]:
                for q in ps:
                    ns_mods[q].add(idx[m])
        stack = []
        for i, l in enumerate(text[m]):
            mm = NS_RE.match(l)
            if mm and mm.group(1) == "namespace" and mm.group(2):
                full = ".".join([x for x in stack if x] + [mm.group(2)])
                ns_before.update(prefixes(full + ".x"))
                if m in idx and i not in deleted_lines[m]:
                    for q in prefixes(full + ".x"):
                        ns_mods[q].add(idx[m])
                stack.append(mm.group(2))
            elif mm and mm.group(1) == "section":
                stack.append(None)
            elif mm and mm.group(1) == "end" and stack:
                stack.pop()
    bits_cache = {}

    def ns_bits(q):
        if q not in bits_cache:
            b = 0
            for k in ns_mods.get(q, ()):
                b |= 1 << k
            bits_cache[q] = b
        return bits_cache[q]

    # ---- 6. 書き出す本文
    edits = []      # (モジュール, 行, 種類, 内容)
    new_text = {}
    changes = {}
    for m in kept_modules:
        lines = text[m]
        if m in fixed:
            new_text[m] = lines
            changes[m] = (0, 0, False, False)
            continue
        dl = set(deleted_lines[m])
        rbl = module_refs_by_line(m)
        # attribute 命令: 消す宣言を指す名前を外す。名前が残らなければ命令ごと消す
        replace = {}
        for s, e, _ in attr_spans(m):
            if any(i in dl for i in range(s, e)):
                continue
            new_lines = []
            removed = []
            for i in range(s, e):
                spans = []
                for (a, b, c, d, rm, rn) in rbl.get(i, ()):
                    if c == i and ref_deleted(rm, rn):
                        ia, ib = u16_to_idx(lines[i], b), u16_to_idx(lines[i], d)
                        spans.append((ia, ib))
                        removed.append(rn)
                new_lines.append(cut_spans(lines[i], spans) if spans else lines[i])
            if not removed:
                continue
            rest = " ".join(new_lines)
            mm = ATTR_RE.match(rest)
            if mm is None or rest[mm.end():].strip() in ("", "in"):
                dl.update(range(s, e))
                edits.append((m, s + 1, "attribute を削除", " ".join(removed)))
            else:
                for i in range(s, e):
                    replace[i] = new_lines[i - s]
                edits.append((m, s + 1, "attribute から名前を外す", " ".join(removed)))
        # 名前空間が見えるか。Lean は open・export の時点で名前空間があるかを確かめるので、このモジュールの
        # namespace 命令と残す宣言は、その位置より前にあるものだけを数える(self_ns に順に足す)
        vm = clos(m)
        me = idx[m]
        starts = collections.defaultdict(list)
        for name, s, _ in decls.get(m, []):
            if keep_decl[(m, name)]:
                starts[s - 1].append(name)
        self_ns = set()
        opened = set()

        def ns_ok(q):
            return q in ext_ns or (ns_bits(q) & vm) != 0 or q in self_ns

        def cands(tok, bases):
            return [tok] + [f"{b}.{tok}" for b in bases + sorted(opened)]

        def vanished(tok, bases):
            if tok.startswith("_root_."):
                return False
            cs = cands(tok, bases)
            if any(ns_ok(c) for c in cs):
                return False
            return any(c in ns_before for c in cs)

        def note_opened(tok, bases):
            for c in cands(tok, bases):
                if ns_ok(c):
                    opened.add(c)

        def later_here(tok, bases):
            return [c for c in cands(tok, bases) if (ns_bits(c) >> me) & 1]

        ilean_refs = None

        def relied_on(ns, after):
            """行 after(0 始まり)より後ろで、名前空間 ns の定数を、ns の外から ns を書かずに参照しているか
            (open に頼っている参照。ドット記法の参照も数えるので多めに出る)"""
            nonlocal ilean_refs
            if ilean_refs is None:
                ilean_refs = module_ilean_refs(m)
            for (a, b, c, e, n, own) in ilean_refs:
                if a <= after or not n.startswith(ns + "."):
                    continue
                if own is not None and (own == ns or own.startswith(ns + ".")):
                    continue
                txt = lines[a][u16_to_idx(lines[a], b):u16_to_idx(lines[a], e)] if a == c else ""
                rest = n[len(ns) + 1:]
                if txt == rest or rest.endswith("." + txt):
                    return True
            return False

        out = []
        stack = []
        imports_done = False
        del_since_text = False
        n_open_fix = 0
        skip_to = -1
        for i, l in enumerate(lines):
            for name in starts.get(i, ()):
                self_ns.update(prefixes(name))
            if i < skip_to:
                continue
            if IMPORT_RE.match(l):
                if not imports_done:
                    out.extend(f"import {x}" for x in new_imports[m])
                    imports_done = True
                continue
            if i in dl:
                del_since_text = True
                continue
            if l.strip() == "":
                if del_since_text and out and out[-1].strip() == "":
                    continue
                out.append(l)
                continue
            del_since_text = False
            l = replace.get(i, l)
            mm = NS_RE.match(l)
            if mm and mm.group(1) == "namespace" and mm.group(2):
                stack.extend(mm.group(2).split("."))
                self_ns.update(prefixes(".".join(x for x in stack if x) + ".x"))
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
            em = EXPORT_RE.match(l) if om is None else None
            if not (om or em):
                out.append(l)
                continue
            # 字下げで続く行も同じ命令とみなす(1 行目が ` in` で終わる前置きなら、続く行は次の命令)
            j = i + 1 if WRAP_END_RE.search(l) else cont_span(lines, i)
            if any(k in dl for k in range(i + 1, j)):
                j = i + 1
            seg = lines[i:j]
            joined = " ".join(x.strip() for x in seg)
            cur = [x for x in stack if x]
            bases = [".".join(cur[:k]) for k in range(1, len(cur) + 1)]
            if om:
                jm = OPEN_RE.match(joined)
                body = jm.group(2)
                if ((not OPEN_SIMPLE_RE.match(body) and not OPEN_LIST_RE.match(body))
                        or KEYWORDS & set(body.split("(")[0].split())):
                    out.append(l)  # 名前空間と名前の並び以外(`open X in theorem …` を 1 行に書いたものなど)は触らない
                    continue
            what = "export" if em else "open"
            if em or "(" in body or " renaming " in body or " hiding " in body:
                if em:
                    ns = em.group(2)
                else:
                    ns = body.split()[1] if body.startswith("scoped ") else body.split()[0]
                skip_to = j
                if vanished(ns, bases):
                    edits.append((m, i + 1, f"{what} を削除(名前空間が見えない)", ns))
                    n_open_fix += 1
                    del_since_text = True
                    continue
                if om:
                    note_opened(ns, bases)
                # 明示した名前のうち、消す宣言を指すもの(.ilean の参照の位置で特定)を外す
                new_seg, removed = [], []
                for k in range(i, j):
                    spans = []
                    for (a, b, c, d, rm, rn) in rbl.get(k, ()):
                        if c == k and ref_deleted(rm, rn):
                            spans.append((u16_to_idx(lines[k], b), u16_to_idx(lines[k], d)))
                            removed.append(rn)
                    new_seg.append(cut_spans(lines[k], spans) if spans else lines[k])
                if not removed:
                    out.extend(seg)
                    continue
                n_open_fix += 1
                if re.search(r"\(\s*\)", " ".join(x.strip() for x in new_seg)):
                    edits.append((m, i + 1, f"{what} を削除(名前が残らない)", " ".join(removed)))
                    del_since_text = True
                    continue
                edits.append((m, i + 1, f"{what} から名前を外す", " ".join(removed)))
                # 名前が無くなった続きの行は消し、`)` だけが残った行は前の行に付ける
                tidy = []
                for x in new_seg:
                    if x.strip() == "":
                        continue
                    if x.strip() == ")" and tidy:
                        tidy[-1] = tidy[-1].rstrip() + ")"
                        continue
                    tidy.append(x)
                out.extend(tidy)
                continue
            # 名前空間の並び: 行ごとに見えない名前空間を外す(行の構成は保つ)
            skip_to = j
            scoped = False
            has_in = False
            per_line = []
            for k, x in enumerate(seg):
                toks = x.split()
                if k == 0:
                    toks = toks[1:]
                    if toks[:1] == ["scoped"]:
                        scoped = True
                        toks = toks[1:]
                if k == len(seg) - 1 and toks[-1:] == ["in"]:
                    has_in = True
                    toks = toks[:-1]
                per_line.append(toks)
            new_toks, removed, made_ns = [], [], []
            cur_s = ".".join(cur)
            for toks in per_line:
                keep = []
                for x in toks:
                    if vanished(x, bases):
                        later = later_here(x, bases)
                        # このモジュールの後ろで初めて現れる名前空間で、名前空間の外から短い名前で参照されるなら、
                        # open は残し、その前に `namespace X end X` で名前空間を作る(外すと参照が解決できなくなる)
                        if later and relied_on(later[0], j - 1):
                            c = later[0]
                            rel = c[len(cur_s) + 1:] if cur_s and c.startswith(cur_s + ".") else (None if cur_s else c)
                            if rel:
                                made_ns.append(rel)
                                self_ns.update(prefixes(c + ".x"))
                                keep.append(x)
                                note_opened(x, bases)
                                edits.append((m, i + 1, "open の前に名前空間を作る(このモジュールの後ろで初めて現れ、"
                                              "名前空間の外から短い名前で参照される)", c))
                                n_open_fix += 1
                                continue
                        removed.append(x)
                        kind = ("open から名前空間を外す(このモジュールの後ろで初めて現れる)" if later
                                else "open から名前空間を外す")
                        edits.append((m, i + 1, kind, x))
                        n_open_fix += 1
                    else:
                        keep.append(x)
                        note_opened(x, bases)
                new_toks.append(keep)
            for rel in made_ns:
                out.append(f"{om.group(1)}namespace {rel} end {rel}")
            if not removed:
                out.extend(seg)
                continue
            nonempty = [k for k, t in enumerate(new_toks) if t]
            if not nonempty:
                del_since_text = True
                continue
            for k in nonempty:
                s_ = " ".join(new_toks[k])
                if k == nonempty[0]:
                    s_ = f"{om.group(1)}open {'scoped ' if scoped else ''}{s_}"
                else:
                    s_ = re.match(r"^\s*", seg[k]).group(0) + s_
                if k == nonempty[-1] and has_in:
                    s_ += " in"
                out.append(s_)
        if not imports_done and new_imports[m]:
            out = [f"import {x}" for x in new_imports[m]] + out
        new_text[m] = out
        changes[m] = (len(dl), n_open_fix, new_imports[m] != orig_imports[m], out != lines)

    # ---- 7. 集計
    def stats(texts):
        st = collections.Counter()
        for ls in texts:
            body = "\n".join(ls)
            st["modules"] += 1
            st["lines"] += body.count("\n")  # README の数え方(改行の数)と同じ
            st["nonblank_lines"] += sum(1 for x in ls if x.strip())
            st["bytes"] += len(body.encode("utf-8"))
        return st

    before = stats(text.values())
    after = stats(new_text.values())
    before["decls"] = sum(len(v) for v in decls.values())
    after["decls"] = sum(1 for m in kept_modules for name, _, _ in decls.get(m, []) if keep_decl[(m, name)])
    report = {
        "kept_list": os.path.realpath(args.kept),
        "decls_source": os.path.realpath(args.decls),
        "before": dict(before), "after": dict(after),
        "deleted_modules": len(deleted_modules),
        "kept_modules_without_decls": dict(keep_reason),
        "deleted_decls": len(deleted_decls),
        "protected_beyond_kept_list": collections.Counter(r for _, _, r in protected),
        "edits": collections.Counter(k for _, _, k, _ in edits),
        "changed_modules": sum(1 for v in changes.values() if v[3]),
    }
    print(json.dumps(report, ensure_ascii=False, indent=1, default=dict), flush=True)
    if args.dry_run:
        return

    # ---- 8. 書き出し
    out = args.out
    if os.path.exists(os.path.join(out, "src")):
        shutil.rmtree(os.path.join(out, "src"))
    rec = os.path.join(out, "stage1a")
    os.makedirs(rec, exist_ok=True)
    for f in ("lakefile.toml", "lake-manifest.json", "lean-toolchain"):
        shutil.copy2(os.path.join(ROOT, "lean", f), os.path.join(out, f))
    for m, ls in new_text.items():
        path = os.path.join(out, "src", *m.split(".")) + ".lean"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(ls))
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
    with open(os.path.join(rec, "edits.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tline\tkind\tnames\n")
        fh.write("".join(f"{a}\t{b}\t{c}\t{d}\n" for a, b, c, d in edits))
    with open(os.path.join(rec, "changes.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tdeleted_lines\topen_fixes\timports_changed\tchanged\n")
        fh.write("".join(f"{m}\t{a}\t{b}\t{int(c)}\t{int(d)}\n" for m, (a, b, c, d) in sorted(changes.items())))
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
