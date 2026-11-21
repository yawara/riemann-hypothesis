#!/usr/bin/env bash
# レポートサイト(site/。Astro 製)をビルドし、公開用ブランチ gh-pages に反映して push する。
#
#   1. scripts/site_data.py でサイト用データ(図・Lean ファイル全文・ビルド進捗)を生成
#   2. site/ を `astro build` で静的ファイル(site/dist/)にする
#   3. site/dist/ を gh-pages の作業ツリー($WT)へ同期して commit / push
#
#   * main ブランチの site/ が原稿、gh-pages ブランチが公開物(GitHub Pages の公開元)。
#   * status.json(進捗の自動集計)は scripts/status_updater.sh の持ち物なので触らない。
#   * Node.js は $RH_NODE_BIN(既定: 検証機に隔離して入れた場所)にあれば PATH に加える。
#
# 使い方: scripts/publish_pages.sh ["コミットメッセージ"] [--no-push]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WT="${RH_PAGES_WORKTREE:-/var/tmp/riemann-hypothesis-ywr/gh-pages}"
LOCK="$WT.lock"
MSG="${1:-レポートを更新}"
PUSH=1
[ "${2:-}" = "--no-push" ] && PUSH=0

NODE_BIN="${RH_NODE_BIN:-/var/tmp/riemann-hypothesis-ywr/tools/node/bin}"
[ -d "$NODE_BIN" ] && export PATH="$NODE_BIN:$PATH"
export npm_config_cache="${npm_config_cache:-/var/tmp/riemann-hypothesis-ywr/tools/npm-cache}"
export npm_config_update_notifier=false ASTRO_TELEMETRY_DISABLED=1

cd "$ROOT"
python3 -I scripts/site_data.py
(
  cd site
  [ -d node_modules ] || npm ci --ignore-scripts --no-fund --no-audit
  npx astro build
)

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
rsync -a --delete --exclude '.git' --exclude 'status.json' "$ROOT/site/dist/" "$WT/"
cd "$WT"
git add -A
if git diff --cached --quiet; then
  echo "gh-pages: 変更なし"
else
  git commit -q -m "$MSG

Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
  echo "gh-pages: $(git log -1 --format='%h %s')"
fi
if [ "$PUSH" = "1" ]; then
  git push -q origin gh-pages
  echo "pushed gh-pages"
fi
