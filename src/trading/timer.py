import json
from pathlib import Path
from datetime import datetime

def get_timer_start_time(timer_state_file: Path) -> datetime:
    """
    Get the start time of the competition from the timer state file.
    If file doesn't exist or is invalid, returns current time as fallback (or raises).
    """
    if not timer_state_file.exists():
        # Fallback: if no timer file, assume start is NOW (or raise error)
        # For robustness, let's return a default or raise. 
        # Given this is a competition, we likely want to know if it's missing.
        raise FileNotFoundError(f"Timer state file not found at {timer_state_file}")
        
    with open(timer_state_file, "r") as f:
        data = json.load(f)
        start_time_str = data.get("start_time")
        if not start_time_str:
             raise ValueError("No start_time in timer state file")
             
        return datetime.fromisoformat(start_time_str)

