"""
Fetch market data for POC markets.

Current implementation: Polymarket via Gamma + CLOB APIs.
Design is extensible to other sources later (e.g., alternative venue APIs,
synthetic data) by adding new fetch_*_market_data functions and updating
MARKETS config.

Outputs (per market_id) into data/raw/:
- {market_id}_market.json : market metadata
- {market_id}_prices.json : price history JSON
"""

import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------
# Market configuration: POC ID -> Polymarket slug
# --------------------------------------------------------------------

MARKETS = {
    "M1": "will-the-doomsday-clock-move-closer-to-midnight-in-2024",
    "M2": "will-the-doomsday-clock-move-closer-to-midnight-in-2025",
    "M3": "us-inflation-0pt1-from-june-to-july-2024",
    "M4": "trump-ends-department-of-education-in-first-100-days",
    "M5": "will-the-house-vote-on-a-government-funding-bill",
}

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"
RAW_DATA_DIR = Path("data/raw")


# --------------------------------------------------------------------
# Polymarket-specific helpers
# --------------------------------------------------------------------

def fetch_market_metadata_polymarket(slug: str) -> Dict:
    """Fetch market metadata from Polymarket Gamma API."""
    url = f"{GAMMA_API_BASE}/markets/slug/{slug}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def extract_yes_token_id(market_data: Dict) -> Optional[str]:
    """
    Extract the YES token ID from market metadata.
    We assume the outcomes list contains "Yes" (or "yes"), or something equivalent.
    For more complex markets (">0.3%", "<=0.3%"), you may need a custom mapping.
    """
    if not market_data:
        return None

    outcomes = None

    # Try shortOutcomes first
    if "shortOutcomes" in market_data:
        short_outcomes = market_data["shortOutcomes"]
        if isinstance(short_outcomes, str):
            try:
                outcomes = json.loads(short_outcomes)
            except (json.JSONDecodeError, TypeError):
                outcomes = [s.strip() for s in short_outcomes.split(",")]
        else:
            outcomes = short_outcomes

    # Fallback to outcomes
    if outcomes is None and "outcomes" in market_data:
        outcomes_raw = market_data["outcomes"]
        if isinstance(outcomes_raw, str):
            try:
                outcomes = json.loads(outcomes_raw)
            except (json.JSONDecodeError, TypeError):
                outcomes = [s.strip() for s in outcomes_raw.split(",")]
        else:
            outcomes = outcomes_raw

    # Fallback to tokens array
    if not outcomes and "tokens" in market_data:
        tokens = market_data["tokens"]
        if isinstance(tokens, list):
            outcomes = [t.get("outcome", "") for t in tokens if isinstance(t, dict)]

    if not outcomes:
        return None

    # Find YES index
    yes_index = None
    try:
        yes_index = outcomes.index("Yes")
    except ValueError:
        for i, o in enumerate(outcomes):
            if isinstance(o, str) and o.lower() == "yes":
                yes_index = i
                break

    if yes_index is None:
        # For non-Yes/No markets, you may want to define a manual mapping
        return None

    # Extract clobTokenIds
    clob_token_ids = market_data.get("clobTokenIds")

    if not clob_token_ids and "tokens" in market_data:
        tokens = market_data["tokens"]
        if isinstance(tokens, list):
            token_ids = []
            for token in tokens:
                if isinstance(token, dict):
                    tid = token.get("tokenId") or token.get("id") or token.get("clobTokenId")
                    if tid:
                        token_ids.append(tid)
            if token_ids:
                clob_token_ids = token_ids

    if not clob_token_ids:
        return None

    # Normalize token IDs to a list
    if isinstance(clob_token_ids, list):
        token_ids = clob_token_ids
    elif isinstance(clob_token_ids, str):
        try:
            token_ids = json.loads(clob_token_ids)
        except json.JSONDecodeError:
            token_ids = [t.strip() for t in clob_token_ids.split(",")]
    else:
        return None

    token_ids = [str(tid).strip('"\'') for tid in token_ids]

    if yes_index < len(token_ids):
        return token_ids[yes_index]

    return None


def fetch_price_history_polymarket(token_id: str, fidelity: int = 60) -> Dict:
    """
    Fetch full price history for a token from Polymarket CLOB API.

    Args:
        token_id: CLOB token ID (YES token)
        fidelity: Resolution in minutes (default 60 = hourly)
                  Will try daily (1440) as fallback if hourly returns empty

    Returns:
        JSON response with "history" array. If empty, it's a hard data error for the POC.
    """
    url = f"{CLOB_API_BASE}/prices-history"

    # Try different fidelity values if the first one fails
    fidelity_options = [fidelity, 1440, 240, 60] if fidelity != 1440 else [1440, 240, 60]
    
    for fid in fidelity_options:
        # First attempt: market=<token_id>
        params = {
            "market": token_id,
            "interval": "max",
            "fidelity": fid,
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        history = data.get("history", [])
        if history:
            if fid != fidelity:
                print(f"    Note: Using {fid}-minute resolution (daily) instead of {fidelity}-minute")
            return data

        # Fallback: token_id param (shape changed in some deployments)
        params2 = {
            "token_id": token_id,
            "interval": "max",
            "fidelity": fid,
        }
        response2 = requests.get(url, params=params2)
        if response2.status_code == 200:
            data2 = response2.json()
            if data2.get("history"):
                if fid != fidelity:
                    print(f"    Note: Using {fid}-minute resolution (daily) instead of {fidelity}-minute")
                return data2

    # If still empty, return the original data (history==[])
    return data


def determine_price_scale_polymarket(token_id: str) -> float:
    """
    Determine the price scaling factor by checking current price.

    Returns:
        Scaling factor (divide raw price by this to get [0,1] probability).
    """
    try:
        url = f"{CLOB_API_BASE}/price"
        params = {"token_id": token_id, "side": "BUY"}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            raw_price = None
            if isinstance(data, dict):
                raw_price = data.get("price") or data.get("p")
            elif isinstance(data, (int, float)):
                raw_price = data

            if raw_price is not None:
                if raw_price <= 1.0:
                    return 1.0
                if raw_price > 100:
                    return 10000.0
                if raw_price > 10:
                    return 1000.0
                if raw_price > 1:
                    return 100.0
    except Exception:
        pass

    # Default: Polymarket commonly uses 10000 scale
    return 10000.0


# --------------------------------------------------------------------
# Raw data persistence
# --------------------------------------------------------------------

def save_raw_data(market_id: str, market_data: Dict, price_data: Dict, price_scale: float) -> None:
    """Save raw JSON responses (plus simple metadata) to data/raw/."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Attach scale into price_data for debugging / future use
    price_data = dict(price_data)
    price_data["_meta"] = {"price_scale": price_scale}

    market_file = RAW_DATA_DIR / f"{market_id}_market.json"
    price_file = RAW_DATA_DIR / f"{market_id}_prices.json"

    with market_file.open("w", encoding="utf-8") as f:
        json.dump(market_data, f, indent=2)

    with price_file.open("w", encoding="utf-8") as f:
        json.dump(price_data, f, indent=2)

    print(f"Saved raw data for {market_id}")


def load_raw_data(market_id: str) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Load previously saved raw JSON responses, if they exist."""
    market_file = RAW_DATA_DIR / f"{market_id}_market.json"
    price_file = RAW_DATA_DIR / f"{market_id}_prices.json"

    market_data = None
    price_data = None

    if market_file.exists():
        with market_file.open("r", encoding="utf-8") as f:
            market_data = json.load(f)

    if price_file.exists():
        with price_file.open("r", encoding="utf-8") as f:
            price_data = json.load(f)

    return market_data, price_data


# --------------------------------------------------------------------
# Polymarket fetch workflow
# --------------------------------------------------------------------

def fetch_polymarket_market_data(
    market_id: str,
    slug: str,
    force_refresh: bool = False,
) -> Tuple[Dict, Dict, str, float]:
    """
    Fetch all Polymarket data for a single market.

    Returns:
        (market_data, price_data, yes_token_id, price_scale)
    """
    # Try cached data first
    if not force_refresh:
        market_data, price_data = load_raw_data(market_id)
        if market_data and price_data:
            history = price_data.get("history", [])
            if history:
                print(f"Using cached Polymarket data for {market_id} ({len(history)} price points)")
                yes_token_id = extract_yes_token_id(market_data)
                price_scale = price_data.get("_meta", {}).get("price_scale")
                if price_scale is None and yes_token_id:
                    price_scale = determine_price_scale_polymarket(yes_token_id)
                if price_scale is None:
                    price_scale = 10000.0
                return market_data, price_data, yes_token_id, price_scale
            else:
                print(f"  Warning: cached data for {market_id} has no price history, refetching...")

    # Fresh fetch
    print(f"Fetching Polymarket metadata for {market_id} (slug: {slug})...")
    market_data = fetch_market_metadata_polymarket(slug)

    yes_token_id = extract_yes_token_id(market_data)
    if not yes_token_id:
        raise ValueError(f"Could not extract YES token ID for {market_id} (slug: {slug})")

    print(f"  YES token ID: {yes_token_id}")
    print(f"  Question: {market_data.get('question', 'N/A')}")
    print(f"  End date: {market_data.get('endDateIso', 'N/A')}")

    price_scale = determine_price_scale_polymarket(yes_token_id)
    print(f"  Price scale: {price_scale}")

    print(f"Fetching Polymarket price history for {market_id}...")
    price_data = fetch_price_history_polymarket(yes_token_id, fidelity=60)

    history = price_data.get("history", [])
    print(f"  Found {len(history)} price points")

    if len(history) == 0:
        raise ValueError(
            f"No price history for {market_id} (token: {yes_token_id[:20]}...). "
            f"This market is likely older than Polymarket's retention window or unsupported."
        )

    save_raw_data(market_id, market_data, price_data, price_scale)

    return market_data, price_data, yes_token_id, price_scale


# --------------------------------------------------------------------
# Placeholder for alternative sources (extend later)
# --------------------------------------------------------------------

def fetch_alternative_market_data(
    market_id: str,
    config: Dict,
) -> Tuple[Dict, Dict, str, float]:
    """
    Stub for fetching from alternative data sources (other venues, synthetic, etc.).

    Right now this just raises; if you want to plug another API, implement:
    - Fetch metadata -> market_data
    - Fetch price history -> price_data with "history" [{t, p}, ...]
    - Decide on a yes_token_id surrogate (e.g., 'YES') and a price_scale
    """
    raise NotImplementedError(
        f"Alternative source not implemented for market_id={market_id}, config={config}"
    )


# --------------------------------------------------------------------
# Main entrypoint
# --------------------------------------------------------------------

def main():
    print("Fetching data for POC markets...")
    print(f"Raw data will be saved to {RAW_DATA_DIR}\n")

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    for market_id, slug in MARKETS.items():
        try:
            market_data, price_data, yes_token_id, price_scale = fetch_polymarket_market_data(
                market_id, slug, force_refresh=False
            )

            results[market_id] = {
                "market_data": market_data,
                "price_data": price_data,
                "yes_token_id": yes_token_id,
                "price_scale": price_scale,
            }
            print(f"✓ {market_id} completed\n")
        except Exception as e:
            print(f"✗ {market_id} failed: {e}\n")
            raise

    print("All markets fetched successfully!")
    print(f"\nRaw data saved to: {RAW_DATA_DIR}")
    print("Next step: Run transform_to_engine_format.py to generate CSVs")


if __name__ == "__main__":
    main()
