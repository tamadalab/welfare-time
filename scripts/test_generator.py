import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generator import (merge_kitchen_car_archive, add_cafeteria_schedules,
                       load_extra_schedules, add_extra_schedules, build_status_source)

TODAY = "2026-08-04"

def entry(shop_id, date, business_hours="11:00〜17:00"):
    return {
        "id": shop_id,
        "name": f"{shop_id}の店",
        "location": "",
        "date": date,
        "start_time": business_hours.split("〜")[0],
        "end_time": business_hours.split("〜")[1],
        "business_hours": business_hours,
        "headline": "",
        "url": f"https://schedule.mellow.jp/ss_web/shops/{shop_id}",
    }

def keys(entries):
    return {(e["id"], e["date"]) for e in entries}

def check(failures, condition, message):
    if not condition:
        failures.append(message)

def test_merge_kitchen_car_archive():
    """アーカイブの不変条件を検証する。

    data/kitchen_cars_past.json は、その日に何が出店していたかの唯一の記録で
    あり、失うと復元できない。
    """
    failures = []

    # 1. 過去のエントリは凍結される。スクレイプに含まれなくても消えない
    archive = [entry("a", "2026-07-29"), entry("b", "2026-07-30")]
    merged = merge_kitchen_car_archive(archive, [entry("c", "2026-08-10")], TODAY)
    check(failures, ("a", "2026-07-29") in keys(merged), "Past entry 'a' must survive a scrape that omits it")
    check(failures, ("b", "2026-07-30") in keys(merged), "Past entry 'b' must survive a scrape that omits it")

    # 2. 当日以降はスクレイプ結果が正。出店の取りやめが反映される
    archive = [entry("past", "2026-07-30"), entry("a", "2026-08-05"), entry("b", "2026-08-05")]
    merged = merge_kitchen_car_archive(archive, [entry("a", "2026-08-05", "11:00〜15:00")], TODAY)
    check(failures, ("b", "2026-08-05") not in keys(merged), "Cancelled upcoming entry 'b' must be dropped")
    check(failures, ("a", "2026-08-05") in keys(merged), "Upcoming entry 'a' must remain")
    check(failures, ("past", "2026-07-30") in keys(merged), "Past entry must survive an upcoming cancellation")
    updated = [e for e in merged if e["id"] == "a"][0]
    check(failures, updated["business_hours"] == "11:00〜15:00",
          f"Upcoming entry must take the scraped hours, but got {updated['business_hours']!r}")

    # 3. スクレイプが0件ならアーカイブに手を加えない（フェッチ失敗の可能性）
    archive = [entry("past", "2026-07-30"), entry("future", "2026-08-05")]
    merged = merge_kitchen_car_archive(archive, [], TODAY)
    check(failures, keys(merged) == keys(archive),
          "An empty scrape must leave the archive untouched, it most likely means a fetch failure")

    # 4. 当日のエントリはスクレイプから取り込まれる（翌日には凍結される）
    merged = merge_kitchen_car_archive([], [entry("today", TODAY)], TODAY)
    check(failures, ("today", TODAY) in keys(merged), "Today's entry must be archived on the day itself")
    frozen = merge_kitchen_car_archive(merged, [], "2026-08-05")
    check(failures, ("today", TODAY) in keys(frozen), "Yesterday's entry must be frozen the next day")

    # 5. スクレイプに過去日が含まれる場合も取りこぼさない（実行が飛んだ日の回復）
    merged = merge_kitchen_car_archive([], [entry("recovered", "2026-08-01")], TODAY)
    check(failures, ("recovered", "2026-08-01") in keys(merged),
          "A past entry present in the scrape must be archived instead of dropped")

    # 6. 重複は (id, date) で排除され、アーカイブ側が優先される
    archive = [entry("dup", "2026-07-30", "11:00〜17:00")]
    scraped = [entry("dup", "2026-07-30", "09:00〜10:00")]
    merged = merge_kitchen_car_archive(archive, scraped, TODAY)
    check(failures, len(merged) == 1, f"Duplicated (id, date) must collapse into one, but got {len(merged)}")
    if merged:
        check(failures, merged[0]["business_hours"] == "11:00〜17:00",
              "The archived entry must win over a conflicting past entry from the scrape")

    # 7. 同じ日の別店舗は別エントリとして残る
    merged = merge_kitchen_car_archive([], [entry("x", TODAY), entry("y", TODAY)], TODAY)
    check(failures, len(merged) == 2, f"Different shops on the same day must be kept, but got {len(merged)}")

    if failures:
        raise AssertionError("\n  - " + "\n  - ".join(failures))

    print("Regression test passed: kitchen car archive invariants.")

def test_unresolved_shops(tmp_dir):
    """マスターに引き当てられない店舗が、集計されつつ公開もされることを検証する。

    データ更新を止めないため、引き当て失敗は例外にせず報告に留める。
    """
    import json
    failures = []

    os.makedirs(tmp_dir, exist_ok=True)
    entries = [
        {"name": "登録済みの店", "location": "1F", "date": "2026-06-01",
         "start_time": "11:00", "end_time": "14:00", "business_hours": "11:00～14:00", "note": ""},
        {"name": "未登録の店", "location": "2F", "date": "2026-06-01",
         "start_time": "11:00", "end_time": "14:00", "business_hours": "11:00～14:00", "note": ""},
        {"name": "未登録の店", "location": "2F", "date": "2026-06-02",
         "start_time": "11:00", "end_time": "14:00", "business_hours": "11:00～14:00", "note": ""},
    ]
    path = os.path.join(tmp_dir, "2026_06.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)

    master_map = {("登録済みの店", "1F"): {"id": "known", "name": "登録済みの店", "location": "1F"}}
    schedule_map = {}
    unresolved = add_cafeteria_schedules(schedule_map, tmp_dir, master_map, "https://example.com")

    check(failures, list(unresolved) == [("未登録の店", "2F")],
          f"Only the unknown shop must be reported, but got {list(unresolved)}")
    if unresolved:
        record = unresolved[("未登録の店", "2F")]
        check(failures, sorted(record["dates"]) == ["2026-06-01", "2026-06-02"],
              f"Every date must be collected, but got {record['dates']}")
        check(failures, record["sources"] == {"2026_06.pdf"},
              f"The source file must be recorded, but got {record['sources']}")

    # 引き当てできなくてもその日のデータは失われない
    day = schedule_map.get("2026-06-01", {})
    ids = [f["id"] for f in day.get("facilities", [])]
    check(failures, "known" in ids, f"The resolved shop must keep its master id, but got {ids}")
    check(failures, any(i.startswith("missing-") for i in ids),
          f"The unresolved shop must still be published with a generated id, but got {ids}")

    if failures:
        raise AssertionError("\n  - " + "\n  - ".join(failures))

    print("Regression test passed: unresolved shops are reported without dropping data.")

def test_extra_schedules(tmp_dir):
    """臨時店舗のJSONの読み込みと、置き換え、読み飛ばしを検証する。

    JSONの不備で毎朝の更新を止めないため、不備は読み飛ばして報告に留める。
    """
    import json
    failures = []

    os.makedirs(tmp_dir, exist_ok=True)
    for name in os.listdir(tmp_dir):
        os.remove(os.path.join(tmp_dir, name))

    def shop(shop_id, date, **kwargs):
        return {"id": shop_id, "name": f"{shop_id}の店", "date": date, "location": "並楽館前",
                "start_time": "11:00", "end_time": "14:00", **kwargs}

    def write(name, content):
        with open(os.path.join(tmp_dir, name), "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))

    write("a.json", [shop("popup", "2026-10-15"), shop("popup", "2026-10-15", end_time="15:00")])
    write("b.json", [shop("ok", "2026-10-16", category="食堂", business_hours="11:00～14:00（売り切れ次第終了）"),
                     shop("bad-date", "2026/10/16"),
                     shop("Bad_Id", "2026-10-16"),
                     shop("tag", "2026-10-16", note="<script>"),
                     shop("js", "2026-10-16", url="javascript:alert(1)"),
                     shop("no-time", "2026-10-16", start_time=""),
                     shop("reversed", "2026-10-16", start_time="14:00", end_time="11:00")])
    write("c.json", "{ broken")
    write("d.json", {"not": "a list"})
    write("ignored.txt", "[]")

    entries, problems = load_extra_schedules(tmp_dir)
    ids = [e["id"] for _, e in entries]
    check(failures, ids == ["popup", "popup", "ok"], f"Only valid entries must be loaded, but got {ids}")
    check(failures, len(problems) == 8, f"Every broken file and entry must be reported, but got {len(problems)}: {problems}")
    check(failures, load_extra_schedules(os.path.join(tmp_dir, "missing")) == ([], []),
          "A missing directory must mean no extra shops, not an error")

    if entries:
        ok = [e for d, e in entries if e["id"] == "ok"][0]
        check(failures, ok["temporary"] is True, "Extra shops must be marked temporary")
        check(failures, ok["category"] == "食堂", f"An explicit category must be kept, but got {ok['category']!r}")
        popup = [e for d, e in entries if e["id"] == "popup"][0]
        check(failures, popup["category"] == "ショップ", f"The default category must be ショップ, but got {popup['category']!r}")
        check(failures, popup["business_hours"] == "11:00～14:00",
              f"The business hours must default to the start and end, but got {popup['business_hours']!r}")

    # 同じ (id, date) は、公式のエントリも含めて、あとのものが置き換える
    schedule_map = {"2026-10-15": {"date": "2026-10-15", "timezone": "JST", "sources": [], "facilities": [
        {"id": "popup", "name": "元の店", "category": "ショップ", "location": "", "start_time": "09:00",
         "end_time": "10:00", "business_hours": "", "note": ""},
        {"id": "other", "name": "別の店", "category": "ショップ", "location": "", "start_time": "09:00",
         "end_time": "10:00", "business_hours": "", "note": ""}]}}
    add_extra_schedules(schedule_map, entries)
    day = schedule_map["2026-10-15"]["facilities"]
    popups = [f for f in day if f["id"] == "popup"]
    check(failures, len(popups) == 1, f"The same id and date must appear once, but got {len(popups)}")
    if popups:
        check(failures, popups[0]["end_time"] == "15:00",
              f"The later entry must win, but got end_time {popups[0]['end_time']!r}")
    check(failures, any(f["id"] == "other" for f in day), "Other shops of the day must be kept")
    check(failures, "2026-10-16" in schedule_map, "The date of an extra shop must be created")

    if failures:
        raise AssertionError("\n  - " + "\n  - ".join(failures))

    print("Regression test passed: extra shops are loaded, replace by (id, date) and skip broken input.")

def test_status_sources():
    """/api/status の sources に、PDF がカバーする月と日付を出す。

    フロントエンドは month で「PDF がまだ公開されていない」を判定する。
    日ごとの sources は休業日にも空になるので、その判定には使えない。
    """
    failures = []
    base_url = "https://example.com/welfare-time"

    info = {"last-modified": "Fri, 02 Oct 2026 03:37:22 GMT", "fetched_at": "2026-10-04T07:54:20.524518+09:00"}
    s = build_status_source("2026_10.pdf", info, base_url)
    check(failures, s["url"] == f"{base_url}/daily/2026_10.pdf", f"The URL must be absolute, but got {s['url']!r}")
    check(failures, s["month"] == "2026-10", f"The month must come from the file name, but got {s['month']!r}")
    check(failures, s["last_modified"] == "2026-10-02T12:37:22+09:00",
          f"last-modified must be converted to JST, but got {s['last_modified']!r}")
    check(failures, s["fetched_at"] == info["fetched_at"], f"fetched_at in JST must be kept, but got {s['fetched_at']!r}")
    s = build_status_source("2026_05.pdf", {"fetched_at": "2026-05-31T02:49:38.393689Z"}, base_url)
    check(failures, s["fetched_at"] == "2026-05-31T11:49:38.393689+09:00",
          f"fetched_at in UTC must be converted to JST, but got {s['fetched_at']!r}")

    # 想定外のファイル名や、欠けた・壊れたメタデータでも、生成を止めない
    s = build_status_source("menu.pdf", {"last-modified": "broken"}, base_url)
    check(failures, s["month"] is None, f"An unknown file name must have no month, but got {s['month']!r}")
    check(failures, s["last_modified"] is None, f"A broken date must be None, but got {s['last_modified']!r}")
    s = build_status_source("2026_11.pdf", None, base_url)
    check(failures, s["last_modified"] is None and s["fetched_at"] is None,
          "Missing metadata must give None for the dates")

    if failures:
        raise AssertionError("\n  - " + "\n  - ".join(failures))

    print("Regression test passed: status sources carry the month and the dates of each PDF.")

if __name__ == "__main__":
    try:
        test_merge_kitchen_car_archive()
        test_unresolved_shops(os.path.join("tmp", "test_generator_cafeterias"))
        test_extra_schedules(os.path.join("tmp", "test_generator_extra"))
        test_status_sources()
    except Exception as e:
        print(f"Test failed: {e}")
        exit(1)
