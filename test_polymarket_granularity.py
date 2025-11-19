"""
test_polymarket_granularity.py

Probe how granular Polymarket's historical price data is for our markets.

Features:
- Uses the same MARKETS, Gamma, and CLOB endpoints as fetch_polymarket_data.py
- For each market (or a single slug/token), tries multiple (interval, fidelity) combos
- Prints a human-readable summary to stdout
- Writes a CSV with ALL results:
    diagnostics/polymarket_granularity_results.csv
- Writes a Markdown summary of "best available granularity" per market:
    diagnostics/polymarket_granularity_summary.md

This script is read-only. It does NOT touch the core POC data or outputs.
"""

import argparse
import csv
import statistics
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# Import from your existing fetch script (no modification needed there)
from fetch_polymarket_data import (
    MARKETS,
    GAMMA_API_BASE,
    CLOB_API_BASE,
    fetch_market_metadata_polymarket,
    extract_yes_token_id,
)

# Alias for compatibility with script expectations
fetch_market_metadata = fetch_market_metadata_polymarket

# Directory for diagnostics
DIAG_DIR = Path("diagnostics")
DIAG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class GranularityRecord:
    market_label: str          # e.g. "M1", "CUSTOM:slug"
    market_id: Optional[str]   # e.g. "M1" or None
    slug: Optional[str]        # Polymarket slug if known
    question: Optional[str]
    yes_token_id: Optional[str]
    interval: str              # "1m", "1h", "1d", "max"
    fidelity_min: int          # fidelity (minutes)
    status: str                # "ok", "http_error", "exception"
    http_status: Optional[int]
    n_points: int
    t_min_iso: Optional[str]
    t_max_iso: Optional[str]
    median_step_minutes: Optional[float]
    min_price: Optional[float]
    max_price: Optional[float]
    error_message: Optional[str]


def fetch_history_raw(
    token_id: str,
    interval: str,
    fidelity: int,
    timeout: float = 15.0,
) -> Tuple[str, Optional[int], Optional[str], List[dict]]:
    """
    Call Polymarket /prices-history for a given token_id, interval, and fidelity.

    Returns:
      - status: "ok" | "http_error" | "exception"
      - http_status: HTTP code (if http_error) or None
      - error_message: str or None
      - history: list of history entries (may be empty)
    """
    url = f"{CLOB_API_BASE}/prices-history"
    params = {
        "market": token_id,
        "interval": interval,
        "fidelity": fidelity,
    }

    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except Exception as e:
        return "exception", None, str(e), []

    if resp.status_code != 200:
        return "http_error", resp.status_code, f"HTTP {resp.status_code}", []

    try:
        data = resp.json()
    except Exception as e:
        return "exception", resp.status_code, f"JSON decode error: {e}", []

    history = data.get("history", []) or []
    return "ok", resp.status_code, None, history


def summarize_history(history: List[dict]) -> Tuple[int, Optional[int], Optional[int], Optional[float], Optional[float], Optional[float]]:
    """
    Compute basic stats for a given history array.

    Each entry should have:
      - t: unix timestamp (seconds)
      - p: price (raw CLOB units)

    Returns:
      - n_points
      - t_min (unix) or None
      - t_max (unix) or None
      - median_step_minutes or None
      - min_price or None
      - max_price or None
    """
    if not history:
        return 0, None, None, None, None, None

    ts = [e.get("t") for e in history if isinstance(e.get("t"), (int, float))]
    ts = sorted(int(t) for t in ts)
    n = len(ts)

    if n == 0:
        return 0, None, None, None, None, None

    t_min = ts[0]
    t_max = ts[-1]

    deltas = [ts[i + 1] - ts[i] for i in range(n - 1) if ts[i + 1] >= ts[i]]
    if deltas:
        median_step_sec = statistics.median(deltas)
        median_step_minutes = median_step_sec / 60.0
    else:
        median_step_minutes = None

    prices = []
    for e in history:
        p = e.get("p")
        if isinstance(p, (int, float)):
            prices.append(float(p))
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None

    return n, t_min, t_max, median_step_minutes, min_price, max_price


def unix_to_iso(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return str(ts)


def test_one_market(
    label: str,
    market_id: Optional[str],
    slug: Optional[str],
    yes_token_id: str,
    question: Optional[str],
    intervals: List[str],
    fidelities: List[int],
    sleep_sec: float,
) -> List[GranularityRecord]:
    """
    Test all (interval, fidelity) combinations for a single token and return records.
    """
    print("=" * 80)
    print(f"Market {label}")
    if slug:
        print(f"  Slug     : {slug}")
    if question:
        print(f"  Question : {question}")
    print(f"  YES token: {yes_token_id}")
    print("-" * 80)

    records: List[GranularityRecord] = []

    for interval in intervals:
        for fid in fidelities:
            status, http_status, err_msg, history = fetch_history_raw(
                token_id=yes_token_id,
                interval=interval,
                fidelity=fid,
            )

            n_points, t_min, t_max, median_step_minutes, p_min, p_max = summarize_history(history)

            t_min_iso = unix_to_iso(t_min)
            t_max_iso = unix_to_iso(t_max)

            # Pretty print
            if median_step_minutes is None:
                step_str = "N/A"
            else:
                step_str = f"{median_step_minutes:.2f} min"

            if p_min is not None and p_max is not None:
                prange_str = f"{p_min:.2f} → {p_max:.2f}"
            else:
                prange_str = "N/A"

            print(
                f"  interval={interval:<3}  fidelity={fid:>4}m  "
                f"points={n_points:>6}  step={step_str:<9}  "
                f"t_min={t_min_iso or 'N/A'}  t_max={t_max_iso or 'N/A'}  "
                f"price_range={prange_str} (raw CLOB units)"
            )

            rec = GranularityRecord(
                market_label=label,
                market_id=market_id,
                slug=slug,
                question=question,
                yes_token_id=yes_token_id,
                interval=interval,
                fidelity_min=fid,
                status=status,
                http_status=http_status,
                n_points=n_points,
                t_min_iso=t_min_iso,
                t_max_iso=t_max_iso,
                median_step_minutes=median_step_minutes,
                min_price=p_min,
                max_price=p_max,
                error_message=err_msg,
            )
            records.append(rec)

            time.sleep(sleep_sec)

    print("=" * 80)
    print()
    return records


def build_market_from_slug(slug: str) -> Tuple[str, Optional[str], str, Optional[str], Optional[str]]:
    """
    Build a (label, market_id, slug, question, yes_token_id) from a slug.
    Used when the user passes --slug directly (current or arbitrary market).
    """
    mdata = fetch_market_metadata(slug)
    question = mdata.get("question") or mdata.get("title") or None
    yes_token_id = extract_yes_token_id(mdata)
    label = f"CUSTOM:{slug}"
    return label, None, slug, question, yes_token_id


def run_tests(
    intervals: List[str],
    fidelities: List[int],
    market_id: Optional[str],
    slug: Optional[str],
    token_id: Optional[str],
    sleep_sec: float,
) -> List[GranularityRecord]:
    """
    Orchestrate running all tests based on CLI options.
    """
    all_records: List[GranularityRecord] = []

    if token_id:
        # Direct token_id: no slug/metadata lookup
        label = f"CUSTOM_TOKEN:{token_id[:8]}..."
        print(f"Testing direct token_id: {token_id}")
        recs = test_one_market(
            label=label,
            market_id=None,
            slug=None,
            yes_token_id=token_id,
            question=None,
            intervals=intervals,
            fidelities=fidelities,
            sleep_sec=sleep_sec,
        )
        all_records.extend(recs)
        return all_records

    if slug:
        # Single arbitrary slug; fetch metadata and YES token
        label, m_id, slug_val, question, yes_token_id = build_market_from_slug(slug)
        if not yes_token_id:
            print(f"ERROR: Could not extract YES token ID for slug {slug}")
            return all_records

        recs = test_one_market(
            label=label,
            market_id=m_id,
            slug=slug_val,
            yes_token_id=yes_token_id,
            question=question,
            intervals=intervals,
            fidelities=fidelities,
            sleep_sec=sleep_sec,
        )
        all_records.extend(recs)
        return all_records

    # Use POC MARKETS mapping: either all, or one by M1/M2/...
    if market_id and market_id.upper() != "ALL":
        mid = market_id.upper()
        if mid not in MARKETS:
            raise SystemExit(f"Unknown market_id {mid}. Valid keys: {list(MARKETS.keys())}")
        targets = [(mid, MARKETS[mid])]
    else:
        targets = list(MARKETS.items())

    for mid, slug_val in targets:
        mdata = fetch_market_metadata(slug_val)
        question = mdata.get("question") or mdata.get("title") or None
        yes_token_id = extract_yes_token_id(mdata)
        if not yes_token_id:
            print(f"ERROR: Could not extract YES token ID for market {mid} ({slug_val})")
            continue
        recs = test_one_market(
            label=mid,
            market_id=mid,
            slug=slug_val,
            yes_token_id=yes_token_id,
            question=question,
            intervals=intervals,
            fidelities=fidelities,
            sleep_sec=sleep_sec,
        )
        all_records.extend(recs)

    return all_records


def write_results_csv(records: List[GranularityRecord], out_path: Path) -> None:
    if not records:
        print("No records to write.")
        return

    fieldnames = list(asdict(records[0]).keys())
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in records:
            w.writerow(asdict(r))

    print(f"Wrote CSV summary to {out_path}")


def write_summary_md(records: List[GranularityRecord], out_path: Path) -> None:
    """
    Write a human-readable Markdown summary that highlights, for each market,
    the best available granularity (smallest median_step_minutes with n_points > 0).
    """
    if not records:
        return

    # Group by market_label
    by_market: Dict[str, List[GranularityRecord]] = {}
    for r in records:
        by_market.setdefault(r.market_label, []).append(r)

    lines: List[str] = []
    lines.append("# Polymarket Granularity Test Summary")
    lines.append("")
    lines.append("This file is auto-generated by `test_polymarket_granularity.py`.")
    lines.append("It summarizes the best available historical resolution per market.")
    lines.append("")
    lines.append("| Market | Slug | Best interval | Best fidelity (min) | Median step (min) | Points | Time range (UTC) |")
    lines.append("|--------|------|---------------|---------------------|-------------------|--------|------------------|")

    for label, recs in by_market.items():
        # Filter to successful rows with data
        valid = [
            r for r in recs
            if r.status == "ok"
            and r.n_points > 0
            and r.median_step_minutes is not None
        ]
        if not valid:
            # No usable data; still write a row with N/A
            lines.append(
                f"| {label} | {recs[0].slug or ''} | N/A | N/A | N/A | 0 | N/A |"
            )
            continue

        # Choose row with smallest median_step_minutes, tie-break by largest n_points
        best = sorted(
            valid,
            key=lambda r: (r.median_step_minutes, -r.n_points),
        )[0]

        trange = "N/A"
        if best.t_min_iso and best.t_max_iso:
            trange = f"{best.t_min_iso} → {best.t_max_iso}"

        lines.append(
            f"| {label} | {best.slug or ''} | {best.interval} | {best.fidelity_min} "
            f"| {best.median_step_minutes:.2f} | {best.n_points} | {trange} |"
        )

    with out_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote Markdown summary to {out_path}")


def parse_list_arg(raw: str, cast_fn):
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return [cast_fn(x) for x in items]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Test how granular Polymarket historical prices are for POC and custom markets."
        )
    )
    parser.add_argument(
        "--market-id",
        type=str,
        default="ALL",
        help="POC market ID to test (e.g. M1) or ALL for all configured POC markets.",
    )
    parser.add_argument(
        "--slug",
        type=str,
        default=None,
        help=(
            "Polymarket slug to test directly (e.g. 'us-inflation-0pt3-from-march-to-april-2024'). "
            "Overrides --market-id if provided."
        ),
    )
    parser.add_argument(
        "--token-id",
        type=str,
        default=None,
        help=(
            "CLOB token ID to test directly (YES token). Overrides both --slug and --market-id."
        ),
    )
    parser.add_argument(
        "--intervals",
        type=str,
        default="1m,1h,1d,max",
        help='Comma-separated intervals to test (default: "1m,1h,1d,max").',
    )
    parser.add_argument(
        "--fidelities",
        type=str,
        default="1,5,15,60,1440",
        help="Comma-separated fidelities (minutes) to test (default: 1,5,15,60,1440).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.3,
        help="Sleep (seconds) between API calls to avoid rate limiting (default: 0.3).",
    )
    parser.add_argument(
        "--csv-path",
        type=str,
        default=str(DIAG_DIR / "polymarket_granularity_results.csv"),
        help="Where to write the CSV summary (default: diagnostics/polymarket_granularity_results.csv).",
    )
    parser.add_argument(
        "--summary-path",
        type=str,
        default=str(DIAG_DIR / "polymarket_granularity_summary.md"),
        help="Where to write the Markdown summary (default: diagnostics/polymarket_granularity_summary.md).",
    )

    args = parser.parse_args()

    intervals = parse_list_arg(args.intervals, str)
    fidelities = parse_list_arg(args.fidelities, int)

    print("Polymarket granularity test")
    print(f"  Gamma API : {GAMMA_API_BASE}")
    print(f"  CLOB API  : {CLOB_API_BASE}")
    print(f"  Intervals : {intervals}")
    print(f"  Fidelities (min): {fidelities}")
    print()

    records = run_tests(
        intervals=intervals,
        fidelities=fidelities,
        market_id=args.market_id,
        slug=args.slug,
        token_id=args.token_id,
        sleep_sec=args.sleep,
    )

    if not records:
        print("No records collected (check errors above).")
        return

    csv_path = Path(args.csv_path)
    write_results_csv(records, csv_path)

    summary_path = Path(args.summary_path)
    write_summary_md(records, summary_path)

    print("Done.")


if __name__ == "__main__":
    main()

