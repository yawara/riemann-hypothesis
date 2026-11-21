#!/usr/bin/env bash
# 検証機での進み具合を status.json にまとめ、公開用ブランチ gh-pages に定期的に push する。
# レポートページはこのファイルを読んで「全体ビルドの進捗」を最新の値に差し替える。
#
# ここで公開するのは中立な進捗だけ(コンパイル済みモジュール数と、いま何を実行中か)。
# 成功・失敗などの判定は自動では書かない。判定は人が結果を精査してからレポートに載せる。
#
# 自動実行の検査がすべて終わったら、その旨を 1 回書いて終了する。
#
# 使い方: scripts/status_updater.sh [間隔秒=1200]
set -uo pipefail
export LC_ALL=C.UTF-8
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WT="${RH_PAGES_WORKTREE:-/var/tmp/riemann-hypothesis-ywr/gh-pages}"
LOCK="$WT.lock"
RUN_ROOT="${RH_RUN_ROOT:-/var/tmp/riemann-hypothesis-ywr/runs}"
P="$RUN_ROOT/pipeline"
INTERVAL="${1:-1200}"
TOTAL=175187

while :; do
  done_n="$(find "$ROOT/lean/.lake/build/lib/lean/" -name '*.olean' 2>/dev/null | wc -l)"
  final=0
  if [ -f "$P/result" ]; then
    phase="finished"; final=1
    note="自動実行の検査が終了しました。結果を精査してからレポートを更新します。"
  elif grep -q 'nanoda: start' "$P/status.txt" 2>/dev/null; then
    phase="independent-kernel"
    note="ビルドは終了し、別実装のカーネルによる照合を実行中です。結果は精査後に掲載します。"
  elif grep -q -E '(checks|leanchecker): start' "$P/status.txt" 2>/dev/null; then
    phase="post-build-checks"
    note="ビルドは終了し、ビルド後の検査(公理・主張の確認、カーネル再検査)を実行中です。結果は精査後に掲載します。"
  elif grep -q 'retrying' "$P/status.txt" 2>/dev/null; then
    phase="build-retry"
    note="ビルドの 1 回目が終了し、再実行中です。結果は精査後に掲載します。"
  elif grep -q 'build finished' "$P/status.txt" 2>/dev/null; then
    phase="build-finished"
    note="ビルドが終了しました。結果を集計しています。"
  else
    phase="build"
    note="全体ビルドを実行中です。"
  fi

  if [ -e "$WT/.git" ]; then
    (
      flock 9
      cat > "$WT/status.json" <<EOF
{
  "updated_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "phase": "$phase",
  "modules_done": $done_n,
  "modules_total": $TOTAL,
  "note_ja": "$note"
}
EOF
      cd "$WT" || exit 0
      git add status.json
      if ! git diff --cached --quiet; then
        git commit -q -m "進捗を自動更新: $done_n / $TOTAL ($phase)

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
        git push -q origin gh-pages || echo "push failed at $(date -u +%FT%TZ)" >&2
      fi
    ) 9>"$LOCK"
  fi

  [ "$final" = "1" ] && break
  sleep "$INTERVAL"
done
