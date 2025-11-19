"""
Minimal META-PM POC engine

Scope:

* One venue (historical prices only).
* 3–5 markets, each with 7–14 days of prices and a resolved binary outcome.
* Fixed set of strategies:

  * PriceFollowerStrategy
  * MomentumStrategy
  * FilteredMomentumStrategy
  * OracleStrategy (cheating baseline)

* Paper-traded PnL, optional Brier / ECE, basic max drawdown.
* Outputs:
  trades.csv  - one row per trade
  scores.csv  - one row per strategy

Usage (example):

```
python engine.py \
    --meta ./data/markets_meta.csv \
    --prices-dir ./data/prices \
    --out-dir ./outputs
```

Expected files:
markets_meta.csv:
market_id,name,outcome
MKT1,"Some election",1
MKT2,"Some CPI print",0
...

```
prices_<market_id>.csv:
    timestamp,price,bid,ask,volume
    2024-01-01T00:00:00,0.42,0.41,0.43,10000
    2024-01-01T06:00:00,0.45,0.44,0.46,12000
    ...
```

You can then build a Jupyter notebook that reads trades.csv and scores.csv,
plots equity curves, and shows a simple leaderboard.
"""

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Iterable, Tuple


# -------------------------- Data model --------------------------

@dataclass
class MarketSeries:
    market_id: str
    name: str
    outcome: float  # usually 0/1 for resolved markets, but can be any [0,1] terminal price
    ts: List[datetime]
    price: List[float]
    bid: Optional[List[float]] = None
    ask: Optional[List[float]] = None
    volume: Optional[List[float]] = None
    slug: Optional[str] = None  # Added for event grouping


@dataclass
class StrategyDecision:
    strategy_name: str
    market_id: str
    entry_index: int
    side: str              # "BUY_YES" or "SELL_YES"
    size: float            # fraction of reference bankroll, e.g. 0.1
    p_hat: float           # predicted probability in [0,1]


@dataclass
class TradeRecord:
    strategy_name: str
    market_id: str
    entry_time: datetime
    side: str
    entry_price: float
    size: float
    p_hat: float
    outcome: float
    pnl: float
    capital_at_entry: float  # capital available when this trade was made


@dataclass
class StrategyScores:
    strategy_name: str
    total_pnl: float
    brier_mean: Optional[float]
    max_drawdown: Optional[float]
    n_trades: int


@dataclass
class StrategyMarketScores:
    strategy_name: str
    market_id: str
    total_pnl: float
    brier_mean: Optional[float]
    max_drawdown: Optional[float]
    n_trades: int


# -------------------------- I/O helpers --------------------------

def parse_timestamp(s: str) -> datetime:
    # Simple ISO-8601 parser. Extend if you have timezones/"Z".
    return datetime.fromisoformat(s)


def load_markets(meta_csv: Path, prices_dir: Path) -> List[MarketSeries]:
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
                raise FileNotFoundError(f"Missing prices file: {prices_path}")

            ts: List[datetime] = []
            price: List[float] = []
            bid: List[float] = []
            ask: List[float] = []
            volume: List[float] = []

            with prices_path.open("r", newline="", encoding="utf-8") as pf:
                preader = csv.DictReader(pf)
                for prow in preader:
                    ts.append(parse_timestamp(prow["timestamp"]))
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

            if len(ts) == 0:
                raise ValueError(f"No price data for market {market_id}")

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


# -------------------------- Strategies --------------------------

class BaseStrategy:
    name: str

    def decide(self, market: MarketSeries) -> Optional[StrategyDecision]:
        raise NotImplementedError


class PriceFollowerStrategy(BaseStrategy):
    """
    Baseline: follow current market price at a fixed entry index.
    If p >= 0.5, buy YES; else sell YES.
    """

    def __init__(self, entry_index: int = 0, size: float = 0.1):
        self.name = "price_follower"
        self.entry_index = entry_index
        self.size = size

    def decide(self, market: MarketSeries) -> Optional[StrategyDecision]:
        if len(market.price) == 0:
            return None
        idx = min(self.entry_index, len(market.price) - 1)
        p = market.price[idx]
        side = "BUY_YES" if p >= 0.5 else "SELL_YES"
        return StrategyDecision(
            strategy_name=self.name,
            market_id=market.market_id,
            entry_index=idx,
            side=side,
            size=self.size,
            p_hat=max(0.0, min(1.0, p)),
        )


class MomentumStrategy(BaseStrategy):
    """
    Simple momentum: compare price vs lookback; trade if drift exceeds threshold.
    """

    def __init__(
        self,
        lookback_steps: int = 3,
        threshold: float = 0.005,
        size: float = 0.1,
    ):
        self.name = "momentum"
        self.lookback_steps = lookback_steps
        self.threshold = threshold
        self.size = size

    def decide(self, market: MarketSeries) -> Optional[StrategyDecision]:
        if len(market.price) <= self.lookback_steps:
            return None
        idx = self.lookback_steps
        p_now = market.price[idx]
        p_prev = market.price[idx - self.lookback_steps]
        delta = p_now - p_prev

        if delta >= self.threshold:
            side = "BUY_YES"
            p_hat = min(1.0, p_now + 0.05)
        elif delta <= -self.threshold:
            side = "SELL_YES"
            p_hat = max(0.0, p_now - 0.05)
        else:
            return None

        return StrategyDecision(
            strategy_name=self.name,
            market_id=market.market_id,
            entry_index=idx,
            side=side,
            size=self.size,
            p_hat=p_hat,
        )


class FilteredMomentumStrategy(BaseStrategy):
    """
    Momentum with simple liquidity/spread filters.
    Requires bid/ask and optionally volume.
    """

    def __init__(
        self,
        lookback_steps: int = 3,
        threshold: float = 0.005,
        max_spread: float = 0.02,
        min_volume: float = 0.0,
        volume_lookback: int = 3,
        size: float = 0.1,
    ):
        self.name = "filtered_momentum"
        self.lookback_steps = lookback_steps
        self.threshold = threshold
        self.max_spread = max_spread
        self.min_volume = min_volume
        self.volume_lookback = volume_lookback
        self.size = size

    def decide(self, market: MarketSeries) -> Optional[StrategyDecision]:
        if len(market.price) <= self.lookback_steps:
            return None
        if market.bid is None or market.ask is None:
            return None  # cannot apply spread filter

        idx = self.lookback_steps
        p_now = market.price[idx]
        p_prev = market.price[idx - self.lookback_steps]
        delta = p_now - p_prev

        # Momentum trigger
        if delta >= self.threshold:
            side = "BUY_YES"
            p_hat = min(1.0, p_now + 0.05)
        elif delta <= -self.threshold:
            side = "SELL_YES"
            p_hat = max(0.0, p_now - 0.05)
        else:
            return None

        # Spread filter
        spread = market.ask[idx] - market.bid[idx]
        if spread > self.max_spread:
            return None

        # Volume filter (if available)
        if market.volume is not None and len(market.volume) > 0 and self.min_volume > 0.0:
            start = max(0, idx - self.volume_lookback + 1)
            vol_recent = sum(market.volume[start : idx + 1])
            if vol_recent < self.min_volume:
                return None

        return StrategyDecision(
            strategy_name=self.name,
            market_id=market.market_id,
            entry_index=idx,
            side=side,
            size=self.size,
            p_hat=p_hat,
        )


class OracleStrategy(BaseStrategy):
    """
    Cheating baseline using the true outcome.
    Uses earliest timestamp; bets YES if outcome=1, NO (short YES) if outcome=0.
    """

    def __init__(self, entry_index: int = 0, size: float = 0.1):
        self.name = "oracle"
        self.entry_index = entry_index
        self.size = size

    def decide(self, market: MarketSeries) -> Optional[StrategyDecision]:
        if len(market.price) == 0:
            return None
        idx = min(self.entry_index, len(market.price) - 1)
        outcome = market.outcome
        if outcome == 1:
            side = "BUY_YES"
            p_hat = 0.99
        else:
            side = "SELL_YES"
            p_hat = 0.01

        return StrategyDecision(
            strategy_name=self.name,
            market_id=market.market_id,
            entry_index=idx,
            side=side,
            size=self.size,
            p_hat=p_hat,
        )


# -------------------------- PnL and metrics --------------------------

def compute_trade_pnl(
    side: str,
    entry_price: float,
    outcome: float,
    size_fraction: float,
    bankroll: float,
) -> float:
    """
    Per-unit PnL:
    BUY_YES  : outcome - entry_price
    SELL_YES : entry_price - outcome
    PnL in currency = per-unit PnL * (size_fraction * bankroll)
    """
    if side == "BUY_YES":
        unit_pnl = outcome - entry_price
    elif side == "SELL_YES":
        unit_pnl = entry_price - outcome
    else:
        raise ValueError(f"Unknown side {side}")
    units = size_fraction * bankroll
    return unit_pnl * units


def brier_score(p_hat: float, outcome: float) -> float:
    return (p_hat - outcome) ** 2


def compute_equity_and_drawdown(trades: List[TradeRecord]) -> Tuple[List[float], float]:
    """
    Compute equity curve and max drawdown for one strategy's trades.
    Trades must already be sorted by entry_time.
    """
    equity: List[float] = []
    cur = 0.0
    max_dd = 0.0
    peak = 0.0

    for tr in trades:
        cur += tr.pnl
        equity.append(cur)
        peak = max(peak, cur)
        dd = peak - cur
        if dd > max_dd:
            max_dd = dd

    return equity, max_dd if trades else 0.0


def compute_scores_by_market(trades: List[TradeRecord]) -> List[StrategyMarketScores]:
    """
    Compute per-strategy, per-market scores from a flat list of TradeRecord.

    For each (strategy_name, market_id) group:
      - total_pnl: sum of pnl
      - n_trades: number of trades
      - brier_mean: mean Brier score over trades in that market
      - max_drawdown: max drawdown on cumulative pnl within that market
    """
    # Group trades by (strategy_name, market_id)
    by_key: Dict[Tuple[str, str], List[TradeRecord]] = {}
    for tr in trades:
        key = (tr.strategy_name, tr.market_id)
        by_key.setdefault(key, []).append(tr)

    scores: List[StrategyMarketScores] = []

    for (strategy_name, market_id), sm_trades in by_key.items():
        # Sort by time for drawdown computation
        sm_trades.sort(key=lambda t: t.entry_time)

        # Cumulative equity and max drawdown for this subset
        _, max_dd = compute_equity_and_drawdown(sm_trades)

        total_pnl = sum(t.pnl for t in sm_trades)
        n = len(sm_trades)

        # Mean Brier score within this market
        if n > 0:
            brier_sum = sum(brier_score(t.p_hat, t.outcome) for t in sm_trades)
            brier_mean = brier_sum / n
        else:
            brier_mean = None

        scores.append(
            StrategyMarketScores(
                strategy_name=strategy_name,
                market_id=market_id,
                total_pnl=total_pnl,
                brier_mean=brier_mean,
                max_drawdown=max_dd if n > 0 else None,
                n_trades=n,
            )
        )

    return scores


# -------------------------- Engine --------------------------

def run_backtest(
    markets: Iterable[MarketSeries],
    strategies: Iterable[BaseStrategy],
    bankroll: float,
) -> Tuple[List[TradeRecord], List[StrategyScores]]:
    """
    Run backtest with built-in strategies.
    
    Each strategy starts with the same initial bankroll.
    Trades are processed chronologically per strategy, with capital tracking:
    - Each trade is sized using current capital (not initial bankroll)
    - Capital is updated after each trade based on P&L
    """
    trades: List[TradeRecord] = []
    scores: List[StrategyScores] = []

    # Build a quick lookup by market_id
    markets_list = list(markets)
    market_by_id: Dict[str, MarketSeries] = {m.market_id: m for m in markets_list}

    # Collect all decisions first, then process chronologically per strategy
    all_decisions: List[Tuple[BaseStrategy, StrategyDecision, datetime]] = []
    
    for strat in strategies:
        for market in markets_list:
            decision = strat.decide(market)
            if decision is None:
                continue

            idx = decision.entry_index
            if idx < 0 or idx >= len(market.price):
                continue  # skip invalid index

            entry_time = market.ts[idx]
            all_decisions.append((strat, decision, entry_time))

    # Group by strategy and sort chronologically
    decisions_by_strategy: Dict[str, List[Tuple[BaseStrategy, StrategyDecision, datetime]]] = {}
    for strat, decision, entry_time in all_decisions:
        decisions_by_strategy.setdefault(strat.name, []).append((strat, decision, entry_time))

    trades_by_strategy: Dict[str, List[TradeRecord]] = {}
    brier_sum: Dict[str, float] = {}
    trade_count: Dict[str, int] = {}

    # Process each strategy's trades chronologically with capital tracking
    for strat_name, decision_list in decisions_by_strategy.items():
        # Sort by entry time
        decision_list.sort(key=lambda x: x[2])

        # Track running capital for this strategy
        current_capital = bankroll

        for strat, decision, entry_time in decision_list:
            market = market_by_id.get(decision.market_id)
            if market is None:
                continue

            idx = decision.entry_index
            if idx < 0 or idx >= len(market.price):
                continue

            entry_price = market.price[idx]

            # Use current capital for position sizing
            pnl = compute_trade_pnl(
                side=decision.side,
                entry_price=entry_price,
                outcome=market.outcome,
                size_fraction=decision.size,
                bankroll=current_capital,  # Use current capital, not initial bankroll
            )

            tr = TradeRecord(
                strategy_name=decision.strategy_name,
                market_id=market.market_id,
                entry_time=entry_time,
                side=decision.side,
                entry_price=entry_price,
                size=decision.size,
                p_hat=decision.p_hat,
                outcome=market.outcome,
                pnl=pnl,
                capital_at_entry=current_capital,
            )

            trades.append(tr)
            trades_by_strategy.setdefault(strat_name, []).append(tr)
            brier_sum[strat_name] = brier_sum.get(strat_name, 0.0) + brier_score(
                decision.p_hat, market.outcome
            )
            trade_count[strat_name] = trade_count.get(strat_name, 0) + 1

            # Update capital after trade
            current_capital += pnl

    # Compute per-strategy metrics
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


# -------------------------- CLI --------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal META-PM POC backtest engine")
    parser.add_argument("--meta", type=str, required=True, help="markets_meta.csv path")
    parser.add_argument(
        "--prices-dir", type=str, required=True, help="directory with prices_<market_id>.csv"
    )
    parser.add_argument(
        "--out-dir", type=str, required=True, help="output directory for CSVs"
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=100.0,
        help="reference bankroll used for sizing (default: 100.0)",
    )
    args = parser.parse_args()

    meta_csv = Path(args.meta)
    prices_dir = Path(args.prices_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    markets = load_markets(meta_csv, prices_dir)

    strategies: List[BaseStrategy] = [
        PriceFollowerStrategy(entry_index=0, size=0.1),
        MomentumStrategy(lookback_steps=3, threshold=0.005, size=0.1),
        FilteredMomentumStrategy(
            lookback_steps=3,
            threshold=0.005,
            max_spread=0.02,
            min_volume=0.0,  # set >0 if your CSV has volume
            volume_lookback=3,
            size=0.1,
        ),
        OracleStrategy(entry_index=0, size=0.1),
    ]

    trades, scores = run_backtest(markets, strategies, bankroll=args.bankroll)

    write_trades_csv(trades, out_dir / "trades.csv")
    write_scores_csv(scores, out_dir / "scores.csv")

    # Per-strategy, per-market scores
    scores_by_market = compute_scores_by_market(trades)
    write_scores_by_market_csv(scores_by_market, out_dir / "scores_by_market.csv")

    print(f"Wrote {len(trades)} trades to {out_dir/'trades.csv'}")
    print(f"Wrote {len(scores)} strategy rows to {out_dir/'scores.csv'}")
    print(f"Wrote {len(scores_by_market)} rows to {out_dir/'scores_by_market.csv'}")


if __name__ == "__main__":
    main()

