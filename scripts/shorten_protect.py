#!/usr/bin/env python3
"""段階 1a: カーネルの項にも .ilean の参照にも現れないのに、消すとエラボレーションが変わりうる宣言を選ぶ。

ここで選んだ宣言は、使われているかどうかにかかわらず残し、閉包の起点に加える
(残す宣言が参照する宣言も残すため。shorten_source_closure.py と rhshrink を交互に回す)。

選ぶもの(宣言のソースの先頭を見て判定する)
  * メタ命令: notation・infix・macro・syntax・elab など。生成される構文の定数が宣言の行範囲を持つため、
    宣言として「使われていない」と判定されうるが、記法として使われている
  * instance(`instance` か `@[instance]`): 強制変換(CoeSort など)の instance は、エラボレーションで展開されて
    証明項に跡を残さない
  * `@[simp]`: rfl で証明した補題は、dsimp が証明項に跡を残さずに使う
  * 別名の定数を生成する属性(`@[reassoc]`・`@[simps]`・`@[to_additive]`・`@[elementwise]`): 生成された定数が
    使われていても、名前が元の宣言の下に無いので、元の宣言に帰属できない
  * タクティクやエラボレーションの拡張に登録する属性(`@[ext]`・`@[positivity]`・`@[norm_num]`・`@[simproc]` など)
  * mutual ブロックを含むモジュールの宣言

入力: decls.tsv.zst(rhshrink)、lean/src
出力: <出力先>/protected.tsv(モジュール\\t名前\\t理由)、protected-roots.txt(rhshrink の起点に渡す名前)

使い方: python3 -I scripts/shorten_protect.py --decls <decls.tsv.zst> --out <ディレクトリ>
"""
import argparse
import collections
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "lean", "src")

META_KW = {"notation", "notation3", "infix", "infixl", "infixr", "prefix", "postfix", "macro", "macro_rules",
           "syntax", "elab", "elab_rules", "declare_syntax_cat", "binder_predicate", "initialize",
           "builtin_initialize", "simproc", "dsimproc"}
GEN_ATTRS = {"reassoc", "simps", "simps!", "to_additive", "elementwise", "to_dual"}
EXT_ATTRS = {"simp", "ext", "positivity", "gcongr", "fun_prop", "norm_num", "simproc", "symm", "trans", "refl",
             "coe", "induction_eliminator", "cases_eliminator", "mono", "aesop", "continuity", "measurability",
             "norm_cast", "push_cast", "field_simps", "bound", "nontriviality", "default_instance", "instance",
             "app_unexpander", "delab", "tactic", "command_elab", "term_elab", "macro", "csimp", "implemented_by",
             "extern", "export", "match_pattern", "grind", "congr", "inherit_doc"}
DOC_RE = re.compile(r"\A\s*/--.*?-/\s*", re.S)
ATTR_RE = re.compile(r"\A\s*@\[((?:[^\[\]]|\[[^\]]*\])*)\]\s*", re.S)
MOD_RE = re.compile(r"\A\s*(?:(?:private|protected|noncomputable|scoped|local|partial|unsafe|nonrec|meta)\s+)*")
KW_RE = re.compile(r"\A\s*([A-Za-z_][A-Za-z_0-9!]*)")
MUTUAL_RE = re.compile(r"^\s*mutual\s*$", re.M)


def split_attrs(body):
    out, depth, cur = [], 0, ""
    for ch in body:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    names = []
    for a in out:
        toks = a.split()
        while toks and toks[0] in ("local", "scoped", "-"):
            toks = toks[1:]
        if toks:
            names.append(toks[0])
    return names


def classify(head):
    """宣言の先頭の文字列から (キーワード, 属性の集合) を返す"""
    s = head
    attrs = set()
    while True:
        m = DOC_RE.match(s)
        if m:
            s = s[m.end():]
            continue
        m = ATTR_RE.match(s)
        if m:
            attrs.update(split_attrs(m.group(1)))
            s = s[m.end():]
            continue
        break
    s = s[MOD_RE.match(s).end():]
    m = KW_RE.match(s)
    return (m.group(1) if m else ""), attrs


def reason_for(kw, attrs, has_mutual):
    if kw in META_KW:
        return f"メタ命令 {kw}"
    if kw == "instance" or "instance" in attrs:
        return "instance"
    g = attrs & GEN_ATTRS
    if g:
        return "定数を生成する属性 " + ",".join(sorted(g))
    e = attrs & EXT_ATTRS
    if e:
        return "拡張に登録する属性 " + ",".join(sorted(e))
    if has_mutual:
        return "mutual を含むモジュール"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decls", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    by_mod = collections.defaultdict(list)
    p = subprocess.Popen(["zstd", "-dc", args.decls], stdout=subprocess.PIPE, text=True)
    next(p.stdout)
    for line in p.stdout:
        mod, name, kind, s, e = line.rstrip("\n").split("\t")[:5]
        by_mod[mod].append((name, int(s), int(e)))
    p.wait()
    rows = []
    for mod, ds in sorted(by_mod.items()):
        with open(os.path.join(SRC, *mod.split(".")) + ".lean", encoding="utf-8") as fh:
            text = fh.read()
        lines = text.split("\n")
        has_mutual = bool(MUTUAL_RE.search(text))
        for name, s, e in ds:
            head = "\n".join(lines[s - 1:min(e, s + 8)])
            kw, attrs = classify(head)
            r = reason_for(kw, attrs, has_mutual)
            if r:
                rows.append((mod, name, r))
    with open(os.path.join(args.out, "protected.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tdecl\treason\n")
        fh.write("".join(f"{a}\t{b}\t{c}\n" for a, b, c in rows))
    with open(os.path.join(args.out, "protected-roots.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(n + "\n" for n in sorted({b for _, b, _ in rows})))
    cnt = collections.Counter(r.split(" ")[0] for *_, r in rows)
    print(f"protected decls: {len(rows)}", dict(cnt))


if __name__ == "__main__":
    main()
