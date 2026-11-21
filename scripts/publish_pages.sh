#!/usr/bin/env bash
# docs/ の内容を公開用ブランチ gh-pages に反映して push する(GitHub Pages の公開元)。
#
#   * main ブランチの docs/ がレポートの原稿、gh-pages ブランチが公開物。
#   * gh-pages は別の作業ツリー($WT)で扱うので、main の作業ツリーには影響しない。
#   * status.json(進捗の自動集計)は scripts/status_updater.sh の持ち物なので触らない。
#
# 使い方: scripts/publish_pages.sh ["コミットメッセージ"]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WT="${RH_PAGES_WORKTREE:-/var/tmp/riemann-hypothesis-ywr/gh-pages}"
LOCK="$WT.lock"
MSG="${1:-レポートを更新}"

cd "$ROOT"
if [ ! -e "$WT/.git" ]; then
  mkdir -p "$(dirname "$WT")"
  if git show-ref --verify --quiet refs/heads/gh-pages; then
    git worktree add "$WT" gh-pages
  else
    git worktree add --orphan -b gh-pages "$WT"
  fi
fi

exec 9>"$LOCK"
flock 9
rsync -a --delete --exclude '.git' --exclude 'status.json' "$ROOT/docs/" "$WT/"
cd "$WT"
git add -A
if git diff --cached --quiet; then
  echo "gh-pages: 変更なし"
else
  git commit -q -m "$MSG

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
  echo "gh-pages: $(git log -1 --format='%h %s')"
fi
git push -q origin gh-pages
echo "pushed gh-pages"
