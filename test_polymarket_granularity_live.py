"""
test_polymarket_granularity_live.py

Probe how granular Polymarket data really is for *live* markets.

What it does:
- Auto-selects 5 live markets with decent 24h volume from Gamma /markets.
- For each market:
  - Tests clob.prices-history with several interval/fidelity combos.
  - Tests data-api.trades for per-trade granularity.
- Writes:
  - granularity_tests_live/granularity_results_live.csv
  - granularity_tests_live/granularity_summary_live.md
  - granularity_tests_live/prices_<slug>_<config>.csv
  - granularity_tests_live/trades_<slug>.csv

This script is standalone and does NOT touch your existing POC code.
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

import requests


GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"
DATA_API_BASE = "https://data-api.polymarket.com"

OUT_DIR = Path("granularity_tests_live")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------- Data model ----------------------- #


@dataclass
class MarketChoice:
    market_id: str
    slug: str
    question: str
    condition_id: str
    yes_token_id: str
    volume24hr: float
    best_bid: Optional[float]
    best_ask: Optional[float]


# ----------------------- Market discovery ----------------------- #


def fetch_live_markets(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Get a batch of markets from Gamma.

    We filter locally for:
    - closed == False
    - enableOrderBook != False
    and later for volume + binary YES/NO markets.
    """
    params = {
        "limit": limit,
        "closed": False,            # only open/live markets
        "order": "volume24hr",      # sort by 24h volume
        "ascending": False,
    }
    resp = requests.get(f"{GAMMA_API_BASE}/markets", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError("Unexpected /markets response (expected list)")
    return data


def parse_outcomes(market_data: Dict[str, Any]) -> Optional[List[str]]:
    """
    Parse outcomes from either shortOutcomes or outcomes field.
    We want a list of strings like ["No", "Yes"].
    """
    if "shortOutcomes" in market_data and market_data["shortOutcomes"]:
        raw = market_data["shortOutcomes"]
    else:
        raw = market_data.get("outcomes")

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


def extract_yes_token_id(market_data: Dict[str, Any]) -> Optional[str]:
    """
    Find the YES outcome index and return its clobTokenId.
    """
    outcomes = parse_outcomes(market_data)
    if not outcomes:
        return None

    yes_index = None
    for i, outcome in enumerate(outcomes):
        if isinstance(outcome, str) and outcome.lower() == "yes":
            yes_index = i
            break
    if yes_index is None:
        return None

    clob_token_ids = market_data.get("clobTokenIds")
    if not clob_token_ids:
        return None

    if isinstance(clob_token_ids, list):
        token_ids = clob_token_ids
    elif isinstance(clob_token_ids, str):
        # Could be JSON or comma-separated
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


def select_top_live_markets(
    n: int = 5,
    min_volume_24h: float = 10_000.0,
) -> List[MarketChoice]:
    """
    Choose N live markets with:
    - decent 24h volume
    - YES/NO structure
    - order book enabled
    """
    markets = fetch_live_markets(limit=200)
    candidates: List[MarketChoice] = []

    for m in markets:
        try:
            if m.get("closed") is True:
                continue
            if m.get("enableOrderBook") is False:
                continue

            vol24 = m.get("volume24hr") or 0.0
            try:
                vol24 = float(vol24)
            except (TypeError, ValueError):
                vol24 = 0.0

            if vol24 < min_volume_24h:
                continue

            yes_token_id = extract_yes_token_id(m)
            if not yes_token_id:
                continue

            condition_id = m.get("conditionId")
            if not condition_id:
                continue

            candidates.append(
                MarketChoice(
                    market_id=str(m.get("id")),
                    slug=str(m.get("slug") or ""),
                    question=str(m.get("question") or ""),
                    condition_id=str(condition_id),
                    yes_token_id=yes_token_id,
                    volume24hr=vol24,
                    best_bid=float(m["bestBid"]) if m.get("bestBid") is not None else None,
                    best_ask=float(m["bestAsk"]) if m.get("bestAsk") is not None else None,
                )
            )
        except Exception:
            # Skip any weird edge cases; this is a diagnostic script
            continue

    candidates.sort(key=lambda x: x.volume24hr, reverse=True)
    return candidates[:n]


# ----------------------- Time-series helpers ----------------------- #


def compute_time_stats(
    unix_ts: List[int],
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[str], Optional[str]]:
    """
    Given list of unix timestamps, compute time-step stats in minutes and time range.
    """
    if not unix_ts:
        return None, None, None, None, None, None

    ts_sorted = sorted(unix_ts)

    if len(ts_sorted) >= 2:
        diffs = [ts_sorted[i] - ts_sorted[i - 1] for i in range(1, len(ts_sorted))]
        diffs_min = [d / 60.0 for d in diffs]
        min_step = min(diffs_min)
        med_step = median(diffs_min)
        max_step = max(diffs_min)
    else:
        min_step = med_step = max_step = None

    start_ts = ts_sorted[0]
    end_ts = ts_sorted[-1]
    time_range_hours = (end_ts - start_ts) / 3600.0 if end_ts > start_ts else 0.0

    start_iso = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat()
    end_iso = datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat()

    return min_step, med_step, max_step, time_range_hours, start_iso, end_iso


# ----------------------- prices-history probing ----------------------- #


def test_prices_history_for_market(market: MarketChoice) -> List[Dict[str, Any]]:
    """
    Probe a grid of interval/fidelity combinations for this YES token.

    We deliberately include combos that might fail; the point is to empirically
    see what Polymarket actually supports and how granular the data really is.
    """
    combos = [
        ("max", 1),
        ("max", 5),
        ("max", 10),
        ("max", 60),
        ("1d", 1),
        ("1d", 5),
        ("6h", 1),
        ("6h", 5),
        ("1h", 1),
        ("1h", 5),
        ("1m", None),   # try 1-minute interval without fidelity
    ]

    results: List[Dict[str, Any]] = []

    for interval, fidelity in combos:
        params: Dict[str, Any] = {"market": market.yes_token_id}
        if interval is not None:
            params["interval"] = interval
        if fidelity is not None:
            params["fidelity"] = fidelity

        label = f"{interval}_f{fidelity}" if fidelity is not None else f"{interval}_noFid"

        try:
            resp = requests.get(
                f"{CLOB_API_BASE}/prices-history",
                params=params,
                timeout=10,
            )
            status = resp.status_code

            history = []
            if status == 200:
                payload = resp.json()
                history = payload.get("history", []) if isinstance(payload, dict) else []

            unix_ts = [int(h["t"]) for h in history if "t" in h]
            (
                min_step,
                med_step,
                max_step,
                range_hours,
                start_iso,
                end_iso,
            ) = compute_time_stats(unix_ts)

            results.append(
                {
                    "market_id": market.market_id,
                    "slug": market.slug,
                    "question": market.question,
                    "source": "prices-history",
                    "config": label,
                    "interval": interval,
                    "fidelity": fidelity,
                    "http_status": status,
                    "n_points": len(unix_ts),
                    "min_step_min": min_step,
                    "median_step_min": med_step,
                    "max_step_min": max_step,
                    "time_range_hours": range_hours,
                    "start_iso": start_iso,
                    "end_iso": end_iso,
                }
            )

            # Dump raw series if the call worked and returned data
            if unix_ts and status == 200:
                out_prices_path = OUT_DIR / f"prices_{market.slug or market.market_id}_{label}.csv"
                with out_prices_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["timestamp", "price_raw"])
                    for h in history:
                        t = int(h["t"])
                        p = h.get("p")
                        ts_iso = datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
                        writer.writerow([ts_iso, p])

        except Exception as e:
            results.append(
                {
                    "market_id": market.market_id,
                    "slug": market.slug,
                    "question": market.question,
                    "source": "prices-history",
                    "config": label,
                    "interval": interval,
                    "fidelity": fidelity,
                    "http_status": f"error:{e}",
                    "n_points": 0,
                    "min_step_min": None,
                    "median_step_min": None,
                    "max_step_min": None,
                    "time_range_hours": None,
                    "start_iso": None,
                    "end_iso": None,
                }
            )

    return results


# ----------------------- trades probing (Data-API) ----------------------- #


def test_trades_for_market(market: MarketChoice, limit: int = 5000) -> Dict[str, Any]:
    """
    Fetch trades for this market via Data-API and inspect temporal granularity.
    """
    params = {
        "limit": limit,
        "market": market.condition_id,   # conditionId is the "market" param here
        "takerOnly": True,
    }

    try:
        resp = requests.get(f"{DATA_API_BASE}/trades", params=params, timeout=10)
        status = resp.status_code

        trades = []
        if status == 200:
            trades = resp.json()
            if not isinstance(trades, list):
                trades = []

        unix_ts = [int(t["timestamp"]) for t in trades if "timestamp" in t]
        (
            min_step,
            med_step,
            max_step,
            range_hours,
            start_iso,
            end_iso,
        ) = compute_time_stats(unix_ts)

        # Dump raw trades if any
        if unix_ts and status == 200:
            out_trades_path = OUT_DIR / f"trades_{market.slug or market.market_id}.csv"
            with out_trades_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "side",
                        "price",
                        "size",
                        "outcome",
                        "conditionId",
                        "transactionHash",
                    ]
                )
                for t in trades:
                    ts = int(t["timestamp"])
                    ts_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    writer.writerow(
                        [
                            ts_iso,
                            t.get("side"),
                            t.get("price"),
                            t.get("size"),
                            t.get("outcome"),
                            t.get("conditionId"),
                            t.get("transactionHash"),
                        ]
                    )

        return {
            "market_id": market.market_id,
            "slug": market.slug,
            "question": market.question,
            "source": "trades",
            "config": f"trades_limit{limit}",
            "interval": None,
            "fidelity": None,
            "http_status": status,
            "n_points": len(unix_ts),
            "min_step_min": min_step,
            "median_step_min": med_step,
            "max_step_min": max_step,
            "time_range_hours": range_hours,
            "start_iso": start_iso,
            "end_iso": end_iso,
        }

    except Exception as e:
        return {
            "market_id": market.market_id,
            "slug": market.slug,
            "question": market.question,
            "source": "trades",
            "config": f"trades_limit{limit}",
            "interval": None,
            "fidelity": None,
            "http_status": f"error:{e}",
            "n_points": 0,
            "min_step_min": None,
            "median_step_min": None,
            "max_step_min": None,
            "time_range_hours": None,
            "start_iso": None,
            "end_iso": None,
        }


# ----------------------- Output writers ----------------------- #


def write_summary_csv(all_results: List[Dict[str, Any]]) -> Path:
    out_path = OUT_DIR / "granularity_results_live.csv"
    fieldnames = [
        "market_id",
        "slug",
        "question",
        "source",
        "config",
        "interval",
        "fidelity",
        "http_status",
        "n_points",
        "min_step_min",
        "median_step_min",
        "max_step_min",
        "time_range_hours",
        "start_iso",
        "end_iso",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_results:
            writer.writerow(row)
    return out_path


def write_summary_markdown(all_results: List[Dict[str, Any]]) -> Path:
    out_md = OUT_DIR / "granularity_summary_live.md"

    # Group by market
    by_market: Dict[str, List[Dict[str, Any]]] = {}
    for row in all_results:
        key = row["market_id"]
        by_market.setdefault(key, []).append(row)

    with out_md.open("w", encoding="utf-8") as f:
        f.write("# Polymarket Live Granularity Test – Summary\n\n")
        f.write(f"Generated at: {datetime.now(timezone.utc).isoformat()}\n\n")

        for market_id, rows in by_market.items():
            any_row = rows[0]
            f.write(f"## Market {market_id} – {any_row.get('slug','')}\n\n")
            f.write(f"**Question:** {any_row.get('question','')}\n\n")

            ph_rows = [
                r
                for r in rows
                if r["source"] == "prices-history"
                and isinstance(r.get("median_step_min"), (int, float))
            ]
            tr_rows = [
                r
                for r in rows
                if r["source"] == "trades"
                and isinstance(r.get("median_step_min"), (int, float))
            ]

            if ph_rows:
                best_ph = min(ph_rows, key=lambda r: r["median_step_min"])
                f.write("**Best prices-history resolution:**\n\n")
                f.write(
                    f"- Config: `{best_ph['config']}`\n"
                    f"- Median step: {best_ph['median_step_min']:.2f} minutes\n"
                    f"- Time range: {best_ph['time_range_hours']:.2f} hours\n"
                    f"- Points: {best_ph['n_points']}\n"
                    f"- Start: {best_ph['start_iso']}\n"
                    f"- End: {best_ph['end_iso']}\n\n"
                )
            else:
                f.write("**Best prices-history resolution:** No successful configs.\n\n")

            if tr_rows:
                best_tr = min(tr_rows, key=lambda r: r["median_step_min"])
                f.write("**Trades endpoint resolution:**\n\n")
                f.write(
                    f"- Median inter-trade gap: {best_tr['median_step_min']:.2f} minutes\n"
                    f"- Time range: {best_tr['time_range_hours']:.2f} hours\n"
                    f"- Trades: {best_tr['n_points']}\n"
                    f"- Start: {best_tr['start_iso']}\n"
                    f"- End: {best_tr['end_iso']}\n\n"
                )
            else:
                f.write("**Trades endpoint resolution:** No trades or request failed.\n\n")

    return out_md


# ----------------------- Main ----------------------- #


def main() -> None:
    print("Discovering top live Polymarket markets by 24h volume...")
    markets = select_top_live_markets(n=5, min_volume_24h=10_000.0)
    if not markets:
        raise SystemExit(
            "No suitable live markets found (adjust min_volume_24h or check API connectivity)."
        )

    print(f"Selected {len(markets)} markets:")
    for m in markets:
        print(f"  - {m.market_id} | {m.slug} | 24h vol ≈ {m.volume24hr:.2f}")

    all_results: List[Dict[str, Any]] = []

    for m in markets:
        print(f"\n== Market: {m.slug} ({m.market_id}) ==")
        print("Testing prices-history granularity...")
        ph_results = test_prices_history_for_market(m)
        all_results.extend(ph_results)

        print("Testing trades granularity (Data-API)...")
        tr_result = test_trades_for_market(m, limit=5000)
        all_results.append(tr_result)

    csv_path = write_summary_csv(all_results)
    md_path = write_summary_markdown(all_results)

    print(f"\nDone.")
    print(f"- Summary CSV: {csv_path}")
    print(f"- Human-readable markdown summary: {md_path}")
    print(f"- Raw series/trades (if any): {OUT_DIR}/")


if __name__ == "__main__":
    main()

