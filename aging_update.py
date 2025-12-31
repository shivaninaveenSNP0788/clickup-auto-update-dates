import json
import requests
from datetime import datetime, timedelta, date
from urllib.parse import quote, unquote

# ---------------- CONFIG LOADERS ---------------- #

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)

# ---------------- WORKING DAYS CALCULATOR ---------------- #

class WorkingDaysCalculator:
    def __init__(self, holidays_file):
        self.holidays = self._load_holidays(holidays_file)

    def _load_holidays(self, path):
        try:
            data = load_json(path)
            return {
                datetime.strptime(d, "%Y-%m-%d").date()
                for d in data.get("holidays", [])
            }
        except Exception:
            return set()

    def is_working_day(self, d):
        return d.weekday() < 5 and d not in self.holidays

    def calculate(self, start_date, end_date):
        if start_date > end_date:
            return 0

        count = 0
        current = start_date
        while current < end_date:
            if self.is_working_day(current):
                count += 1
            current += timedelta(days=1)
        return count

# ---------------- CLICKUP CLIENT ---------------- #

class ClickUpClient:
    BASE_URL = "https://api.clickup.com/api/v2"

    def __init__(self, config):
        self.headers = {
            "Authorization": config["api_token"],
            "Content-Type": "application/json"
        }
        self.list_id = config["list_id"]
        self.kickoff_field_id = config["kickoff_field_id"]
        self.go_live_field_id = config["go_live_field_id"]
        self.aging_field_id = config["aging_field_id"]
        self.required_tag = unquote(config["required_tag"]).lower()
        print("🔎 Matching tag:", self.required_tag)

        self.calculator = WorkingDaysCalculator("config/holidays.json")

    def get_tasks_with_kickoff(self):
        """
        Fetch only tasks where the kickoff custom field is set using ClickUp API filter.
        Prints task details for debugging.
        """
        filter_obj = [
            {"field_id": self.kickoff_field_id, "operator": "IS NOT NULL"}
        ]
        encoded_filter = quote(json.dumps(filter_obj))

        url = f"{self.BASE_URL}/list/{self.list_id}/task"
        params = f"include_closed=true&subtasks=false&custom_fields={encoded_filter}"
        full_url = f"{url}?{params}"

        response = requests.get(full_url, headers=self.headers)
        response.raise_for_status()
        tasks = response.json().get("tasks", [])

        print(f"ℹ Fetched {len(tasks)} tasks with kickoff date set\n")

        # Print task details
        for task in tasks:
            name = task.get("name")
            status = task.get("status", {}).get("status")
            kickoff = self.get_custom_field(task, self.kickoff_field_id)
            go_live = self.get_custom_field(task, self.go_live_field_id)
            print(f"Task: {name} | Status: {status} | Kickoff: {kickoff} | Go Live: {go_live}")

        return tasks

    def update_field(self, task_id, value):
        url = f"{self.BASE_URL}/task/{task_id}/field/{self.aging_field_id}"
        response = requests.post(url, headers=self.headers, json={"value": str(value)})
        if not response.ok:
            print(f"✗ Failed update for {task_id}: {response.status_code}, {response.text}")
        return response.ok

    @staticmethod
    def get_custom_field(task, field_id):
        for field in task.get("custom_fields", []):
            if field["id"] == field_id and field.get("value"):
                if field["type"] == "date":
                    return datetime.fromtimestamp(int(field["value"]) / 1000).date()
                return field["value"]
        return None

    @staticmethod
    def has_required_tag(task, tag):
        return tag in [t["name"].lower() for t in task.get("tags", [])]

# ---------------- MAIN LOGIC ---------------- #

LIVE_STATUSES = {"live", "prod qa", "hypercare"}

def main():
    try:
        config = load_json("config/clickup_config.json")
    except Exception as e:
        print(f"❌ Failed to load ClickUp config: {e}")
        return

    client = ClickUpClient(config)
    tasks = client.get_tasks_with_kickoff()  # Fetch only tasks with kickoff

    updated = skipped = 0
    today = date.today()

    for task in tasks:
        name = task["name"]
        status = task["status"]["status"].lower()

        # Check for required tag
        if not client.has_required_tag(task, client.required_tag):
            print(f"⊘ Skipped: {name} (Missing required tag)")
            skipped += 1
            continue

        kickoff = client.get_custom_field(task, client.kickoff_field_id)
        go_live = client.get_custom_field(task, client.go_live_field_id)

        # Determine end date
        if status in LIVE_STATUSES:
            if not go_live:
                print(f"⚠ {name} is {status} but Go Live not set, using today as end date")
            end_date = go_live if go_live else today
        else:
            end_date = today

        # Calculate aging
        aging_days = client.calculator.calculate(kickoff, end_date)
        aging_value = f"{aging_days}d"

        # Update ClickUp field
        if client.update_field(task["id"], aging_value):
            print(f"✓ {name} [{task['status']['status']}] → Aging: {aging_value}")
            updated += 1
        else:
            skipped += 1

    print("\n" + "=" * 60)
    print(f"Summary: {updated} updated | {skipped} skipped")
    print("=" * 60)

# ---------------- ENTRY POINT ---------------- #

if __name__ == "__main__":
    main()
