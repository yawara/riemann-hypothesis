#!/usr/bin/env python3
"""守る宣言の見直し: 使われれば必ず証明項に跡が残る種類の宣言を、守る宣言(shorten_protect.py)から外す。

段階 1a では、カーネルの項にも .ilean の参照にも現れないのに消すとエラボレーションが変わりうる宣言を、使われているか
どうかにかかわらず残した(閉包の起点に加えた)。そのうち次のものは、実際に使われれば証明項に跡が残るので、守らなくてよい
(守るのをやめても、使われていれば閉包が残す)。

  * `@[simp]` の定理で、`@[defeq]` も `@[backward_defeq]` も付いていないもの: Lean 4.33 の simp・dsimp が跡を残さずに
    使うのは、この 2 つの属性の付いた(rfl で証明できる)定理だけ。それ以外の simp 補題で書き換えると、証明項に補題の
    定数が入る。`backward.defeqAttrib.useBackward` を使うファイルがあるので、`@[backward_defeq]` も rfl とみなす
  * instance で、class が強制変換(`Coe…` で始まる名前)でないもの: instance の引数は証明項に入る。強制変換の instance は
    エラボレーションで展開されて跡を残さない
  * `@[ext]` の定理(rfl でないもの): ext タクティクが使えば証明項に入る

ほかの理由(記法・マクロ、別名の定数を生成する属性、mutual、ほかの拡張の属性)で守っている宣言はそのまま守る。
1 つの宣言に理由が複数あれば、すべてが外せる理由のときだけ外す。

入力: --protected(shorten_protect.py の protected.tsv)、--info(rhshrink の RHSHRINK_DECL_INFO が書く decl-info.tsv)
出力(--out): review.tsv(モジュール・名前・守る理由・判定・根拠)、roots.txt(守り続ける宣言の名前 + --extra-root)、
      summary.json
"""
import argparse
import collections
import json
import os

UNPROTECTABLE = {"instance", "拡張に登録する属性 simp", "拡張に登録する属性 ext"}


def is_coe_class(head):
    last = head.rsplit(".", 1)[-1]
    return last.startswith("Coe")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protected", required=True)
    ap.add_argument("--info", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--extra-root", action="append", default=[], help="起点に足す名前(cpt_copy_thms の根など)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    info = {}
    with open(a.info, encoding="utf-8") as fh:
        next(fh)
        for l in fh:
            n, kind, df, bdf, head = l.rstrip("\n").split("\t")
            info[n] = (kind, df == "1", bdf == "1", head)
    reasons = collections.defaultdict(list)
    mod = {}
    with open(a.protected, encoding="utf-8") as fh:
        next(fh)
        for l in fh:
            m, n, r = l.rstrip("\n").split("\t", 2)
            reasons[n].append(r)
            mod[n] = m
    rows = []
    keep = []
    stat = collections.Counter()
    for n, rs in sorted(reasons.items()):
        kind, df, bdf, head = info.get(n, ("?", False, False, "-"))
        verdicts = []
        for r in rs:
            if r == "instance":
                verdicts.append((not is_coe_class(head), f"class {head}"))
            elif r in ("拡張に登録する属性 simp", "拡張に登録する属性 ext"):
                ok = kind == "theorem" and not df and not bdf
                why = "rfl でない定理" if ok else ("rfl の定理(defeq)" if kind == "theorem" else f"{kind}")
                verdicts.append((ok, why))
            else:
                verdicts.append((False, "ほかの理由"))
        drop = all(v for v, _ in verdicts)
        detail = "; ".join(w for _, w in verdicts)
        rows.append((mod[n], n, ",".join(rs), "外す" if drop else "守る", detail))
        key = ("外す" if drop else "守る") + ":" + ",".join(sorted(set(rs)))
        stat[key] += 1
        if not drop:
            keep.append(n)
    with open(os.path.join(a.out, "review.tsv"), "w", encoding="utf-8") as fh:
        fh.write("module\tdecl\treasons\tdecision\tdetail\n")
        fh.write("".join("\t".join(r) + "\n" for r in rows))
    with open(os.path.join(a.out, "roots.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(n + "\n" for n in sorted(set(keep) | set(a.extra_root))))
    summary = {"protected": len(reasons), "dropped": sum(1 for r in rows if r[3] == "外す"),
               "kept": len(keep), "by_reason": dict(sorted(stat.items(), key=lambda kv: -kv[1]))}
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
