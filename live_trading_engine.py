"""
live_trading_engine.py

Real-time trading engine that runs strategies on live Polymarket data.

- Loads live market data from data_live/
- Runs strategies from live_24h_strategies.py
- Generates trades as new price data arrives
- Evaluates trades using current prices (mark-to-market)
- Writes live trade logs to logs_live/
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from engine import (
    load_markets, MarketSeries, StrategyDecision, TradeRecord, 
    compute_trade_pnl, brier_score, parse_timestamp
)
from live_24h_strategies import (
    generate_trend_fast,
    generate_trend_slow,
    generate_mean_revert,
    generate_range_reversion,
    generate_cross_section_spread,
)
from strategy_context import StrategyContext

DATA_LIVE_DIR = Path("data_live")
LOGS_LIVE_DIR = Path("logs_live")
LOGS_LIVE_DIR.mkdir(parents=True, exist_ok=True)

META_PATH = DATA_LIVE_DIR / "markets_live_meta.csv"
PRICES_DIR = DATA_LIVE_DIR
BANKROLL = 100.0
TIMER_STATE_FILE = LOGS_LIVE_DIR / "timer_state.json"


def get_timer_start_time() -> datetime:
    """Get the competition start time from the shared timer state file."""
    if TIMER_STATE_FILE.exists():
        try:
            with TIMER_STATE_FILE.open("r") as f:
                state = json.load(f)
                if "start_time" in state:
                    saved_start = datetime.fromisoformat(state["start_time"])
                    # Check if expired
                    elapsed = datetime.now(timezone.utc) - saved_start
                    if elapsed.total_seconds() < 86400:  # Less than 24 hours
                        return saved_start
        except Exception:
            pass
    # Create new timer if none exists or expired
    new_start = datetime.now(timezone.utc)
    try:
        with TIMER_STATE_FILE.open("w") as f:
            json.dump({"start_time": new_start.isoformat()}, f)
    except Exception:
        pass
    return new_start


class LiveTradingEngine:
    """Engine for running strategies on live data."""
    
    def __init__(self, bankroll: float = 100.0):
        self.bankroll = bankroll
        self.markets: List[MarketSeries] = []
        self.processed_trades: set = set()  # Track processed trades by (strategy, market_id, entry_time)
        self.capital_tracker: Dict[str, float] = {}  # strategy -> current capital
        self.all_trades: List[TradeRecord] = []
        self.strategy_contexts: Dict[str, StrategyContext] = {}  # strategy -> context
        
        # Load historical trades on startup
        self.load_historical_trades()
        
    def load_historical_trades(self) -> None:
        """Load historical trades from CSV to maintain continuity."""
        log_path = LOGS_LIVE_DIR / "live_trades.csv"
        if not log_path.exists():
            return
        
        try:
            with log_path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        trade = TradeRecord(
                            strategy_name=row["strategy_name"],
                            market_id=row["market_id"],
                            entry_time=parse_timestamp(row["entry_time"]),
                            side=row["side"],
                            entry_price=float(row["entry_price"]),
                            size=float(row["size"]),
                            p_hat=float(row["p_hat"]),
                            outcome=float(row["outcome"]),
                            pnl=float(row["pnl"]),
                            capital_at_entry=float(row.get("capital_at_entry", self.bankroll)),
                        )
                        self.all_trades.append(trade)
                        
                        # Track as processed
                        trade_key = (trade.strategy_name, trade.market_id, trade.entry_time.isoformat())
                        self.processed_trades.add(trade_key)
                        
                        # Update capital tracker
                        if trade.strategy_name not in self.capital_tracker:
                            self.capital_tracker[trade.strategy_name] = self.bankroll
                        # Capital should be: last capital + last pnl, but we'll recalculate from trades
                    except Exception as e:
                        print(f"Error loading trade from CSV: {e}")
                        continue
            
            # Recalculate capital for each strategy from historical trades
            for strat_name in set(t.strategy_name for t in self.all_trades):
                strat_trades = sorted(
                    [t for t in self.all_trades if t.strategy_name == strat_name],
                    key=lambda t: t.entry_time
                )
                if strat_trades:
                    # Start with initial bankroll, add P&L from each trade
                    capital = self.bankroll
                    for trade in strat_trades:
                        capital += trade.pnl
                    self.capital_tracker[strat_name] = capital
            
            print(f"Loaded {len(self.all_trades)} historical trades")
        except Exception as e:
            print(f"Error loading historical trades: {e}")
    
    def load_markets(self) -> bool:
        """Load current market data."""
        if not META_PATH.exists():
            return False
        try:
            self.markets = load_markets(META_PATH, PRICES_DIR)
            
            # Update strategy contexts with latest market data
            self._update_strategy_contexts()
            
            return len(self.markets) > 0
        except Exception as e:
            print(f"Error loading markets: {e}")
            return False
    
    def _update_strategy_contexts(self) -> None:
        """Update strategy contexts with current market data and trade history."""
        strategy_names = [
            "live_trend_fast",
            "live_trend_slow",
            "live_mean_revert",
            "live_range_reversion",
            "live_cross_section_spread",
        ]
        
        for strat_name in strategy_names:
            strat_trades = [t for t in self.all_trades if t.strategy_name == strat_name]
            current_capital = self.capital_tracker.get(strat_name, self.bankroll)
            
            self.strategy_contexts[strat_name] = StrategyContext(
                strategy_name=strat_name,
                current_capital=current_capital,
                initial_capital=self.bankroll,
                trade_history=strat_trades,
                markets=self.markets,
            )
    
    def generate_strategy_decisions(self) -> List[StrategyDecision]:
        """Generate new trade decisions from all strategies with context."""
        if not self.markets:
            return []
        
        all_decisions: List[StrategyDecision] = []
        
        # Get contexts for each strategy
        trend_fast_ctx = self.strategy_contexts.get("live_trend_fast")
        trend_slow_ctx = self.strategy_contexts.get("live_trend_slow")
        mean_revert_ctx = self.strategy_contexts.get("live_mean_revert")
        range_revert_ctx = self.strategy_contexts.get("live_range_reversion")
        cross_section_ctx = self.strategy_contexts.get("live_cross_section_spread")
        
        # Generate decisions with context (strategies can adapt based on performance)
        all_decisions.extend(generate_trend_fast(self.markets, trend_fast_ctx))
        all_decisions.extend(generate_trend_slow(self.markets, trend_slow_ctx))
        all_decisions.extend(generate_mean_revert(self.markets, mean_revert_ctx))
        all_decisions.extend(generate_range_reversion(self.markets, range_revert_ctx))
        all_decisions.extend(generate_cross_section_spread(self.markets, cross_section_ctx))
        
        return all_decisions
    
    def evaluate_new_trades(self, decisions: List[StrategyDecision]) -> List[TradeRecord]:
        """
        Evaluate new trades that haven't been processed yet.
        Uses capital tracking - each strategy maintains its own capital.
        """
        market_by_id = {m.market_id: m for m in self.markets}
        new_trades: List[TradeRecord] = []
        
        # Group decisions by strategy and sort by time
        decisions_by_strategy: Dict[str, List[StrategyDecision]] = {}
        for decision in decisions:
            market = market_by_id.get(decision.market_id)
            if market is None:
                continue
            if decision.entry_index < 0 or decision.entry_index >= len(market.price):
                continue
            
            entry_time = market.ts[decision.entry_index]
            decisions_by_strategy.setdefault(decision.strategy_name, []).append((decision, entry_time))
        
        # Process each strategy's trades chronologically
        for strat_name, decision_list in decisions_by_strategy.items():
            # Sort by time
            decision_list.sort(key=lambda x: x[1])
            
            # Initialize capital if needed
            if strat_name not in self.capital_tracker:
                self.capital_tracker[strat_name] = self.bankroll
            
            current_capital = self.capital_tracker[strat_name]
            
            # Process new decisions
            for decision, entry_time in decision_list:
                # Check if we've already processed this trade
                # Use strategy + market_id + entry_time as unique key
                trade_key = (strat_name, decision.market_id, entry_time.isoformat())
                if trade_key in self.processed_trades:
                    continue
                
                market = market_by_id[decision.market_id]
                entry_price = market.price[decision.entry_index]
                
                # Use current capital for sizing
                pnl = compute_trade_pnl(
                    side=decision.side,
                    entry_price=entry_price,
                    outcome=market.outcome,  # Current price as outcome (mark-to-market)
                    size_fraction=decision.size,
                    bankroll=current_capital,
                )
                
                trade = TradeRecord(
                    strategy_name=decision.strategy_name,
                    market_id=decision.market_id,
                    entry_time=entry_time,
                    side=decision.side,
                    entry_price=entry_price,
                    size=decision.size,
                    p_hat=decision.p_hat,
                    outcome=market.outcome,
                    pnl=pnl,
                    capital_at_entry=current_capital,
                )
                
                new_trades.append(trade)
                self.all_trades.append(trade)
                self.processed_trades.add(trade_key)
                
                # Update capital
                current_capital += pnl
                self.capital_tracker[strat_name] = current_capital
                
                # Update strategy context with new trade
                if strat_name in self.strategy_contexts:
                    self.strategy_contexts[strat_name].trade_history.append(trade)
                    self.strategy_contexts[strat_name].current_capital = current_capital
        
        return new_trades
    
    def run_cycle(self) -> Dict[str, any]:
        """
        Run one cycle of the trading engine.
        Returns status dict with new trades info.
        """
        if not self.load_markets():
            return {"status": "no_markets", "new_trades": 0}
        
        # Check if competition timer has expired
        timer_start = get_timer_start_time()
        elapsed = datetime.now(timezone.utc) - timer_start
        if elapsed.total_seconds() >= 86400:
            # Competition ended - no new trades
            return {
                "status": "competition_ended",
                "new_trades": 0,
                "total_trades": len(self.all_trades),
                "markets": len(self.markets),
                "strategies": len(self.capital_tracker),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "timer_remaining_seconds": 0,
            }
        
        decisions = self.generate_strategy_decisions()
        new_trades = self.evaluate_new_trades(decisions)
        
        # Write new trades to log
        if new_trades:
            self.write_trades_to_log(new_trades)
        
        remaining_seconds = max(0, 86400 - elapsed.total_seconds())
        
        return {
            "status": "success",
            "new_trades": len(new_trades),
            "total_trades": len(self.all_trades),
            "markets": len(self.markets),
            "strategies": len(self.capital_tracker),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timer_remaining_seconds": remaining_seconds,
        }
    
    def write_trades_to_log(self, trades: List[TradeRecord]) -> None:
        """Append trades to live trade log."""
        log_path = LOGS_LIVE_DIR / "live_trades.csv"
        
        # Write header if file doesn't exist
        file_exists = log_path.exists()
        
        with log_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow([
                    "strategy_name", "market_id", "entry_time", "side",
                    "entry_price", "size", "p_hat", "outcome", "pnl", "capital_at_entry"
                ])
            
            for trade in trades:
                writer.writerow([
                    trade.strategy_name,
                    trade.market_id,
                    trade.entry_time.isoformat(),
                    trade.side,
                    f"{trade.entry_price:.6f}",
                    f"{trade.size:.6f}",
                    f"{trade.p_hat:.6f}",
                    f"{trade.outcome:.6f}",
                    f"{trade.pnl:.6f}",
                    f"{trade.capital_at_entry:.6f}",
                ])
    
    def get_strategy_performance(self) -> Dict[str, Dict[str, float]]:
        """Get current performance metrics per strategy."""
        performance: Dict[str, Dict[str, float]] = {}
        
        for strat_name in self.capital_tracker.keys():
            strat_trades = [t for t in self.all_trades if t.strategy_name == strat_name]
            if not strat_trades:
                continue
            
            total_pnl = sum(t.pnl for t in strat_trades)
            current_capital = self.capital_tracker[strat_name]
            n_trades = len(strat_trades)
            
            # Calculate Brier score
            brier_sum = sum(brier_score(t.p_hat, t.outcome) for t in strat_trades)
            brier_mean = brier_sum / n_trades if n_trades > 0 else None
            
            performance[strat_name] = {
                "total_pnl": total_pnl,
                "current_capital": current_capital,
                "n_trades": n_trades,
                "brier_mean": brier_mean,
            }
        
        return performance


def main():
    """Run the live trading engine once."""
    engine = LiveTradingEngine(bankroll=BANKROLL)
    result = engine.run_cycle()
    print(f"Status: {result['status']}")
    print(f"New trades: {result['new_trades']}")
    print(f"Total trades: {result['total_trades']}")
    
    if result['status'] == 'success':
        perf = engine.get_strategy_performance()
        print("\nStrategy Performance:")
        for strat, metrics in perf.items():
            print(f"  {strat}: P&L={metrics['total_pnl']:.3f}, Capital={metrics['current_capital']:.3f}, Trades={metrics['n_trades']}")


if __name__ == "__main__":
    main()

