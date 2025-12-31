import requests
import json
from datetime import datetime, timedelta, date

# ============================
# CONFIGURATION
# ============================
API_TOKEN = "pk_218696006_UXYXEI6AKDLMXJ3P4INX79SD9ZO0UTF0"

# LIST_ID = "901413543284"  # NEW LIST
LIST_ID = "901412176234"   # ONBOARDING

TAG_FILTER = "%23new"

FIELD_COMMERCE_PLATFORM = "4927273a-9c1f-4042-8aca-5fd4d14fa26a"

FIELD_KICKOFF     = "7c302bd2-027a-4f17-b795-c3f55a044868"
FIELD_DESIGN      = "8425e4a9-2dc3-4064-88ce-629706717aab"
FIELD_INTEGRATION = "ed0a3f9a-824d-40cd-9b43-4fb72e1876f4"
FIELD_PREGOLIVE   = "afc4d2a9-4a58-4038-b96d-248a7c7d765e"
FIELD_QA          = "59bfc489-64c2-402a-bf35-865116d22af5"
FIELD_GOLIVE      = "7344338c-1889-443b-b698-9924c9c936f2"

headers = {"Authorization": API_TOKEN}

PLATFORM_UUID_TO_NAME = {}
PLATFORM_ID_BY_INDEX = []

# ============================
# PUBLIC HOLIDAYS (INDIA)
# ============================

PUBLIC_HOLIDAYS = {
    # 2025
    date(2025, 1, 1),
    date(2025, 3, 14),
    date(2025, 4, 7),
    date(2025, 5, 1),
    date(2025, 8, 15),
    date(2025, 8, 27),
    date(2025, 10, 2),
    date(2025, 10, 20),
    date(2025, 10, 21),
    date(2025, 12, 25),

    # 2026
    date(2026, 1, 1),
    date(2026, 1, 26),
    date(2026, 3, 4),
    date(2026, 3, 20),
    date(2026, 5, 1),
    date(2026, 8, 15),
    date(2026, 8, 28),
    date(2026, 10, 2),
    date(2026, 10, 20),
    date(2026, 11, 9),
    date(2026, 12, 25),
}

# ============================
# DATE OFFSETS
# ============================

DATE_OFFSETS = {
    "shopify": {"Kickoff": 2, "Design": 4, "Integration": 6, "PreGoLive": 7, "QA": 8, "GoLive": 9},
    "rich": {"Kickoff": 2, "Design": 5, "Integration": 7, "PreGoLive": 16, "QA": 20, "GoLive": 21},
    "custom": {"Kickoff": 2, "Design": 6, "Integration": 8, "PreGoLive": 30, "QA": 34, "GoLive": 35}
}

FIELD_MAP = {
    "Kickoff": FIELD_KICKOFF,
    "Design": FIELD_DESIGN,
    "Integration": FIELD_INTEGRATION,
    "PreGoLive": FIELD_PREGOLIVE,
    "QA": FIELD_QA,
    "GoLive": FIELD_GOLIVE
}

RICH_PLATFORMS = [
    "woocommerce", "woo commerce", "woo",
    "magento", "sfcc", "salesforce",
    "bigcommerce", "big commerce"
]

# ============================
# DATE HELPERS
# ============================

def add_calendar_days(start_ms, days):
    date_obj = datetime.fromtimestamp(start_ms / 1000)
    date_obj += timedelta(days=days)
    return int(date_obj.timestamp() * 1000)

def add_workdays(start_ms, days):
    current = datetime.fromtimestamp(start_ms / 1000)
    one_day = timedelta(days=1)

    while days > 0:
        current += one_day
        d = current.date()

        if current.weekday() < 5 and d not in PUBLIC_HOLIDAYS:
            days -= 1

    return int(current.timestamp() * 1000)

# ============================
# CLICKUP HELPERS
# ============================

def fetch_field_options(list_id, field_id):
    url = f"https://api.clickup.com/api/v2/list/{list_id}/field"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print("❌ Failed to fetch platform field")
        return False

    data = r.json()
    field_def = next((f for f in data.get("fields", []) if f["id"] == field_id), None)
    if not field_def:
        return False

    global PLATFORM_UUID_TO_NAME, PLATFORM_ID_BY_INDEX

    PLATFORM_UUID_TO_NAME = {o["id"]: o["name"] for o in field_def["type_config"]["options"]}
    sorted_opts = sorted(field_def["type_config"]["options"], key=lambda x: x["orderindex"])
    PLATFORM_ID_BY_INDEX = [o["id"] for o in sorted_opts]

    return True

def get_all_tasks(list_id):
    tasks = []
    page = 0
    while True:
        url = f"https://api.clickup.com/api/v2/list/{list_id}/task?page={page}&tags[]={TAG_FILTER}"
        r = requests.get(url, headers=headers)
        data = r.json()
        if not data.get("tasks"):
            break
        tasks.extend(data["tasks"])
        page += 1
    return tasks

def classify_platform(option_uuid):
    name = PLATFORM_UUID_TO_NAME.get(option_uuid, "").lower()
    if "shopify" in name:
        return "shopify"
    if any(p in name for p in RICH_PLATFORMS):
        return "rich"
    return "custom"

# ============================
# MAIN EXECUTION
# ============================

def run_update_script():

    if not fetch_field_options(LIST_ID, FIELD_COMMERCE_PLATFORM):
        print("Script aborted")
        return

    tasks = get_all_tasks(LIST_ID)
    print(f"Found {len(tasks)} tasks\n")

    updated = skipped = 0

    for task in tasks:
        task_id = task["id"]

        try:
            date_created = int(task["date_created"])
        except:
            continue

        platform_id = None
        for f in task.get("custom_fields", []):
            if f["id"] == FIELD_COMMERCE_PLATFORM:
                val = f.get("value")
                if isinstance(val, int):
                    platform_id = PLATFORM_ID_BY_INDEX[val]
                elif isinstance(val, list) and val:
                    platform_id = val[0]
                elif isinstance(val, str):
                    platform_id = val
                break

        if not platform_id:
            skipped += 1
            continue

        group = classify_platform(platform_id)
        offsets = DATE_OFFSETS[group]

        for stage, field_id in FIELD_MAP.items():

            calculator = add_workdays
            if group in ["rich", "custom"] and stage in ["PreGoLive", "QA", "GoLive"]:
                calculator = add_calendar_days

            target = calculator(date_created, offsets[stage])
            payload = {"value_options": {"time": True}, "value": target}

            url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{field_id}"
            requests.post(url, headers=headers, json=payload)

        updated += 1
        print(f"✅ {task_id} updated ({group})")

    print("\n==============================")
    print(f"UPDATED : {updated}")
    print(f"SKIPPED : {skipped}")
    print("==============================")

if __name__ == "__main__":
    run_update_script()
