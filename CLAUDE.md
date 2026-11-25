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

## いまの状況(2026-11-25 10:50 JST。レート制限の前に書いた引き継ぎ)

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
| 短縮の段階 1a の全体ビルドと検査 | **3 回目の全体ビルド(11/24 17:04〜19:07)でエラー 0**(**148,931 モジュール、14,160,262 行、−18.5%**)。公理(標準の 3 つのみ)・主張の一致・主張の依存は元と同じ結果で通過(`shorten/results/02-stage1a/checks/`)。**カーネル再検査も通過**(11/25 09:13 終了、148,931 / 148,931 モジュール、失敗 0。`shorten/results/02-stage1a/checks/04-kernel-recheck-meta.txt`) |
| 短縮の段階 1b(重複の統合) | 作業中(ユーザーは 11/24「細かいとは任せるから進めて」)。やり直した計画(`$RUN_ROOT/shorten/plan1b-4/`、53,513 個をまとめる)→ 閉包(`analysis-c1b2-3-…`、3 回で閉じ、残す宣言 844,182 個、まとめた写しの紛れ 0)→ 書き出し(**110,562 モジュール・13,562,079 行、元から −21.9%**)→ 試し(変わった 29,014 モジュールから 3,000 個、失敗 0)まで済んだ。**全体ビルドを 11/24 20:53 JST に起動**(並列 64、ログ `/var/tmp/riemann-hypothesis-ywr/shorten/stage-1b/builds/build-20261124T115302Z/`、7〜8 時間の見込み)。README の段階 1b の節と `shorten/results/03-stage1b/` はやり直した計画の数字に差し替え済み。**ビルド中に 1 モジュールが失敗**(`…HolomorphicFamilies.BiextChangeSecondFactor`、下流 557 個。discharger `disch := simp [...]` の中の参照が .ilean に無く、写し 2 個 `cc_pt'`・`cc_comp1'` を消していた)。02:05 に 2 件目が失敗(`…DivisorProofs.PrimitiveFrameDatumZetaIntegralEqSmaller`。`…Statement` モジュールが消えて import を引き継ぎ・推移簡約したため読み込み順が変わり `μ.IsHaarMeasure` が見つからない。`shorten/keep-import-order.txt` に足して直した)。08:54 に 3 件目(`…WordSpans.ModelWalkOfInputs`。名前を長い `_root_.…` に書き換えて、同じ行の後ろの `(by have …` の列がずれ、そろえてあった続きの行と合わなくなった。書き出し `scripts/shorten_stage1a.py` に、そろえた続きの行も同じだけずらす規則を足して直した)。3 件を直した版を `/var/tmp/riemann-hypothesis-ywr/shorten/writer-test-1b-fix3/` に書き出し済み(計画 `$RUN_ROOT/shorten/plan1b-4p/` = plan1b-4 から 2 個を外し、残す宣言に 2 個を足したもの。変わるのは失敗した 3 ファイルと、まだビルドしていない `…FirstChernCocycleAllLevels` の 4 ファイルだけ。どれも単体コンパイルが通過)。**ビルドが終わったら** `rsync -a --checksum --delete <fix3>/src/ <stage-1b>/src/` と `stage1a/` を反映して続きからビルドする |

## 動いている常駐プロセス

検証の常駐プロセス(検査パイプライン、Mathlib 再ビルドの連結、定点観測、進捗の自動更新)は、すべて役目を終えて止まっている。
いま動いているのは、段階 1a のカーネル再検査(`scripts/run_leanchecker.sh` を RH_LEAN_PROJECT・RH_RUN_ROOT で短縮版に向けたもの。PID は `ps` で `run_leanchecker.sh` を探す)と、段階 1b の全体ビルドとメモリの見張り。

| 名前 | PID ファイル | 中身 |
|---|---|---|
| 短縮版のビルド | `/var/tmp/riemann-hypothesis-ywr/shorten/stage-1b-build.pid` | `JOBS=64 scripts/shorten_build_stage.sh /var/tmp/riemann-hypothesis-ywr/shorten/stage-1b`(`setsid` で切り離し。段階 1a のビルドは終わっている) |
| メモリの見張り | (なし。`ps` で `shorten_memguard.sh` を探す) | `scripts/shorten_memguard.sh <ビルドの PID> 80 30` |
| 段階 1a のカーネル再検査(**11/25 09:13 に終了、全モジュール通過**) | (なし) | 11/24 19:33 起動。00:20 で 2,560/5,958 組・64,000 モジュールが通過、失敗 0(ビルドと CPU を分け合うので遅い。朝 7 時ごろの見込み) |
| 使われない引数の見積もり(段階 2 の下調べ。**02:31 に終了**) | `$RUN_ROOT/shorten/analysis-dae1b.pid` | `RHSHRINK_DAE=1` の rhshrink(`$RUN_ROOT/shorten/analysis-dae1b-20261124T130655Z/`)。固定点の反復が 1 回 1 時間(1 回目で残る位置 1,507,211 → 508,992)。終わったら `python3 -I shorten/tools/domtree/dae_report.py $RUN_ROOT/shorten/analysis-dom1b-20261124T121043Z/domtree.tsv <その出力>/dae-dropped-decls.tsv <その出力>/dae-dead-args.tsv <その出力>/report` で、どの定理の使われない仮定が何行を抱えているかをまとめる |
| 宣言の属性の書き出し(守る宣言の見直し用) | `$RUN_ROOT/shorten/analysis-declinfo.pid` | `RHSHRINK_DECL_INFO=1` の rhshrink(別に作った `/var/tmp/riemann-hypothesis-ywr/shorten/rhshrink-dev` の実行ファイル。出力 `$RUN_ROOT/shorten/analysis-declinfo-20261124T151010Z/decl-info.tsv`) |
| import を足してまとめる見積もり(厳しい版) | (止めた) | `scripts/shorten_estimate_import_merge.py` は **10 時間でメモリを 333 GB まで使い、空きメモリが下限を切ってメモリの見張りが段階 1b の続きのビルドを止めた**(11/25 10:20)。11/25 10:22 に止めた。メモリを抑えるように作り直すまで回さない |

ビルドの進み具合: `grep -oE '^\S+ \[[0-9]+/[0-9]+\]' <ログ>/build.log | tail -1`、失敗: `grep -c '^✖' <ログ>/build.log`。
ビルドを止めるときは `kill -TERM -- -<ビルドの PID>`(プロセスグループごと)。`pkill -f` は自分のコマンド行に当たるので使わない。

`shorten/tools/rhshrink/Main.lean` には `RHSHRINK_DECL_INFO` を足したが、使われない引数の見積もりがその実行ファイルを使って動いているので、そこではまだビルドしていない。見積もりが終わるまでは、解析を `RH_RHSHRINK_DIR=/var/tmp/riemann-hypothesis-ywr/shorten/rhshrink-dev scripts/shorten_analyze.sh …`(閉包の繰り返し `scripts/shorten_closure_loop.sh` も環境変数をそのまま引き継ぐ)で回す。終わったあとは普通に回せばよい(最初に作り直す)。

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
     (最後の閉包は `$RUN_ROOT/shorten/analysis-closure6-20261124T074447Z/`。書き出しは約 4 分。ビルド中に書き出さない: src/ を作り直すので、先にビルドを止める)
  4. `JOBS=64 setsid scripts/shorten_build_stage.sh /var/tmp/riemann-hypothesis-ywr/shorten/stage-1a [対象 …]`(依存とビルド結果は reflink で写し、変わらないモジュールは再利用される)。
     起動したら `setsid scripts/shorten_memguard.sh <ビルドの PID> 80 30` も起動し、PID を `stage-1a-build.pid` に書く
     (`setsid cmd &` の `$!` は setsid が別に作ったプロセスを指さないことがある。PID は `ps -eo pid,args` で `bash scripts/shorten_build_stage.sh` を探して取る)
  - 閉包 6 の起点は `$RUN_ROOT/shorten/closure6-roots.txt`(閉包 5 の起点 + `cpt_copy_thms` の根 1 つ)。読み込み順を保つモジュールは
    `shorten/keep-import-order.txt`(書き出しの既定の入力)。
  - 書き出しは、先に別の場所(`--out /var/tmp/riemann-hypothesis-ywr/shorten/writer-test-…`)に出して `diff -rq` で今の短縮版と比べ、
    変わるファイルとその下流の数を確かめてから、`rsync -a --checksum --delete <試し>/src/ <stage>/src/` で反映するとよい
- これまでにはまった点(段階 1a): カーネルの項に現れない使われ方がある(`simp [X]` の使われなかった X、強制変換の instance、rfl の simp 補題、notation の構文定数)。
  `… in` の前置きは空行を挟んで宣言に掛かることがある。消したモジュールの import をそのまま引き継ぐと import が膨らむ(推移簡約する)。
  Lean 4.33 は同じ名前・同じ型の定理の重複 import を許す(133 組ある)ので、宣言は (モジュール, 名前) で区別する。
  前置きには `attribute […] … in`・`unseal … in`・`universe … in` もある。`open` は字下げした続きの行を持つことがあり、
  Lean は `open` の時点で名前空間があるかを確かめる(同じファイルの後ろで初めて現れる名前空間は見えない)。`export X (…)` も名前を外す対象。
  マクロの本文の名前は定義の位置で解決され、.ilean にも証明項にも跡が残らない(名前の末尾だけで照合すると `e`・`h` などが大量に当たる)。
  Lake 4.33 は import 先を推移的に辿ったすべての `.olean` の中身のハッシュで作り直すかを決める(モジュール方式でないファイルの
  `legacyTransTrace`)。`.olean` が変わったモジュールの下流は、直接 import していなくてもすべて作り直しになる(出力が同じでも止まらない)。
  `open private 名前 … from M`(Batteries)は名前を M の非公開の定数に末尾で照合する。配布物の自作コマンド `cpt_copy_thms` は
  カーネルの項の外で写しを作る(写しの元を消すと写しができない)。import の推移簡約は読み込み順を変え、同じ優先度の instance の試す順が変わる
  (読み込み順のせいで失敗したモジュールだけ `shorten/keep-import-order.txt` に挙げる。全体に当てると 75% の作り直しになる)。

### 短縮で次にやること(引き継ぎ)

1. **段階 1b の全体ビルドは 11/25 10:15 に終わり(13 時間 22 分、失敗は直し済みの 3 件だけ)、直した 4 ファイルを反映して 10:17 に続きのビルドを起動した**(ログ `/var/tmp/riemann-hypothesis-ywr/shorten/stage-1b/builds/build-20261125T011702Z/`、PID は `stage-1b-build.pid`、作り直しは約 700 モジュール)。反映後の数字は 110,562 モジュール・**13,562,093 行**・宣言 844,184 個。続きのビルドは見積もりのスクリプトのメモリのせいで 10:20 に止まり、**10:23 に再起動**(ログ `…/stage-1b/builds/build-20261125T012325Z/`)。**10:44 に通った(エラー 0)**。2 の検査とカーネル再検査を 10:46 に起動した(ログ: 検査は `/var/tmp/riemann-hypothesis-ywr/shorten/checks-1b/`、結果は `shorten/results/03-stage1b/checks/`。カーネル再検査は `/var/tmp/riemann-hypothesis-ywr/shorten/kernel-1b/latest-leanchecker-project/`、並列 48)。以下は反映までの手順の控え。
   ビルドの終了は `stage-1b-build.pid` のプロセスが消えることで分かる(ログの `meta.txt` に終了コード)。ほかの失敗があれば、同じ回でまとめて直す
   (ログの `✖` の行とその下のエラーを読み、計画 `scripts/shorten_plan1b.py` か書き出し `scripts/shorten_stage1a.py` の規則に取り込む)。
   反映は `rsync -a --checksum --delete /var/tmp/riemann-hypothesis-ywr/shorten/writer-test-1b-fix3/src/ /var/tmp/riemann-hypothesis-ywr/shorten/stage-1b/src/` と
   `stage1a/`(report.json など)の同じ写し。変わるのは `…HolomorphicFamilies.BiextChangeSecondFactor.lean` と `…DivisorProofs.PrimitiveFrameDatumZetaIntegralEqSmaller.lean`・`…WordSpans.ModelWalkOfInputs.lean`・`…HodgeTateResidues.FirstChernCocycleAllLevels.lean` の 4 ファイルだけ(反映の前に `diff -rq` で確かめる。3 件目以降の失敗があれば、同じように直して試しの場所に書き出し直す)。
   続きのビルドは `JOBS=64 setsid scripts/shorten_build_stage.sh /var/tmp/riemann-hypothesis-ywr/shorten/stage-1b` と `scripts/shorten_memguard.sh <PID> 80 30`
   (PID は `ps -eo pid,args` で `bash scripts/shorten_build_stage.sh` を探し、`stage-1b-build.pid` に書く)。
   直した版の数字: 110,562 モジュール・**13,562,091 行**・宣言 844,184 個(計画 `$RUN_ROOT/shorten/plan1b-4p/`、記録は `shorten/results/03-stage1b/unmerged-after-build.tsv`)。
   README の段階 1b の表(13,562,079 行)は、ビルドが通ったらこの数字に直す。
2. 通ったら検査(`RH_LEAN_PROJECT=/var/tmp/riemann-hypothesis-ywr/shorten/stage-1b RH_RESULTS_DIR=shorten/results/03-stage1b/checks RH_CHECK_DIR=/var/tmp/riemann-hypothesis-ywr/shorten/checks-1b scripts/run_checks.sh`、
   カーネル再検査は `RH_LEAN_PROJECT=… RH_RUN_ROOT=/var/tmp/riemann-hypothesis-ywr/shorten/kernel-1b VALIDATE=0 JOBS=… scripts/run_leanchecker.sh`)。
   `shorten/README.md` の段階 1b の節(「全体のビルド」の段落と検査の表)と、ルートの `README.md` の行数を直す。
3. (済み)段階 1a のカーネル再検査が終わったら、`meta.txt` の末尾(`failed_chunks`・`ok_modules`・`missing_modules`・`failed_modules`)を確かめ、
   `shorten/README.md` の段階 1a の検査の表と `shorten/results/02-stage1a/` に書く。
4. 守る宣言の見直し: **閉包 pr1 は閉じた**(`$RUN_ROOT/shorten/analysis-pr1-3-20261124T180925Z/`)。段階 1b から 9,856 宣言・**51,418 行**が減り、598 モジュールが空になる(外した宣言 3,282 個と、それだけが使っていた宣言 6,574 個)。README の「次の短縮の道」に書いて、次の作り直しに入れる。以下は経緯: 判定は済み(`$RUN_ROOT/shorten/protect-review/summary.json`。守る 22,043 個のうち外すのは 11,077 個 = 強制変換でない instance 8,177、rfl でない simp の定理 2,646、ext の定理 254)。**閉包 `pr1` を 11/25 02:07 に起動**(ログ `$RUN_ROOT/shorten/pr1-loop.log`、1 回 15〜25 分で 2〜3 回)。閉じたら、最後の `analysis-pr1-k-…/source-closure/kept-decls.tsv` の数を段階 1b の 844,184 個と比べ、減る行を数えて README に書く。以下は手順の控え: `decl-info.tsv` ができたら
   `python3 -I scripts/shorten_protect_review.py --protected $RUN_ROOT/shorten/protect/protected.tsv --info <decl-info.tsv> --out $RUN_ROOT/shorten/protect-review --extra-root Formalism.FourierDecayAlt.P.CutBP.block_growth_bound_of_compact_coef`
   で守り続ける起点(roots.txt)を作り、`scripts/shorten_closure_loop.sh pr1 <roots.txt> $RUN_ROOT/shorten/plan1b-4p/merge.tsv $RUN_ROOT/shorten/plan1b-4/redirect.tsv`
   (上の RH_RHSHRINK_DIR に注意)で閉包を取り、残す宣言が段階 1b(844,184 個)からどれだけ減るかを見る。外すのは、rfl でない(`@[defeq]`・`@[backward_defeq]` の無い)
   simp の定理・ext の定理と、強制変換(`Coe…`)でない class の instance。
5. import を足してまとめる: 厳しい見積もり(新たに見える Mathlib などのモジュールが無い、新たに見える宣言の名前が参照するモジュールの識別子と重ならない、を足した)の
   結果を README の「次の短縮の道」の表に書く。実際の計画は `scripts/shorten_plan1b.py` に、この条件で import を足す道を足して作る。
   4 と 5(と `--drop-open-list-refs`)は、全体の作り直しを 1 回にまとめる。
6. 使われない引数の見積もりは終わった(02:31)。消せるのは 447 宣言・5,178 行だけで、この道は効かない(README の段階 2 の節、`shorten/results/05-dae/`)。

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
