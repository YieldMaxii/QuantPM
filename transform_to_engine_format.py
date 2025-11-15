"""
Transform raw Polymarket JSON data to engine-compatible CSV format.

Reads raw JSON files from data/raw/ and generates:
- data/prices_{market_id}.csv files with columns: timestamp,price,bid,ask,volume
- data/markets_meta.csv with columns: market_id,name,outcome

This script assumes raw data was fetched by fetch_polymarket_data.py.
"""

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


RAW_DATA_DIR = Path("data/raw")
OUTPUT_DIR = Path("data")

# Market configuration (same keys as fetch script)
MARKETS = {
    "M1": "will-the-doomsday-clock-move-closer-to-midnight-in-2024",
    "M2": "will-the-doomsday-clock-move-closer-to-midnight-in-2025",
    "M3": "us-inflation-0pt1-from-june-to-july-2024",
    "M4": "trump-ends-department-of-education-in-first-100-days",
    "M5": "will-the-house-vote-on-a-government-funding-bill",
}

# POC outcomes: based on actual resolution (1=YES won, 0=NO)
MARKET_OUTCOMES: Dict[str, int] = {
    "M1": 0,  # Will the Doomsday Clock move closer to Midnight in 2024? -> NO
    "M2": 1,  # Will the Doomsday Clock move closer to Midnight in 2025? -> YES
    "M3": 1,  # US inflation >0.1% from June to July 2024? -> YES
    "M4": 0,  # Will Trump end Department of Education in first 100 days? -> NO
    "M5": 1,  # Will the House vote on a government funding bill today? (Nov 12, 25) -> YES
}


def parse_end_date(market_data: Dict) -> Optional[datetime]:
    """Parse end date from market metadata."""
    end_date_str = market_data.get("endDateIso") or market_data.get("endDate")
    if not end_date_str:
        return None
    
    try:
        # Try ISO format first
        if "T" in end_date_str:
            return datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        else:
            # Date only
            return datetime.fromisoformat(end_date_str)
    except Exception:
        return None


def determine_price_scale(price_data: Dict) -> float:
    """
    Determine price scaling factor from price data.
    
    Checks if prices are already normalized or need scaling.
    Defaults to 10000.0 (common Polymarket scale).
    """
    history = price_data.get("history", [])
    if not history:
        return 10000.0
    
    # Check a few recent prices
    recent_prices = [h.get("p", 0) for h in history[-10:]]
    if not recent_prices:
        return 10000.0
    
    max_price = max(recent_prices)
    min_price = min(recent_prices)
    
    # If prices are already in [0,1] range, no scaling needed
    if max_price <= 1.0 and min_price >= 0.0:
        return 1.0
    
    # If prices are > 1, they're likely scaled
    # Common scales: 10000, 1000, 100
    if max_price > 100:
        return 10000.0
    elif max_price > 10:
        return 1000.0
    elif max_price > 1:
        return 100.0
    
    return 10000.0


def transform_price_history(
    price_data: Dict,
    market_data: Dict,
    price_scale: float = 10000.0,
    window_days: Optional[int] = None,
) -> List[Dict]:
    """
    Transform price history JSON to engine CSV format.
    
    Args:
        price_data: JSON with "history" array of {t, p} objects
        market_data: Market metadata (for end date filtering)
        price_scale: Scaling factor to convert raw price to [0,1]
        window_days: Optional number of days before resolution to include
    
    Returns:
        List of dicts with keys: timestamp, price, bid, ask, volume
    """
    history = price_data.get("history", [])
    if not history:
        return []
    
    # Determine time window if specified
    end_date = parse_end_date(market_data)
    cutoff_time = None
    if window_days and end_date:
        cutoff_time = end_date - timedelta(days=window_days)
    
    rows = []
    
    for entry in history:
        unix_ts = entry.get("t")
        raw_price = entry.get("p")
        
        if unix_ts is None or raw_price is None:
            continue
        
        # Convert timestamp
        try:
            dt = datetime.utcfromtimestamp(unix_ts)
            timestamp_str = dt.isoformat()
        except (ValueError, OSError):
            continue
        
        # Apply time window filter
        if cutoff_time and dt < cutoff_time:
            continue
        
        # Scale price to [0,1]
        price = raw_price / price_scale
        price = max(0.0, min(1.0, price))  # Clamp to [0,1]
        
        # Synthetic bid/ask (0.01 spread)
        bid = max(0.0, price - 0.01)
        ask = min(1.0, price + 0.01)
        
        # Synthetic volume
        volume = 1000.0
        
        rows.append({
            "timestamp": timestamp_str,
            "price": price,
            "bid": bid,
            "ask": ask,
            "volume": volume,
        })
    
    # Sort by timestamp
    rows.sort(key=lambda r: r["timestamp"])
    
    return rows


def write_price_csv(market_id: str, rows: List[Dict]) -> None:
    """Write price data to CSV file."""
    output_path = OUTPUT_DIR / f"prices_{market_id}.csv"
    
    fieldnames = ["timestamp", "price", "bid", "ask", "volume"]
    
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "timestamp": row["timestamp"],
                "price": f"{row['price']:.6f}",
                "bid": f"{row['bid']:.6f}",
                "ask": f"{row['ask']:.6f}",
                "volume": f"{row['volume']:.0f}",
            })
    
    print(f"  Wrote {len(rows)} rows to {output_path}")


def transform_market(market_id: str, window_days: Optional[int] = None) -> None:
    """Transform a single market's data."""
    market_file = RAW_DATA_DIR / f"{market_id}_market.json"
    price_file = RAW_DATA_DIR / f"{market_id}_prices.json"
    
    if not market_file.exists():
        raise FileNotFoundError(f"Market file not found: {market_file}")
    if not price_file.exists():
        raise FileNotFoundError(f"Price file not found: {price_file}")
    
    # Load JSON files
    with market_file.open("r", encoding="utf-8") as f:
        market_data = json.load(f)
    
    with price_file.open("r", encoding="utf-8") as f:
        price_data = json.load(f)
    
    # For this POC, Polymarket CLOB prices are already in [0,1], so no scaling
    price_scale = 1.0
    
    # Transform price history
    rows = transform_price_history(
        price_data, market_data, price_scale=price_scale, window_days=window_days
    )
    
    if not rows:
        print(f"  Warning: No price data for {market_id} - creating empty CSV with headers")
        # Create empty file with headers so engine can at least see the file exists
        output_path = OUTPUT_DIR / f"prices_{market_id}.csv"
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "price", "bid", "ask", "volume"])
            writer.writeheader()
        print(f"  Created empty CSV: {output_path}")
        return
    
    # Validate price range
    prices = [r["price"] for r in rows]
    min_price = min(prices)
    max_price = max(prices)
    
    if min_price < 0.0 or max_price > 1.0:
        print(f"  Warning: Prices outside [0,1] range for {market_id}: [{min_price:.4f}, {max_price:.4f}]")
    
    # Write CSV
    write_price_csv(market_id, rows)
    
    print(f"  Price range: [{min_price:.4f}, {max_price:.4f}]")
    print(f"  Time range: {rows[0]['timestamp']} to {rows[-1]['timestamp']}")


def write_markets_meta_csv() -> None:
    """
    Build markets_meta.csv for the engine.

    Relies on:
    - RAW_DATA_DIR/{market_id}_market.json for question/name.
    - MARKET_OUTCOMES for outcome labels (0/1).
    """
    output_path = OUTPUT_DIR / "markets_meta.csv"
    fieldnames = ["market_id", "name", "outcome"]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for market_id in MARKETS.keys():
            market_file = RAW_DATA_DIR / f"{market_id}_market.json"
            if not market_file.exists():
                raise FileNotFoundError(
                    f"Cannot write markets_meta.csv: missing {market_file}"
                )

            with market_file.open("r", encoding="utf-8") as mf:
                market_data = json.load(mf)

            question = (
                market_data.get("question")
                or market_data.get("title")
                or market_id
            )

            if market_id not in MARKET_OUTCOMES:
                raise KeyError(
                    f"MARKET_OUTCOMES missing outcome for {market_id}. "
                    f"Fill MARKET_OUTCOMES with 0/1 for all markets."
                )

            outcome = MARKET_OUTCOMES[market_id]

            writer.writerow(
                {
                    "market_id": market_id,
                    "name": question,
                    "outcome": int(outcome),
                }
            )

    print(f"markets_meta.csv written to {output_path}")


def main():
    """Transform all markets."""
    print("Transforming Polymarket data to engine format...")
    print(f"Reading from: {RAW_DATA_DIR}")
    print(f"Writing to: {OUTPUT_DIR}\n")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Optional: filter to 14 days before resolution
    # Set window_days=None to include full history
    window_days = None  # Change to 14 if you want to filter
    
    for market_id in MARKETS.keys():
        try:
            print(f"Transforming {market_id}...")
            transform_market(market_id, window_days=window_days)
            print(f"✓ {market_id} completed\n")
        except Exception as e:
            print(f"✗ {market_id} failed: {e}\n")
            raise
    
    # Now build markets_meta.csv
    write_markets_meta_csv()

    print("All markets transformed successfully!")
    print(f"\nPrice CSVs and markets_meta.csv written to: {OUTPUT_DIR}")
    print(
        "Next step: Run engine.py with:\n"
        "  python engine.py --meta data/markets_meta.csv --prices-dir data --out-dir outputs"
    )


if __name__ == "__main__":
    main()

