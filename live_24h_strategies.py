"""
live_24h_strategies.py

Generate trade logs for 5 intraday strategies over the last 24h of live Polymarket data.

- Reads:
    data_live/markets_live_meta.csv
    data_live/prices_L*.csv
- Uses engine.load_markets to get MarketSeries objects.
- For each strategy, emits multiple StrategyDecision entries across time.
- Writes:
    logs/live_24h_strategies_trades.csv

You then evaluate this log with evaluate_trade_logs.py.
"""

import csv
from pathlib import Path
from statistics import mean
from typing import List

from typing import Optional
from engine import load_markets, MarketSeries, StrategyDecision
from strategy_context import StrategyContext

DATA_LIVE_DIR = Path("data_live")
META_PATH = DATA_LIVE_DIR / "markets_live_meta.csv"
PRICES_DIR = DATA_LIVE_DIR
LOG_PATH = Path("logs/live_24h_strategies_trades.csv")


def generate_trend_fast(markets: List[MarketSeries], context: Optional[StrategyContext] = None) -> List[StrategyDecision]:
    """
    Strategy 1: Fast trend-following.
    - Lookback: 5 steps (≈ 5 minutes).
    - Threshold: 0.01 (1 percentage-point move).
    - If price increased > threshold over 5 minutes => BUY_YES.
    - If price decreased < -threshold => SELL_YES.
    
    Adaptive behavior:
    - Reduces position size if win rate < 40%
    - Increases position size if win rate > 60% and capital > initial
    """
    decisions: List[StrategyDecision] = []
    lookback = 5
    threshold = 0.01
    base_size = 0.02
    
    # Adaptive sizing based on performance
    if context:
        win_rate = context.get_win_rate()
        capital_return = context.get_capital_return_pct()
        
        # Reduce size if performing poorly
        if win_rate < 0.40 or capital_return < -10:
            size = base_size * 0.5  # Reduce to 50%
        # Increase size if performing well and have gains
        elif win_rate > 0.60 and capital_return > 5:
            size = base_size * 1.5  # Increase to 150%
        else:
            size = base_size
    else:
        size = base_size

    for m in markets:
        n = len(m.price)
        for idx in range(lookback, n):
            p_now = m.price[idx]
            p_prev = m.price[idx - lookback]
            delta = p_now - p_prev
            if delta > threshold:
                side = "BUY_YES"
                p_hat = min(1.0, p_now + 0.05)
            elif delta < -threshold:
                side = "SELL_YES"
                p_hat = max(0.0, p_now - 0.05)
            else:
                continue

            decisions.append(
                StrategyDecision(
                    strategy_name="live_trend_fast",
                    market_id=m.market_id,
                    entry_index=idx,
                    side=side,
                    size=size,
                    p_hat=p_hat,
                )
            )
    return decisions


def generate_trend_slow(markets: List[MarketSeries], context: Optional[StrategyContext] = None) -> List[StrategyDecision]:
    """
    Strategy 2: Slow trend-following.
    - Lookback: 30 steps (≈ 30 minutes).
    - Threshold: 0.02 (2 percentage points).
    - Larger moves, fewer trades.
    
    Adaptive behavior:
    - Adjusts threshold based on recent performance
    """
    decisions: List[StrategyDecision] = []
    lookback = 30
    base_threshold = 0.02
    base_size = 0.05
    
    # Adaptive threshold based on performance
    if context:
        recent_trades = context.get_recent_trades(10)
        if recent_trades:
            recent_win_rate = sum(1 for t in recent_trades if t.pnl > 0) / len(recent_trades)
            # Tighten threshold if winning (be more selective)
            if recent_win_rate > 0.6:
                threshold = base_threshold * 1.2
            # Widen threshold if losing (be less selective)
            elif recent_win_rate < 0.4:
                threshold = base_threshold * 0.8
            else:
                threshold = base_threshold
        else:
            threshold = base_threshold
        
        # Adjust size based on capital
        if context.current_capital < context.initial_capital * 0.8:
            size = base_size * 0.7  # Reduce risk if down
        else:
            size = base_size
    else:
        threshold = base_threshold
        size = base_size

    for m in markets:
        n = len(m.price)
        for idx in range(lookback, n):
            p_now = m.price[idx]
            p_prev = m.price[idx - lookback]
            delta = p_now - p_prev
            if delta > threshold:
                side = "BUY_YES"
                p_hat = min(1.0, p_now + 0.10)
            elif delta < -threshold:
                side = "SELL_YES"
                p_hat = max(0.0, p_now - 0.10)
            else:
                continue

            decisions.append(
                StrategyDecision(
                    strategy_name="live_trend_slow",
                    market_id=m.market_id,
                    entry_index=idx,
                    side=side,
                    size=size,
                    p_hat=p_hat,
                )
            )
    return decisions


def generate_mean_revert(markets: List[MarketSeries], context: Optional[StrategyContext] = None) -> List[StrategyDecision]:
    """
    Strategy 3: Mean-reversion intraday.
    - Rolling window: 60 steps (≈ 1 hour).
    - If price is below MA - 0.01 => BUY_YES.
    - If price is above MA + 0.01 => SELL_YES.
    
    Adaptive behavior:
    - Adjusts band width based on volatility and performance
    """
    decisions: List[StrategyDecision] = []
    window = 60
    base_band = 0.01
    base_size = 0.03
    
    # Adaptive band based on performance
    if context:
        max_dd = context.get_max_drawdown()
        # Widen band if experiencing large drawdowns
        if max_dd > 5.0:
            band = base_band * 1.5
        else:
            band = base_band
        
        # Reduce size if losing
        if context.get_total_pnl() < -5.0:
            size = base_size * 0.6
        else:
            size = base_size
    else:
        band = base_band
        size = base_size

    for m in markets:
        n = len(m.price)
        for idx in range(window, n):
            window_prices = m.price[idx - window : idx]
            ma = sum(window_prices) / len(window_prices)
            p_now = m.price[idx]
            diff = p_now - ma
            if diff < -band:
                side = "BUY_YES"
                p_hat = min(1.0, ma)
            elif diff > band:
                side = "SELL_YES"
                p_hat = max(0.0, ma)
            else:
                continue

            decisions.append(
                StrategyDecision(
                    strategy_name="live_mean_revert",
                    market_id=m.market_id,
                    entry_index=idx,
                    side=side,
                    size=size,
                    p_hat=p_hat,
                )
            )
    return decisions


def generate_range_reversion(markets: List[MarketSeries], context: Optional[StrategyContext] = None) -> List[StrategyDecision]:
    """
    Strategy 4: Range-based contrarian.
    - Compute per-market 24h min and max.
    - If price near lower 20% of range => BUY_YES.
    - If price near upper 20% of range => SELL_YES.
    
    Adaptive behavior:
    - Adjusts cutoffs based on recent performance per market
    """
    decisions: List[StrategyDecision] = []
    base_size = 0.04
    base_lower_cut = 0.2
    base_upper_cut = 0.8

    for m in markets:
        prices = m.price
        if not prices:
            continue
        p_min = min(prices)
        p_max = max(prices)
        rng = p_max - p_min
        if rng <= 0:
            continue

        # Get market-specific performance
        if context:
            market_perf = context.get_market_performance(m.market_id)
            # Adjust cutoffs based on market performance
            if market_perf["total_pnl"] < -2.0:
                # If losing on this market, be more conservative
                lower_cut = base_lower_cut * 0.5  # Only trade at extremes
                upper_cut = base_upper_cut + (1 - base_upper_cut) * 0.5
                size = base_size * 0.7
            else:
                lower_cut = base_lower_cut
                upper_cut = base_upper_cut
                size = base_size
        else:
            lower_cut = base_lower_cut
            upper_cut = base_upper_cut
            size = base_size

        for idx, p in enumerate(prices):
            pos = (p - p_min) / rng  # 0 = min, 1 = max
            if pos <= lower_cut:
                side = "BUY_YES"
                p_hat = min(1.0, p + 0.05)
            elif pos >= upper_cut:
                side = "SELL_YES"
                p_hat = max(0.0, p - 0.05)
            else:
                continue

            decisions.append(
                StrategyDecision(
                    strategy_name="live_range_reversion",
                    market_id=m.market_id,
                    entry_index=idx,
                    side=side,
                    size=size,
                    p_hat=p_hat,
                )
            )
    return decisions


def generate_cross_section_spread(markets: List[MarketSeries], context: Optional[StrategyContext] = None) -> List[StrategyDecision]:
    """
    Strategy 5: Cross-sectional Momentum (Relative Strength).
    - Groups markets by event (slug).
    - For each group and time index i:
        * Compute % change over last 10 minutes for each market.
        * Compute average % change of the group.
        * If market change > avg + threshold => BUY_YES (Momentum).
        * If market change < avg - threshold => SELL_YES.
    
    Adaptive behavior:
    - Adjusts threshold based on overall performance
    """
    decisions: List[StrategyDecision] = []
    base_size = 0.02
    base_threshold = 0.01  # 1% relative outperformance
    lookback = 10
    
    # Adaptive threshold
    if context:
        avg_trade_pnl = context.get_avg_trade_pnl()
        if avg_trade_pnl > 0.1:
            threshold = base_threshold * 1.2
            size = base_size * 1.2
        elif avg_trade_pnl < -0.1:
            threshold = base_threshold * 0.8
            size = base_size * 0.7
        else:
            threshold = base_threshold
            size = base_size
    else:
        threshold = base_threshold
        size = base_size

    # Group markets by slug
    markets_by_slug = {}
    for m in markets:
        slug = m.slug or "unknown"
        markets_by_slug.setdefault(slug, []).append(m)

    for slug, group_markets in markets_by_slug.items():
        n_markets = len(group_markets)
        if n_markets < 2:
            continue

        # Filter out markets with too little history
        valid_markets = [m for m in group_markets if len(m.price) > lookback]
        if len(valid_markets) < 2:
            continue
            
        min_len = min(len(m.price) for m in valid_markets)

        for idx in range(lookback, min_len):
            # Calculate returns
            returns = []
            for m in valid_markets:
                p_now = m.price[idx]
                p_prev = m.price[idx - lookback]
                # Avoid division by zero, use simple delta for low price assets
                if p_prev > 0.05:
                    ret = (p_now - p_prev) / p_prev
                else:
                    ret = (p_now - p_prev) # Simple delta for cheap options
                returns.append(ret)
            
            avg_ret = mean(returns)

            for m, ret in zip(valid_markets, returns):
                diff = ret - avg_ret
                p_now = m.price[idx]
                
                if diff > threshold:
                    side = "BUY_YES"
                    p_hat = min(1.0, p_now + 0.05)
                elif diff < -threshold:
                    side = "SELL_YES"
                    p_hat = max(0.0, p_now - 0.05)
                else:
                    continue

                decisions.append(
                    StrategyDecision(
                        strategy_name="live_cross_section_spread",
                        market_id=m.market_id,
                        entry_index=idx,
                        side=side,
                        size=size,
                        p_hat=p_hat,
                    )
                )

    return decisions


def write_trade_log(decisions: List[StrategyDecision], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["strategy_name", "market_id", "entry_index", "side", "size", "p_hat"])
        for d in decisions:
            writer.writerow(
                [
                    d.strategy_name,
                    d.market_id,
                    d.entry_index,
                    d.side,
                    f"{d.size:.6f}",
                    f"{d.p_hat:.6f}",
                ]
            )


def main() -> None:
    print(f"Loading live markets from {META_PATH} ...")
    markets = load_markets(META_PATH, PRICES_DIR)
    print(f"Loaded {len(markets)} live markets")

    all_decisions: List[StrategyDecision] = []

    print("Generating trades for live_trend_fast...")
    all_decisions.extend(generate_trend_fast(markets))
    print("Generating trades for live_trend_slow...")
    all_decisions.extend(generate_trend_slow(markets))
    print("Generating trades for live_mean_revert...")
    all_decisions.extend(generate_mean_revert(markets))
    print("Generating trades for live_range_reversion...")
    all_decisions.extend(generate_range_reversion(markets))
    print("Generating trades for live_cross_section_spread...")
    all_decisions.extend(generate_cross_section_spread(markets))

    print(f"Total trades generated: {len(all_decisions)}")
    write_trade_log(all_decisions, LOG_PATH)
    print(f"Wrote trade log to {LOG_PATH}")


if __name__ == "__main__":
    main()

