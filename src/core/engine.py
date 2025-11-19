"""
Core trading engine for evaluating trades and computing performance.

Provides market loading, trade evaluation, and CSV I/O utilities.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .metrics import brier_score, compute_equity_and_drawdown, compute_trade_pnl
from .models import (
    MarketSeries,
    StrategyDecision,
    StrategyScores,
    StrategyMarketScores,
    TradeRecord,
)


def parse_timestamp(s: str) -> datetime:
    """Parse ISO-8601 timestamp string."""
    return datetime.fromisoformat(s)


def load_markets(meta_csv: Path, prices_dir: Path, timer_start: datetime = None) -> List[MarketSeries]:
    """
    Load market data from CSV files.
    
    Args:
        meta_csv: Path to market metadata CSV
        prices_dir: Directory containing price CSV files
        timer_start: Optional competition start time - filters out price data before this time
    """
    markets: List[MarketSeries] = []

    with meta_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            market_id = row["market_id"]
            name = row.get("name", market_id)
            outcome = float(row["outcome"])
            slug = row.get("slug", "")  # Read slug if available

            prices_path = prices_dir / f"prices_{market_id}.csv"
            if not prices_path.exists():
                # Skip markets without price files (they'll be created by data service)
                continue

            ts: List[datetime] = []
            price: List[float] = []
            bid: List[float] = []
            ask: List[float] = []
            volume: List[float] = []

            with prices_path.open("r", newline="", encoding="utf-8") as pf:
                preader = csv.DictReader(pf)
                for prow in preader:
                    timestamp = parse_timestamp(prow["timestamp"])
                    
                    # Filter out data from before competition start
                    if timer_start is not None and timestamp < timer_start:
                        continue
                    
                    ts.append(timestamp)
                    price.append(float(prow["price"]))
                    if "bid" in preader.fieldnames and prow.get("bid"):
                        bid.append(float(prow["bid"]))
                    if "ask" in preader.fieldnames and prow.get("ask"):
                        ask.append(float(prow["ask"]))
                    if "volume" in preader.fieldnames and prow.get("volume"):
                        volume.append(float(prow["volume"]))

            # Normalize optional arrays to None if empty
            bid_arr = bid if bid else None
            ask_arr = ask if ask else None
            vol_arr = volume if volume else None

            # Skip markets with no valid price data (after filtering)
            if len(ts) == 0:
                continue

            markets.append(
                MarketSeries(
                    market_id=market_id,
                    name=name,
                    outcome=outcome,
                    ts=ts,
                    price=price,
                    bid=bid_arr,
                    ask=ask_arr,
                    volume=vol_arr,
                    slug=slug,
                )
            )

    return markets


def evaluate_trade_log(
    markets: Iterable[MarketSeries],
    trade_specs: Iterable[StrategyDecision],
    bankroll: float,
) -> Tuple[List[TradeRecord], List[StrategyScores]]:
    """
    Evaluate an arbitrary trade log (possibly multiple trades per market per strategy).

    trade_specs is a sequence of StrategyDecision objects interpreted as:
        - strategy_name
        - market_id
        - entry_index
        - side
        - size
        - p_hat

    The engine:
        - Looks up canonical prices via market_id and entry_index.
        - Processes trades chronologically per strategy.
        - Tracks running capital per strategy (starts at bankroll, updates after each trade).
        - Uses current capital for position sizing (size_fraction * current_capital).
        - Computes PnL using compute_trade_pnl (settling at final outcome).
        - Aggregates per-strategy scores (total_pnl, Brier, max_drawdown, n_trades).

    This is what you use to evaluate real miner strategies that submit
    full trade logs.
    """
    markets_list = list(markets)
    market_by_id: Dict[str, MarketSeries] = {m.market_id: m for m in markets_list}

    # Group trade specs by strategy and create tuples with entry_time for sorting
    specs_with_time: List[Tuple[StrategyDecision, datetime]] = []
    for spec in trade_specs:
        market = market_by_id.get(spec.market_id)
        if market is None:
            continue
        idx = spec.entry_index
        if idx < 0 or idx >= len(market.price):
            continue
        entry_time = market.ts[idx]
        specs_with_time.append((spec, entry_time))

    # Group by strategy and sort chronologically
    specs_by_strategy: Dict[str, List[Tuple[StrategyDecision, datetime]]] = {}
    for spec, entry_time in specs_with_time:
        specs_by_strategy.setdefault(spec.strategy_name, []).append((spec, entry_time))

    # Process each strategy's trades chronologically with capital tracking
    trades: List[TradeRecord] = []
    trades_by_strategy: Dict[str, List[TradeRecord]] = {}
    brier_sum: Dict[str, float] = {}
    trade_count: Dict[str, int] = {}

    for strat_name, spec_list in specs_by_strategy.items():
        # Sort by entry time
        spec_list.sort(key=lambda x: x[1])

        # Track running capital for this strategy
        current_capital = bankroll

        for spec, entry_time in spec_list:
            market = market_by_id.get(spec.market_id)
            if market is None:
                continue

            idx = spec.entry_index
            if idx < 0 or idx >= len(market.price):
                continue

            entry_price = market.price[idx]

            # Use current capital for position sizing
            pnl = compute_trade_pnl(
                side=spec.side,
                entry_price=entry_price,
                outcome=market.outcome,
                size_fraction=spec.size,
                bankroll=current_capital,  # Use current capital, not initial bankroll
            )

            tr = TradeRecord(
                strategy_name=spec.strategy_name,
                market_id=spec.market_id,
                entry_time=entry_time,
                side=spec.side,
                entry_price=entry_price,
                size=spec.size,
                p_hat=spec.p_hat,
                outcome=market.outcome,
                pnl=pnl,
                capital_at_entry=current_capital,
            )

            trades.append(tr)
            trades_by_strategy.setdefault(strat_name, []).append(tr)
            brier_sum[strat_name] = brier_sum.get(strat_name, 0.0) + brier_score(
                spec.p_hat, market.outcome
            )
            trade_count[strat_name] = trade_count.get(strat_name, 0) + 1

            # Update capital after trade (capital grows/shrinks with P&L)
            current_capital += pnl

    # Aggregate per-strategy scores
    scores: List[StrategyScores] = []
    for strat_name, strat_trades in trades_by_strategy.items():
        strat_trades.sort(key=lambda t: t.entry_time)
        _, max_dd = compute_equity_and_drawdown(strat_trades)
        n = trade_count.get(strat_name, 0)
        total_pnl = sum(t.pnl for t in strat_trades)
        brier_mean = brier_sum[strat_name] / n if n > 0 else None

        scores.append(
            StrategyScores(
                strategy_name=strat_name,
                total_pnl=total_pnl,
                brier_mean=brier_mean,
                max_drawdown=max_dd if n > 0 else None,
                n_trades=n,
            )
        )

    return trades, scores


# -------------------------- CSV writers --------------------------


def write_trades_csv(trades: List[TradeRecord], out_path: Path) -> None:
    """Write trades to CSV file."""
    fieldnames = [
        "strategy_name",
        "market_id",
        "entry_time",
        "side",
        "entry_price",
        "size",
        "p_hat",
        "outcome",
        "pnl",
        "capital_at_entry",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for tr in trades:
            w.writerow(
                {
                    "strategy_name": tr.strategy_name,
                    "market_id": tr.market_id,
                    "entry_time": tr.entry_time.isoformat(),
                    "side": tr.side,
                    "entry_price": f"{tr.entry_price:.6f}",
                    "size": f"{tr.size:.6f}",
                    "p_hat": f"{tr.p_hat:.6f}",
                    "outcome": f"{tr.outcome:.6f}",
                    "pnl": f"{tr.pnl:.6f}",
                    "capital_at_entry": f"{tr.capital_at_entry:.6f}",
                }
            )


def write_scores_csv(scores: List[StrategyScores], out_path: Path) -> None:
    """Write strategy scores to CSV file."""
    fieldnames = [
        "strategy_name",
        "total_pnl",
        "brier_mean",
        "max_drawdown",
        "n_trades",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for s in scores:
            w.writerow(
                {
                    "strategy_name": s.strategy_name,
                    "total_pnl": f"{s.total_pnl:.6f}",
                    "brier_mean": "" if s.brier_mean is None else f"{s.brier_mean:.6f}",
                    "max_drawdown": ""
                    if s.max_drawdown is None
                    else f"{s.max_drawdown:.6f}",
                    "n_trades": s.n_trades,
                }
            )


def write_scores_by_market_csv(
    scores_by_market: List[StrategyMarketScores],
    out_path: Path,
) -> None:
    """Write per-market strategy scores to CSV file."""
    fieldnames = [
        "strategy_name",
        "market_id",
        "total_pnl",
        "brier_mean",
        "max_drawdown",
        "n_trades",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for s in scores_by_market:
            w.writerow(
                {
                    "strategy_name": s.strategy_name,
                    "market_id": s.market_id,
                    "total_pnl": f"{s.total_pnl:.6f}",
                    "brier_mean": ""
                    if s.brier_mean is None
                    else f"{s.brier_mean:.6f}",
                    "max_drawdown": ""
                    if s.max_drawdown is None
                    else f"{s.max_drawdown:.6f}",
                    "n_trades": s.n_trades,
                }
            )

