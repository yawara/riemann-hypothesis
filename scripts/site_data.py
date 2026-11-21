#!/usr/bin/env python3
"""レポートサイト(site/)がビルド時に読み込むデータ site/src/data/generated.json を作る。

入れるもの:
  * zeta  … 図 1 下段のデータ(verification/zeta-figure.json。scripts/gen_zeta_figure.py の出力)
  * lean  … 配布物の Main.lean / Statements.lean の全文(lean/ が無ければ既存の値を引き継ぐ)
  * obs   … 定点観測のまとめ(scripts/observe.py の出力。無ければ既存の値を引き継ぐ)

生成物はリポジトリに含めるので、lean/ を再構成していない環境でもサイトをビルドできる。

使い方: python3 -I scripts/site_data.py
"""
import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "src", "data", "generated.json")
RUN_ROOT = os.environ.get("RH_RUN_ROOT", "/var/tmp/riemann-hypothesis-ywr/runs")
OBS = os.path.join(RUN_ROOT, "observations", "observations.json")


def read_text(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return fh.read().rstrip("\n")


def main():
    prev = {}
    if os.path.isfile(OUT):
        with open(OUT, encoding="utf-8") as fh:
            prev = json.load(fh)

    with open(os.path.join(ROOT, "verification", "zeta-figure.json"), encoding="utf-8") as fh:
        fig = json.loads(fh.readline())
    zeta = {"tMax": fig["t_max"], "step": fig["step"], "z": fig["z"], "zeros": fig["zeros"]}

    lean = {
        "main": read_text("lean/src/Main.lean") or prev.get("lean", {}).get("main"),
        "statements": read_text("lean/src/Statements.lean") or prev.get("lean", {}).get("statements"),
    }
    assert lean["main"] and lean["statements"], "lean/src が無く、引き継げる値も無い"

    obs = prev.get("obs")
    if os.path.isfile(OBS):
        with open(OBS, encoding="utf-8") as fh:
            obs = json.load(fh)
    assert obs, "定点観測のまとめが無い(先に scripts/observe.py を実行する)"

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    out = {
        "generatedAt": now.strftime("%Y-%m-%d %H:%M JST"),
        "zeta": zeta,
        "lean": lean,
        "obs": obs,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: done={obs['latest']['done']} points={len(obs['points'])} "
          f"zeros={len(zeta['zeros'])}")


if __name__ == "__main__":
    main()
