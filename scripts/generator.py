import json
import os
import argparse
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# Define timezones
JST = timezone(timedelta(hours=9), "JST")

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def squash_name(x):
    if not isinstance(x, str): return ""
    x = unicodedata.normalize("NFKC", x)
    x = x.replace("(", "（").replace(")", "）")
    x = re.sub(r"\s+", " ", x).strip()
    return x

def squash_field(x):
    if not isinstance(x, str): return ""
    x = unicodedata.normalize("NFKC", x)
    x = re.sub(r"\s+", "", x)
    x = x.replace("(", "（").replace(")", "）")
    x = x.replace("~", "～")
    return x

def slugify(text):
    return re.sub(r"[^\w\s-]", "", text).strip().lower().replace(" ", "-")

def get_id_from_url(url, fallback_name):
    if url:
        match = re.search(r"/([^/]+)$", url.strip("/"))
        if match:
            return match.group(1)
    return slugify(fallback_name)

def load_master(master_path):
    """Load the master data and build the lookup maps.

    Cafeterias are looked up by (name, location) because the source PDF has no
    identifier. Kitchen cars are looked up by name only.
    """
    master_raw = load_json(master_path)
    if not master_raw:
        master_raw = {"facilities": [], "kitchen_cars": []}

    facilities = master_raw.get("facilities", [])

    cafeteria_master_map = {}
    for c in facilities:
        key = (squash_name(c["name"]), squash_field(c["location"]))
        cafeteria_master_map[key] = c

    kitchen_car_master_map = {}
    kc_list = master_raw.get("kitchen_cars", []) + [f for f in facilities if f.get("category") == "キッチンカー"]
    for k in kc_list:
        key = squash_name(k["name"])
        kitchen_car_master_map[key] = k

    return cafeteria_master_map, kitchen_car_master_map, facilities

def merge_kitchen_car_archive(past_archive, scraped, today_str):
    """Merge the archive with a fresh scrape. No side effects.

    Entries before today are frozen: the source site drops past data quickly,
    so the archive is the only record of what actually happened.
    Entries from today on are replaced by the scraped data, so that cancellations
    and time changes are reflected. Today's entries become frozen tomorrow.
    """
    frozen_past = [d for d in past_archive if d["date"] < today_str]
    # A scrape may still contain past entries (e.g. recovering after skipped runs);
    # archive them too instead of dropping them. Archived entries take precedence.
    frozen_past += [d for d in scraped if d["date"] < today_str]
    if scraped:
        upcoming = [d for d in scraped if d["date"] >= today_str]
    else:
        # An empty scrape most likely means a fetch failure; keep the archive as is.
        upcoming = [d for d in past_archive if d["date"] >= today_str]

    merged = []
    seen = set()
    for d in frozen_past + upcoming:
        key = (d["id"], d["date"])
        if key not in seen:
            merged.append(d)
            seen.add(key)
    return merged

def get_or_create_date(schedule_map, date_str):
    if date_str not in schedule_map:
        schedule_map[date_str] = {
            "date": date_str,
            "timezone": "JST",
            "facilities": [],
            "sources": []
        }
    return schedule_map[date_str]

def add_cafeteria_schedules(schedule_map, cafeteria_dir, cafeteria_master_map, base_url):
    """Add the parsed cafeteria entries, resolving the shop id from the master.

    Returns the shops that could not be resolved, keyed by (name, location).
    They still get an entry with a generated id so that the day is not lost;
    the caller reports them instead of failing the whole run.
    """
    unresolved = {}
    for p in Path(cafeteria_dir).glob("*.json"):
        # Match {YYYY_MM}.json to daily/{YYYY_MM}.pdf
        source_filename = p.name.replace(".json", ".pdf")

        entries = load_json(str(p))
        if not isinstance(entries, list):
            continue

        for s in entries:
            day_data = get_or_create_date(schedule_map, s["date"])

            # Add source to day as an absolute path for the frontend
            source_entry = {"name": source_filename, "url": f"{base_url}/daily/{source_filename}"}
            if source_entry not in day_data["sources"]:
                day_data["sources"].append(source_entry)

            norm_name = squash_name(s["name"])
            norm_loc = squash_field(s["location"])
            m_info = cafeteria_master_map.get((norm_name, norm_loc))

            if not m_info:
                record = unresolved.setdefault((norm_name, norm_loc), {"dates": [], "sources": set(), "hints": set()})
                record["dates"].append(s["date"])
                record["sources"].add(source_filename)
                # Provide hints for potential matches
                record["hints"].update(m["id"] for k, m in cafeteria_master_map.items()
                                       if norm_name in k[0] or k[0] in norm_name)
                shop_id = slugify(f"MISSING-{norm_name}-{norm_loc}")
            else:
                shop_id = m_info["id"]

            day_data["facilities"].append({
                "id": shop_id,
                "name": s["name"],
                "location": s["location"],
                "category": m_info.get("category", "食堂") if m_info else "食堂",
                "url": m_info.get("url", "") if m_info else "",
                "google_map": m_info.get("google_map", "") if m_info else "",
                "image_url": m_info.get("image_url", "") if m_info else "",
                "headline": m_info.get("headline", "") if m_info else "",
                "start_time": s["start_time"],
                "end_time": s["end_time"],
                "business_hours": s["business_hours"],
                "note": s["note"]
            })

    return unresolved

def report_unresolved_shops(unresolved):
    """Report shops missing from the master. Notifies, never fails the run.

    Failing here would stop the whole daily update over a single renamed shop,
    so the data keeps flowing and the operator is told what to fix.
    """
    if not unresolved:
        return

    print(f"\n!!! MAJOR ERROR: {len(unresolved)} shop(s) not found in master data:")
    for (name, location), record in sorted(unresolved.items()):
        dates = sorted(record["dates"])
        print(f"  - Name='{name}', Location='{location}'"
              f" ({len(dates)} entries, {dates[0]} - {dates[-1]}, source: {', '.join(sorted(record['sources']))})")
        if record["hints"]:
            print(f"    Hint: Found similar names in master data: {', '.join(sorted(record['hints']))}")

    # GitHub Actions では注釈として表示する。ジョブは失敗させない。
    if os.environ.get("GITHUB_ACTIONS") == "true":
        shops = ", ".join(f"{name}（{location}）" for name, location in sorted(unresolved))
        print(f"::warning title=マスターに未登録の店舗::{len(unresolved)}件: {shops}"
              f" / scripts/facilities.json に追加してください。未登録のままだと missing- で始まるIDで公開されます。")

def add_kitchen_car_schedules(schedule_map, kitchen_car_schedules, kitchen_car_master_map):
    """Add the archived kitchen car entries."""
    for s in kitchen_car_schedules:
        day_data = get_or_create_date(schedule_map, s["date"])
        norm_name = squash_name(s["name"])
        m_info = kitchen_car_master_map.get(norm_name)
        target_url = s.get("url", "") or (m_info.get("url", "") if m_info else "")

        # For kitchen cars, missing from master is NOT an error.
        # Priority: Master ID > URL Hash > Slugified Name
        if m_info and "id" in m_info:
            shop_id = m_info["id"]
        elif target_url:
            shop_id = get_id_from_url(target_url, s["name"])
        else:
            shop_id = slugify(norm_name)

        day_data["facilities"].append({
            "id": shop_id,
            "name": s["name"],
            "url": target_url,
            "image_url": m_info.get("image_url", "") if m_info else "",
            "headline": s.get("headline", "") or (m_info.get("headline", "") if m_info else ""),
            "location": s.get("location") or "大学内指定場所",
            "google_map": "",
            "category": "キッチンカー",
            "start_time": s.get("start_time", "00:00"),
            "end_time": s.get("end_time", "00:00"),
            "business_hours": s.get("business_hours", ""),
            "note": ""
        })

EXTRA_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
EXTRA_TIME_PATTERN = re.compile(r"^\d{1,2}:\d{2}$")
EXTRA_TEXT_FIELDS = ("name", "location", "category", "headline", "url", "note")

def to_minutes(hhmm):
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)

def validate_extra_entry(raw):
    """Normalize one entry of data/extra/*.json. Returns (entry, error)."""
    if not isinstance(raw, dict):
        return None, "エントリがオブジェクトではありません"

    for key in ("id", "name", "date", "location", "start_time", "end_time"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            return None, f"必須の項目 '{key}' がありません"

    for key in EXTRA_TEXT_FIELDS + ("business_hours",):
        value = raw.get(key, "")
        if not isinstance(value, str):
            return None, f"項目 '{key}' が文字列ではありません"
        # カードは innerHTML で組み立てるため、タグになりうる文字は受け付けない
        if "<" in value or ">" in value:
            return None, f"項目 '{key}' に < または > は使えません"

    if not EXTRA_ID_PATTERN.match(raw["id"]):
        return None, f"id '{raw['id']}' は半角英小文字・数字・ハイフンだけで書いてください"
    try:
        datetime.strptime(raw["date"], "%Y-%m-%d")
    except ValueError:
        return None, f"date '{raw['date']}' は YYYY-MM-DD の形式ではありません"
    for key in ("start_time", "end_time"):
        if not EXTRA_TIME_PATTERN.match(raw[key]):
            return None, f"{key} '{raw[key]}' は HH:MM の形式ではありません"
    if to_minutes(raw["start_time"]) >= to_minutes(raw["end_time"]):
        return None, f"end_time '{raw['end_time']}' は start_time '{raw['start_time']}' より後にしてください"
    url = raw.get("url", "")
    if url and not re.match(r"^https?://", url):
        return None, "url は http:// または https:// で始めてください"

    entry = {
        "id": raw["id"],
        "name": squash_name(raw["name"]),
        "url": url,
        "image_url": "",
        "headline": raw.get("headline", ""),
        "location": squash_field(raw["location"]),
        "google_map": "",
        "category": raw.get("category") or "ショップ",
        "start_time": raw["start_time"],
        "end_time": raw["end_time"],
        "business_hours": raw.get("business_hours") or f"{raw['start_time']}～{raw['end_time']}",
        "note": raw.get("note", ""),
        "temporary": True,
    }
    return (raw["date"], entry), None

def load_extra_schedules(extra_dir):
    """Read data/extra/*.json: shops that are not official or open only temporarily.

    Each file is an array of one-day entries. Files are read in name order, so a
    later file wins over an earlier one for the same (id, date). A broken file or
    entry is skipped and reported; it never stops the daily update.

    Returns the (date, entry) pairs and the problems found.
    """
    entries, problems = [], []
    if not extra_dir or not os.path.isdir(extra_dir):
        return entries, problems

    for path in sorted(Path(extra_dir).glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_entries = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            problems.append((path.name, f"読み込めません: {e}"))
            continue
        if not isinstance(raw_entries, list):
            problems.append((path.name, "最上位が配列ではありません"))
            continue
        for i, raw in enumerate(raw_entries, start=1):
            parsed, error = validate_extra_entry(raw)
            if error:
                problems.append((f"{path.name} の {i} 件目", error))
            else:
                entries.append(parsed)
    return entries, problems

def report_extra_problems(problems):
    """Report skipped extra entries. Notifies, never fails the run."""
    if not problems:
        return
    print(f"\n!!! {len(problems)} problem(s) in data/extra, skipped:")
    for where, message in problems:
        print(f"  - {where}: {message}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        detail = " / ".join(f"{where}: {message}" for where, message in problems)
        print(f"::warning title=臨時店舗のJSONに問題があります::{len(problems)}件を読み飛ばしました: {detail}")

def add_extra_schedules(schedule_map, extra_entries):
    """Add the extra shops. The same (id, date) as an existing entry replaces it."""
    for date_str, entry in extra_entries:
        day_data = get_or_create_date(schedule_map, date_str)
        day_data["facilities"] = [f for f in day_data["facilities"] if f["id"] != entry["id"]]
        day_data["facilities"].append(dict(entry))

def fill_date_gaps(schedule_map):
    """Fill gaps between the first and last dates to ensure continuity."""
    if not schedule_map:
        return
    all_dates = sorted(schedule_map.keys())
    curr_dt = datetime.strptime(all_dates[0], "%Y-%m-%d")
    last_dt = datetime.strptime(all_dates[-1], "%Y-%m-%d")
    while curr_dt <= last_dt:
        get_or_create_date(schedule_map, curr_dt.strftime("%Y-%m-%d"))
        curr_dt += timedelta(days=1)

def inject_static_schedules(schedule_map, facilities):
    """Add shops that keep fixed hours (ATMs, convenience stores) to every day."""
    for date_str, day_data in schedule_map.items():
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = dt.weekday() # 0=Mon, 5=Sat, 6=Sun

        for m_shop in facilities:
            if "static-hours" not in m_shop:
                continue

            hours_str = ""
            if weekday < 5: # Mon-Fri
                hours_str = m_shop["static-hours"].get("ordinary", "")
            elif weekday == 5: # Sat
                hours_str = m_shop["static-hours"].get("saturday", "")

            if hours_str and hours_str != "closed":
                start_time, end_time = "00:00", "00:00"
                if "-" in hours_str:
                    start_time, end_time = hours_str.split("-")

                day_data["facilities"].append({
                    "id": m_shop["id"],
                    "name": m_shop["name"],
                    "url": m_shop.get("url", ""),
                    "location": m_shop["location"],
                    "category": m_shop.get("category", "サービス"),
                    "headline": m_shop.get("headline", ""),
                    "google_map": "",
                    "image_url": "",
                    "start_time": start_time,
                    "end_time": end_time,
                    "business_hours": hours_str,
                    "note": ""
                })

def build_schedule_map(cafeteria_dir, kitchen_car_schedules, cafeteria_master_map,
                       kitchen_car_master_map, facilities, base_url, now_jst, extra_entries=()):
    """Build the date-keyed schedule from every source.

    The order matters: cafeterias, kitchen cars, static shops, then extra shops,
    so that the facilities of a day keep that order. Gaps are filled before
    injecting the static shops so that the filled days get them too. The extra
    shops come last so that they can replace an entry of any other source, and
    their dates are created before the gaps are filled.

    Returns the schedule and the shops that could not be resolved in the master.
    """
    schedule_map = {}

    # Ensure a minimum window around today (7 days ago to 32 days ahead)
    # This ensures static shops appear for the current period even if no other data exists.
    start_init = now_jst - timedelta(days=7)
    for i in range(40):
        get_or_create_date(schedule_map, (start_init + timedelta(days=i)).strftime("%Y-%m-%d"))

    unresolved = add_cafeteria_schedules(schedule_map, cafeteria_dir, cafeteria_master_map, base_url)
    add_kitchen_car_schedules(schedule_map, kitchen_car_schedules, kitchen_car_master_map)
    for date_str, _ in extra_entries:
        get_or_create_date(schedule_map, date_str)
    fill_date_gaps(schedule_map)
    inject_static_schedules(schedule_map, facilities)
    add_extra_schedules(schedule_map, extra_entries)
    return schedule_map, unresolved

def write_daily_api(schedule_map, api_schedule_dir, now_jst):
    """Write api/schedule/{date} and the today/yesterday/tomorrow shortcuts."""
    for date_str, data in schedule_map.items():
        save_json(data, os.path.join(api_schedule_dir, f"{date_str}"))

    shortcuts = {
        "today": now_jst.strftime("%Y-%m-%d"),
        "yesterday": (now_jst - timedelta(days=1)).strftime("%Y-%m-%d"),
        "tomorrow": (now_jst + timedelta(days=1)).strftime("%Y-%m-%d")
    }
    for label, d_str in shortcuts.items():
        if d_str in schedule_map:
            save_json(schedule_map[d_str], os.path.join(api_schedule_dir, f"{label}"))

def write_weekly_api(schedule_map, api_schedule_dir, now_jst):
    """Write api/schedule/weeks/{n}, covering this week and the following ones."""
    current_monday = now_jst - timedelta(days=now_jst.weekday())
    all_dates = sorted(schedule_map.keys())
    max_date_str = all_dates[-1] if all_dates else now_jst.strftime("%Y-%m-%d")
    max_dt = datetime.strptime(max_date_str, "%Y-%m-%d").replace(tzinfo=JST)

    delta_days = (max_dt - current_monday).days
    total_weeks = (delta_days // 7) + 1 if delta_days >= 0 else 1

    for w in range(total_weeks):
        week_start = current_monday + timedelta(weeks=w)
        daily_schedules = [schedule_map.get((week_start + timedelta(days=i)).strftime("%Y-%m-%d"), {"date": (week_start + timedelta(days=i)).strftime("%Y-%m-%d"), "facilities": [], "sources": []}) for i in range(7)]
        week_data = {
            "week_index": w,
            "start_date": week_start.strftime("%Y-%m-%d"),
            "end_date": (week_start + timedelta(days=6)).strftime("%Y-%m-%d"),
            "timezone": "JST",
            "daily_schedules": daily_schedules
        }
        # Save as weeks/0, weeks/1, etc.
        os.makedirs(os.path.join(api_schedule_dir, "weeks"), exist_ok=True)
        save_json(week_data, os.path.join(api_schedule_dir, f"weeks/{w}"))
        if w == 0: save_json(week_data, os.path.join(api_schedule_dir, "week"))

def write_shops_api(schedule_map, output_dir):
    """Write api/shops/{id} and the index. Returns the shops keyed by id."""
    all_shops = {}
    for date_str, data in sorted(schedule_map.items()):
        for c in data["facilities"]:
            sid = c["id"]
            if sid not in all_shops:
                all_shops[sid] = {**{k: v for k, v in c.items() if k not in ["start_time", "end_time", "business_hours", "note", "date"]}, "schedules": []}
            all_shops[sid]["schedules"].append({"date": date_str, "location": c["location"], "start_time": c["start_time"], "end_time": c["end_time"], "note": c["note"]})

    api_shops_dir = os.path.join(output_dir, "api/shops")
    shops_index = {"shops": []}
    for sid, sdata in all_shops.items():
        save_json(sdata, os.path.join(api_shops_dir, f"{sid}"))
        shops_index["shops"].append({k: v for k, v in sdata.items() if k != "schedules"})
    save_json(shops_index, os.path.join(api_shops_dir, "index.json"))
    return all_shops

def build_status_source(filename, info, base_url):
    """Build one entry of sources in api/status from the PDF metadata.

    month tells which month the PDF covers, so that the frontend can tell
    "not published yet" from "closed all day" (a closed day has no source either).
    last_modified comes as an HTTP date and fetched_at is in UTC for older PDFs,
    so both are converted to JST like the other timestamps.
    """
    m = re.fullmatch(r"(\d{4})_(\d{2})\.pdf", filename)
    info = info if isinstance(info, dict) else {}
    last_modified = None
    if info.get("last-modified"):
        try:
            last_modified = parsedate_to_datetime(info["last-modified"]).astimezone(JST).isoformat()
        except (TypeError, ValueError):
            pass
    fetched_at = info.get("fetched_at")
    if fetched_at:
        try:
            fetched_at = datetime.fromisoformat(fetched_at).astimezone(JST).isoformat()
        except (TypeError, ValueError):
            pass
    return {
        "name": filename,
        "url": f"{base_url}/daily/{filename}",
        "month": f"{m.group(1)}-{m.group(2)}" if m else None,
        "last_modified": last_modified,
        "fetched_at": fetched_at,
    }

def write_status_api(schedule_map, shop_count, metadata, base_url, output_dir, last_updated):
    """Write api/status, the only place that carries the build timestamp."""
    dates = sorted(schedule_map.keys())
    global_sources = []
    if isinstance(metadata, dict):
        for filename, info in metadata.items():
            global_sources.append(build_status_source(filename, info, base_url))

    save_json({
        "last_updated": last_updated,
        "timezone": "JST",
        "data_range": {"start": dates[0] if dates else "", "end": dates[-1] if dates else ""},
        "shop_count": shop_count,
        "sources": global_sources
    }, os.path.join(output_dir, "api/status"))

def generator(cafeteria_dir, kitchen_cars_path, master_path, output_dir, kitchen_cars_archive, base_url, extra_dir=None):
    # Use JST for all time-based logic and timestamps
    now_jst = datetime.now(JST)
    today_str = now_jst.strftime("%Y-%m-%d")
    last_updated = now_jst.isoformat()
    base_url = base_url.rstrip("/")

    cafeteria_master_map, kitchen_car_master_map, facilities = load_master(master_path)

    # Load metadata for PDF URLs from the new public/daily location
    metadata = load_json(os.path.join(output_dir, "daily/.metadata.json"))

    scraped = load_json(kitchen_cars_path)
    if isinstance(scraped, dict):
        scraped = []
    past_archive = load_json(kitchen_cars_archive)
    if isinstance(past_archive, dict):
        past_archive = []

    # The archive is the only record of what actually happened, so it is written
    # back here and committed to main by the daily workflow.
    kitchen_car_schedules = merge_kitchen_car_archive(past_archive, scraped, today_str)
    save_json(kitchen_car_schedules, kitchen_cars_archive)

    extra_entries, extra_problems = load_extra_schedules(extra_dir)

    schedule_map, unresolved = build_schedule_map(cafeteria_dir, kitchen_car_schedules, cafeteria_master_map,
                                                  kitchen_car_master_map, facilities, base_url, now_jst,
                                                  extra_entries)
    report_unresolved_shops(unresolved)
    report_extra_problems(extra_problems)

    api_schedule_dir = os.path.join(output_dir, "api/schedule")
    write_daily_api(schedule_map, api_schedule_dir, now_jst)
    write_weekly_api(schedule_map, api_schedule_dir, now_jst)
    all_shops = write_shops_api(schedule_map, output_dir)
    write_status_api(schedule_map, len(all_shops), metadata, base_url, output_dir, last_updated)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cafeteria-dir", required=True)
    parser.add_argument("--kitchen-cars", required=True)
    parser.add_argument("--kitchen-cars-archive", required=True)
    parser.add_argument("--master", required=True)
    parser.add_argument("-o", "--output-dir", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--extra-dir", default=None, help="臨時店舗などのJSONを置くディレクトリ")
    args = parser.parse_args()
    generator(args.cafeteria_dir, args.kitchen_cars, args.master, args.output_dir, args.kitchen_cars_archive,
              args.base_url, args.extra_dir)
