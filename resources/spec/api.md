# 公開APIの設計方針

エンドポイントと各項目の定義は、サイトの APIリファレンス（[content/help/api.md](../../content/help/api.md)、公開版は <https://tamadalab.github.io/welfare-time/help/api/>）を正とします。ここには、APIを変更するときに守る方針をまとめます。

## エンドポイント

| エンドポイント | 内容 |
| :--- | :--- |
| `/api/schedule/today`、`tomorrow`、`yesterday` | 前日・当日・翌日の営業情報 |
| `/api/schedule/YYYY-MM-DD` | 指定した日の営業情報 |
| `/api/schedule/week`、`/api/schedule/weeks/{n}` | 週単位の営業情報（`n` は 0 が今週、1 が来週） |
| `/api/shops`、`/api/shops/{shop-id}` | 店舗の情報と営業日時の一覧 |
| `/api/status` | データ全体の更新状況と範囲 |

## 方針

- **静的ファイルで配信します。** サーバーは持たず、`generator.py` がすべてのエンドポイントをファイルとして事前に生成します。日付を指定したアクセスに応えるため、過去と未来の日付の分もファイルを置きます。
- **パスに拡張子を付けません。** `api/schedule/today` のように、拡張子のないファイル名で置きます。
  - 例外は店舗一覧です。`api/shops` は店舗ごとのファイル（`api/shops/{shop-id}`）を置くディレクトリなので、一覧は `api/shops/index.json` に置きます。GitHub Pages では `/api/shops/` でこのファイルが返り、`/api/shops` は `/api/shops/` にリダイレクトされます。
- **施設は1つの配列にまとめます。** 日付ごとの営業情報は、食堂もキッチンカーも `facilities` の1つの配列で返し、種類は `category` で区別します（v0.2.0 で `cafeterias` と `kitchen_cars` から統合しました）。
- **URL は絶対URLで返します。** 取得元のURL（`sources[].url`）など、APIが返すURLはベースURLを前置した絶対URLにします。相対URLでは、利用者がAPIのURLに対して解決すると存在しないURLになります。APIリファレンスの例も絶対URLで書きます。
- **PDF の公開の有無は月で判定します。** 日付ごとのAPIの `sources` は、その日に営業の行がある PDF だけを返すので、休業日にも空になります。そのため、食堂の PDF が公開済みかどうかは、`/api/status` の `sources[].month` で判定します。
- **意味のない差分を出しません。** 日付ごとのAPIには生成時刻を入れません。毎朝すべてのファイルが書き換わるのを避けるためです。更新時刻は `/api/status` で返します。
- **生成されなくなったファイルを残しません。** デプロイのたびに `public/api` を削除して作り直します。配信中のファイルとの差は `just stale_api` で確認できます。
- **形式を変えるときはバージョンを上げます。** 利用者の対応が必要な変更は、[CHANGELOG.md](../../CHANGELOG.md) に明記します。
