"""
Generate trade logs for multiple strategies on canonical market data.

Strategies implemented:

  1. baseline_hold
     - One trade per market at the first timestamp.
     - BUY_YES if price >= 0.5, otherwise SELL_YES.

  2. swing_v1
     - Simple price-swing momentum.
     - For each market and each time step i > 0:
         delta = price[i] - price[i-1]
         if delta >= up_threshold: BUY_YES at i
         if delta <= -down_threshold: SELL_YES at i

  3. mean_revert_v1
     - Mean-reversion vs a short rolling window.
     - For each market and i >= window:
         mean = average(price[i-window : i])
         diff = price[i] - mean
         if diff <= -threshold: BUY_YES (cheap vs recent avg)
         if diff >= threshold: SELL_YES (rich vs recent avg)

  4. cross_section_value_v1
     - Cross-sectional "value" across all markets.
     - Compute average price per market over full window.
     - Compute global mean over markets.
     - For each market:
         if avg_price <= global_mean - threshold: BUY_YES at last index
         if avg_price >= global_mean + threshold: SELL_YES at last index

  5. risk_managed_momo_v1
     - Momentum with basic risk controls.
     - For each market and i > 0:
         delta = price[i] - price[i-1]
         trade only if |delta| >= threshold,
                        price[i] in [min_price, max_price],
                        trades_per_market < max_trades_per_market.

All strategies emit StrategyDecision objects, which are then written
to a combined CSV log:

    strategy_name,market_id,entry_index,side,size,p_hat

You can evaluate this log with evaluate_trade_logs.py, e.g.:

    python multi_strategies.py \
        --meta data/markets_meta.csv \
        --prices-dir data \
        --out-log logs/strategies_suite_trades.csv

    python evaluate_trade_logs.py \
        --meta data/markets_meta.csv \
        --prices-dir data \
        --log-file logs/strategies_suite_trades.csv \
        --out-dir outputs \
        --bankroll 100.0
"""

import argparse
import csv
from pathlib import Path
from typing import List

from engine import MarketSeries, StrategyDecision, load_markets


# ---------------------------------------------------------------------
# Strategy 1: Baseline buy-and-hold at first timestamp
# ---------------------------------------------------------------------

def generate_baseline_hold_trades(
    markets: List[MarketSeries],
    strategy_name: str = "baseline_hold",
    size_fraction: float = 0.1,
) -> List[StrategyDecision]:
    """
    One trade per market at the first timestamp.

    If first price >= 0.5 -> BUY_YES
    else                 -> SELL_YES
    """
    decisions: List[StrategyDecision] = []

    for market in markets:
        if not market.price:
            continue

        idx = 0
        p = market.price[idx]
        side = "BUY_YES" if p >= 0.5 else "SELL_YES"
        p_hat = max(0.0, min(1.0, p))  # use market price as probability estimate

        decisions.append(
            StrategyDecision(
                strategy_name=strategy_name,
                market_id=market.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat,
            )
        )

    return decisions


# ---------------------------------------------------------------------
# Strategy 2: Swing momentum (already conceptually defined earlier)
# ---------------------------------------------------------------------

def generate_swing_trades(
    markets: List[MarketSeries],
    strategy_name: str = "swing_v1",
    up_threshold: float = 0.05,
    down_threshold: float = 0.05,
    size_fraction: float = 0.1,
) -> List[StrategyDecision]:
    """
    Simple swing momentum:

    For each market and each i > 0:
        delta = price[i] - price[i-1]
        if delta >= up_threshold:   BUY_YES at i
        if delta <= -down_threshold: SELL_YES at i
    """
    decisions: List[StrategyDecision] = []

    for market in markets:
        prices = market.price
        n = len(prices)
        if n < 2:
            continue

        for idx in range(1, n):
            p_now = prices[idx]
            p_prev = prices[idx - 1]
            delta = p_now - p_prev

            if delta >= up_threshold:
                side = "BUY_YES"
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
                    size=size_fraction,
                    p_hat=p_hat,
                )
            )

    return decisions


# ---------------------------------------------------------------------
# Strategy 3: Mean reversion vs rolling window
# ---------------------------------------------------------------------

def generate_mean_reversion_trades(
    markets: List[MarketSeries],
    strategy_name: str = "mean_revert_v1",
    window: int = 3,
    threshold: float = 0.05,
    size_fraction: float = 0.1,
) -> List[StrategyDecision]:
    """
    Mean-reversion strategy:

    For each market and i >= window:
        mean_recent = average(price[i-window : i])
        diff = price[i] - mean_recent

        If diff <= -threshold -> BUY_YES  (cheap vs recent average)
        If diff >=  threshold -> SELL_YES (rich vs recent average)
    """
    decisions: List[StrategyDecision] = []

    for market in markets:
        prices = market.price
        n = len(prices)
        if n <= window:
            continue

        for idx in range(window, n):
            window_start = idx - window
            recent_slice = prices[window_start:idx]
            if not recent_slice:
                continue

            mean_recent = sum(recent_slice) / len(recent_slice)
            diff = prices[idx] - mean_recent

            if diff <= -threshold:
                side = "BUY_YES"
                p_hat = min(1.0, prices[idx] + 0.05)
            elif diff >= threshold:
                side = "SELL_YES"
                p_hat = max(0.0, prices[idx] - 0.05)
            else:
                continue

            decisions.append(
                StrategyDecision(
                    strategy_name=strategy_name,
                    market_id=market.market_id,
                    entry_index=idx,
                    side=side,
                    size=size_fraction,
                    p_hat=p_hat,
                )
            )

    return decisions


# ---------------------------------------------------------------------
# Strategy 4: Cross-sectional "value" across markets
# ---------------------------------------------------------------------

def generate_cross_section_value_trades(
    markets: List[MarketSeries],
    strategy_name: str = "cross_section_value_v1",
    cs_threshold: float = 0.1,
    size_fraction: float = 0.1,
) -> List[StrategyDecision]:
    """
    Cross-sectional value strategy:

    - Compute average price per market over the full available window.
    - Compute global mean across markets.
    - For each market:
        if avg_price <= global_mean - cs_threshold: BUY_YES at last index
        if avg_price >= global_mean + cs_threshold: SELL_YES at last index
    """
    decisions: List[StrategyDecision] = []
    avg_price_per_market = {}

    for market in markets:
        prices = market.price
        if not prices:
            continue
        avg_price = sum(prices) / len(prices)
        avg_price_per_market[market.market_id] = avg_price

    if not avg_price_per_market:
        return decisions

    global_mean = sum(avg_price_per_market.values()) / len(avg_price_per_market)

    for market in markets:
        prices = market.price
        if not prices:
            continue

        avg_price = avg_price_per_market[market.market_id]
        diff = avg_price - global_mean

        # Last index as the "execution point"
        idx = len(prices) - 1
        p_now = prices[idx]

        if diff <= -cs_threshold:
            # Value buy: market is overall cheap relative to others
            side = "BUY_YES"
            p_hat = min(1.0, p_now + 0.05)
        elif diff >= cs_threshold:
            # Value short: market is rich relative to others
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
                size=size_fraction,
                p_hat=p_hat,
            )
        )

    return decisions


# ---------------------------------------------------------------------
# Strategy 5: Risk-managed momentum
# ---------------------------------------------------------------------

def generate_risk_managed_momo_trades(
    markets: List[MarketSeries],
    strategy_name: str = "risk_managed_momo_v1",
    threshold: float = 0.05,
    size_fraction: float = 0.05,
    min_price: float = 0.2,
    max_price: float = 0.8,
    max_trades_per_market: int = 3,
) -> List[StrategyDecision]:
    """
    Momentum with simple risk controls:

    For each market and i > 0:
      delta = price[i] - price[i-1]
      Trade only if:
        - |delta| >= threshold
        - price[i] in [min_price, max_price]
        - trades_per_market < max_trades_per_market

      If delta > 0 -> BUY_YES
      If delta < 0 -> SELL_YES
    """
    decisions: List[StrategyDecision] = []

    for market in markets:
        prices = market.price
        n = len(prices)
        if n < 2:
            continue

        trades_count = 0

        for idx in range(1, n):
            if trades_count >= max_trades_per_market:
                break

            p_now = prices[idx]
            p_prev = prices[idx - 1]
            delta = p_now - p_prev

            if abs(delta) < threshold:
                continue

            # Avoid extremes
            if p_now < min_price or p_now > max_price:
                continue

            if delta > 0:
                side = "BUY_YES"
                p_hat = min(1.0, p_now + 0.05)
            else:
                side = "SELL_YES"
                p_hat = max(0.0, p_now - 0.05)

            decisions.append(
                StrategyDecision(
                    strategy_name=strategy_name,
                    market_id=market.market_id,
                    entry_index=idx,
                    side=side,
                    size=size_fraction,
                    p_hat=p_hat,
                )
            )

            trades_count += 1

    return decisions


# ---------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------

def write_trade_log_csv(decisions: List[StrategyDecision], out_path: Path) -> None:
    """
    Write a combined trade log CSV that evaluate_trade_logs.py can consume.
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


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate trade logs for multiple strategies on canonical market data"
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
    args = parser.parse_args()

    meta_csv = Path(args.meta)
    prices_dir = Path(args.prices_dir)
    out_log = Path(args.out_log)

    # Load canonical markets from engine
    markets = load_markets(meta_csv, prices_dir)

    # Generate decisions for all strategies
    all_decisions: List[StrategyDecision] = []

    all_decisions.extend(generate_baseline_hold_trades(markets))
    all_decisions.extend(generate_swing_trades(markets))
    all_decisions.extend(generate_mean_reversion_trades(markets))
    all_decisions.extend(generate_cross_section_value_trades(markets))
    all_decisions.extend(generate_risk_managed_momo_trades(markets))

    # Write combined log
    write_trade_log_csv(all_decisions, out_log)


if __name__ == "__main__":
    main()

