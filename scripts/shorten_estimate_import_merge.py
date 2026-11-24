"""段階 1b の次の手の見積もり: import を足してまとめる。足す import で増える読み込みが「無害」なモジュールだけなら可とする。
無害 = 守る宣言(instance・simp 補題・記法・マクロ・拡張に登録する属性など)が無く、宣言の外の大域的な attribute 命令や
メタ命令(notation・macro_rules など)も無いモジュール。"""
import collections, os, re, sys

R = "/var/tmp/riemann-hypothesis-ywr/runs/shorten"
STAGE = "/var/tmp/riemann-hypothesis-ywr/shorten/stage-1a/src"
DUPS = sorted(d for d in os.listdir(R) if d.startswith("analysis-dups1b-"))[-1]
IMPORT_RE = re.compile(r"^import\s+(\S+)\s*$")
META_RE = re.compile(r"^(attribute\s+\[(?!local)|run_cmd|run_elab|run_meta|initialize|builtin_initialize|notation|notation3|infix|infixl|infixr|prefix|postfix|macro|macro_rules|syntax|elab|elab_rules|declare_syntax_cat|export|binder_predicate|scoped|local\s+notation|unif_hint|add_decl_doc)\b")

# 段階 1a の短縮版の import と、無害かどうか
imps, inert = {}, {}
prot_mods = set()
for l in list(open(f"{R}/protect/protected.tsv", encoding="utf-8"))[1:]:
    prot_mods.add(l.split("\t", 1)[0])
for d, _, fs in os.walk(STAGE):
    for f in fs:
        if not f.endswith(".lean"):
            continue
        m = os.path.relpath(os.path.join(d, f), STAGE)[:-5].replace(os.sep, ".")
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
clos = {}
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
        c = 0
        for x in ims:
            c |= (1 << idx[x]) | clos[x]
        clos[m] = c
        st.pop()
noninert_bits = 0
for m, ok in inert.items():
    if not ok:
        noninert_bits |= 1 << idx[m]
print(f"modules {len(imps)}, inert {sum(inert.values())}", flush=True)

# 計画(plan1b-4)の結果
merged = set()
canon = set()
for l in list(open(f"{R}/plan1b-4/redirect.tsv", encoding="utf-8"))[1:]:
    xm, x, cm, c = l.rstrip("\n").split("\t")
    merged.add((xm, x)); canon.add((cm, c))
blocked = {}
for l in list(open(f"{R}/plan1b-4/blocked.tsv", encoding="utf-8"))[1:]:
    m, n, r = l.rstrip("\n").split("\t")
    blocked[(m, n)] = r
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

def need_import(cm, n):
    """n から C(モジュール cm)が見えなければ、足す import の可否と増える読み込み"""
    if n == cm or (n in clos and (clos[n] >> idx[cm]) & 1):
        return True, None
    if cm in clos and n in idx and (clos[cm] >> idx[n]) & 1:
        return False, "循環"
    add = (clos[cm] | (1 << idx[cm])) & ~(clos[n] | (1 << idx[n]))
    if add & noninert_bits:
        return False, "無害でない読み込みが増える"
    return True, (n, cm)

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
            ok = True
            add_here = set()
            for (rm, owner, problem) in refs.get(x, ()):
                if owner == "-" or (rm, owner) in merged or owner == x[1]:
                    continue
                if problem != "-":
                    ok = False; reasons["参照に別の問題"] += 1; break
                if rm == c[0]:
                    continue  # 同じモジュール(前後は今回は見ない。見積もり)
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
