# リーマン予想 Lean 証明の独立検証

2026 年 11 月 20 日付で <https://alpo.ge/remark.pdf> に公開された文書と、そこから配布されている
Lean 4 の形式証明(リーマン予想・一般化リーマン予想の証明とされるもの)を、**原本を保全したうえで
独立に再コンパイル・検査する** ためのリポジトリです。

検証結果のレポート(日本語)は GitHub Pages で公開しています: <https://yawara.github.io/riemann-hypothesis/>
(原稿は [`site/`](site/)。検証の進行に合わせて逐次更新します。)

## 現在の状態

| 検査 | 状態 |
|---|---|
| 原本(PDF・Lean 配布物 14 分割)の取得と保全 | 完了 |
| 配布物の完全性(gzip / tar、175,190 ファイル) | 完了 |
| 依存ライブラリの真正性(Mathlib 公式タグ `v4.33.1`) | 完了 |
| ソースの静的スキャン(`sorry` / `axiom` / `native_decide` ほか) | 0 件 |
| import グラフ(欠落 0・循環 0・全モジュールが `Main` から到達可能) | 完了 |
| 全 175,187 モジュールのコンパイル(`lake build`) | 完了(エラー 0。2026-11-21 10:42 〜 11-22 9:22 JST、22 時間 40 分。50 分ごとの定点観測はレポートの 2 節) |
| 主定理が依存する公理(`#print axioms`) | 完了(5 定理とも `propext`・`Classical.choice`・`Quot.sound` のみ) |
| 主張の一致確認・主張の依存解析 | 完了(型は検証者の命題と一致。主張に配布物本体の定義は現れない) |
| カーネルによる再検査(`leanchecker` と同じ再生処理) | 完了(配布物 175,187 と依存ライブラリ 8,700 の全モジュールが通過、失敗 0) |
| 独立実装のカーネル(`nanoda`)による照合 | 完了(主定理 5 件の依存一式 1,484,729 宣言がエラー 0。一式に含まれる公理は標準の 3 つだけ) |
| ビルド後のソース不変確認 | 完了(175,190 ファイルすべてが原本と一致。2026-11-22 22:41 JST) |
| Mathlib のソースからの再ビルド照合(追加) | 完了(8,690 モジュール中 8,689 がキャッシュとバイト単位で一致。違う 1 つは主定理に関係しない自動生成の等式補題 1 個の書き方。レポート 7.9 節) |

**判定: 予定したすべての検査を通過しました。**

配布物は指定どおりの Lean 4.33.1・Mathlib v4.33.1 でエラーなくコンパイルでき、主定理 5 件(リーマン予想と一般化リーマン予想)は標準の 3 公理だけに依存していました。主張は検証者が Mathlib だけで書いた命題と一致し、カーネルによる再検査と別実装カーネル `nanoda` の検査も通りました。Lean のカーネルが正しく、Mathlib の定義が意図どおりである限り、Mathlib の `RiemannHypothesis` が形式的に証明されていることになります。この検証で言えないこと(証明の数学的な筋道の理解、カーネル実装の正しさなど)は、レポートの 9 節にまとめています。

## 次の目標: 証明の短縮

検証が終わったら、この証明が主張を変えずにどこまで短くできるかに挑みます。まず、機械的に消せるもの
(証明に使われていない宣言)、明らかな重複、Mathlib の定理で置き換えられるものを片づけ、そのあとで数学的な近道を探します。
検証と並行して、使われていない宣言を消した短縮版(段階 1a)まで作りました。**17,374,215 行 → 14,159,480 行(−18.5%)**
で、いま全体のビルドで確かめています。型が同じ定理の余分な写し(99,393 個)をまとめるのが次の段階です。
計画と結果は [`shorten/README.md`](shorten/README.md) にあります。

## Lean コードの規模

* Lean ファイル(`.lean`): **175,187 個**
* 行数: **17,374,215 行**(1 ファイルあたり平均 99.2 行、中央値 58 行、最大 17,981 行)
* 合計サイズ: **1,030,531,854 バイト(約 1.03 GB)**(1 ファイルあたり平均 5,882 バイト、最大 913,995 バイト)
* 配布アーカイブ: 239,275,554 バイト(約 239 MB。gzip 圧縮・14 分割の合計)、展開後の tar は 1,270,753,280 バイト
* 参考: Mathlib 本体(v4.33.1)は 8,311 ファイル・2,293,877 行・97,067,375 バイト
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
verification/   検査の結果・ログ・検査用 Lean ファイル、定点観測の記録(observations.jsonl)
site/           GitHub Pages 用レポートサイトの原稿(Astro プロジェクト。ビルド結果を gh-pages ブランチへ公開)
shorten/        証明の短縮(2 つ目の目標)。計画と結果、解析ツール rhshrink
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
scripts/rebuild_mathlib_from_source.sh # Mathlib をソースから作り直し、キャッシュとバイト単位で突き合わせる
```

### 定点観測

ビルドの開始時刻(2026-11-21 10:42:23 JST)を起点に、50 分ごとの時点を観測点として、検証機の状態
(コンパイル済みモジュール数、ビルドログのエラー行数、負荷、メモリ、ディスクの空き)を記録しました。
検査がすべて終わったあとの第 44 回(2026-11-22 23:22 JST)で終えています。

```bash
python3 -I scripts/observe.py --daemon     # 常駐。観測点ごとに記録し、gh-pages の observations.json を更新
python3 -I scripts/observe.py              # いまの状態でまとめを作り直すだけ(観測点は増やさない)
python3 -I scripts/build_speed_analysis.py # 速度が落ちていく理由の集計(import の数と所要時間の関係)
```

観測点の一覧は [`verification/observations.jsonl`](verification/observations.jsonl) に残します。
記録するのは測定値だけで、合否の判定は含みません。

ビルドの速度は、後半ほど落ちます。Lake が 1 モジュールごとに推移的な import を最初からたどり直すためで、
集計は [`verification/build-speed/`](verification/build-speed/) にあります(レポートの 2 節に説明)。

### レポートの更新と公開

レポートは、墨・藍・朱の 3 色刷りの印刷物に見立てています。

* 巻頭に、リーマン ζ 関数の位相図を大きな図版として置き、題字は縦組みにする。
* 見出しは活字らしい太明朝(解星 特ミン)。本文は和文の数学書の組版で、本文は明朝、図表まわりはゴシック、
  欧文と数字は Computer Modern(数式と同じ書体)。
* 検査の状態は印で示す(朱の「済」、藍の「中」、灰の「未」)。図表の番号も朱。
* 枠や角丸の部品は使わず、罫と余白、右余白の注で組む。色は位相図と同じ 4 色(紙・墨・藍・朱)だけ。

土台には既存のフレームワークを使っています(バージョンは `site/package-lock.json` で固定)。

| 役割 | 採用したもの | 選んだ理由 |
|---|---|---|
| サイト生成 | [Astro](https://astro.build/) 7 | 静的 HTML を出力し、閲覧時の JavaScript を最小にできる。画像の変換と Shiki を標準で備える |
| 版面と本文の組み | [Tailwind CSS](https://tailwindcss.com/) 4 | 余白・行長・罫を変数とユーティリティで管理でき、既製部品の見た目を持ち込まずに済む |
| 数式と欧文の書体 | [KaTeX](https://katex.org/) | 数式をビルド時に HTML へ変換できる。同梱の Computer Modern を本文の欧文・数字にも使い、数式と地の文をそろえる |
| 図 | [Observable Plot](https://observablehq.com/plot/) | SVG 出力で CSS 変数による配色に追従し、十字線とツールチップを標準で備える |
| コードの色分け | [Shiki](https://shiki.style/)(Astro 同梱) | Lean 4 の文法定義を持つ。色は CSS 変数で紙面の 4 色に合わせる |
| 観測値の読み込み | [Alpine.js](https://alpinejs.dev/) | 静的ページに少量の動きを足す用途に合う(宣言的で軽い) |
| コードの書体 | [Fontsource](https://fontsource.org/)(JetBrains Mono) | 外部 CDN に依存せず自前配信できる。Lean の Unicode 記号を広く収録している |
| 見出しの書体 | 解星 特ミン ExtraBold(SIL OFL 1.1。npm の `@expo-google-fonts/kaisei-tokumin`)と [subset-font](https://github.com/papandreou/subset-font) | 活字らしい太明朝。全体では 4.5 MB あるので、紙面で使う約 100 字だけに絞って約 40 KB で配信する |

本文の和文書体は配信せず、閲覧環境の明朝・ゴシックを使います。

```bash
python3 -I scripts/gen_zeta_figure.py > verification/zeta-figure.json   # 図 1 下段(臨界線上の Z 関数)のデータ
python3 -I scripts/gen_zeta_phase.py site/src/assets                    # 巻頭図と図 1 上段(ζ の位相図。明暗 2 枚ずつ)
(cd site && node scripts/subset-display-font.mjs)                       # 見出し用の書体を、使う文字だけに絞り直す
scripts/publish_pages.sh "レポートを更新"                               # データ生成 → astro build → gh-pages へ公開
scripts/status_updater.sh                                               # コンパイル済みモジュール数を 20 分ごとに公開
```

サイトのビルドには Node.js 22.23 以上が必要です(`cd site && npm ci && npx astro build`)。
`site/src/assets/remark-p1.png` は原本 PDF の 1 ページ目を縮小したものです
(`pdftoppm -f 1 -l 1 -scale-to-x 560 -scale-to-y -1 -png evidence/01-remark-pdf/remark.pdf …`)。

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
