import requests
import json
import os
from datetime import datetime, timedelta

# ============================
# CONFIGURATION
# ============================

API_TOKEN = "pk_218696006_UXYXEI6AKDLMXJ3P4INX79SD9ZO0UTF0"
LIST_ID = "901412176234"
TAG_FILTER = "%23new"

headers = {"Authorization": API_TOKEN}

# ============================
# CLICKUP FIELD IDS
# ============================

FIELD_COMMERCE_PLATFORM = "4927273a-9c1f-4042-8aca-5fd4d14fa26a"

FIELD_MAP = {
    "Kickoff": "7c302bd2-027a-4f17-b795-c3f55a044868",
    "Design": "8425e4a9-2dc3-4064-88ce-629706717aab",
    "Integration": "ed0a3f9a-824d-40cd-9b43-4fb72e1876f4",
    "PreGoLive": "afc4d2a9-4a58-4038-b96d-248a7c7d765e",
    "QA": "59bfc489-64c2-402a-bf35-865116d22af5",
    "GoLive": "7344338c-1889-443b-b698-9924c9c936f2"
}

STAGE_ORDER = ["Kickoff", "Design", "Integration", "PreGoLive", "QA", "GoLive"]

# ============================
# PLATFORM OFFSETS (WORKING DAYS)
# ============================

STAGE_OFFSETS = {
    "shopify": {
        "Kickoff": 2,
        "Design": 2,
        "Integration": 2,
        "PreGoLive": 1,
        "QA": 1,
        "GoLive": 1
    },
    "rich": {
        "Kickoff": 2,
        "Design": 5,
        "Integration": 7,
        "PreGoLive": 2,
        "QA": 4,
        "GoLive": 1
    },
    "custom": {
        "Kickoff": 2,
        "Design": 6,
        "Integration": 20,
        "PreGoLive": 2,
        "QA": 4,
        "GoLive": 1
    }
}

RICH_PLATFORMS = ["woo", "woocommerce", "magento", "sfcc", "big"]

# ============================
# GLOBAL DROPDOWN MAPS
# ============================

PLATFORM_UUID_TO_NAME = {}
PLATFORM_ID_BY_INDEX = []

# ============================
# LOAD HOLIDAYS
# ============================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOLIDAY_FILE = os.path.join(BASE_DIR, "config", "holidays.json")

with open(HOLIDAY_FILE, "r") as f:
    HOLIDAYS = {
        datetime.strptime(d, "%Y-%m-%d").date()
        for d in json.load(f)["holidays"]
    }

print(f"✅ Loaded {len(HOLIDAYS)} holidays")

# ============================
# DATE HELPERS
# ============================

def add_workdays(start_date, days):
    current = start_date
    while days > 0:
        current += timedelta(days=1)
        if current.weekday() < 5 and current.date() not in HOLIDAYS:
            days -= 1
    return current

# ============================
# CLICKUP HELPERS
# ============================

def fetch_field_options():
    global PLATFORM_UUID_TO_NAME, PLATFORM_ID_BY_INDEX

    url = f"https://api.clickup.com/api/v2/list/{LIST_ID}/field"
    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        return False

    fields = r.json().get("fields", [])
    field = next(f for f in fields if f["id"] == FIELD_COMMERCE_PLATFORM)

    PLATFORM_UUID_TO_NAME = {o["id"]: o["name"] for o in field["type_config"]["options"]}
    sorted_opts = sorted(field["type_config"]["options"], key=lambda x: x["orderindex"])
    PLATFORM_ID_BY_INDEX = [o["id"] for o in sorted_opts]

    return True

def get_all_tasks():
    tasks = []
    page = 0
    while True:
        url = f"https://api.clickup.com/api/v2/list/{LIST_ID}/task?page={page}&tags[]={TAG_FILTER}"
        r = requests.get(url, headers=headers)
        data = r.json()
        if not data.get("tasks"):
            break
        tasks.extend(data["tasks"])
        page += 1
    return tasks

def resolve_platform(task):
    platform = "custom"

    for f in task.get("custom_fields", []):
        if f["id"] == FIELD_COMMERCE_PLATFORM:
            raw = f.get("value")
            option_id = None

            if isinstance(raw, int) and raw < len(PLATFORM_ID_BY_INDEX):
                option_id = PLATFORM_ID_BY_INDEX[raw]
            elif isinstance(raw, str):
                option_id = raw
            elif isinstance(raw, list) and raw:
                option_id = raw[0]

            if option_id:
                name = PLATFORM_UUID_TO_NAME.get(option_id, "").lower()
                if "shopify" in name:
                    platform = "shopify"
                elif any(p in name for p in RICH_PLATFORMS):
                    platform = "rich"
            break

    return platform

# ============================
# MAIN
# ============================

def run():
    if not fetch_field_options():
        print("❌ Failed to load platform dropdown")
        return

    tasks = get_all_tasks()
    print(f"🔎 Processing {len(tasks)} tasks")

    for task in tasks:
        task_id = task["id"]
        created = datetime.fromtimestamp(int(task["date_created"]) / 1000)

        platform = resolve_platform(task)
        current_date = created

        for stage in STAGE_ORDER:
            offset = STAGE_OFFSETS[platform][stage]
            current_date = add_workdays(current_date, offset)

            payload = {
                "value": int(current_date.timestamp() * 1000),
                "value_options": {"time": True}
            }

            url = f"https://api.clickup.com/api/v2/task/{task_id}/field/{FIELD_MAP[stage]}"
            requests.post(url, headers=headers, json=payload)

        print(f"✅ {task_id} | Platform: {platform}")

    print("🎯 Completed successfully")

if __name__ == "__main__":
    run()
