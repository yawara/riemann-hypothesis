# リーマン予想 Lean 証明の独立検証

2026 年 11 月 20 日付で <https://alpo.ge/remark.pdf> に公開された文書と、そこから配布されている
Lean 4 の形式証明(リーマン予想・一般化リーマン予想の証明とされるもの)を、**原本を保全したうえで
独立に再コンパイル・検査する** ためのリポジトリです。

検証結果のレポート(日本語)は [`docs/index.html`](docs/index.html) にあり、GitHub Pages で公開する想定です。

## 現在の状態

| 検査 | 状態 |
|---|---|
| 原本(PDF・Lean 配布物 14 分割)の取得と保全 | 完了 |
| 配布物の完全性(gzip / tar、175,190 ファイル) | 完了 |
| 依存ライブラリの真正性(Mathlib 公式タグ `v4.33.1`) | 完了 |
| ソースの静的スキャン(`sorry` / `axiom` / `native_decide` ほか) | 0 件 |
| import グラフ(欠落 0・循環 0・全モジュールが `Main` から到達可能) | 完了 |
| 全 175,187 モジュールのコンパイル(`lake build`) | **進行中**(2026-11-21 10:42 JST 開始) |
| 主定理が依存する公理(`#print axioms`) | 未実施(ビルド完了後) |
| 主張の一致確認・主張の依存解析 | 未実施(ビルド完了後) |
| カーネルによる再検査(`leanchecker`) | 未実施(ビルド完了後) |
| 独立実装のカーネル(`nanoda`)による照合 | 未実施(ビルド完了後。道具は準備済み) |
| ビルド後のソース不変確認 | 未実施(ビルド完了後) |

決定的な検査がまだ終わっていないため、**証明の正否についてはまだ何も言えません。**

## Lean コードの規模

* Lean ファイル(`.lean`): **175,187 個**
* 行数: 17,374,215 行
* 合計サイズ: 1,030,531,854 バイト(約 1.03 GB)
* ほかにビルド設定 3 ファイル(`lakefile.toml`, `lake-manifest.json`, `lean-toolchain`)
* Lean `v4.33.1` / Mathlib タグ `v4.33.1`(コミット `0df444a360ea…`)

## ディレクトリ構成

```
evidence/       原本(書き換え禁止)。取得記録とハッシュつき → evidence/README.md
  01-remark-pdf/           起点の PDF
  02-remark-pdf-text/      PDF から抽出した全文
  03-lean-tarball-parts/   Lean 配布物の 14 分割(原本)
  04-tarball-contents/     tarball の一覧と、展開後 175,190 ファイルの SHA-256
scripts/        検証手順を再実行するスクリプト
verification/   検査の結果・ログ・検査用 Lean ファイル
docs/           GitHub Pages 用のレポート
lean/           展開した Lean プロジェクト(git 管理外。原本から再構成する)
```

`lean/` は配布 tarball をそのまま展開したもので、原本(`evidence/03-lean-tarball-parts/`)から
`scripts/reconstruct.sh` でバイト単位に再構成できます。原本と二重に持たないよう git には含めていません。
配布物の `lakefile.toml` などはそのままコンパイル可能な Lake プロジェクトになっており、
ソースには一切手を加えていません。

## 再現手順

`elan`、`zstd`、`ripgrep`、Python 3 が必要です。

```bash
scripts/reconstruct.sh                 # 原本から lean/ を再構成し、全ファイルのハッシュを照合
scripts/static_scan.sh                 # 静的スキャン
python3 -I scripts/import_graph.py lean/src verification/import-graph

(cd lean && lake exe cache get)        # Lean 4.33.1 と Mathlib v4.33.1(ビルド済みキャッシュ)を取得
scripts/build.sh                       # 全体ビルド
scripts/progress.sh                    # ビルドの進捗を表示
scripts/run_checks.sh                  # 公理の一覧、主張の一致確認、主張の依存解析
scripts/run_leanchecker.sh             # 全モジュールのカーネル再検査
scripts/setup_external_checkers.sh     # lean4export / nanoda / lean4lean を用意
scripts/run_nanoda.sh                  # 主定理の依存一式を別実装カーネル nanoda で検査
scripts/reconstruct.sh --verify        # ビルド後もソースが原本と一致することを確認
```

### ビルド時の注意(ディスク)

Lake 5 はモジュールごとに、推移的に import する全成果物のパスを列挙した `setup.json` を書き出します。
`import Mathlib` だけで約 6 MB あり、このプロジェクト全体では合計 1.4 TB を超える見積もりです。
`scripts/build.sh` はビルド済みモジュールの `setup.json` を随時削除する
`scripts/setup_json_reaper.sh` を並走させてこれを回避します(削除しても Lake は再ビルドしません)。

この検証では、ビルド生成物を `/var/tmp/riemann-hypothesis-ywr/` に置き、`lean/.lake` を
そこへのシンボリックリンクにしています。

## 検証環境

AMD EPYC 7742(64 コア / 128 スレッド)、メモリ約 503 GiB、NVMe SSD、Ubuntu 24.04.4 LTS。
詳細は [`verification/hardware.txt`](verification/hardware.txt)。GPU は使用しません。
