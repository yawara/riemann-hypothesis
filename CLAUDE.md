# このリポジトリで作業する Claude へ(引き継ぎ用)

公開されたリーマン予想の Lean 4 証明(<https://alpo.ge/remark.pdf> から配布)を、原本を保全したうえで独立に検証している。
2026-11-22 に 2 つ目の目標が加わった。検証が終わったら、この証明を主張を変えずにどこまで短くできるかに挑む(下の「証明の短縮」)。
ユーザーは途中でアカウントを切り替えることがあるので、別のセッションでもここを読めば作業を続けられるようにしてある。
状況が変わったら、このファイルの「いまの状況」も直すこと。

## 方針(ユーザーの指示)

- 報告は日本語(レポート、README、コミットメッセージ)。GPU の情報は書かない。行数・サイズは目立つ位置に書く。
- 原本 `evidence/` は書き換えない。
- レポートは `site/`(Astro)。`scripts/publish_pages.sh "<メッセージ>"` で GitHub Pages(gh-pages ブランチ)に公開する。逐次公開してよい。
- 合否や最終判定は自動では公開しない。結果を精査してから載せる。**最終判定の文言は、公開する前にユーザーに確かめる。**
- デザイン: 既製部品を並べたダッシュボード風は「AI っぽい」、装飾を削りきった論文風は「味気ない」と言われた。いまの紙面(墨・藍・朱の 3 色刷り、巻頭の ζ の位相図、印)を保つ。
- コミットの末尾の共著者表記は、そのセッションの指示に従う。`scripts/publish_pages.sh`・`scripts/observe.py`・`scripts/status_updater.sh` にも同じ表記が書き込んであるので合わせて直す(動いている `status_updater.sh` は、別ファイルに書いてから `mv` で差し替える)。
- 好みの詳細は Claude のメモリ(`~/.claude/projects/-home-ywr-riemann-hypothesis/memory/`)にもある。

## いまの状況(2026-11-22 18:00 JST)

| 検査 | 状態 |
|---|---|
| 全体ビルド(175,187 モジュール) | 完了。エラー 0、22 時間 40 分 |
| 主定理の公理 | 完了。5 定理とも `propext`・`Classical.choice`・`Quot.sound` のみ |
| 主張の一致確認・依存解析 | 完了。検証者の命題と一致し、本体の定義は主張に現れない |
| カーネル再検査(配布物) | 完了。175,187 / 175,187 が通過、失敗 0(17:48)。経緯はレポート 7.6 節 |
| カーネル再検査(依存ライブラリ) | 完了。8,700 / 8,700 が通過、失敗 0(17:55) |
| 別実装カーネル nanoda | 17:55 開始。まず lean4export で主定理の依存一式を書き出し、次に nanoda で検査 |
| 以降(パイプラインが自動で実行) | ソース不変確認 → `result=done` → Mathlib のソースからの再ビルド照合(任意) |
| 短縮の下調べ(`rhshrink`) | 18:23 開始。主定理から使われている宣言・重複・Mathlib との一致を数える(検証とは独立) |

最新の値は、下の「見回り」の確認先を見ること。

## 動いている常駐プロセス

すべて `setsid` で切り離してあり、セッションが切れても止まらない。`RUN_ROOT=/var/tmp/riemann-hypothesis-ywr/runs`。

| 名前 | PID ファイル | 中身 |
|---|---|---|
| 検査パイプライン | `$RUN_ROOT/pipeline.pid` | `scripts/post_build_pipeline.sh --from-leanchecker`(状態は `$RUN_ROOT/pipeline/status.txt`) |
| Mathlib 再ビルドの連結 | `$RUN_ROOT/mathlib-from-source.pid` | `$RUN_ROOT/mathlib-chain.sh`(パイプラインが `done` で終われば再ビルド照合を始める) |
| 定点観測 | `$RUN_ROOT/observer.pid` | `scripts/observe.py --daemon`(50 分ごと。記録は `$RUN_ROOT/observations/fixed.jsonl`、公開は gh-pages の `observations.json`) |
| 進捗の自動更新 | `$RUN_ROOT/status-updater.pid` | `scripts/status_updater.sh 1200`(20 分ごとに gh-pages の `status.json`) |

定点観測は、`pipeline.pid` と `mathlib-from-source.pid` のどちらの PID も生きていない状態で観測点を迎えると終わる。

## 証明の短縮(2 つ目の目標、2026-11-22 にユーザーが追加)

ユーザーの言葉: 「検証が終わったら、どこまで lean 証明を短くできるかにチャレンジ。まずは機械的に削除できるものや、明らかな重複、
mathlib で置き換えられるものにトライ。それが終わったら数学的な短絡を見つける。いまの検証と並行に進められるところは進めたい」。

- 計画・決まりごと・結果は `shorten/README.md`。段階は (1a) 使われていない宣言の削除 → (1b) 重複の統合 → (1c) Mathlib への置き換え → (2) 数学的な短絡。
- 主張(`Statements.lean` と `Main.lean` の 5 定理)は変えない。短縮版にも検証と同じ検査をかける。
- `lean/` と `evidence/` は書き換えない。短縮版は別の場所に写して作る(`lean/` はソース不変確認の対象)。
- 配布物にライセンスの表示がないので、短縮版のソースは公開しない(手順・一覧・数字だけ公開する)。
- 解析ツールは `shorten/tools/rhshrink`(Lean。配布物の `.olean` を読むだけ)、実行は `scripts/shorten_analyze.sh`(`nice` つき、`setsid` で切り離す)。
  出力は `$RUN_ROOT/shorten/latest-analysis/`(`summary.json`、`modules.tsv` など)、PID は `$RUN_ROOT/shorten/analysis.pid`。

## 見回り(ユーザーの依頼「50 おきには定点観測して」)

観測点は `2026-11-21T01:42:23Z + 50 分 × k`。各観測点の約 2 分半後に次を確かめる。

1. `$RUN_ROOT/observer.out` と `$RUN_ROOT/observations/fixed.jsonl` の最新の観測点が記録され、gh-pages に公開されているか
2. `$RUN_ROOT/pipeline/status.txt` の段階、再検査の `ok` / `FAILED` 件数(`$RUN_ROOT/latest-leanchecker-*/batch.*.log`)、メモリ(`MemAvailable`)、ディスク
3. 上の 4 つの常駐プロセスが生きているか
4. `verification/observations.jsonl` に差分があればコミットして push

段階が進んだら結果を精査し、`site/src/pages/index.astro`(表 1 の `checks`、7.x 節、巻頭の判定欄)と `README.md` の状態表を直して公開する。結果のファイルは `verification/results/` に写す。

`/loop` で回すときの入力:

```
/loop 定点観測の見回り(riemann-hypothesis。観測点はビルド開始 2026-11-21T01:42:23Z + 50 分 × k。次の起床は次の観測点の約 2 分半後に合わせる): /var/tmp/riemann-hypothesis-ywr/runs/observer.out と observations/fixed.jsonl の最新の観測点を読み、(1) 50 分ごとの観測が記録され gh-pages に公開されているか、(2) ビルドログのエラー行・進捗の停滞・ディスクやメモリの異常がないか、(3) 常駐プロセス(build / pipeline / observer / status-updater)が生きているかを確認する。エラー行や異常があれば原因を調べて報告する。ビルドやパイプラインの段階が進んでいたら結果を精査し、レポート(site/src/pages/index.astro の検査の状態と本文)を更新して scripts/publish_pages.sh で公開する。verification/observations.jsonl に差分があればコミットして push する。最後に、観測回・完了モジュール数・進捗率・エラー行数を 1〜2 行の日本語で報告する。
```

## 各段階の結果の見方

- カーネル再検査: `$RUN_ROOT/latest-leanchecker-{project,deps}/meta.txt` の末尾。`failed_chunks: 0`、`ok_modules: N / N`、`missing_modules: 0`、`failed_modules: 0` なら全モジュールが通った。失敗は `batch.*.log` の `FAILED` 行。配布物は 2 回目の実行の記録を引き継いでいる(`batch.prev.log`)。
- 別実装カーネル(nanoda): `$RUN_ROOT/latest-nanoda/` と `$RUN_ROOT/pipeline/run_nanoda.out`。
- ソース不変確認: `$RUN_ROOT/pipeline/reconstruct-verify.out`。
- Mathlib の再ビルド照合(任意の追加照合): `$RUN_ROOT/mathlib-from-source/compare-summary.txt` と `$RUN_ROOT/mathlib-from-source.rc`。

## これまでにはまった点

- ツールチェーン同梱の `leanchecker` は、引数の名前 1 つごとに検索パス全体(約 18.6 万個の `.olean`)を走査する。多数のモジュールには、同じ再生処理を直接呼ぶ `verification/leanchecker-driver`(`rhcheck`)を使う。
- 大きな組を最初に固定で割り当てると進み方が偏る。小分けの組を `xargs -P` で空いたプロセスから取らせる。
- bash で `a && b && c &` と書くと全体が背景のサブシェルで走り、その中で設定した変数は後続のコマンドに残らない。
- `pgrep -f` で PID を拾うと、自分のコマンド行に当たることがある。`ps -eo pid,args` の引数で厳密に照合する。
- 動いている bash スクリプトをその場で書き換えない(別ファイルに書いて `mv` で差し替える)。
- 表示確認は snap 版 Firefox のヘッドレス撮影で行う(プロファイルと出力はリポジトリ内の `.ff-tmp/`。`/tmp` は snap から見えない)。
