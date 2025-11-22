from typing import List
from ..core.models import MarketSeries, StrategyDecision
from .base import StrategyContext

# ---------------------------------------------------------------------
# 1. Trend Following (Fast)
# ---------------------------------------------------------------------
def generate_trend_fast(
    markets: List[MarketSeries],
    context: StrategyContext,
    lookback: int = 5,
    threshold: float = 0.02,
    size_fraction: float = 0.1
) -> List[StrategyDecision]:
    """
    Fast trend following:
    If price moved > threshold over 'lookback' minutes, follow the trend.
    """
    decisions: List[StrategyDecision] = []
    for market in markets:
        if len(market.price) <= lookback:
            continue
            
        idx = len(market.price) - 1
        p_now = market.price[idx]
        p_prev = market.price[idx - lookback]
        delta = p_now - p_prev
        
        if delta >= threshold:
            side = "BUY_YES"
            p_hat = min(1.0, p_now + 0.05)
            decisions.append(StrategyDecision(
                strategy_name="live_trend_fast",
                market_id=market.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
        elif delta <= -threshold:
            side = "SELL_YES"
            p_hat = max(0.0, p_now - 0.05)
            decisions.append(StrategyDecision(
                strategy_name="live_trend_fast",
                market_id=market.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
            
    return decisions

# ---------------------------------------------------------------------
# 2. Trend Following (Slow)
# ---------------------------------------------------------------------
def generate_trend_slow(
    markets: List[MarketSeries],
    context: StrategyContext,
    lookback: int = 60,  # 1 hour
    threshold: float = 0.05,
    size_fraction: float = 0.1
) -> List[StrategyDecision]:
    """
    Slow trend following:
    If price moved > threshold over 'lookback' minutes, follow the trend.
    """
    decisions: List[StrategyDecision] = []
    for market in markets:
        if len(market.price) <= lookback:
            continue
            
        idx = len(market.price) - 1
        p_now = market.price[idx]
        p_prev = market.price[idx - lookback]
        delta = p_now - p_prev
        
        if delta >= threshold:
            side = "BUY_YES"
            p_hat = min(1.0, p_now + 0.05)
            decisions.append(StrategyDecision(
                strategy_name="live_trend_slow",
                market_id=market.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
        elif delta <= -threshold:
            side = "SELL_YES"
            p_hat = max(0.0, p_now - 0.05)
            decisions.append(StrategyDecision(
                strategy_name="live_trend_slow",
                market_id=market.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
            
    return decisions

# ---------------------------------------------------------------------
# 3. Mean Reversion
# ---------------------------------------------------------------------
def generate_mean_revert(
    markets: List[MarketSeries],
    context: StrategyContext,
    window: int = 20,
    threshold: float = 0.05,
    size_fraction: float = 0.1
) -> List[StrategyDecision]:
    """
    Mean reversion:
    If current price deviates from rolling mean by > threshold, bet on reversion.
    """
    decisions: List[StrategyDecision] = []
    for market in markets:
        if len(market.price) <= window:
            continue
            
        idx = len(market.price) - 1
        p_now = market.price[idx]
        
        # Calculate simple moving average
        recent_prices = market.price[idx-window:idx]
        sma = sum(recent_prices) / len(recent_prices)
        
        diff = p_now - sma
        
        if diff >= threshold:
            # Price is too high, sell
            side = "SELL_YES"
            p_hat = max(0.0, sma)
            decisions.append(StrategyDecision(
                strategy_name="live_mean_revert",
                market_id=market.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
        elif diff <= -threshold:
            # Price is too low, buy
            side = "BUY_YES"
            p_hat = min(1.0, sma)
            decisions.append(StrategyDecision(
                strategy_name="live_mean_revert",
                market_id=market.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
            
    return decisions

# ---------------------------------------------------------------------
# 4. Range Reversion (RSI-like)
# ---------------------------------------------------------------------
def generate_range_reversion(
    markets: List[MarketSeries],
    context: StrategyContext,
    min_price: float = 0.15,
    max_price: float = 0.85,
    size_fraction: float = 0.1
) -> List[StrategyDecision]:
    """
    Simple range bound strategy.
    Buy if price < min_price, Sell if price > max_price.
    Assumes markets generally stay within bounds.
    """
    decisions: List[StrategyDecision] = []
    for market in markets:
        if not market.price:
            continue
            
        idx = len(market.price) - 1
        p_now = market.price[idx]
        
        if p_now < min_price:
            side = "BUY_YES"
            p_hat = 0.5 # Expect reversion to mean
            decisions.append(StrategyDecision(
                strategy_name="live_range_reversion",
                market_id=market.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
        elif p_now > max_price:
            side = "SELL_YES"
            p_hat = 0.5
            decisions.append(StrategyDecision(
                strategy_name="live_range_reversion",
                market_id=market.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
            
    return decisions

# ---------------------------------------------------------------------
# 5. Cross-Sectional Spread
# ---------------------------------------------------------------------
def generate_cross_section_spread(
    markets: List[MarketSeries],
    context: StrategyContext,
    size_fraction: float = 0.1
) -> List[StrategyDecision]:
    """
    Cross-sectional strategy:
    Compare each market's price to the average of all markets (in the same event group if possible, 
    but here we just do global average for simplicity or per-event if we had grouping info).
    
    If market price > global_avg + 0.1 -> SELL
    If market price < global_avg - 0.1 -> BUY
    """
    decisions: List[StrategyDecision] = []
    if not markets:
        return decisions
        
    # Calculate current prices
    current_prices = []
    valid_markets = []
    
    for m in markets:
        if m.price:
            p = m.price[-1]
            current_prices.append(p)
            valid_markets.append(m)
            
    if not current_prices:
        return decisions
        
    global_avg = sum(current_prices) / len(current_prices)
    threshold = 0.1
    
    for m in valid_markets:
        idx = len(m.price) - 1
        p_now = m.price[idx]
        
        diff = p_now - global_avg
        
        if diff > threshold:
            side = "SELL_YES"
            p_hat = global_avg
            decisions.append(StrategyDecision(
                strategy_name="live_cross_section_spread",
                market_id=m.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
        elif diff < -threshold:
            side = "BUY_YES"
            p_hat = global_avg
            decisions.append(StrategyDecision(
                strategy_name="live_cross_section_spread",
                market_id=m.market_id,
                entry_index=idx,
                side=side,
                size=size_fraction,
                p_hat=p_hat
            ))
            
    return decisions

