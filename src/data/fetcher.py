"""
Fetch 24-hour 1-minute Polymarket prices for live markets.

Uses Gamma /markets to discover live markets from target events.
For each selected market, fetches 24h of 1-minute price data and writes
to data_live/ directory.
"""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import urllib3

from .polymarket_api import GAMMA_API_BASE, extract_yes_token_id, fetch_current_price
from src.trading.timer import get_timer_start_time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_LIVE_DIR = Path("data_live")
DATA_LIVE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_LIVE_DIR = Path("logs_live")
TIMER_STATE_FILE = LOGS_LIVE_DIR / "timer_state.json"

MIN_VOLUME_24H = 10_000.0
MAX_MARKETS = 100

TARGET_EVENTS = [
    "fed-decision-in-december",
    "super-bowl-champion-2026-731",
    "chile-presidential-election"
]


@dataclass
class LiveMarket:
    """Represents a live market from Polymarket."""
    local_id: str         # "L1", "L2", ...
    polymarket_id: str    # Gamma "id"
    slug: str
    event_slug: str       # Event grouping
    question: str
    condition_id: str
    yes_token_id: str
    volume24hr: float


def fetch_event_data(slug: str) -> Optional[Dict[str, Any]]:
    """Fetch full event data including all markets."""
    url = f"{GAMMA_API_BASE}/events"
    params = {"slug": slug}
    try:
        resp = requests.get(url, params=params, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]  # Gamma returns list of events
        if isinstance(data, dict):
            return data
        return None
    except Exception as e:
        print(f"Error fetching event {slug}: {e}")
        return None


def select_target_markets() -> List[LiveMarket]:
    """Select all valid markets from the TARGET_EVENTS list."""
    candidates: List[LiveMarket] = []

    for slug in TARGET_EVENTS:
        print(f"Fetching event: {slug}")
        event_data = fetch_event_data(slug)
        if not event_data:
            print(f"  No data found for {slug}")
            continue
        
        markets = event_data.get("markets", [])
        if not markets:
            print(f"  No markets found in event {slug}")
            continue
            
        print(f"  Found {len(markets)} markets in event")
        
        for m in markets:
            try:
                yes_token_id = extract_yes_token_id(m)
                if not yes_token_id:
                    continue

                condition_id = m.get("conditionId")
                if not condition_id:
                    continue
                
                vol24 = m.get("volume24hr") or 0.0
                try:
                    vol24 = float(vol24)
                except (TypeError, ValueError):
                    vol24 = 0.0

                candidates.append(
                    LiveMarket(
                        local_id="",  # fill later
                        polymarket_id=str(m.get("id")),
                        slug=str(m.get("slug") or ""),
                        event_slug=slug,  # Store the event slug for grouping
                        question=str(m.get("question") or m.get("groupItemTitle") or ""),
                        condition_id=str(condition_id),
                        yes_token_id=yes_token_id,
                        volume24hr=vol24,
                    )
                )
            except Exception as e:
                print(f"  Error processing market: {e}")
                continue

    selected = candidates[:MAX_MARKETS]

    # Assign local ids L1..LN
    for i, mk in enumerate(selected):
        mk.local_id = f"L{i+1}"

    return selected


def initialize_price_csv(local_id: str) -> None:
    """
    Initialize an empty price CSV file with only the header.
    This ensures strategies start fresh from the competition start time.
    """
    out_path = DATA_LIVE_DIR / f"prices_{local_id}.csv"
    # Only overwrite if it doesn't exist or we want to force reset (assumed fresh start)
    # Just truncate it to be safe for a fresh start
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "price", "bid", "ask", "volume"])


def write_markets_meta(live_markets: List[LiveMarket], outcomes: Dict[str, float]) -> None:
    """
    Write data_live/markets_live_meta.csv with:
    market_id,name,outcome,slug,event_slug,condition_id,yes_token_id,last_updated
    """
    out_path = DATA_LIVE_DIR / "markets_live_meta.csv"
    now_ts = datetime.now(timezone.utc).isoformat()
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["market_id", "name", "outcome", "slug", "event_slug", "condition_id", "yes_token_id", "last_updated"])
        for mk in live_markets:
            # outcome here is just the reference price at start
            last_price = outcomes.get(mk.local_id, 0.5) 
            writer.writerow(
                [
                    mk.local_id,
                    mk.question,
                    f"{last_price:.6f}",
                    mk.slug,
                    mk.event_slug,
                    mk.condition_id,
                    mk.yes_token_id,
                    now_ts,
                ]
            )


def main() -> None:
    """Main entry point for fetching initial market data."""
    print("Selecting target live Polymarket markets...")
    live_markets = select_target_markets()
    if not live_markets:
        raise SystemExit("No suitable live markets found.")

    print(f"Selected {len(live_markets)} markets:")
    for mk in live_markets:
        print(f"  {mk.local_id} | {mk.slug} | 24h volume ≈ {mk.volume24hr:.2f}")

    final_markets = []
    outcomes: Dict[str, float] = {}

    print("\nInitializing market files (fetching current price for metadata only)...")
    
    for mk in live_markets:
        # 1. Initialize empty price file
        initialize_price_csv(mk.local_id)
        
        # 2. Fetch current price for metadata "outcome" reference
        # We try to get a starting price so the dashboard isn't totally blank on outcomes
        try:
            current_price = fetch_current_price(mk.yes_token_id)
            if current_price is None:
                current_price = 0.5
            
            outcomes[mk.local_id] = current_price
            final_markets.append(mk)
            print(f"  Initialized {mk.local_id} (Start Price: {current_price:.4f})")
            
        except Exception as e:
            print(f"  Error initializing {mk.local_id}: {e}")
            continue

    write_markets_meta(final_markets, outcomes)
    print("\nDone.")
    print(f"  - Markets meta: {DATA_LIVE_DIR/'markets_live_meta.csv'}")
    print(f"  - Prices files: {DATA_LIVE_DIR}/prices_L*.csv (Initialized empty)")


if __name__ == "__main__":
    main()
