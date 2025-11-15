"""
Example complex strategy plugin that generates a multi-trade log.

This script:
  - Loads canonical markets (MarketSeries) via engine.load_markets.
  - Implements a simple "swing" momentum strategy:
      * For each market and time step, compare price vs previous step.
      * If price increases by > up_threshold, BUY_YES.
      * If price decreases by < -down_threshold, SELL_YES.
  - Emits a trade log CSV that can be evaluated by evaluate_trade_logs.py.

Usage:

    python example_complex_strategy.py \
        --meta data/markets_meta.csv \
        --prices-dir data \
        --out-log logs/swing_v1_trades.csv \
        --bankroll 100.0
"""

import argparse
import csv
from pathlib import Path
from typing import List

from engine import MarketSeries, StrategyDecision, load_markets


def generate_swing_trades(
    markets: List[MarketSeries],
    strategy_name: str = "swing_v1",
    up_threshold: float = 0.05,
    down_threshold: float = 0.05,
    trade_size_fraction: float = 0.1,
) -> List[StrategyDecision]:
    """
    Generate a multi-trade log based on price swings.

    For each market and each time index i > 0:
        delta = price[i] - price[i-1]
        if delta >= up_threshold: BUY_YES at i
        if delta <= -down_threshold: SELL_YES at i

    This is just an example; real miners can implement arbitrarily complex logic.
    """
    decisions: List[StrategyDecision] = []

    for market in markets:
        prices = market.price
        if len(prices) < 2:
            continue

        for idx in range(1, len(prices)):
            p_now = prices[idx]
            p_prev = prices[idx - 1]
            delta = p_now - p_prev

            if delta >= up_threshold:
                side = "BUY_YES"
                # Simple p_hat: current price plus a small "edge"
                p_hat = min(1.0, p_now + 0.05)
            elif delta <= -down_threshold:
                side = "SELL_YES"
                p_hat = max(0.0, p_now - 0.05)
            else:
                continue

            decisions.append(
                StrategyDecision(
                    strategy_name=strategy_name,
                    market_id=market.market_id,
                    entry_index=idx,
                    side=side,
                    size=trade_size_fraction,
                    p_hat=p_hat,
                )
            )

    return decisions


def write_trade_log_csv(decisions: List[StrategyDecision], out_path: Path) -> None:
    """
    Write a trade log CSV that evaluate_trade_logs.py can consume.

    Columns:
      strategy_name,market_id,entry_index,side,size,p_hat
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["strategy_name", "market_id", "entry_index", "side", "size", "p_hat"]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for d in decisions:
            writer.writerow(
                {
                    "strategy_name": d.strategy_name,
                    "market_id": d.market_id,
                    "entry_index": d.entry_index,
                    "side": d.side,
                    "size": f"{d.size:.6f}",
                    "p_hat": f"{d.p_hat:.6f}",
                }
            )

    print(f"Wrote {len(decisions)} trades to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate example multi-trade log using canonical market data"
    )
    parser.add_argument("--meta", type=str, required=True, help="markets_meta.csv path")
    parser.add_argument(
        "--prices-dir",
        type=str,
        required=True,
        help="directory with prices_<market_id>.csv files",
    )
    parser.add_argument(
        "--out-log",
        type=str,
        required=True,
        help="output trade log CSV path",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=100.0,
        help="reference bankroll (used only for sizing decisions, not computing PnL here)",
    )
    args = parser.parse_args()

    meta_csv = Path(args.meta)
    prices_dir = Path(args.prices_dir)
    out_log = Path(args.out_log)

    # Load markets from engine
    markets = load_markets(meta_csv, prices_dir)

    # Generate trade specs
    # Use reasonable thresholds for prices in [0,1] range
    decisions = generate_swing_trades(
        markets,
        up_threshold=0.05,  # 5% price increase
        down_threshold=0.05,  # 5% price decrease
    )

    # Write trade log CSV
    write_trade_log_csv(decisions, out_log)


if __name__ == "__main__":
    main()

