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

from .polymarket_api import GAMMA_API_BASE, extract_yes_token_id, fetch_24h_history
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


def write_prices_csv(local_id: str, history: List[Dict[str, Any]]) -> float:
    """
    Write data_live/prices_<local_id>.csv from history entries.
    Filters out data from before the competition start time.

    Returns:
        last_price (float) to be used as "outcome" for this 24h window.
    """
    if not history:
        raise ValueError(f"No history returned for {local_id}")

    # Get timer start time to filter garbage data
    timer_start = get_timer_start_time(TIMER_STATE_FILE)

    out_path = DATA_LIVE_DIR / f"prices_{local_id}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "price", "bid", "ask", "volume"])

        last_price = None
        valid_points = 0
        
        for h in history:
            t = h.get("t")
            p = h.get("p")
            if t is None or p is None:
                continue
            
            ts_dt = datetime.fromtimestamp(int(t), tz=timezone.utc)
            
            # Filter out data from before competition start
            if ts_dt < timer_start:
                continue
                
            ts = ts_dt.isoformat()
            price = float(p)  # clob prices are already in [0,1]
            bid = max(0.0, price - 0.01)
            ask = min(1.0, price + 0.01)
            volume = 1000.0  # synthetic; your engine only needs price

            writer.writerow([ts, f"{price:.6f}", f"{bid:.6f}", f"{ask:.6f}", f"{volume:.0f}"])
            last_price = price
            valid_points += 1

    if last_price is None:
        # If no data after start time, use the last available price from history as a fallback
        # but don't write it as a historical point
        if history:
            last_h = history[-1]
            if last_h.get("p") is not None:
                return float(last_h["p"])
        raise ValueError(f"Could not determine last price for {local_id} (no valid data after start time)")
    
    return last_price


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
            last_price = outcomes[mk.local_id]
            # Here we interpret "outcome" as the terminal 24h price (mark-to-market).
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

    for mk in live_markets:
        print(f"\nFetching 24h 1-minute prices for {mk.local_id} ({mk.slug})...")
        history = fetch_24h_history(mk.yes_token_id)
        print(f"  Received {len(history)} history points")
        
        if not history:
            print(f"  WARNING: No history for {mk.local_id}. Skipping.")
            continue

        try:
            last_price = write_prices_csv(mk.local_id, history)
            print(f"  Last price in window: {last_price:.4f}")
            outcomes[mk.local_id] = last_price
            final_markets.append(mk)
        except Exception as e:
            print(f"  Error writing prices for {mk.local_id}: {e}")
            continue

    write_markets_meta(final_markets, outcomes)
    print("\nDone.")
    print(f"  - Markets meta: {DATA_LIVE_DIR/'markets_live_meta.csv'}")
    print(f"  - Prices files: {DATA_LIVE_DIR}/prices_L*.csv")


if __name__ == "__main__":
    main()

