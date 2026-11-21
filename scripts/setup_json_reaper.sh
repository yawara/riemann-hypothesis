#!/usr/bin/env bash
# Lake 5 が各モジュールごとに書き出す <Module>.setup.json を、不要になり次第削除する。
#
# 背景: setup.json には推移的に import する全モジュールの成果物パスが列挙される。
# `import Mathlib` するだけで約 6 MB、本プロジェクト(175,187 モジュール)全体では
# 合計 1.4 TB を超える見積もりとなり、検証機のディスクに収まらない。
# 一方 setup.json は `lean --setup <file>` の起動時入力にすぎず、ビルド済みモジュールの
# setup.json を消しても Lake は再ビルドしない(trace の出力一覧に含まれない)ことを
# 小さな例で確認済み。したがってビルドの正しさ・再現性には影響しない。
#
# 削除条件(両方を満たすもの):
#   * 最終更新から MIN_AGE_MIN 分以上経過している
#   * 実行中のどの lean プロセスの `--setup` 引数にも現れない
#
# 使い方: scripts/setup_json_reaper.sh <lean/.lake/build/ir> [間隔秒=30] [MIN_AGE_MIN=5]
set -u
IR="${1:?usage: setup_json_reaper.sh <ir-dir> [interval] [min-age-min]}"
INTERVAL="${2:-30}"
MIN_AGE_MIN="${3:-5}"
export LC_ALL=C

while :; do
  if [ -d "$IR" ]; then
    running="$(ps -eo args -ww 2>/dev/null | grep -o -- '--setup [^ ]*\.setup\.json' | sed -e 's/^--setup //' -e 's|.*/build/ir/||' | sort -u)"
    find "$IR/" -type f -name '*.setup.json' -mmin "+$MIN_AGE_MIN" -printf '%P\n' 2>/dev/null \
      | { if [ -n "$running" ]; then grep -v -x -F -f <(printf '%s\n' "$running"); else cat; fi; } \
      | while IFS= read -r rel; do rm -f -- "$IR/$rel"; done
  fi
  sleep "$INTERVAL"
done
