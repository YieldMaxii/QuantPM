from dataclasses import dataclass
from typing import List
from ..core.models import MarketSeries, TradeRecord

@dataclass
class StrategyContext:
    strategy_name: str
    current_capital: float
    initial_capital: float
    trade_history: List[TradeRecord]
    markets: List[MarketSeries]

