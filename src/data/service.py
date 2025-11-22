"""
Service to continuously fetch live Polymarket data for real-time trading.

Fetches current prices for selected markets every N seconds and updates
data_live/ files for consumption by trading engine.
"""

import sys
print(f"SERVICE RUNNING WITH: {sys.executable}")
import csv
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .polymarket_api import fetch_current_price
from src.trading.timer import get_timer_start_time

DATA_LIVE_DIR = Path("data_live")
DATA_LIVE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_LIVE_DIR = Path("logs_live")
TIMER_STATE_FILE = LOGS_LIVE_DIR / "timer_state.json"


@dataclass
class LiveMarketInfo:
    """Market info loaded from metadata CSV."""
    local_id: str
    polymarket_id: str
    slug: str
    question: str
    condition_id: str
    yes_token_id: str
    volume24hr: float


# Cache market info to avoid reloading on every cycle
_market_info_cache: List[LiveMarketInfo] = []
_market_info_cache_mtime: float = 0

def load_market_info() -> List[LiveMarketInfo]:
    """
    Load market info from markets_live_meta.csv if it exists.
    Caches the result and only reloads if the file has changed.
    """
    global _market_info_cache, _market_info_cache_mtime
    
    meta_path = DATA_LIVE_DIR / "markets_live_meta.csv"
    if not meta_path.exists():
        _market_info_cache = []
        return []
    
    # Check if file has changed
    try:
        current_mtime = meta_path.stat().st_mtime
        if current_mtime == _market_info_cache_mtime and _market_info_cache:
            # File hasn't changed, return cached data
            return _market_info_cache
    except OSError:
        # File might have been deleted or is inaccessible
        _market_info_cache = []
        return []
    
    # File changed or cache is empty, reload
    markets = []
    with meta_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            markets.append(
                LiveMarketInfo(
                    local_id=row["market_id"],
                    polymarket_id="",  # Not needed for live updates
                    slug=row.get("slug", ""),
                    question=row.get("name", ""),
                    condition_id=row.get("condition_id", ""),
                    yes_token_id=row.get("yes_token_id", ""),
                    volume24hr=0.0,
                )
            )
    
    # Update cache
    _market_info_cache = markets
    _market_info_cache_mtime = current_mtime
    
    return markets


def append_price_to_csv(local_id: str, price: float, timestamp: datetime) -> None:
    """
    Append a new price point to the CSV file.
    Checks for duplicates to avoid re-adding the same timestamp.
    """
    prices_path = DATA_LIVE_DIR / f"prices_{local_id}.csv"
    
    # If file doesn't exist, create it with header
    if not prices_path.exists():
        with prices_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "price", "bid", "ask", "volume"])
    else:
        # Check if this timestamp already exists (avoid duplicates)
        ts_str = timestamp.isoformat()
        with prices_path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                if row and row[0] == ts_str:
                    # Timestamp already exists, skip
                    return
    
    # Append new row
    with prices_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        ts_str = timestamp.isoformat()
        bid = max(0.0, price - 0.01)
        ask = min(1.0, price + 0.01)
        volume = 1000.0  # synthetic
        writer.writerow([ts_str, f"{price:.6f}", f"{bid:.6f}", f"{ask:.6f}", f"{volume:.0f}"])


def update_market_outcome(local_id: str, current_price: float) -> None:
    """Update the outcome (last price) and timestamp in markets_live_meta.csv."""
    meta_path = DATA_LIVE_DIR / "markets_live_meta.csv"
    if not meta_path.exists():
        return
    
    # Read all rows
    rows = []
    timestamp = datetime.now(timezone.utc).isoformat()
    
    with meta_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if "last_updated" not in fieldnames:
            fieldnames.append("last_updated")
            
        for row in reader:
            if row["market_id"] == local_id:
                row["outcome"] = f"{current_price:.6f}"
                row["last_updated"] = timestamp
            rows.append(row)
    
    # Write back
    with meta_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fetch_and_update_live_data() -> Dict[str, Any]:
    """
    Fetch current prices for all tracked markets and update CSV files.
    Returns status dict with update info.
    """
    markets = load_market_info()
    if not markets:
        return {"status": "no_markets", "updated": 0}
    
    updated_count = 0
    errors = []
    timestamp = datetime.now(timezone.utc)
    
    # Check if competition has started
    timer_start = get_timer_start_time(TIMER_STATE_FILE)
    if timestamp < timer_start:
        return {
            "status": "waiting_for_start",
            "updated": 0,
            "total": len(markets),
            "timestamp": timestamp.isoformat(),
            "errors": [f"Competition starts at {timer_start.isoformat()}"],
        }
    
    for market in markets:
        if not market.yes_token_id:
            continue
        
        try:
            current_price = fetch_current_price(market.yes_token_id)
            if current_price is not None:
                append_price_to_csv(market.local_id, current_price, timestamp)
                update_market_outcome(market.local_id, current_price)
                updated_count += 1
            else:
                errors.append(f"{market.local_id}: Failed to fetch price")
            
            # Sleep to avoid rate limiting
            time.sleep(0.1)
            
        except Exception as e:
            errors.append(f"{market.local_id}: {str(e)}")
    
    return {
        "status": "success" if updated_count > 0 else "partial",
        "updated": updated_count,
        "total": len(markets),
        "timestamp": timestamp.isoformat(),
        "errors": errors,
    }


def run_live_data_service(update_interval: int = 10) -> None:
    """
    Run the live data service continuously.
    Fetches data every update_interval seconds.
    """
    print(f"Starting live data service (update interval: {update_interval}s)")
    print("Press Ctrl+C to stop", flush=True)
    
    try:
        while True:
            # Check for reset signal and clear cache if needed
            reset_signal_path = LOGS_LIVE_DIR / "reset_signal"
            if reset_signal_path.exists():
                print("Reset signal detected. Clearing data service cache.", flush=True)
                global _market_info_cache, _market_info_cache_mtime
                _market_info_cache = []
                _market_info_cache_mtime = 0
                # Note: Price CSV files are deleted by the reset button in dashboard
                # We just need to clear our cache here
            
            try:
                result = fetch_and_update_live_data()
                print(f"[{result['timestamp']}] Updated {result['updated']}/{result['total']} markets", flush=True)
                if result.get("errors"):
                    for error in result["errors"]:
                        print(f"  Error: {error}", flush=True)
            except Exception as e:
                print(f"Error in fetch cycle: {e}", flush=True)
                
            time.sleep(update_interval)
    except KeyboardInterrupt:
        print("\nStopping live data service...", flush=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Live Polymarket data service")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Update interval in seconds (default: 60)",
    )
    args = parser.parse_args()
    
    run_live_data_service(args.interval)
