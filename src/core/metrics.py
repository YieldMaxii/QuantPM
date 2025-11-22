from typing import List, Tuple, Optional, Dict
from .models import TradeRecord, StrategyMarketScores

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

