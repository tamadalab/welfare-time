---
title: "💻 API 利用ガイド"
type: "help"
---

Welfare TIME のデータを活用するためのAPIエンドポイントです。すべてGETリクエストでアクセス可能です。

## 1. 今日の予定 (`/api/schedule/today`)

当日の食堂およびキッチンカーの営業情報リストを返します。

```json
{
  "date": "2026-05-18",
  "timezone": "JST",
  "facilities": [
    {
      "id": "shop-id",
      "name": "食堂名",
      "location": "場所",
      "category": "食堂",
      "url": "...",
      "start_time": "11:00",
      "end_time": "14:00",
      "business_hours": "11:00～14:00",
      "note": "備考"
    }
  ]
}
```

常設ではない店舗や、大学の管理外の店舗には、`"temporary": true` が付きます。大学が営業情報を公開している店舗には、この項目はありません。

### その他

- `/api/schedule/YYYY-MM-DD` の GET リクエストにより当該日時の営業店舗の情報を取得できます。
- `/api/schedule/tomorrow`, `/api/schedule/yesterday` で翌日、昨日の営業店舗の情報を取得できます。
- データ全体の更新時刻は `/api/status` の `last_updated` で取得できます。

## 2. 店舗一覧 (`/api/shops`)

登録されている全店舗のマスター情報および営業スケジュール履歴です。

```json
{
  "shops": [
    {
      "id": "shop-id",
      "name": "店舗名",
      "location": "場所",
      "category": "食堂",
      "url": "..."
    }
  ]
}
```

### 当該店舗の営業日時

`/api/shops/{shop-id}` で、その店舗の営業日時の一覧を取得できます。

## 3. ステータス情報 (`/api/status`)

データセット全体の更新状況と範囲を確認します。

```json
{
  "last_updated": "2026-05-18T07:00:00",
  "data_range": { "start": "2026-05-01", "end": "2026-06-30" },
  "shop_count": 42,
  "sources": [
    {
      "name": "2026_05.pdf",
      "url": "https://tamadalab.github.io/welfare-time/daily/2026_05.pdf",
      "month": "2026-05",
      "last_modified": "2026-05-01T10:15:00+09:00",
      "fetched_at": "2026-05-02T07:03:12+09:00"
    }
  ]
}
```

`sources` は、取得済みの食堂の営業カレンダー（PDF）の一覧です。

- `month`：その PDF が対象とする月（`YYYY-MM`）。ファイル名から分からないときは `null` です。
- `last_modified`：大学サイトで PDF が更新された日時。分からないときは `null` です。
- `fetched_at`：このサイトが PDF を取得した日時。

ある月の食堂の営業予定が公開済みかどうかは、`month` で判定してください。日付ごとの API の `sources` は、その日に営業の予定がある PDF だけを返すので、日曜日や一斉休業の日にも空になります。
