import json
import requests
import urllib3
from typing import Dict, Optional, List, Any

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

def fetch_market_metadata_polymarket(slug: str) -> Dict:
    """Fetch market metadata from Polymarket Gamma API."""
    url = f"{GAMMA_API_BASE}/markets/slug/{slug}"
    response = requests.get(url, verify=False)
    response.raise_for_status()
    return response.json()

def extract_yes_token_id(market_data: Dict) -> Optional[str]:
    """
    Extract the YES token ID from market metadata.
    We assume the outcomes list contains "Yes" (or "yes"), or something equivalent.
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
        try:
            response = requests.get(url, params=params, verify=False)
            response.raise_for_status()
            data = response.json()

            history = data.get("history", [])
            if history:
                return data
                
            # Fallback: token_id param
            params2 = {
                "token_id": token_id,
                "interval": "max",
                "fidelity": fid,
            }
            response2 = requests.get(url, params=params2, verify=False)
            if response2.status_code == 200:
                data2 = response2.json()
                if data2.get("history"):
                    return data2
        except Exception:
            continue

    # If still empty, return empty struct
    return {"history": []}

def fetch_24h_history(token_id: str) -> List[Dict[str, Any]]:
    """
    Fetch last 24 hours of 1-minute candles (or best available).
    Used by the live data fetcher.
    """
    data = fetch_price_history_polymarket(token_id, fidelity=1) # Try 1 minute fidelity
    history = data.get("history", [])
    
    if not history:
        # Fallback to hourly if minute data not available
        data = fetch_price_history_polymarket(token_id, fidelity=60)
        history = data.get("history", [])
        
    return history

def fetch_current_price(token_id: str) -> Optional[float]:
    """
    Fetch the current midpoint price for a token.
    """
    try:
        url = f"{CLOB_API_BASE}/price"
        params = {"token_id": token_id, "side": "BUY"} # Looking for BUY side (ask) or midpoint?
        # To get a single 'price' usually we look at the midpoint or last trade.
        # The API returns top of book usually.
        # Let's check how determine_price_scale_polymarket did it.
        # It checked "side": "BUY" and used "price" field.
        
        response = requests.get(url, params=params, verify=False)
        if response.status_code == 200:
            data = response.json()
            raw_price = None
            if isinstance(data, dict):
                raw_price = data.get("price") or data.get("p")
            elif isinstance(data, (int, float)):
                raw_price = data

            if raw_price is not None:
                try:
                    price_val = float(raw_price)
                except (ValueError, TypeError):
                    return None

                # Normalize price if it's scaled
                if price_val > 1.0:
                    # Try to infer scale
                    if price_val > 100: return price_val / 10000.0
                    if price_val > 10: return price_val / 1000.0
                    if price_val > 1: return price_val / 100.0
                return price_val
    except Exception as e:
        print(f"Error fetching price for {token_id}: {e}")
        pass
    return None

def determine_price_scale_polymarket(token_id: str) -> float:
    """
    Determine the price scaling factor by checking current price.
    """
    try:
        url = f"{CLOB_API_BASE}/price"
        params = {"token_id": token_id, "side": "BUY"}
        response = requests.get(url, params=params, verify=False)
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

    return 10000.0

