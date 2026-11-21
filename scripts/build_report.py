#!/usr/bin/env python3
"""docs-src/template.html からレポートページ docs/index.html を生成する。

テンプレートに差し込むもの:
  * 臨界線上の Z(t) の図(verification/zeta-figure.json。scripts/gen_zeta_figure.py の出力)
  * 配布物の Main.lean / Statements.lean の全文(簡易ハイライトつき)
  * ビルド進捗(ビルド出力ディレクトリと最新のビルドログから集計。無ければ引数の値)

使い方: python3 -I scripts/build_report.py [--done N] [--errors N]
"""
import argparse
import datetime
import html
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOTAL = 175187
RUN_ROOT = os.environ.get("RH_RUN_ROOT", "/var/tmp/riemann-hypothesis-ywr/runs")


def num(v, nd=2):
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def highlight_lean(src):
    out = []
    for line in src.rstrip("\n").split("\n"):
        e = html.escape(line, quote=False)
        e = re.sub(r"^(import|theorem|def|lemma|open|namespace|end)\b", r'<span class="kw">\1</span>', e)
        e = re.sub(r'(<span class="kw">(?:theorem|def|lemma)</span> )([^\s:]+)', r'\1<span class="nm">\2</span>', e)
        e = re.sub(r"\bProp\b", '<span class="ty">Prop</span>', e)
        out.append(e)
    return "\n".join(out)


def count_oleans():
    lib = os.path.join(ROOT, "lean", ".lake", "build", "lib", "lean")
    if not os.path.isdir(lib):
        return None
    r = subprocess.run(["find", lib + "/", "-name", "*.olean"], capture_output=True, text=True)
    return len(r.stdout.splitlines())


def count_error_lines():
    log = os.path.join(RUN_ROOT, "latest-build", "build.log")
    if not os.path.isfile(log):
        return None
    n = 0
    with open(log, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("error: ") or line.startswith("✖"):
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--done", type=int)
    ap.add_argument("--errors", type=int)
    args = ap.parse_args()

    with open(os.path.join(ROOT, "docs-src", "template.html"), encoding="utf-8") as fh:
        tpl = fh.read()
    with open(os.path.join(ROOT, "verification", "zeta-figure.json"), encoding="utf-8") as fh:
        fig = json.loads(fh.readline())

    # ---- 図 ----
    zs, step, t_max = fig["z"], fig["step"], fig["t_max"]
    pts = []
    for i, z in enumerate(zs):
        x = i * step * 10        # viewBox の横 600 = t 60
        y = 40 - z * 10          # 縦 80 = Z ∈ [-4, 4]
        pts.append(f"{num(x, 1)},{num(y, 2)}")
    path = "M" + "L".join(pts)
    zeros = fig["zeros"]
    zero_spans = "\n".join(
        f'        <span class="zero" style="left:{num(t / t_max * 100, 3)}%"></span>' for t in zeros)
    rows = "\n".join(
        f'          <tr><td class="n">{i}</td><td class="n">{t:.6f}</td></tr>' for i, t in enumerate(zeros, 1))
    coarse = [round(zs[i], 3) for i in range(0, len(zs), 2)]   # 0.1 刻み
    zdata = json.dumps({"tMax": t_max, "step": step * 2, "z": coarse, "zeros": zeros}, separators=(",", ":"))

    # ---- コード ----
    with open(os.path.join(ROOT, "lean", "src", "Main.lean"), encoding="utf-8") as fh:
        code_main = highlight_lean(fh.read())
    with open(os.path.join(ROOT, "lean", "src", "Statements.lean"), encoding="utf-8") as fh:
        code_statements = highlight_lean(fh.read())

    # ---- 進捗 ----
    done = args.done if args.done is not None else (count_oleans() or 0)
    errors = args.errors if args.errors is not None else count_error_lines()
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    stamp = now.strftime("%Y-%m-%d %H:%M JST")
    pct = min(100.0, done / TOTAL * 100)
    err_txt = "集計なし" if errors is None else f"{stamp} 時点で {errors} 件" + ("(リンタの警告のみ)" if errors == 0 else "")
    note = f"{stamp} 時点。" + ("" if errors is None else f"エラー {errors} 件。")

    subs = {
        "ZPLOT_PATH": path,
        "ZPLOT_ZEROS": zero_spans,
        "ZPLOT_FIRST_LEFT": num(zeros[0] / t_max * 100, 3),
        "ZPLOT_TABLE_ROWS": rows,
        "ZDATA_JSON": zdata,
        "CODE_MAIN": code_main,
        "CODE_STATEMENTS": code_statements,
        "UPDATED": stamp,
        "BUILD_DONE": f"{done:,}",
        "BUILD_PCT": f"{pct:.1f}",
        "BUILD_NOTE": note,
        "BUILD_ERRORS": err_txt,
    }
    out = tpl
    for k, v in subs.items():
        assert "{{" + k + "}}" in out, k
        out = out.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", out)
    assert not left, left
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    with open(os.path.join(ROOT, "docs", "index.html"), "w", encoding="utf-8") as fh:
        fh.write(out)
    print(f"wrote docs/index.html ({len(out.encode('utf-8')):,} bytes) done={done} pct={pct:.1f} errors={errors} stamp={stamp}")


if __name__ == "__main__":
    main()
