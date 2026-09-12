# news-watch

Prossimo Tech の日次企業ニュース（Slack #news_summary）を支えるデータ置き場。
Claude Code の routine「Daily Company News Watch」が毎朝この repo を clone して使う。

## 構成

| パス | 役割 |
|---|---|
| `watchlist.yaml` | 監視企業リストの正本。上場区分、タグ（client / prospect / watch）、検索補助語、同名他社の注意 |
| `scripts/fetch_prices.py` | 上場銘柄の前営業日終値・前日比を取得して `data/` に書く（yfinance、予備に Yahoo chart API 直叩き） |
| `.github/workflows/prices.yml` | 平日 07:15 JST に上のスクリプトを実行し、結果を commit する |
| `data/prices.json` | 当日分の株価（routine が読む） |
| `data/history.csv` | 日次の履歴（追記のみ） |
| `prompt/routine_prompt.md` | routine の指示書。routine 側のプロンプトは「このファイルを読んで従え」だけ |

## 運用

- 企業の追加・削除・上場区分の変更は `watchlist.yaml` を編集して push するだけ。routine の設定変更は不要。
- 投稿の書式や調査ルールを変えたい時は `prompt/routine_prompt.md` を編集して push する。
- 株価が更新されない日は Actions のログを確認する（`Actions` タブ → `fetch-prices`）。routine 側は `as_of` が古いと「未更新」と注記して投稿する。
- 手元で試す: `uv run --with-requirements requirements.txt python scripts/fetch_prices.py`

## 設計メモ

- routine の実行環境は egress proxy で金融サイト・各社 IR サイトへの WebFetch がほぼ全てブロックされる。株価取得を GitHub Actions 側に出したのはそのため。
- stooq は JavaScript による人間確認が入るためスクリプトからは使えない（2026-09 時点）。
