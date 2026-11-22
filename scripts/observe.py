#!/usr/bin/env python3
"""定点観測: ビルド開始から 50 分ごとの時点で、検証機の状態を記録する。

観測点は「ビルド開始時刻 + 50 分 × k」(k = 1, 2, …)に固定する。各観測点で次を記録する。

  * コンパイル済みモジュール数(.olean の個数)
  * ビルドログのエラー行数・警告付きでビルドされたモジュール数(自動集計。精査前の生の値)
  * 実行中の lean プロセス数、ロードアベレージ、メモリ使用量、ディスクの空き
  * いま実行中の段階(ビルド / ビルド後の検査 / 別実装カーネル / …)
  * カーネルによる再検査(scripts/run_leanchecker.sh)で再生を終えたモジュール数(配布物・依存ライブラリ)

常駐を始める前の観測点は、.olean の更新時刻から「その時点で何個できていたか」だけを復元する
(source = "mtime"。負荷やメモリは記録が無いので空欄)。

出力:
  $RH_RUN_ROOT/observations/fixed.jsonl        実測した観測点の生記録(追記のみ)
  $RH_RUN_ROOT/observations/observations.json  サイト用のまとめ(5 分刻みの進捗曲線 + 観測点の一覧)
  verification/observations.jsonl              観測点の一覧(リポジトリに残す分)
  <gh-pages 作業ツリー>/observations.json      --publish / --daemon のとき。commit して push する

ここで公開するのは測定値だけで、合否の判定は含まない。

使い方:
  python3 -I scripts/observe.py              # いまの状態でまとめを作り直す(観測点は増やさない)
  python3 -I scripts/observe.py --publish    # 上に加えて gh-pages に反映
  python3 -I scripts/observe.py --daemon     # 常駐。観測点ごとに記録して gh-pages に反映
"""
import argparse
import bisect
import datetime
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_ROOT = os.environ.get("RH_RUN_ROOT", "/var/tmp/riemann-hypothesis-ywr/runs")
WT = os.environ.get("RH_PAGES_WORKTREE", "/var/tmp/riemann-hypothesis-ywr/gh-pages")
OBS_DIR = os.path.join(RUN_ROOT, "observations")
FIXED = os.path.join(OBS_DIR, "fixed.jsonl")
OUT = os.path.join(OBS_DIR, "observations.json")
REPO_COPY = os.path.join(ROOT, "verification", "observations.jsonl")
LIB = os.path.join(ROOT, "lean", ".lake", "build", "lib", "lean")
INTERVAL_MIN = 50
STEP_MIN = 5
TOTAL = 175187
# これらのプロセスがすべて終わったら、最後の観測をして常駐を終える
PID_FILES = ["build.pid", "pipeline.pid", "mathlib-from-source.pid"]


def iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def read_t0():
    """観測の起点(ビルド開始時刻)。再ビルドで latest-build が変わっても動かないよう、最初に固定する。"""
    pin = os.path.join(OBS_DIR, "t0_utc")
    s = read_text(pin).strip()
    if s:
        return parse_iso(s)
    for line in read_text(os.path.join(RUN_ROOT, "latest-build", "build.meta.txt")).splitlines():
        if line.startswith("started_at_utc:"):
            s = line.split(":", 1)[1].strip()
            os.makedirs(OBS_DIR, exist_ok=True)
            with open(pin, "w", encoding="utf-8") as fh:
                fh.write(s + "\n")
            return parse_iso(s)
    raise SystemExit("ビルド開始時刻が分からない(build.meta.txt が無い)")


def olean_mtimes():
    out = []
    stack = [LIB]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.name.endswith(".olean"):
                        try:
                            out.append(e.stat().st_mtime)
                        except OSError:
                            pass
        except OSError:
            pass
    out.sort()
    return out


def log_counts():
    """ビルドログの行頭の記号を数える。✔ = 警告なしでビルド、⚠ = 警告付きでビルド、✖ / error: = エラー。"""
    ok = warn = err = 0
    try:
        with open(os.path.join(RUN_ROOT, "latest-build", "build.log"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                c = line[:1]
                if c == "✔":
                    ok += 1
                elif c == "⚠":
                    warn += 1
                elif c == "✖" or line.startswith("error: "):
                    err += 1
    except OSError:
        return None, None, None
    return ok, warn, err


def lean_procs():
    n = 0
    for name in os.listdir("/proc"):
        if name.isdigit():
            try:
                with open(f"/proc/{name}/comm") as fh:
                    if fh.read().strip() == "lean":
                        n += 1
            except OSError:
                pass
    return n


def meminfo_gib():
    vals = {}
    for line in read_text("/proc/meminfo").splitlines():
        k, _, rest = line.partition(":")
        if k in ("MemTotal", "MemAvailable"):
            vals[k] = int(rest.split()[0])
    if len(vals) < 2:
        return None
    return round((vals["MemTotal"] - vals["MemAvailable"]) / 1048576, 1)


def disk_free_gib(path):
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    return round(st.f_bavail * st.f_frsize / 2**30, 1)


def phase():
    p = os.path.join(RUN_ROOT, "pipeline")
    st = read_text(os.path.join(p, "status.txt"))
    if os.path.exists(os.path.join(p, "result")):
        if os.path.exists(os.path.join(RUN_ROOT, "mathlib-from-source.out")) and not os.path.exists(
            os.path.join(RUN_ROOT, "mathlib-from-source.rc")
        ):
            return "mathlib-rebuild"
        return "finished"
    if "nanoda: start" in st:
        return "independent-kernel"
    if re.search(r"(checks|leanchecker): start", st):
        return "post-build-checks"
    if "retrying" in st:
        return "build-retry"
    if "build finished" in st:
        return "build-finished"
    return "build"


def any_alive():
    for name in PID_FILES:
        s = read_text(os.path.join(RUN_ROOT, name)).strip()
        if s.isdigit() and os.path.exists(f"/proc/{s}"):
            return True
    return False


def replay_counts():
    """カーネルによる再検査の進み具合。各バッチのログの `ok` / `FAILED` 行を数える。"""
    out = {}
    for scope in ("project", "deps"):
        d = os.path.join(RUN_ROOT, f"latest-leanchecker-{scope}")
        modules = os.path.join(d, "modules.txt")
        if not os.path.isfile(modules):
            continue
        ok = failed = 0
        for name in os.listdir(d):
            if name.startswith("batch.") and name.endswith(".log"):
                try:
                    with open(os.path.join(d, name), encoding="utf-8", errors="replace") as fh:
                        for line in fh:
                            if line.startswith("ok "):
                                ok += 1
                            elif line.startswith("FAILED "):
                                failed += 1
                except OSError:
                    pass
        with open(modules, encoding="utf-8") as fh:
            total = sum(1 for line in fh if line.strip())
        out[scope] = {"ok": ok, "failed": failed, "total": total}
    return out or None


def measure(mt):
    ok, warn, err = log_counts()
    load = read_text("/proc/loadavg").split()
    return {
        "done": len(mt),
        "error_lines": err,
        "built_with_warnings": warn,
        "lean_procs": lean_procs(),
        "load1": float(load[0]) if load else None,
        "mem_used_gib": meminfo_gib(),
        "disk_free_gib": disk_free_gib(os.path.dirname(RUN_ROOT)),
        "phase": phase(),
        "replay": replay_counts(),
    }


def load_live():
    live = {}
    for line in read_text(FIXED).splitlines():
        line = line.strip()
        if line:
            rec = json.loads(line)
            live[rec["seq"]] = rec
    return live


def build(now=None, new_fixed=None):
    """まとめを作って書き出す。new_fixed = (k, tk) を渡すと、その観測点を実測として記録する。"""
    os.makedirs(OBS_DIR, exist_ok=True)
    t0 = read_t0()
    now = now or time.time()
    mt = olean_mtimes()
    m = measure(mt)

    if new_fixed:
        k, tk = new_fixed
        rec = {"seq": k, "t_utc": iso(tk), "elapsed_min": k * INTERVAL_MIN, "measured_at_utc": iso(now), **m, "source": "live"}
        with open(FIXED, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    live = load_live()
    points = []
    prev_done = bisect.bisect_right(mt, t0)
    k = 1
    while t0 + k * INTERVAL_MIN * 60 <= now:
        tk = t0 + k * INTERVAL_MIN * 60
        rec = live.get(k)
        if rec:
            p = {key: rec.get(key) for key in (
                "seq", "t_utc", "elapsed_min", "done", "error_lines", "built_with_warnings",
                "lean_procs", "load1", "mem_used_gib", "disk_free_gib", "phase", "replay", "source")}
        else:
            p = {"seq": k, "t_utc": iso(tk), "elapsed_min": k * INTERVAL_MIN, "done": bisect.bisect_right(mt, tk),
                 "error_lines": None, "built_with_warnings": None, "lean_procs": None, "load1": None,
                 "mem_used_gib": None, "disk_free_gib": None, "phase": "build", "replay": None, "source": "mtime"}
        p["rate_per_min"] = round((p["done"] - prev_done) / INTERVAL_MIN, 1)
        prev_done = p["done"]
        points.append(p)
        k += 1

    # 5 分刻みの進捗曲線(t0 + i*5 分の時点でできていた .olean の数)。最後の点は「いま」。
    series = []
    i = 0
    while t0 + i * STEP_MIN * 60 <= now:
        series.append(bisect.bisect_right(mt, t0 + i * STEP_MIN * 60))
        i += 1

    projection = None
    if m["phase"] == "build" and m["done"] < TOTAL:
        window = 100 * 60
        since = max(t0, now - window)
        made = m["done"] - bisect.bisect_right(mt, since)
        minutes = (now - since) / 60
        if made > 0 and minutes >= 20:
            rate = made / minutes
            projection = {
                "window_min": round(minutes),
                "rate_per_min": round(rate, 1),
                "eta_utc": iso(now + (TOTAL - m["done"]) / rate * 60),
            }

    out = {
        "schema": 1,
        "t0_utc": iso(t0),
        "interval_min": INTERVAL_MIN,
        "step_min": STEP_MIN,
        "total": TOTAL,
        "generated_at_utc": iso(now),
        "latest": {"t_utc": iso(now), **m},
        "projection": projection,
        "series": series,
        "points": points,
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    os.replace(tmp, OUT)

    os.makedirs(os.path.dirname(REPO_COPY), exist_ok=True)
    tmp = REPO_COPY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for p in points:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    os.replace(tmp, REPO_COPY)
    return out


def publish(message):
    if not os.path.exists(os.path.join(WT, ".git")):
        print("gh-pages の作業ツリーが無いので公開は省略", file=sys.stderr)
        return
    with open(WT + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        shutil.copyfile(OUT, os.path.join(WT, "observations.json"))
        subprocess.run(["git", "-C", WT, "add", "observations.json"], check=True)
        if subprocess.run(["git", "-C", WT, "diff", "--cached", "--quiet"]).returncode != 0:
            subprocess.run(
                ["git", "-C", WT, "commit", "-q", "-m",
                 message + "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"],
                check=True,
            )
            r = subprocess.run(["git", "-C", WT, "push", "-q", "origin", "gh-pages"])
            if r.returncode != 0:
                print(f"push failed at {iso(time.time())}", file=sys.stderr)


def message_for(out, seq=None):
    m = out["latest"]
    head = f"定点観測 #{seq}" if seq else "観測記録を更新"
    return f"{head}: {m['done']} / {TOTAL} ({m['phase']})"


def daemon():
    t0 = read_t0()
    out = build()
    publish(message_for(out))
    print(f"{iso(time.time())} start: points={len(out['points'])} done={out['latest']['done']}", flush=True)
    while True:
        now = time.time()
        k = int((now - t0) // (INTERVAL_MIN * 60)) + 1
        tk = t0 + k * INTERVAL_MIN * 60
        while True:
            left = tk - time.time()
            if left <= 0:
                break
            time.sleep(min(left, 30))
        try:
            out = build(new_fixed=(k, tk))
            publish(message_for(out, k))
            print(f"{iso(time.time())} #{k}: done={out['latest']['done']} phase={out['latest']['phase']}", flush=True)
        except Exception as e:  # 1 回の失敗で常駐を止めない
            print(f"{iso(time.time())} #{k}: FAILED {e!r}", file=sys.stderr, flush=True)
        if not any_alive():
            print(f"{iso(time.time())} 監視対象のプロセスがすべて終了したので、観測を終える", flush=True)
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()
    if a.daemon:
        daemon()
        return
    out = build()
    if a.publish:
        publish(message_for(out))
    m = out["latest"]
    print(f"points={len(out['points'])} done={m['done']} errors={m['error_lines']} phase={m['phase']} "
          f"projection={out['projection']}")


if __name__ == "__main__":
    main()
