"""
strategy_context.py

Provides context and historical data to strategies for adaptive decision-making.

Strategies can access:
- Their own trade history
- Current P&L and capital
- Historical market data
- Performance metrics
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict

from engine import TradeRecord, MarketSeries


@dataclass
class StrategyContext:
    """Context provided to strategies for adaptive decision-making."""
    
    strategy_name: str
    current_capital: float
    initial_capital: float
    trade_history: List[TradeRecord]
    markets: List[MarketSeries]
    
    def get_total_pnl(self) -> float:
        """Get total P&L from all trades."""
        return sum(t.pnl for t in self.trade_history)
    
    def get_recent_trades(self, n: int = 10) -> List[TradeRecord]:
        """Get the N most recent trades."""
        sorted_trades = sorted(self.trade_history, key=lambda t: t.entry_time, reverse=True)
        return sorted_trades[:n]
    
    def get_trades_by_market(self, market_id: str) -> List[TradeRecord]:
        """Get all trades for a specific market."""
        return [t for t in self.trade_history if t.market_id == market_id]
    
    def get_win_rate(self) -> float:
        """Calculate win rate (fraction of profitable trades)."""
        if not self.trade_history:
            return 0.0
        wins = sum(1 for t in self.trade_history if t.pnl > 0)
        return wins / len(self.trade_history)
    
    def get_avg_trade_pnl(self) -> float:
        """Calculate average P&L per trade."""
        if not self.trade_history:
            return 0.0
        return sum(t.pnl for t in self.trade_history) / len(self.trade_history)
    
    def get_cumulative_pnl_curve(self) -> List[float]:
        """Get cumulative P&L over time."""
        sorted_trades = sorted(self.trade_history, key=lambda t: t.entry_time)
        cumulative = []
        running_total = 0.0
        for trade in sorted_trades:
            running_total += trade.pnl
            cumulative.append(running_total)
        return cumulative
    
    def get_max_drawdown(self) -> float:
        """Calculate maximum drawdown."""
        if not self.trade_history:
            return 0.0
        cumulative = self.get_cumulative_pnl_curve()
        if not cumulative:
            return 0.0
        
        max_dd = 0.0
        peak = 0.0
        for value in cumulative:
            peak = max(peak, value)
            dd = peak - value
            max_dd = max(max_dd, dd)
        return max_dd
    
    def get_capital_return_pct(self) -> float:
        """Get return percentage based on initial capital."""
        if self.initial_capital == 0:
            return 0.0
        return (self.current_capital - self.initial_capital) / self.initial_capital * 100.0
    
    def get_market_performance(self, market_id: str) -> Dict[str, float]:
        """Get performance metrics for a specific market."""
        market_trades = self.get_trades_by_market(market_id)
        if not market_trades:
            return {
                "total_pnl": 0.0,
                "n_trades": 0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
            }
        
        total_pnl = sum(t.pnl for t in market_trades)
        wins = sum(1 for t in market_trades if t.pnl > 0)
        
        return {
            "total_pnl": total_pnl,
            "n_trades": len(market_trades),
            "win_rate": wins / len(market_trades) if market_trades else 0.0,
            "avg_pnl": total_pnl / len(market_trades) if market_trades else 0.0,
        }

