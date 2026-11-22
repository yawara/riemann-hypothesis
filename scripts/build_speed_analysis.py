#!/usr/bin/env python3
"""ビルドの速度が落ちていく理由を調べる。

Lake は 1 モジュールをコンパイルする前に、そのモジュールが推移的に import するモジュールを 1 つずつたどって
成果物の一覧(setup.json の中身)を作る(Lake/Build/Module.lean の fetchTransImportArts)。
そこで、各モジュールの「推移的 import の数(プロジェクト内)」と、Lake がビルドログに報告した所要時間を突き合わせる。

調べること:
  * import 数ごとの所要時間(区間別の中央値・平均)と、直線の当てはめ  所要時間 ≒ a + b × import 数
  * 50 分ごとの区間に完成したモジュールの数と、その import 数
  * まだビルドされていないモジュールの import 数の分布
  * 最後に残る、順番にしか進められない部分(依存の鎖のうち、見積もり時間の合計が最長のもの)
  * Main に至るいちばん深い依存の鎖の、最後の 8 個の実績(ビルド済みなら実際の所要時間)
  * 計測時点の CPU の使われ方(全体、Lake 本体、lean プロセスの数と経過時間)

外部ライブラリは使わない。推移閉包は Python の整数をビット集合として数える(メモリを数 GB 使う)。

出力: verification/build-speed/summary.json と summary.txt
(ビルド途中の 2026-11-21 21:10 JST に実行した結果は snapshot-20261121T1210Z.* として残してある)

使い方: python3 -I scripts/build_speed_analysis.py [--no-cpu]     # ビルドが終わったあとは --no-cpu を付ける
"""
import datetime
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict, deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import closure_stats as cs  # noqa: E402  (import 行の読み取りを共用する)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_ROOT = os.environ.get("RH_RUN_ROOT", "/var/tmp/riemann-hypothesis-ywr/runs")
SRC = os.path.join(ROOT, "lean", "src")
LIB = os.path.join(ROOT, "lean", ".lake", "build", "lib", "lean")
PACKAGES = os.path.join(ROOT, "lean", ".lake", "packages")
LOG = os.path.join(RUN_ROOT, "latest-build", "build.log")
OUT_DIR = os.path.join(ROOT, "verification", "build-speed")
INTERVAL_S = 50 * 60
BINS = [0, 100, 300, 1000, 3000, 6000, 10000, 15000, 25000, None]
BUILT_RE = re.compile(r"^[✔⚠] \[\d+/\d+\] Built (\S+) \(([^)]+)\)")
DUR_RE = re.compile(r"(?:(\d+)m\s*)?(?:([\d.]+)s)?(?:(\d+)ms)?")


def iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()


def seconds(text):
    m = DUR_RE.fullmatch(text.strip())
    if not m or not any(m.groups()):
        return None
    return int(m.group(1) or 0) * 60 + float(m.group(2) or 0) + int(m.group(3) or 0) / 1000


def quantile(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def has_module_header(path):
    """ファイルが新しいモジュール方式(先頭の `module` 宣言)を使っているか。"""
    in_block = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if in_block:
                in_block = max(0, in_block + s.count("/-") - s.count("-/"))
                continue
            if not s or s.startswith("--"):
                continue
            if s.startswith("/-"):
                in_block = max(0, s.count("/-") - s.count("-/"))
                continue
            return s == "module"
    return False


def sample_cpu(duration=20):
    """duration 秒のあいだ、CPU の使われ方を測る。"""
    hz = os.sysconf("SC_CLK_TCK")

    def total():
        with open("/proc/stat") as fh:
            v = list(map(int, fh.readline().split()[1:]))
        return sum(v), v[3] + v[4]

    def procs():
        out = {}
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open(f"/proc/{name}/stat") as fh:
                    s = fh.read()
            except OSError:
                continue
            comm = s[s.index("(") + 1:s.rindex(")")]
            f = s[s.rindex(")") + 2:].split()
            out[int(name)] = (comm, int(f[11]) + int(f[12]), int(f[19]))   # 名前、CPU 時間、開始時刻
        return out

    def uptime():
        with open("/proc/uptime") as fh:
            return float(fh.read().split()[0])

    up0, (t0, i0), p0 = uptime(), total(), procs()
    counts, ages = [], []
    for _ in range(duration):
        time.sleep(1)
        up = uptime()
        lean = [v for v in procs().values() if v[0] == "lean"]
        counts.append(len(lean))
        ages += [up - v[2] / hz for v in lean]
    up1, (t1, i1), p1 = uptime(), total(), procs()
    dt = up1 - up0
    lake = sum((v[1] - p0[pid][1]) / hz for pid, v in p1.items()
               if v[0] == "lake" and pid in p0 and p0[pid][2] == v[2])
    cores = os.cpu_count()
    return {
        "seconds": round(dt, 1),
        "cores": cores,
        "busy_cores": round(cores * (1 - (i1 - i0) / (t1 - t0)), 1),
        "lake_cores": round(lake / dt, 1),
        "lean_procs_median": int(statistics.median(counts)),
        "lean_age_median_s": round(statistics.median(ages), 1) if ages else None,
        "lean_age_p90_s": round(quantile(ages, 0.9), 1) if ages else None,
    }


def main():
    want_cpu = "--no-cpu" not in sys.argv
    now = time.time()
    t0 = parse_iso(open(os.path.join(RUN_ROOT, "observations", "t0_utc")).read().strip())

    # ---- import グラフと、各モジュールの推移的 import 数 ----
    modules = {}
    for root, _dirs, files in os.walk(SRC):
        for f in files:
            if f.endswith(".lean"):
                p = os.path.join(root, f)
                modules[os.path.relpath(p, SRC)[:-5].replace(os.sep, ".")] = p
    deps = {m: [i for i in dict.fromkeys(cs.read_imports(p)) if i in modules] for m, p in modules.items()}
    with_module_header = sum(1 for p in modules.values() if has_module_header(p))
    indeg = {m: len(ds) for m, ds in deps.items()}
    rdeps = defaultdict(list)
    for m, ds in deps.items():
        for d in ds:
            rdeps[d].append(m)
    queue = deque(m for m, k in indeg.items() if k == 0)
    order = []
    while queue:
        m = queue.popleft()
        order.append(m)
        for r in rdeps[m]:
            indeg[r] -= 1
            if indeg[r] == 0:
                queue.append(r)
    assert len(order) == len(modules), "import が循環している"
    idx = {m: i for i, m in enumerate(order)}
    bits, size, depth = {}, {}, {}
    users_left = {m: len(rdeps[m]) for m in order}
    for m in order:
        b, dmax = 0, 0
        for d in deps[m]:
            b |= bits[d] | (1 << idx[d])
            dmax = max(dmax, depth[d] + 1)
            users_left[d] -= 1
            if users_left[d] == 0:
                del bits[d]            # もう誰も使わない集合は捨てる
        bits[m], size[m], depth[m] = b, b.bit_count(), dmax
    del bits

    external = 0
    for _root, _dirs, files in os.walk(PACKAGES):
        external += sum(1 for f in files if f.endswith(".olean"))

    # ---- ビルドログの所要時間と、成果物の完成時刻 ----
    dur = {}
    with open(LOG, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            mm = BUILT_RE.match(line)
            if mm and mm.group(1) in modules:
                d = seconds(mm.group(2))
                if d is not None:
                    dur[mm.group(1)] = d
    mtime = {}
    for root, _dirs, files in os.walk(LIB):
        for f in files:
            if f.endswith(".olean"):
                m = os.path.relpath(os.path.join(root, f), LIB)[:-6].replace(os.sep, ".")
                if m in modules:
                    try:
                        mtime[m] = os.stat(os.path.join(root, f)).st_mtime
                    except OSError:
                        pass
    rest = [m for m in order if m not in mtime]

    # ---- 直線の当てはめ: 所要時間 ≒ a + b × import 数 ----
    xs = [size[m] for m in dur]
    ys = [dur[m] for m in dur]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    intercept = my - slope * mx

    def predict(m):
        return intercept + slope * size[m]

    bins = []
    for lo, hi in zip(BINS, BINS[1:]):
        inside = (lambda k: lo <= k < hi) if hi is not None else (lambda k: lo <= k)
        ds = [dur[m] for m in dur if inside(size[m])]
        bins.append({
            "lo": lo, "hi": hi, "built": len(ds),
            "median_s": round(quantile(ds, 0.5), 1) if ds else None,
            "mean_s": round(sum(ds) / len(ds), 1) if ds else None,
            "remaining": sum(1 for m in rest if inside(size[m])),
        })

    intervals = []
    k = 1
    while t0 + k * INTERVAL_S <= now:
        ms = [m for m, t in mtime.items() if t0 + (k - 1) * INTERVAL_S < t <= t0 + k * INTERVAL_S]
        if ms:
            sz = [size[m] for m in ms]
            intervals.append({"seq": k, "count": len(ms), "rate_per_min": round(len(ms) / 50, 1),
                              "closure_median": quantile(sz, 0.5), "closure_mean": round(sum(sz) / len(sz), 1)})
        k += 1

    rest_sizes = [size[m] for m in rest]
    # ---- 順番にしか進められない部分: 未ビルドのモジュールだけからなる鎖で、見積もり時間の合計が最長のもの ----
    rest_set = set(rest)
    best, prev = {}, {}
    for m in sorted(rest, key=lambda m: depth[m]):       # 深さの順はトポロジカル順
        w0, p = 0.0, None
        for d in deps[m]:
            if d in rest_set and best[d] > w0:
                w0, p = best[d], d
        best[m], prev[m] = w0 + predict(m), p
    end = max(best, key=best.get) if best else None
    path = []
    while end is not None:
        path.append(end)
        end = prev[end]
    path.reverse()
    tail = [{"module": m, "closure": size[m], "predicted_s": round(predict(m))} for m in path[-8:]]

    # ---- Main に至るいちばん深い依存の鎖(深さが最大の import を順にたどる)。最後の 8 個の実績 ----
    chain = []
    cur = "Main" if "Main" in modules else None
    while cur is not None:
        chain.append(cur)
        cur = max(deps[cur], key=lambda d: depth[d]) if deps[cur] else None
    chain.reverse()
    chain_tail = [{
        "module": m, "closure": size[m], "predicted_s": round(predict(m)),
        "actual_s": dur.get(m), "finished_at_utc": iso(mtime[m]) if m in mtime else None,
    } for m in chain[-8:]]

    recent = intervals[-3:]
    out = {
        "as_of_utc": iso(now),
        "t0_utc": iso(t0),
        "modules_total": len(modules),
        "built": len(mtime),
        "remaining": len(rest),
        "external_modules": external,
        "files_with_module_header": with_module_header,
        "regression": {"n": n, "intercept_s": round(intercept, 1), "slope_s_per_1000": round(slope * 1000, 2)},
        "bins": bins,
        "intervals": intervals,
        "recent": {
            "rate_per_min": round(sum(i["count"] for i in recent) / (50 * len(recent)), 1),
            "closure_mean": round(sum(i["closure_mean"] * i["count"] for i in recent) / sum(i["count"] for i in recent)),
        } if recent else None,
        "remaining_closure": {
            "median": quantile(rest_sizes, 0.5), "mean": round(sum(rest_sizes) / len(rest_sizes)),
            "p90": quantile(rest_sizes, 0.9), "p99": quantile(rest_sizes, 0.99), "max": max(rest_sizes),
        } if rest_sizes else None,
        "critical_path": {"hours": round(best[path[-1]] / 3600, 1), "length": len(path)} if path else None,
        "tail": tail,
        "finished": not rest,
        "chain_length": len(chain),
        "chain_tail": chain_tail,
        "cpu": sample_cpu() if want_cpu else None,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    lines = [
        f"集計時刻: {out['as_of_utc']}  済 {out['built']} / 残り {out['remaining']} / 全 {out['modules_total']}",
        f"外部ライブラリの .olean: {external} 個  `module` 宣言のあるファイル: {with_module_header} 個",
        f"当てはめ(済 {n} 件): 所要時間 ≒ {intercept:.1f} 秒 + {slope * 1000:.2f} 秒 × (import 数 / 1000)",
        "",
        "推移的 import 数(プロジェクト内)ごとの所要時間",
    ]
    for b in bins:
        rng = f"{b['lo']}〜{b['hi'] - 1}" if b["hi"] is not None else f"{b['lo']}〜"
        lines.append(f"  {rng:>14}  済 {b['built']:6d} 件  中央値 {b['median_s']} 秒  平均 {b['mean_s']} 秒  残り {b['remaining']:6d} 件")
    lines += ["", "50 分ごとの区間に完成したモジュール"]
    for i in intervals:
        lines.append(f"  #{i['seq']:2d}  {i['count']:6d} 件  {i['rate_per_min']:6.1f} /分  import 数 中央値 {i['closure_median']:6d}  平均 {i['closure_mean']:8.1f}")
    if out["remaining_closure"]:
        r = out["remaining_closure"]
        lines += ["", f"残り {len(rest)} 件の import 数: 中央値 {r['median']}  平均 {r['mean']}  90% {r['p90']}  99% {r['p99']}  最大 {r['max']}"]
    if path:
        lines += [f"順番にしか進められない鎖: {out['critical_path']['length']} 段、見積もり {out['critical_path']['hours']} 時間", "鎖の最後の 8 個:"]
        lines += [f"  {t['module']}  import 数 {t['closure']}  見積もり {t['predicted_s']} 秒" for t in tail]
    lines += ["", f"Main に至るいちばん深い鎖({len(chain)} 段)の最後の 8 個: import 数 / 当てはめの見積もり / 実際"]
    for t in chain_tail:
        actual = f"{t['actual_s']:.0f} 秒" if t["actual_s"] is not None else "未"
        lines.append(f"  {t['module']}  {t['closure']}  {t['predicted_s']} 秒  {actual}")
    if out["cpu"]:
        c = out["cpu"]
        lines += ["", f"CPU({c['seconds']} 秒間): {c['cores']} スレッド中 {c['busy_cores']} 本ぶんを使用、うち Lake 本体が {c['lake_cores']} 本ぶん。"
                      f"lean プロセスは中央値 {c['lean_procs_median']} 個、起動からの経過は中央値 {c['lean_age_median_s']} 秒(90% 点 {c['lean_age_p90_s']} 秒)"]
    with open(os.path.join(OUT_DIR, "summary.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
