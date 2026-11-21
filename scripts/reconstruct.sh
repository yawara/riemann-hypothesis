#!/usr/bin/env bash
# 保全した原本(14 分割の tarball)から、コンパイル可能な Lean プロジェクト lean/ を
# バイト単位で再構成し、原本との一致を検証する。
#
#   1. 14 分割それぞれの SHA-256 を evidence/03-lean-tarball-parts/SHA256SUMS と照合
#   2. 連結した gzip ストリームの SHA-256 を照合
#   3. リポジトリ直下に展開(tarball のトップレベルが lean/)
#   4. 展開した全 175,190 ファイルの SHA-256 を evidence/04-tarball-contents の一覧と照合
#
# 使い方: scripts/reconstruct.sh           # lean/ が無ければ展開して検証
#         scripts/reconstruct.sh --verify  # 既存の lean/ を検証するだけ(展開しない)
set -euo pipefail
export LC_ALL=C

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARTS="$ROOT/evidence/03-lean-tarball-parts"
CONTENTS="$ROOT/evidence/04-tarball-contents"
EXPECTED_STREAM_SHA256="9631b4f020199e580ba86178cb56c6e9b09f690c2369a80dc4334aa93f49c7fc"
EXPECTED_STREAM_BYTES=239275554

cd "$ROOT"

echo "[1/4] 分割ファイルの SHA-256 を照合"
(cd "$PARTS" && sha256sum --quiet -c SHA256SUMS)
echo "      OK (14 parts)"

echo "[2/4] 連結ストリームの SHA-256 とサイズを照合"
actual_sha="$(cat "$PARTS"/lean.tar.gz.part?? | sha256sum | cut -d' ' -f1)"
actual_bytes="$(cat "$PARTS"/lean.tar.gz.part?? | wc -c)"
[ "$actual_sha" = "$EXPECTED_STREAM_SHA256" ] || { echo "NG: stream sha256 = $actual_sha"; exit 1; }
[ "$actual_bytes" = "$EXPECTED_STREAM_BYTES" ] || { echo "NG: stream bytes = $actual_bytes"; exit 1; }
echo "      OK ($actual_bytes bytes, sha256 $actual_sha)"

if [ "${1:-}" != "--verify" ]; then
  echo "[3/4] 展開"
  if [ -e "$ROOT/lean/src" ]; then
    echo "      lean/src が既に存在するため展開をスキップ(検証のみ行う)"
  else
    # 通常ファイルのみ・絶対パスや .. を含まないことは evidence/04 の一覧で確認済み。
    cat "$PARTS"/lean.tar.gz.part?? | tar -xzf - --no-same-owner --no-same-permissions
    echo "      OK"
  fi
else
  echo "[3/4] 展開はスキップ(--verify)"
fi

echo "[4/4] 展開済み全ファイルの SHA-256 を照合"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
zstd -dc "$CONTENTS/SHA256SUMS.extracted.txt.zst" > "$tmp"
expected_n="$(wc -l < "$tmp")"
# 一覧に無い余分なファイルが lean/src と設定 3 ファイルに紛れていないかも確認する
actual_n="$( { find lean/src -type f; ls lean/lake-manifest.json lean/lakefile.toml lean/lean-toolchain; } | wc -l)"
[ "$actual_n" = "$expected_n" ] || { echo "NG: file count $actual_n != $expected_n"; exit 1; }
xargs -a "$tmp" -d '\n' -n 4000 -P "$(nproc)" sh -c 'printf "%s\n" "$@" | sha256sum --quiet -c -' _
echo "      OK ($expected_n files, 原本と完全一致)"
