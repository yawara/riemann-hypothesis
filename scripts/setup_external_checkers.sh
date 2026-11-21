#!/usr/bin/env bash
# Lean 本体とは別実装のカーネルで照合するための外部ツールを用意する。
#
#   * lean4export … Lean の環境を NDJSON(export format 3.1.0)に書き出す公式ツール
#   * nanoda_lib  … Rust で書かれた独立実装の Lean 4 型検査器
#   * lean4lean   … Lean で書かれたカーネル実装(C++ カーネルから派生しており、完全に
#                   独立とは言えないが、別のコードベースによる検査になる)
#
# いずれも配布物とは無関係の公開リポジトリから取得する。配布物の .olean は Lean 4.33.1 で
# 生成されるので、lean4export と lean4lean は lean-toolchain を v4.33.1 に書き換えて
# ビルドする(.olean はバージョンが一致しないと読めないため)。
#
# Rust は検証機に入っていた 1.67 では nanoda をビルドできなかったため、利用者の環境を
# 変えないよう $TOOLS 配下に隔離した rustup で stable を入れる。
#
# 使い方: scripts/setup_external_checkers.sh
set -euo pipefail
TOOLS="${RH_TOOLS:-/var/tmp/riemann-hypothesis-ywr/tools}"
mkdir -p "$TOOLS"
cd "$TOOLS"

LEAN4EXPORT_REV="v4.33.0"                                  # 15f6055e299ad5b89345e533cc2192f4cc00f659
LEAN4LEAN_REV="67f63b0c818920dfaed2ad07ccff187a6a8fe1e3"   # master, 2026-10-10
NANODA_REV="0da9f98feadd3a0a2ef4b3dbcf52a298a6fef929"      # master, 2026-11-07 (v0.4.32)

# ---- lean4export ----
[ -d lean4export ] || git clone -q https://github.com/leanprover/lean4export.git
( cd lean4export
  git checkout -q -f "$LEAN4EXPORT_REV"
  echo "leanprover/lean4:v4.33.1" > lean-toolchain
  lake build lean4export )

# ---- lean4lean ----
[ -d lean4lean ] || git clone -q https://github.com/digama0/lean4lean.git
( cd lean4lean
  git checkout -q -f "$LEAN4LEAN_REV"
  echo "leanprover/lean4:v4.33.1" > lean-toolchain
  sed -i 's|rev = "v4.33.0-rc2"|rev = "v4.33.0"|' lakefile.toml   # Batteries も 4.33 正式版へ
  lake update batteries
  lake build lean4lean )

# ---- Rust(隔離)と nanoda ----
export RUSTUP_HOME="$TOOLS/rustup" CARGO_HOME="$TOOLS/cargo"
if [ ! -x "$CARGO_HOME/bin/cargo" ]; then
  mkdir -p rustup-init
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o rustup-init/rustup-init.sh
  sh rustup-init/rustup-init.sh -y --no-modify-path --profile minimal --default-toolchain stable
fi
export PATH="$CARGO_HOME/bin:$PATH"
[ -d nanoda_lib ] || git clone -q https://github.com/ammkrn/nanoda_lib.git
( cd nanoda_lib
  git checkout -q "$NANODA_REV"
  cargo build --release )

echo "lean4export: $(git -C lean4export rev-parse HEAD)"
echo "lean4lean:   $(git -C lean4lean rev-parse HEAD)"
echo "nanoda_lib:  $(git -C nanoda_lib rev-parse HEAD)"
echo "rustc:       $(rustc --version)"
