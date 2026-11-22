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

## いまの状況(2026-11-22 23:45 JST)

**検証は終わった**(パイプラインは 22:41 JST に `result=done`)。結果は精査してレポート(7.7〜7.9 節、表 1、1 節、9 節)と README に反映した。
**最終判定は、ユーザーが文言を承認して(2026-11-22)、巻頭の判定欄に掲げた**: 印「通過」、見出し「予定したすべての検査を通過しました」、
本文「配布物は指定どおりの Lean 4.33.1・Mathlib v4.33.1 でエラーなくコンパイルでき、主定理 5 件(リーマン予想と一般化リーマン予想)は標準の 3 公理だけに
依存していました。主張は検証者が Mathlib だけで書いた命題と一致し、カーネルによる再検査と別実装カーネル nanoda の検査も通りました。Lean のカーネルが正しく、
Mathlib の定義が意図どおりである限り、Mathlib の RiemannHypothesis が形式的に証明されていることになります。」。この文言を変えるときも、公開前にユーザーに確かめる。

| 検査 | 状態 |
|---|---|
| 全体ビルド(175,187 モジュール) | 完了。エラー 0、22 時間 40 分 |
| 主定理の公理 | 完了。5 定理とも `propext`・`Classical.choice`・`Quot.sound` のみ |
| 主張の一致確認・依存解析 | 完了。検証者の命題と一致し、本体の定義は主張に現れない |
| カーネル再検査 | 完了。配布物 175,187 / 175,187、依存ライブラリ 8,700 / 8,700 が通過、失敗 0 |
| 別実装カーネル nanoda | 完了(22:41)。主定理 5 件の依存一式 1,484,729 宣言がエラー 0(1 時間 12 分、最大 74 GiB)。一式の axiom 宣言は標準の 3 つだけ(書き出しを直接調べて確認)。記録は `verification/results/06-nanoda/` |
| ソース不変確認 | 完了(22:41)。175,190 ファイルすべてが原本と一致(`verification/results/07-source-verify.out.txt`) |
| Mathlib のソースからの再ビルド照合(任意) | 完了(23:08)。8,690 個中 8,689 個の `.olean` がキャッシュと一致。違う `Mathlib.Combinatorics.SimpleGraph.Walk.Operations` は自動生成の等式補題 `SimpleGraph.Walk.take.eq_2` の書き方だけが違う(並列コンパイルの非決定性。主定理の依存一式に `SimpleGraph` は無い)。`rebuild_mathlib_from_source.sh` は違いがあると終了コード 1 を返すので、`mathlib-from-source.rc` は 1。記録は `verification/results/08-mathlib-from-source/`、読み比べのプログラムは `verification/olean-diff/Cmp.lean` |
| 定点観測 | 終了。#44(23:22 JST、段階 `finished`)で observer が自動で終わった(監視対象のプロセスがすべて終了したため)。進捗の自動更新も `finished` を書いて終わった |
| 短縮の下調べ(`rhshrink`) | 完了(18:37)。使われていない宣言は約 330 万行(19.0%)、重複した定理の写し 99,393 個。結果は `shorten/results/01-analysis/` と `shorten/README.md` |
| 短縮の段階 1a | 短縮版(148,924 モジュール、**14,159,480 行、−18.5%**)を `/var/tmp/riemann-hypothesis-ywr/shorten/stage-1a` に作成。1 回目の全体ビルド(20:26〜23:16、26,775 モジュールが通過)の失敗 30 件は原因 5 つで、すべて規則に取り込んで書き出し直した(`shorten/results/02-stage1a/full-build1-failures.tsv`、`shorten/README.md`) |
| 短縮の段階 1a の全体ビルド | 23:38 JST に並列 64(nice 10)で続きから再開(ログは `stage-1a/builds/build-20261122T143844Z/`、PID は `/var/tmp/riemann-hypothesis-ywr/shorten/stage-1a-build.pid`)。直前の並列 32 の回(23:21〜23:38)は失敗 0。空きメモリが 80 GiB を切ると `scripts/shorten_memguard.sh` が止める(記録は `/var/tmp/riemann-hypothesis-ywr/shorten/memguard.log`) |

## 動いている常駐プロセス

検証の常駐プロセス(検査パイプライン、Mathlib 再ビルドの連結、定点観測、進捗の自動更新)は、すべて役目を終えて止まっている。
いま動いているのは短縮版のビルドだけ。

| 名前 | PID ファイル | 中身 |
|---|---|---|
| 短縮版のビルド | `/var/tmp/riemann-hypothesis-ywr/shorten/stage-1a-build.pid` | `JOBS=64 scripts/shorten_build_stage.sh /var/tmp/riemann-hypothesis-ywr/shorten/stage-1a`(`setsid` で切り離し) |
| メモリの見張り | (なし。`ps` で `shorten_memguard.sh` を探す) | `scripts/shorten_memguard.sh <ビルドの PID> 80 30` |

ビルドの進み具合: `grep -oE '^\S+ \[[0-9]+/[0-9]+\]' <ログ>/build.log | tail -1`、失敗: `grep -c '^✖' <ログ>/build.log`。
ビルドを止めるときは `kill -TERM -- -<ビルドの PID>`(プロセスグループごと)。`pkill -f` は自分のコマンド行に当たるので使わない。

## 証明の短縮(2 つ目の目標、2026-11-22 にユーザーが追加)

ユーザーの言葉: 「検証が終わったら、どこまで lean 証明を短くできるかにチャレンジ。まずは機械的に削除できるものや、明らかな重複、
mathlib で置き換えられるものにトライ。それが終わったら数学的な短絡を見つける。いまの検証と並行に進められるところは進めたい」。

- 計画・決まりごと・結果は `shorten/README.md`。段階は (1a) 使われていない宣言の削除 → (1b) 重複の統合 → (1c) Mathlib への置き換え → (2) 数学的な短絡。
- 主張(`Statements.lean` と `Main.lean` の 5 定理)は変えない。短縮版にも検証と同じ検査をかける。
- `lean/` と `evidence/` は書き換えない。短縮版は別の場所に写して作る(`lean/` はソース不変確認の対象)。
- 配布物にライセンスの表示がないので、短縮版のソースは公開しない(手順・一覧・数字だけ公開する)。
- 解析ツールは `shorten/tools/rhshrink`(Lean。配布物の `.olean` を読むだけ)、実行は `scripts/shorten_analyze.sh`(`nice` つき、`setsid` で切り離す)。
  出力は `$RUN_ROOT/shorten/latest-analysis/`(`summary.json`、`modules.tsv` など)、PID は `$RUN_ROOT/shorten/analysis.pid`。
- 段階 1a の手順(`$RUN_ROOT/shorten/` の下で):
  1. `scripts/shorten_protect.py --decls <decls.tsv.zst> --out $RUN_ROOT/shorten/protect`(使われていなくても残す宣言: notation・マクロ、instance、`@[simp]`、定数を生成する属性など)
  2. 閉包: `RH_ANALYSIS_TAG=closureN RHSHRINK_SKIP_DUPS=1 scripts/shorten_analyze.sh Main <主定理 5 件> @<起点の一覧>` と
     `scripts/shorten_source_closure.py --analysis <その出力>` を、足す宣言が 0 になるまで交互に回す(起点 = 守る宣言 + これまでに足した宣言)
  3. `scripts/shorten_stage1a.py --kept <最後の kept-decls.tsv> --decls <decls.tsv.zst> --protected <protected.tsv> --module-refs <最後の module-refs.tsv>` で短縮版を書き出す
     (最後の閉包は `$RUN_ROOT/shorten/analysis-closure5-20261122T135849Z/`。書き出しは約 4 分。ビルド中に書き出さない: src/ を作り直すので、先にビルドを止める)
  4. `JOBS=64 setsid scripts/shorten_build_stage.sh /var/tmp/riemann-hypothesis-ywr/shorten/stage-1a [対象 …]`(依存とビルド結果は reflink で写し、変わらないモジュールは再利用される)。
     起動したら `setsid scripts/shorten_memguard.sh <ビルドの PID> 80 30` も起動し、PID を `stage-1a-build.pid` に書く
- これまでにはまった点(段階 1a): カーネルの項に現れない使われ方がある(`simp [X]` の使われなかった X、強制変換の instance、rfl の simp 補題、notation の構文定数)。
  `… in` の前置きは空行を挟んで宣言に掛かることがある。消したモジュールの import をそのまま引き継ぐと import が膨らむ(推移簡約する)。
  Lean 4.33 は同じ名前・同じ型の定理の重複 import を許す(133 組ある)ので、宣言は (モジュール, 名前) で区別する。
  前置きには `attribute […] … in`・`unseal … in`・`universe … in` もある。`open` は字下げした続きの行を持つことがあり、
  Lean は `open` の時点で名前空間があるかを確かめる(同じファイルの後ろで初めて現れる名前空間は見えない)。`export X (…)` も名前を外す対象。
  マクロの本文の名前は定義の位置で解決され、.ilean にも証明項にも跡が残らない(名前の末尾だけで照合すると `e`・`h` などが大量に当たる)。
  Lake 4.33 は import 先の `.olean` の中身のハッシュで作り直すかを決める(ソースの行がずれると `.olean` が変わり、下流も作り直しになる)。

### 短縮で次にやること(引き継ぎ)

1. 段階 1a の全体ビルドを見守る(並列 64 で 23:38 JST に再開)。失敗が出たら、ログ(`grep '^✖'` と、その直後の `error:` 行)から原因を調べて
   `scripts/shorten_stage1a.py`(または `shorten_protect.py`・閉包)に取り込み、ビルドを止めてから段階 1a の手順 3 で書き出し直し、手順 4 で続きからビルドする
   (Lake は済んだモジュールを再利用する。中身が同じファイルは再ビルドされない)。
2. ビルドが通ったら、検証と同じ検査(`#print axioms`、主張の一致、カーネル再検査)を短縮版にかけ、`shorten/README.md` に結果を書く。
3. 段階 1b(重複の統合)。下調べの `duplicates.tsv`・`aliases.tsv`(`shorten/results/01-analysis/`)が材料。

## 見回り(ユーザーの依頼「50 おきには定点観測して」)

**検証の定点観測は #44(2026-11-22 23:22 JST)で終わった**(observer が終了条件を満たして自動で止まった)。以下は記録として残す。

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
  違ったモジュールの中身は `lean --run verification/olean-diff/Cmp.lean <片方> <もう片方>`(拡張子なしのパス)で宣言ごとに読み比べる。

## これまでにはまった点

- ツールチェーン同梱の `leanchecker` は、引数の名前 1 つごとに検索パス全体(約 18.6 万個の `.olean`)を走査する。多数のモジュールには、同じ再生処理を直接呼ぶ `verification/leanchecker-driver`(`rhcheck`)を使う。
- 大きな組を最初に固定で割り当てると進み方が偏る。小分けの組を `xargs -P` で空いたプロセスから取らせる。
- bash で `a && b && c &` と書くと全体が背景のサブシェルで走り、その中で設定した変数は後続のコマンドに残らない。
- `pgrep -f` で PID を拾うと、自分のコマンド行に当たることがある。`ps -eo pid,args` の引数で厳密に照合する。
- 動いている bash スクリプトをその場で書き換えない(別ファイルに書いて `mv` で差し替える)。
- 表示確認は snap 版 Firefox のヘッドレス撮影で行う(プロファイルと出力はリポジトリ内の `.ff-tmp/`。`/tmp` は snap から見えない)。
  `site/dist` を `.ff-tmp/www/riemann-hypothesis/` に写し、`python3 -m http.server` で配って撮る(サイトの base は `/riemann-hypothesis`)。
  ページの一部だけ見たいときは、HTML の要らない節を削った写しを作って撮る。
- `pkill -f <パターン>` は自分の bash のコマンド行にも当たり、自分ごと止める(実際に起きた)。PID を `ps -eo pid,args` で特定して `kill` する。
