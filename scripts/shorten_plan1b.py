#!/usr/bin/env python3
"""段階 1b: 型が同じ定理(厳しい重複)をまとめる計画を立てる。

型が同じ定理 X と C があれば、X への参照をすべて C に付け替えて X を消せる(定理は証明の中身を問われないので、
カーネルの項としても同じ型の別の証明に置き換わるだけ)。ソース上で付け替えても同じように引数が渡るよう、
rhshrink の「厳しい重複」(宇宙変数を位置で付け替えた型が α 同値で、束縛の種類の並びと宇宙変数の数が同じ)だけを使う。

X をまとめる条件(どれかに外れれば X は残す。blocked.tsv に理由を書く)
  * X は守る宣言(instance・simp 補題など)でも、マクロの本文が参照する宣言でも、cpt_copy_thms が辿る宣言でも、
    そのまま写すモジュール(Main など)の宣言でもない。同じ名前の宣言が別のモジュールにもある定理(Lean は名前と型が
    同じなら重複 import を許す)は、カーネルでは 1 つの定数なので、まとめる側にも残す側にもしない。
  * X への参照(.ilean の位置)のうち、段階 1b でも残る宣言の中のものは、すべて書き換えられる:
      - 1 行に収まり、ソースの字面が X の名前(の末尾)である(`open … renaming` などで別の名前になっていない)
      - 直前が `.` でない(`h.X` のようなフィールド記法でない)、直後が `.{` でない(宇宙変数の明示でない)
      - X と C の束縛変数の名前が違うなら、同じ行の後ろに名前つき引数 `(名前 :=` がない
      - 参照を含む宣言が cpt_copy_thms の辿る宣言でなく、そのまま写すモジュールの中でもない
      - その位置から C が見える: C のモジュールが参照するモジュールの import の閉包(段階 1a の短縮版)にあるか、
        同じモジュールなら参照を含む宣言より前で C が終わっている(C の証明が X を使っている場合の循環もこれで防ぐ)
  * 宣言の外の参照は `open X (…)`・`export X (…)` の中だけ(段階 1a の書き出しが、消す宣言の名前を外す)。
  * discharger の中に .ilean に記録されない参照がない: `simp (disch := simp [X])` のような discharger の引数の中の参照は
    .ilean に記録されず、書き換えから漏れる(段階 1b の 1 回目の全体ビルドで失敗した)。コメントと文字列を除いたソースで、
    `(disch := …)`・`(discharger := …)` の括弧の中に、X が見える位置で X の名前(の後ろの部分)と同じ識別子があり、
    どの .ilean の参照・定義の範囲にも入らないなら、X は残す。discharger の外の記録されない字面(局所変数の名前、
    キーワード、`first` の失敗した分岐など)は害がないので数えない(unrecorded.tsv に in_discharger=0 で書く)。
C の選び方: 組の中で、非公開でない宣言のうち、まとめられる写しが最も多いもの。同じなら行数の少ない(短い証明の)もの。
残った写しの中で、同じことを繰り返す。参照を含む宣言自身がまとめられて消えるなら、その参照は数えない
(まとめる集合が変わらなくなるまで繰り返す)。

付け替えた参照は `_root_.<C の名前>` と書く(名前空間の中でも同じものに解決される。`@`・`.symm`・`simp only [...]`・
`rw [...]` の中でも使えることを確かめた)。

入力: --strict-dups(rhshrink の duplicates-strict.tsv)、--decls(rhshrink の decls.tsv.zst)、--kept(段階 1a の
      kept-decls.tsv)、--protected、--macro-refs、--cpt(tools/cptcopy の出力)、--stage-src(段階 1a の短縮版の src)
出力(--out): merge.tsv(rhshrink の RHSHRINK_REDIRECT 用: X\\tC)、redirect.tsv(X のモジュール・X・C のモジュール・C)、
      rewrites.tsv(書き換える参照の位置)、blocked.tsv、summary.json
"""
import argparse
import bisect
import collections
import json
import multiprocessing as mp
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "lean", "src")
ILEAN_ROOT = "/var/tmp/riemann-hypothesis-ywr/lake/build/lib/lean"
PROJECT_ROOTS = {"BuildAid", "CompanionTheory", "Development", "Formalism", "GroundTheory", "Lemmata",
                 "PositivityTheory", "ReciprocityTheory", "Supplements", "Main", "Statements"}
IMPORT_RE = re.compile(r"^import\s+(\S+)\s*$")
OPEN_EXPORT_RE = re.compile(r"^\s*(open|export)\b")
NAMED_ARG_RE = re.compile(r"\(\s*[^\s():=,]+\s*:=")
DISCH_RE = re.compile(r"\((?:disch|discharger)\s*:=")
IDENT_RE = re.compile(r"(?<![\w'!?.])((?:«[^»]*»|[^\W\d][\w'!?₀-₉ₐ-ₜᵢ-ᵪ]*)(?:\.(?:«[^»]*»|[^\W\d][\w'!?₀-₉ₐ-ₜᵢ-ᵪ]*))*)")

CANDIDATES = None
SHORT_NAMES = None


def unpriv(n):
    if n and n.startswith("_private."):
        k = n.find(".0.")
        return n[k + 3:] if k >= 0 else n
    return n


def u16_to_idx(s, u16):
    k = 0
    for idx, ch in enumerate(s):
        if k >= u16:
            return idx
        k += 2 if ord(ch) > 0xFFFF else 1
    return len(s)


def init_worker(cands):
    global CANDIDATES, SHORT_NAMES
    CANDIDATES = cands
    SHORT_NAMES = {unpriv(n).rsplit(".", 1)[-1] for _, n in cands}


def blank_comments(text):
    """コメント・文字列・文字リテラルを空白に置き換える(行と列の位置は保つ)"""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "-" and text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c == "/" and text.startswith("/-", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith("/-", j):
                    depth += 1
                    j += 2
                elif text.startswith("-/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c == "'" and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] in "_'!?₀₁₂₃₄₅₆₇₈₉")):
            m = re.match(r"'(\\.[^']*|[^'\\])'", text[i:i + 12])
            if m:
                for k in range(i, i + m.end()):
                    out[k] = " "
                i += m.end()
            else:
                i += 1
        else:
            i += 1
    return "".join(out)


def refs_in_module(m):
    """モジュール m の .ilean から、候補の定数への参照 (行, 列, 終わりの行, 終わりの列, 参照先の名前, 持ち主) を返す。
    あわせて、ソースの識別子のうち、末尾が候補の名前の末尾と同じで、どの .ilean の参照・定義の範囲にも入らないもの
    (行, 始めの文字位置, 終わりの文字位置, 字面)も返す"""
    try:
        with open(os.path.join(ILEAN_ROOT, *m.split(".")) + ".ilean", encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return m, [], []
    out = []
    for key, v in d.get("references", {}).items():
        if not key.startswith('{"c":'):
            continue
        c = json.loads(key)["c"]
        if (c["m"], c["n"]) not in CANDIDATES:
            continue
        for u in v.get("usages", []):
            out.append((u[0], u[1], u[2], u[3], (c["m"], c["n"]), u[4] if len(u) >= 5 else None))
    # .ilean に記録されない字面の参照
    try:
        with open(os.path.join(SRC, *m.split(".")) + ".lean", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return m, out, []
    clean = blank_comments(text)
    starts = [0]
    for i, ch in enumerate(clean):
        if ch == "\n":
            starts.append(i + 1)
    # simp などの discharger の引数 `(disch := …)`・`(discharger := …)` の範囲(括弧の対応で閉じるところまで)
    dspans = []
    for mm in DISCH_RE.finditer(clean):
        depth, j = 0, mm.start()
        while j < len(clean):
            if clean[j] == "(":
                depth += 1
            elif clean[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        dspans.append((mm.start(), j))
    cands = []
    for mm in IDENT_RE.finditer(clean):
        tok = mm.group(1)
        if tok.rsplit(".", 1)[-1] in SHORT_NAMES:
            ln = bisect.bisect_right(starts, mm.start(1)) - 1
            a = mm.start(1) - starts[ln]
            in_disch = any(x <= mm.start(1) < y for (x, y) in dspans)
            cands.append((ln, a, a + len(tok), tok, in_disch))
    if not cands:
        return m, out, []
    lines = text.split("\n")
    cover = collections.defaultdict(list)
    for v in d.get("references", {}).values():
        rs = list(v.get("usages") or [])
        if v.get("definition"):
            rs.append(v["definition"])
        for u in rs:
            for ln in range(u[0], u[2] + 1):
                if ln < len(lines):
                    a = u16_to_idx(lines[ln], u[1]) if ln == u[0] else 0
                    b = u16_to_idx(lines[ln], u[3]) if ln == u[2] else len(lines[ln])
                    cover[ln].append((a, b))
    unrec = [c for c in cands if not any(x < c[2] and c[1] < y for (x, y) in cover.get(c[0], ()))]
    return m, out, unrec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict-dups", required=True)
    ap.add_argument("--decls", required=True)
    ap.add_argument("--kept", required=True)
    ap.add_argument("--protected", required=True)
    ap.add_argument("--macro-refs", required=True)
    ap.add_argument("--cpt", required=True)
    ap.add_argument("--stage-src", default="/var/tmp/riemann-hypothesis-ywr/shorten/stage-1a/src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=32)
    ap.add_argument("--dump-refs", action="store_true", help="候補への参照の一覧 refs.tsv も書き出す(分析用)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    # ---- 読み込み
    kept = set()
    with open(args.kept, encoding="utf-8") as fh:
        for l in fh:
            if l.strip():
                m, n = l.rstrip("\n").split("\t", 1)
                kept.add((m, n))
    rng = collections.defaultdict(dict)   # モジュール -> 宣言 -> (開始行, 終了行)(1 始まり)
    p = subprocess.Popen(["zstd", "-dc", args.decls], stdout=subprocess.PIPE, text=True)
    next(p.stdout)
    for line in p.stdout:
        f = line.rstrip("\n").split("\t")
        rng[f[0]][f[1]] = (int(f[3]), int(f[4]))
    p.wait()
    groups = collections.defaultdict(list)
    info = {}
    with open(args.strict_dups, encoding="utf-8") as fh:
        next(fh)
        for l in fh:
            g, size, n, m, s, e, priv, sig, bnames = l.rstrip("\n").split("\t")
            if s == "-" or (m, n) not in kept:
                continue
            groups[g].append((m, n))
            info[(m, n)] = {"start": int(s), "end": int(e), "private": priv == "true", "bnames": bnames, "group": g}
    groups = {g: ms for g, ms in groups.items() if len(ms) >= 2}
    info = {k: v for k, v in info.items() if v["group"] in groups}
    protected = set()
    with open(args.protected, encoding="utf-8") as fh:
        next(fh)
        for l in fh:
            m, n, _ = l.rstrip("\n").split("\t", 2)
            protected.add((m, n))
    macro_ref = set()
    with open(args.macro_refs, encoding="utf-8") as fh:
        next(fh)
        for l in fh:
            f = l.rstrip("\n").split("\t")
            macro_ref.add((f[5], f[6]))
    cpt_seen = set()
    with open(args.cpt, encoding="utf-8") as fh:
        for l in fh:
            f = l.rstrip("\n").split("\t")
            if f[0] == "SEEN" and f[1].endswith(".block_growth_bound_of_compact_coef"):
                cpt_seen.add(f[2])
    print(f"groups={len(groups)} members={len(info)} protected={len(protected)} macro_refs={len(macro_ref)} "
          f"cpt_seen={len(cpt_seen)}", flush=True)

    # ---- 段階 1a の短縮版の import の閉包(ビット集合)
    imps = {}
    for d, _, fs in os.walk(args.stage_src):
        for f in fs:
            if f.endswith(".lean"):
                m = os.path.relpath(os.path.join(d, f), args.stage_src)[:-5].replace(os.sep, ".")
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    imps[m] = [mm.group(1) for l in fh if (mm := IMPORT_RE.match(l))]
    fixed = {"Main", "Statements"} | {x for x in imps.get("Main", []) if x.split(".")[0] in PROJECT_ROOTS}
    idx = {m: i for i, m in enumerate(sorted(imps))}
    clos = {}
    for m0 in imps:
        if m0 in clos:
            continue
        stack = [m0]
        while stack:
            m = stack[-1]
            if m in clos:
                stack.pop()
                continue
            ims = [x for x in imps.get(m, []) if x in idx]
            todo = [x for x in ims if x not in clos]
            if todo:
                stack.extend(todo)
                continue
            c = 0
            for x in ims:
                c |= (1 << idx[x]) | clos[x]
            clos[m] = c
            stack.pop()
    print(f"import closures: {len(clos)} modules", flush=True)

    def owner_key(m, own):
        names = rng.get(m)
        n = own
        while names and n:
            if n in names:
                return (m, n)
            if "." not in n:
                return None
            n = n.rsplit(".", 1)[0]
        return None

    def visible(c_key, ref_mod, okey):
        cm = c_key[0]
        if cm == ref_mod:
            return okey is not None and info[c_key]["end"] < rng[ref_mod][okey[1]][0]
        if ref_mod not in clos or cm not in idx:
            return False
        return bool((clos[ref_mod] >> idx[cm]) & 1)

    # ---- 候補への参照
    # 同じ名前の宣言が 2 つ以上のモジュールにあるもの(Lean は名前と型が同じなら重複 import を許す)。カーネルの定数は
    # 名前で 1 つなので、片方を消しても、もう片方が使われていれば消えない。まとめる側にも残す側にもしない
    name_mods = collections.defaultdict(set)
    for m, ds in rng.items():
        for n in ds:
            name_mods[n].add(m)
    dupname = {n for n, ms in name_mods.items() if len(ms) > 1}
    excluded = {}
    for k in info:
        if k[1] in dupname:
            excluded[k] = "同じ名前の宣言が別のモジュールにもある"
        elif k in protected:
            excluded[k] = "守る宣言"
        elif k in macro_ref:
            excluded[k] = "マクロの本文が参照する"
        elif k[1] in cpt_seen:
            excluded[k] = "cpt_copy_thms が辿る"
        elif k[0] in fixed:
            excluded[k] = "そのまま写すモジュールにある"
    refs = collections.defaultdict(list)
    unrecorded = []
    modules = sorted({m for m, _ in kept})
    with mp.Pool(args.jobs, initializer=init_worker, initargs=(set(info),)) as pool:
        for i, (m, rs, us) in enumerate(pool.imap_unordered(refs_in_module, modules, chunksize=64)):
            for r in rs:
                refs[r[4]].append((m,) + r[:4] + (r[5],))
            for u in us:
                unrecorded.append((m,) + u)
            if (i + 1) % 30000 == 0:
                print(f"  ilean {i + 1}/{len(modules)}", flush=True)
    print(f"references to candidates: {sum(len(v) for v in refs.values())}; "
          f"unrecorded tokens with a candidate's last name: {len(unrecorded)}", flush=True)

    # ---- .ilean に記録されない字面の参照: 字面が候補 X の名前の後ろの部分と同じで、X が見える位置にあり、段階 1a で
    # 残した宣言の中(または宣言の外)にあるもの。局所変数などとは区別せず、その X はまとめない
    by_short = collections.defaultdict(list)
    for k in info:
        by_short[unpriv(k[1]).rsplit(".", 1)[-1]].append(k)
    spans = {}

    def enclosing(m, ln1):
        if m not in spans:
            spans[m] = sorted((a, b, n) for n, (a, b) in rng.get(m, {}).items())
        best = None
        for (a, b, n) in spans[m]:
            if a > ln1:
                break
            if a <= ln1 <= b and (best is None or b - a < best[1] - best[0]):
                best = (a, b, n)
        return best

    unrec_rows = []
    for (m, ln, a, b, tok, in_disch) in unrecorded:
        hits = []
        for xk in by_short[tok.rsplit(".", 1)[-1]]:
            xn = unpriv(xk[1])
            if not (xn == tok or xn.endswith("." + tok) or tok == "_root_." + xn):
                continue
            if xk[0] == m:
                if info[xk]["end"] >= ln + 1:
                    continue
            elif m not in clos or xk[0] not in idx or not (clos[m] >> idx[xk[0]]) & 1:
                continue
            hits.append(xk)
        if not hits:
            continue
        ow = enclosing(m, ln + 1)
        if ow is not None and (m, ow[2]) not in kept:
            continue
        for xk in hits:
            unrec_rows.append((m, ln + 1, a, tok, ow[2] if ow else "-", xk, in_disch))
            if in_disch and xk not in excluded:
                excluded[xk] = "discharger の中の記録されない参照"
    print(f"unrecorded references: {len(unrec_rows)} (X: {len({r[5] for r in unrec_rows})}); "
          f"in a discharger: {sum(1 for r in unrec_rows if r[6])} (X: {len({r[5] for r in unrec_rows if r[6]})})",
          flush=True)
    with open(os.path.join(args.out, "unrecorded.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tline\tcol\ttoken\towner\tx_module\tx\tin_discharger\n")
        fh.write("".join(f"{m}\t{l}\t{c}\t{t}\t{o}\t{xk[0]}\t{xk[1]}\t{int(dd)}\n"
                         for m, l, c, t, o, xk, dd in unrec_rows))

    # ---- 参照ごとの、C によらない判定
    text_cache = {}

    def src_lines(m):
        if m not in text_cache:
            with open(os.path.join(SRC, *m.split(".")) + ".lean", encoding="utf-8") as fh:
                text_cache[m] = fh.read().split("\n")
        return text_cache[m]

    stat = {}   # X -> [(参照, 持ち主, 問題 or None, 名前つき引数がありそうか, 置き換える文字位置 (行, 始, 終))]
    for x in info:
        xs = unpriv(x[1])
        lst = []
        for (m, a, b, c, e, own) in refs.get(x, ()):
            okey = owner_key(m, own) if own else None
            lines = src_lines(m)
            line = lines[a] if a < len(lines) else ""
            if okey is None:
                # 宣言の外の参照: open (…)・export (…) の中なら段階 1a の書き出しが外す(字下げで続く行も含めて見る)
                j = a
                while j > 0 and lines[j][:1] in (" ", "\t") and not OPEN_EXPORT_RE.match(lines[j]):
                    j -= 1
                if OPEN_EXPORT_RE.match(lines[j]) and m not in fixed:
                    continue
                lst.append(((m, a, b, c, e), None, "宣言の外の参照", False, None))
                continue
            if okey not in kept:
                continue
            ib, ie = u16_to_idx(line, b), u16_to_idx(line, e)
            sl = line[ib:ie]
            problem = None
            if a != c:
                problem = "参照が複数行"
            elif m in fixed:
                problem = "そのまま写すモジュールの中"
            elif okey[1] in cpt_seen:
                problem = "cpt_copy_thms が辿る宣言の中"
            elif not (sl == xs or xs.endswith("." + sl) or sl == "_root_." + xs):
                problem = "字面が名前と違う"
            elif ib > 0 and line[ib - 1] == ".":
                problem = "フィールド記法"
            elif line[ie:].startswith(".{"):
                problem = "宇宙変数の明示"
            named = bool(NAMED_ARG_RE.search(line[ie:]))
            lst.append(((m, a, b, c, e), okey, problem, named, (a, ib, ie)))
        stat[x] = lst

    def mergeable(x, ck, gone):
        for (r, okey, problem, named, _) in stat[x]:
            if okey is not None and (okey in gone or okey == x):
                continue
            if problem:
                return False, problem
            if named and info[x]["bnames"] != info[ck]["bnames"]:
                return False, "名前つき引数"
            if not visible(ck, r[0], okey):
                return False, "C が見えない"
        return True, None

    # ---- 組ごとに C を選んでまとめる。まとめた写しと選んだ C は以後変えない(増やすだけ)。前の回までにまとめた写しの
    # 中の参照だけを数えない(その写しは必ず消えるので、計画は食い違わない)。新しくまとめるものが無くなるまで繰り返す
    merged = {}
    canon = set()
    why = {}
    for it in range(50):
        gone = set(merged)
        new = {}
        for g, members in groups.items():
            remaining = [k for k in members if k not in merged]
            while len(remaining) >= 2:
                best = None
                for ck in remaining:
                    if info[ck]["private"] or ck[1] in dupname:
                        continue
                    absorbed = []
                    for xk in remaining:
                        if xk == ck or xk in canon:
                            continue
                        if xk in excluded:
                            why[xk] = excluded[xk]
                            continue
                        ok, reason = mergeable(xk, ck, gone)
                        if ok:
                            absorbed.append(xk)
                        else:
                            why[xk] = reason
                    if absorbed:
                        score = (len(absorbed), -(info[ck]["end"] - info[ck]["start"]), ck)
                        if best is None or score > best[0]:
                            best = (score, ck, absorbed)
                if best is None:
                    break
                _, ck, absorbed = best
                canon.add(ck)
                for xk in absorbed:
                    new[xk] = ck
                remaining = [k for k in remaining if k != ck and k not in absorbed]
        merged.update(new)
        print(f"round {it}: newly merged {len(new)}, total {len(merged)}", flush=True)
        if not new:
            break

    if args.dump_refs:
        with open(os.path.join(args.out, "refs.tsv"), "w", encoding="utf-8") as fh:
            fh.write("x_module\tx\tref_module\tline\towner\tproblem\n")
            for xk, lst in stat.items():
                for (r, okey, problem, named, _) in lst:
                    fh.write(f"{xk[0]}\t{xk[1]}\t{r[0]}\t{r[1]}\t{okey[1] if okey else '-'}\t{problem or '-'}\n")
    # ---- 書き出し
    gone = set(merged)
    rewrites = []
    for xk, ck in merged.items():
        cs = "_root_." + unpriv(ck[1])
        for (r, okey, problem, named, pos) in stat[xk]:
            if okey is None or okey in gone or okey == xk:
                continue
            a, ib, ie = pos
            rewrites.append((r[0], a, ib, ie, xk[1], cs, okey[1]))
    rewrites.sort()
    with open(os.path.join(args.out, "merge.tsv"), "w", encoding="utf-8") as fh:
        fh.write("".join(f"{x[1]}\t{c[1]}\n" for x, c in sorted(merged.items())))
    with open(os.path.join(args.out, "redirect.tsv"), "w", encoding="utf-8") as fh:
        fh.write("x_module\tx\tc_module\tc\n")
        fh.write("".join(f"{x[0]}\t{x[1]}\t{c[0]}\t{c[1]}\n" for x, c in sorted(merged.items())))
    with open(os.path.join(args.out, "rewrites.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tline\tstart_char\tend_char\tx\treplacement\towner\n")
        fh.write("".join(f"{m}\t{a}\t{ib}\t{ie}\t{x}\t{cs}\t{o}\n" for m, a, ib, ie, x, cs, o in rewrites))
    canon = set(merged.values())
    blocked = [(k, why.get(k, "?")) for k in info if k not in merged and k not in canon]
    with open(os.path.join(args.out, "blocked.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tdecl\treason\n")
        fh.write("".join(f"{k[0]}\t{k[1]}\t{r}\n" for k, r in sorted(blocked)))
    lines = sum(info[x]["end"] - info[x]["start"] + 1 for x in merged)
    stmt = sum(1 for x in merged if x[0].endswith("Statement"))
    by_mod = collections.Counter(x[0] for x in merged)
    kept_by_mod = collections.Counter(m for m, _ in kept)
    emptied = [m for m, c in by_mod.items() if c == kept_by_mod[m]]
    summary = {
        "groups": len(groups),
        "members": len(info),
        "merged": len(merged),
        "merged_in_statement_modules": stmt,
        "merged_decl_lines": lines,
        "canonicals": len(set(merged.values())),
        "rewrites": len(rewrites),
        "modules_with_rewrites": len({r[0] for r in rewrites}),
        "modules_emptied": len(emptied),
        "blocked": dict(collections.Counter(r for _, r in blocked)),
    }
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
