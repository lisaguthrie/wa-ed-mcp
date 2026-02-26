import os
import requests
from urllib.parse import quote
import json


CONFIG_FILE_NAME = "wa-ed-config.json"

def load_config() -> dict:
    config_file = os.path.join(os.path.dirname(__file__), CONFIG_FILE_NAME)
    with open(config_file) as f:
        return json.load(f)

def get_school_year(year: int) -> str:
    """Convert a year to a school year string."""
    return f"{year-1}-{str(year)[-2:]}"

def get_school_year_from_string(year_str: str) -> int:
    """Convert a school year string to a year."""
    return int(year_str.split("-")[1]) + 2000

def get_grade_as_string(grade: int, all_values_for_k: bool = True) -> str:
    """Convert a grade number to a string."""
    if grade == 0:
        if all_values_for_k:
            return "'Kindergarten', 'Half-day Kindergarten', 'Half-Day Kindergarten'"
        else:
            return "'Kindergarten'"
    elif grade == 1:
        return f"'{grade}st Grade'"
    elif grade == 2:
        return f"'{grade}nd Grade'"
    elif grade == 3:
        return f"'{grade}rd Grade'"
    elif grade in [4, 5, 6, 7, 8, 9, 10, 11, 12]:
        return f"'{grade}th Grade'"
    else:
        return []

def execute_query(url: str, query_string: str) -> dict:
    query = f"{url}?app_token={os.getenv('DATA_PORTAL_APP_TOKEN')}&query={quote(query_string)}"
    response = requests.get(query, timeout=10)
    try:
        response.raise_for_status() 
    except requests.exceptions.HTTPError as e:
        return {"error": str(e), "url": query, "query": query_string, "status_code": response.status_code}
    except requests.exceptions.RequestException as e:
        return {"error": str(e), "url": query, "query": query_string}

    return response.json()