"""
fetch_polymarket_live_24h.py

Fetch 24-hour 1-minute Polymarket prices for 5 live, high-volume markets.

- Uses Gamma /markets to discover live markets.
- Filters to:
  * closed == False
  * enableOrderBook != False
  * volume24hr >= MIN_VOLUME_24H
  * binary YES/NO markets (we can extract YES token)
- For each selected market:
  * Calls clob.prices-history with interval=1d, fidelity=1
    => ~1-minute bars over last 24h
  * Writes data_live/prices_L{i}.csv
  * Writes data_live/markets_live_meta.csv with:
      market_id, name, outcome, slug, condition_id, yes_token_id

For this 24h experiment:
- "outcome" is defined as the last observed price in the 24h window
  (mark-to-market), not the actual 0/1 resolution of the event.
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

DATA_LIVE_DIR = Path("data_live")
DATA_LIVE_DIR.mkdir(parents=True, exist_ok=True)

MIN_VOLUME_24H = 10_000.0   # adjust if you want more/less liquid markets
MAX_MARKETS = 100  # Increased to support all outcomes of multi-outcome markets

TARGET_EVENTS = [
    "fed-decision-in-december",
    "super-bowl-champion-2026-731",
    "chile-presidential-election"
]

@dataclass
class LiveMarket:
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


def parse_outcomes(m: Dict[str, Any]) -> Optional[List[str]]:
    raw = m.get("shortOutcomes") or m.get("outcomes")
    if not raw:
        return None

    if isinstance(raw, list):
        return [str(x) for x in raw]

    if isinstance(raw, str):
        # Try JSON first
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except json.JSONDecodeError:
            pass
        # Fallback comma-separated
        return [s.strip() for s in raw.split(",") if s.strip()]

    return None


def extract_yes_token_id(m: Dict[str, Any]) -> Optional[str]:
    outcomes = parse_outcomes(m)
    if not outcomes:
        return None

    yes_index = None
    for i, o in enumerate(outcomes):
        if isinstance(o, str) and o.lower() == "yes":
            yes_index = i
            break
    if yes_index is None:
        return None

    clob_token_ids = m.get("clobTokenIds")
    if not clob_token_ids:
        return None

    if isinstance(clob_token_ids, list):
        token_ids = clob_token_ids
    elif isinstance(clob_token_ids, str):
        try:
            parsed = json.loads(clob_token_ids)
            if isinstance(parsed, list):
                token_ids = parsed
            else:
                token_ids = [s.strip() for s in clob_token_ids.split(",") if s.strip()]
        except json.JSONDecodeError:
            token_ids = [s.strip() for s in clob_token_ids.split(",") if s.strip()]
    else:
        return None

    token_ids = [str(t).strip('"\'') for t in token_ids]
    if yes_index >= len(token_ids):
        return None
    return token_ids[yes_index]


def select_target_markets() -> List[LiveMarket]:
    """
    Select all valid markets from the TARGET_EVENTS list.
    """
    candidates: List[LiveMarket] = []
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
                # Skip if not active/open (optional: strict check)
                # Some markets in an event might be closed, but we want to see if we can trade them.
                # For now, filter only if completely invalid.
                
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

    # Sort optionally? Or keep event order?
    # Keeping event order is nice for grouping.
    
    selected = candidates[:MAX_MARKETS]

    # Assign local ids L1..LN
    for i, mk in enumerate(selected):
        mk.local_id = f"L{i+1}"

    return selected


def fetch_24h_1min_history(yes_token_id: str) -> List[Dict[str, Any]]:
    """
    Use clob.prices-history to fetch ~24h of 1-minute bars.
    interval=1d, fidelity=1 => recent one-day window.
    """
    url = f"{CLOB_API_BASE}/prices-history"
    params = {
        "market": yes_token_id,
        "interval": "1d",
        "fidelity": 1,
    }
    try:
        resp = requests.get(url, params=params, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
        history = data.get("history", []) if isinstance(data, dict) else []
        return history or []
    except Exception as e:
        print(f"Error fetching history for {yes_token_id}: {e}")
        return []


def write_prices_csv(local_id: str, history: List[Dict[str, Any]]) -> float:
    """
    Write data_live/prices_<local_id>.csv from history entries.

    Returns:
        last_price (float) to be used as "outcome" for this 24h window.
    """
    if not history:
        raise ValueError(f"No history returned for {local_id}")

    out_path = DATA_LIVE_DIR / f"prices_{local_id}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "price", "bid", "ask", "volume"])

        last_price = None
        for h in history:
            t = h.get("t")
            p = h.get("p")
            if t is None or p is None:
                continue
            ts = datetime.fromtimestamp(int(t), tz=timezone.utc).isoformat()
            price = float(p)  # clob prices are already in [0,1]
            bid = max(0.0, price - 0.01)
            ask = min(1.0, price + 0.01)
            volume = 1000.0  # synthetic; your engine only needs price

            writer.writerow([ts, f"{price:.6f}", f"{bid:.6f}", f"{ask:.6f}", f"{volume:.0f}"])
            last_price = price

    if last_price is None:
        raise ValueError(f"Could not determine last price for {local_id}")
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
        history = fetch_24h_1min_history(mk.yes_token_id)
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

