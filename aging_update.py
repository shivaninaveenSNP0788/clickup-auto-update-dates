import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
import os

class WorkingDaysCalculator:
    def __init__(self, holidays_file='config/holidays.json'):
        """Initialize calculator with holidays from JSON file."""
        self.holidays = self._load_holidays(holidays_file)
    
    def _load_holidays(self, filepath):
        """Load holidays from JSON file."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                holidays = [datetime.strptime(date, '%Y-%m-%d').date() 
                           for date in data.get('holidays', [])]
                return set(holidays)
        except FileNotFoundError:
            print(f"Warning: {filepath} not found. Using empty holidays list.")
            return set()
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in {filepath}. Using empty holidays list.")
            return set()
    
    def is_working_day(self, date):
        """Check if a date is a working day (not weekend or holiday)."""
        if date.weekday() >= 5:  # Weekend
            return False
        if date in self.holidays:  # Holiday
            return False
        return True
    
    def calculate_working_days(self, start_date, end_date=None):
        """Calculate number of working days between two dates."""
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        if end_date is None:
            end_date = datetime.now()
        elif isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()
        
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        
        working_days = 0
        current_date = start_date
        
        while current_date < end_date:
            if self.is_working_day(current_date):
                working_days += 1
            current_date += timedelta(days=1)
        
        return working_days


class ClickUpIntegration:
    def __init__(self, api_token, workspace_id=None):
        """Initialize ClickUp API integration."""
        self.api_token = api_token
        self.workspace_id = workspace_id
        self.base_url = "https://api.clickup.com/api/v2"
        self.headers = {
            "Authorization": api_token,
            "Content-Type": "application/json"
        }
        self.calculator = WorkingDaysCalculator('config/holidays.json')
    
    def get_tasks(self, list_id, custom_fields=None):
        """Get tasks from a ClickUp list."""
        url = f"{self.base_url}/list/{list_id}/task"
        params = {
            "include_closed": "true",
            "subtasks": "true"
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json().get('tasks', [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching tasks: {e}")
            return []
    
    def get_task(self, task_id):
        """Get a single task by ID."""
        url = f"{self.base_url}/task/{task_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching task {task_id}: {e}")
            return None
    
    def update_custom_field(self, task_id, field_id, value):
        """Update a custom field value for a task."""
        url = f"{self.base_url}/task/{task_id}/field/{field_id}"
        
        payload = {
            "value": value
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error updating field for task {task_id}: {e}")
            return False
    
    def get_custom_field_value(self, task, field_name):
        """Extract custom field value by field name."""
        custom_fields = task.get('custom_fields', [])
        for field in custom_fields:
            if field.get('name', '').lower() == field_name.lower():
                value = field.get('value')
                if value:
                    # Handle date fields (timestamp in milliseconds)
                    if field.get('type') == 'date':
                        return datetime.fromtimestamp(int(value) / 1000)
                    return value
        return None
    
    def get_custom_field_id(self, task, field_name):
        """Get custom field ID by field name."""
        custom_fields = task.get('custom_fields', [])
        for field in custom_fields:
            if field.get('name', '').lower() == field_name.lower():
                return field.get('id')
        return None
    
    def get_custom_field_value_by_id(self, task, field_id):
        """Extract custom field value by field ID."""
        custom_fields = task.get('custom_fields', [])
        for field in custom_fields:
            if field.get('id') == field_id:
                value = field.get('value')
                if value:
                    # Handle date fields (timestamp in milliseconds)
                    if field.get('type') == 'date':
                        return datetime.fromtimestamp(int(value) / 1000)
                    return value
        return None
    
    def calculate_and_update_aging(self, list_id, 
                                   kickoff_field_id,
                                   aging_field_id):
        """
        Calculate aging from Actual Kickoff Date and update the aging field.
        
        Args:
            list_id: ClickUp list ID
            kickoff_field_id: ID of the custom field containing kickoff date
            aging_field_id: ID of the custom field to store aging value
        """
        print(f"Fetching tasks from list {list_id}...")
        tasks = self.get_tasks(list_id)
        
        updated_count = 0
        skipped_count = 0
        
        for task in tasks:
            task_id = task.get('id')
            task_name = task.get('name')
            
            # Get Actual Kickoff Date using field ID
            kickoff_date = self.get_custom_field_value_by_id(task, kickoff_field_id)
            
            if not kickoff_date:
                print(f"⊘ Skipped: {task_name} (No kickoff date in field {kickoff_field_id})")
                skipped_count += 1
                continue
            
            # Calculate working days
            closed_date = None
            if task.get('status', {}).get('status', '').lower() in ['closed', 'complete', 'done']:
                closed_date = task.get('date_closed')
                if closed_date:
                    closed_date = datetime.fromtimestamp(int(closed_date) / 1000)
            
            working_days = self.calculator.calculate_working_days(kickoff_date, closed_date)
            
            # Update the custom field
            if self.update_custom_field(task_id, aging_field_id, working_days):
                status = "Closed" if closed_date else "Open"
                print(f"✓ Updated: {task_name} ({status}) - {working_days} working days")
                updated_count += 1
            else:
                print(f"✗ Failed: {task_name}")
                skipped_count += 1
        
        print("\n" + "="*60)
        print(f"Summary: {updated_count} updated, {skipped_count} skipped")
        print("="*60)


if __name__ == "__main__":
    run()
