# 証拠(原本)の保全記録

このディレクトリは、検証対象を **取得した時点のバイト列のまま** 保存したものです。
ここにあるファイルは検証作業のいかなる段階でも書き換えません。

## 取得の連鎖

```
https://alpo.ge/remark.pdf                      (起点。ユーザー指定)
  └─ 脚注 1 が Lean コードの所在を示す
      https://alpo.ge/lean.tar.gz.part01 … part14
        └─ 14 個を順に連結 → lean.tar.gz(gzip 圧縮 tar)
            └─ 展開 → lean/(Lake プロジェクト、175,190 ファイル)
```

## 01-remark-pdf/ — 起点の PDF

| 項目 | 値 |
|---|---|
| URL | `https://alpo.ge/remark.pdf` |
| 取得時刻 (UTC) | 2026-11-21T01:24:45Z |
| HTTP | 200, `content-type: application/pdf`, `content-length: 245114` |
| サイズ | 245,114 バイト |
| SHA-256 | `3fc97784b71ddd44ff8aa0a177e99622a1c61b13cfa843a0989ee4a7a0cfeb8d` |
| PDF 情報 | 4 ページ、PDF 1.5、pdfTeX-1.40.29 / LaTeX with hyperref、作成日時 2026-11-20 21:52:48 JST |
| 著者表記 | PDF メタデータの Title / Author は空。本文にも署名なし |

* `remark.pdf` … 原本
* `http-response-headers.txt` … サーバの応答ヘッダ全文(ETag 含む)
* `curl-writeout.txt` … curl が記録した接続先 IP・最終 URL・リダイレクト回数・TLS 検証結果
* `fetched-at-utc.txt` … 取得時刻
* `SHA256SUMS` … ハッシュ

PDF に埋め込まれたリンク注釈は `…/lean.tar.gz.part01` と `…/lean.tar.gz.part14` の 2 つだけです。

## 02-remark-pdf-text/ — PDF から抽出した全文(派生物)

`pdftotext`(poppler 24.02.0)で 3 通りに抽出した全文テキスト。原本は 01 の PDF で、こちらは読みやすさのための派生物です。

* `remark.reading-order.txt` … 既定モード(読み順)
* `remark.layout.txt` … `-layout`(紙面配置を保持)
* `remark.raw.txt` … `-raw`(コンテンツストリーム順)

## 03-lean-tarball-parts/ — Lean コード配布物(14 分割の原本)

| 項目 | 値 |
|---|---|
| URL | `https://alpo.ge/lean.tar.gz.part01` 〜 `part14` |
| 取得時刻 (UTC) | 2026-11-21T01:25:45Z 〜 01:25:50Z |
| サイズ | part01〜13 は各 18,000,000 バイト、part14 は 5,275,554 バイト(計 239,275,554 バイト) |
| 連結後の SHA-256 | `9631b4f020199e580ba86178cb56c6e9b09f690c2369a80dc4334aa93f49c7fc` |
| 連結後の検査 | `gzip -t` 正常。展開後の tar は 1,270,753,280 バイト |

* `lean.tar.gz.partNN` … 原本(14 個)
* `lean.tar.gz.partNN.http-headers.txt` … 各分割の応答ヘッダ(ETag 含む)
* `SHA256SUMS` … 各分割の SHA-256
* `REASSEMBLED.sha256` … 連結したストリームの SHA-256
* `curl-writeout.txt`, `fetch-started-at-utc.txt`, `fetch-finished-at-utc.txt` … 取得記録

補足:

* サーバは分割ファイルに `Content-Length` も `Content-Type` も付けていません(応答ヘッダ参照)。
  サイズは実際に受信したバイト数です。
* 存在範囲の確認として `part00` / `part15` / `part16` と分割なしの `lean.tar.gz` も要求しましたが、
  いずれも `text/html` が返りました(サイトの既定ページ)。配布物は part01〜part14 の 14 個です。
* 応答ヘッダの ETag は内容の MD5 とは一致しません(Cloudflare 側の独自値)。完全性は
  本リポジトリで計算した SHA-256 で管理します。

## 04-tarball-contents/ — tarball の中身の目録(派生物)

* `tar-listing.txt.zst` … `tar -tzvf` の一覧(175,190 エントリ)
* `SHA256SUMS.extracted.txt.zst` … 展開した全 175,190 ファイルの SHA-256

一覧から確認できること:

* エントリは **すべて通常ファイル**(シンボリックリンク・ハードリンク・デバイス等は 0)
* 絶対パスや `..` を含むパスは 0。トップレベルは `lean/` のみ
* 所有者 0/0、モード 0644、更新時刻 1970-01-01(正規化された tarball)
* 内訳: `.lean` 175,187 個 + `lakefile.toml` + `lake-manifest.json` + `lean-toolchain`

## 再検証の方法

```bash
scripts/reconstruct.sh            # 原本から lean/ を再構成し、全ファイルのハッシュを照合
scripts/reconstruct.sh --verify   # 既存の lean/ が原本と一致するかだけを確認
```

展開ツリー `lean/` は原本から完全に再構成できるため git には含めていません(`.gitignore` 参照)。
