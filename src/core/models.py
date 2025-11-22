from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class MarketSeries:
    market_id: str
    name: str
    outcome: float  # 0.0 to 1.0 (float for mark-to-market)
    ts: List[datetime]
    price: List[float]
    bid: Optional[List[float]] = None
    ask: Optional[List[float]] = None
    volume: Optional[List[float]] = None
    slug: Optional[str] = None

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
    capital_at_entry: float = 0.0

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

