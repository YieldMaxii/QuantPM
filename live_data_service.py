"""
live_data_service.py

Service to continuously fetch live Polymarket data for real-time trading.

- Fetches current prices for selected markets every N seconds
- Maintains a rolling 24-hour window of price data
- Updates data_live/ files for consumption by trading engine
"""

import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

DATA_LIVE_DIR = Path("data_live")
DATA_LIVE_DIR.mkdir(parents=True, exist_ok=True)

MIN_VOLUME_24H = 10_000.0
MAX_MARKETS = 100


@dataclass
class LiveMarketInfo:
    local_id: str
    polymarket_id: str
    slug: str
    question: str
    condition_id: str
    yes_token_id: str
    volume24hr: float


def fetch_current_price(yes_token_id: str) -> Optional[float]:
    """Fetch current price for a token."""
    try:
        url = f"{CLOB_API_BASE}/price"
        params = {"token_id": yes_token_id}
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                price = data.get("price") or data.get("p")
            elif isinstance(data, (int, float)):
                price = data
            else:
                return None
            
            # Normalize to [0,1] if needed
            if price is not None:
                if price > 1.0:
                    # Might be in cents or other scale
                    if price > 100:
                        price = price / 10000.0
                    elif price > 10:
                        price = price / 1000.0
                    else:
                        price = price / 100.0
                return max(0.0, min(1.0, float(price)))
    except Exception:
        pass
    return None


def fetch_24h_history(yes_token_id: str) -> List[Dict[str, Any]]:
    """Fetch 24h of 1-minute price history."""
    url = f"{CLOB_API_BASE}/prices-history"
    params = {
        "market": yes_token_id,
        "interval": "1d",
        "fidelity": 1,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        history = data.get("history", []) if isinstance(data, dict) else []
        return history or []
    except Exception:
        return []


def load_market_info() -> List[LiveMarketInfo]:
    """Load market info from markets_live_meta.csv if it exists."""
    meta_path = DATA_LIVE_DIR / "markets_live_meta.csv"
    if not meta_path.exists():
        return []
    
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
        except Exception as e:
            errors.append(f"{market.local_id}: {str(e)}")
    
    return {
        "status": "success" if updated_count > 0 else "partial",
        "updated": updated_count,
        "total": len(markets),
        "timestamp": timestamp.isoformat(),
        "errors": errors,
    }


def run_live_data_service(update_interval: int = 60) -> None:
    """
    Run the live data service continuously.
    Fetches data every update_interval seconds.
    """
    print(f"Starting live data service (update interval: {update_interval}s)")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            result = fetch_and_update_live_data()
            print(f"[{result['timestamp']}] Updated {result['updated']}/{result['total']} markets")
            if result.get("errors"):
                for error in result["errors"]:
                    print(f"  Error: {error}")
            time.sleep(update_interval)
    except KeyboardInterrupt:
        print("\nStopping live data service...")


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

