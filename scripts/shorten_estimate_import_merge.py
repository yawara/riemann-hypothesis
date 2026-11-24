"""import を足してまとめる見積もりを厳しくする: 足す import で新たに見えるライブラリ(Mathlib など)のモジュールが無いこと、
新たに見える配布物の宣言の名前(末尾)が参照するモジュールのソースの識別子に無いこと、を条件に足す。"""
import collections, glob, os, re, sys
sys.path.insert(0, "/home/ywr/riemann-hypothesis/scripts")
R = "/var/tmp/riemann-hypothesis-ywr/runs/shorten"
STAGE = "/var/tmp/riemann-hypothesis-ywr/shorten/stage-1a"
IMPORT_RE = re.compile(r"^import\s+(\S+)\s*$")
META_RE = re.compile(r"^(attribute\s+\[(?!local)|run_cmd|run_elab|run_meta|initialize|builtin_initialize|notation|notation3|infix|infixl|infixr|prefix|postfix|macro|macro_rules|syntax|elab|elab_rules|declare_syntax_cat|export|binder_predicate|scoped|local\s+notation|unif_hint|add_decl_doc)\b")
IDENT_RE = re.compile(r"(?<![\w'!?])((?:«[^»]*»|[^\W\d][\w'!?₀-₉ₐ-ₜᵢ-ᵪ]*)(?:\.(?:«[^»]*»|[^\W\d][\w'!?₀-₉ₐ-ₜᵢ-ᵪ]*))*)")
# ライブラリの import の閉包
lib_imps = {}
roots = [(f"{STAGE}/.lake/packages/{p}", None) for p in os.listdir(f"{STAGE}/.lake/packages")]
roots.append((os.path.expanduser("~/.elan/toolchains/leanprover--lean4---v4.33.1/src/lean"), None))
for base, _ in roots:
    for f in glob.glob(f"{base}/**/*.lean", recursive=True):
        rel = os.path.relpath(f, base)
        if rel.startswith((".lake", "test", "tests")):
            continue
        m = rel[:-5].replace(os.sep, ".")
        if m in lib_imps:
            continue
        ims = []
        try:
            with open(f, encoding="utf-8") as fh:
                for l in fh:
                    s = l.strip()
                    mm = re.match(r"^(?:public\s+|meta\s+|private\s+)*import\s+(?:all\s+)?(\S+)", s)
                    if mm:
                        ims.append(mm.group(1))
                    elif s and not s.startswith(("--", "/-", "module", "prelude", "-/")) and not ims == [] and not s.startswith(("public", "meta", "import")):
                        break
        except OSError:
            pass
        lib_imps[m] = ims
lidx = {m: i for i, m in enumerate(sorted(lib_imps))}
lclos = {}
def lib_closure(m0):
    st = [m0]
    while st:
        m = st[-1]
        if m in lclos:
            st.pop(); continue
        ims = [x for x in lib_imps.get(m, []) if x in lidx]
        todo = [x for x in ims if x not in lclos]
        if todo:
            st.extend(todo); continue
        c = 0
        for x in ims:
            c |= (1 << lidx[x]) | lclos[x]
        lclos[m] = c
        st.pop()
    return lclos[m0]
print("library modules", len(lib_imps), flush=True)
# 配布物(段階 1a)の import と閉包、ライブラリの閉包
imps, inert, toks = {}, {}, {}
prot_mods = set(l.split("\t", 1)[0] for l in list(open(f"{R}/protect/protected.tsv", encoding="utf-8"))[1:])
for d, _, fs in os.walk(f"{STAGE}/src"):
    for f in fs:
        if not f.endswith(".lean"):
            continue
        m = os.path.relpath(os.path.join(d, f), f"{STAGE}/src")[:-5].replace(os.sep, ".")
        ims, bad = [], False
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            for l in fh:
                mm = IMPORT_RE.match(l)
                if mm:
                    ims.append(mm.group(1))
                elif META_RE.match(l):
                    bad = True
        imps[m] = ims
        inert[m] = (not bad) and (m not in prot_mods)
idx = {m: i for i, m in enumerate(sorted(imps))}
clos, plib = {}, {}
for m0 in imps:
    if m0 in clos:
        continue
    st = [m0]
    while st:
        m = st[-1]
        if m in clos:
            st.pop(); continue
        ims = [x for x in imps.get(m, []) if x in idx]
        todo = [x for x in ims if x not in clos]
        if todo:
            st.extend(todo); continue
        c, lc = 0, 0
        for x in imps.get(m, []):
            if x in idx:
                c |= (1 << idx[x]) | clos[x]
                lc |= plib[x]
            elif x in lidx:
                lc |= (1 << lidx[x]) | lib_closure(x)
        clos[m] = c
        plib[m] = lc
        st.pop()
noninert_bits = 0
for m, ok in inert.items():
    if not ok:
        noninert_bits |= 1 << idx[m]
print(f"project modules {len(imps)}, inert {sum(inert.values())}", flush=True)
# 宣言の名前(末尾)をモジュールごとに
import subprocess
A = sorted(glob.glob(f"{R}/analysis-c1b2-3-*"))[-1]
shortnames = collections.defaultdict(set)
p = subprocess.Popen(["zstd", "-dc", f"{A}/decls.tsv.zst"], stdout=subprocess.PIPE, text=True)
next(p.stdout)
for l in p.stdout:
    f = l.split("\t", 2)
    n = f[1]
    if n.startswith("_private."):
        k = n.find(".0."); n = n[k + 3:] if k >= 0 else n
    shortnames[f[0]].add(n.rsplit(".", 1)[-1])
names_by_mod = {m: s for m, s in shortnames.items()}
tok_cache = {}
def tokens(m):
    if m not in tok_cache:
        try:
            text = open(f"{STAGE}/src/" + m.replace(".", "/") + ".lean", encoding="utf-8").read()
        except OSError:
            text = ""
        tok_cache[m] = {t.rsplit(".", 1)[-1] for t in IDENT_RE.findall(text)}
    return tok_cache[m]
inv_idx = {i: m for m, i in idx.items()}
def bits(x):
    while x:
        b = x & -x
        yield b.bit_length() - 1
        x ^= b
# 計画と参照
merged, canon = set(), set()
for l in list(open(f"{R}/plan1b-4/redirect.tsv", encoding="utf-8"))[1:]:
    xm, x, cm, c = l.rstrip("\n").split("\t")
    merged.add((xm, x)); canon.add((cm, c))
blocked = {}
for l in list(open(f"{R}/plan1b-4/blocked.tsv", encoding="utf-8"))[1:]:
    m, n, r = l.rstrip("\n").split("\t")
    blocked[(m, n)] = r
DUPS = sorted(d for d in os.listdir(R) if d.startswith("analysis-dups1b-"))[-1]
groups = collections.defaultdict(list)
info = {}
for l in list(open(f"{R}/{DUPS}/duplicates-strict.tsv", encoding="utf-8"))[1:]:
    g, size, n, m, s, e, priv, sig, bn = l.rstrip("\n").split("\t")
    if s == "-":
        continue
    groups[g].append((m, n))
    info[(m, n)] = (int(s), int(e), priv == "true", g)
refs = collections.defaultdict(list)
for l in list(open(f"{R}/plan1b-refs/refs.tsv", encoding="utf-8"))[1:]:
    xm, x, rm, line, owner, problem = l.rstrip("\n").split("\t")
    refs[(xm, x)].append((rm, owner, problem))
pair_cache = {}
def need_import(cm, n):
    if n == cm or (n in clos and (clos[n] >> idx[cm]) & 1):
        return True, None
    key = (cm, n)
    if key in pair_cache:
        return pair_cache[key]
    if cm not in idx or n not in idx:
        res = (False, "モジュールが無い")
    elif (clos[cm] >> idx[n]) & 1:
        res = (False, "循環")
    else:
        add = (clos[cm] | (1 << idx[cm])) & ~(clos[n] | (1 << idx[n]))
        if add & noninert_bits:
            res = (False, "無害でない読み込みが増える")
        elif plib[cm] & ~plib[n]:
            res = (False, "新たに見えるライブラリのモジュールがある")
        else:
            tk = tokens(n)
            clash = False
            for b in bits(add):
                if names_by_mod.get(inv_idx[b], set()) & tk:
                    clash = True
                    break
            res = (False, "新たに見える名前がソースの識別子と重なる") if clash else (True, (n, cm))
    pair_cache[key] = res
    return res
absorbed, lines, imports_needed = 0, 0, set()
reasons = collections.Counter()
for g, members in groups.items():
    xs = [k for k in members if blocked.get(k) == "C が見えない"]
    if not xs:
        continue
    cands = [k for k in members if k not in merged and not info[k][2]]
    best = None
    for c in cands:
        got, imp = [], set()
        for x in xs:
            if x == c:
                continue
            ok, add_here = True, set()
            for (rm, owner, problem) in refs.get(x, ()):
                if owner == "-" or (rm, owner) in merged or owner == x[1]:
                    continue
                if problem != "-":
                    ok = False; reasons["参照に別の問題"] += 1; break
                if rm == c[0]:
                    continue
                v, why = need_import(c[0], rm)
                if not v:
                    ok = False; reasons[why] += 1; break
                if why:
                    add_here.add(why)
            if ok:
                got.append(x); imp |= add_here
        if got and (best is None or len(got) > len(best[1])):
            best = (c, got, imp)
    if best:
        absorbed += len(best[1])
        lines += sum(info[x][1] - info[x][0] + 1 for x in best[1])
        imports_needed |= best[2]
print(f"import を足してまとめられる写し: {absorbed} 個、宣言の行 {lines}、足す import {len(imports_needed)} 行"
      f"({len({n for n, _ in imports_needed})} モジュール)")
print("まとめられない理由(最初に当たったもの):", dict(reasons.most_common()))
