# Live Market Granularity Test - Interpretation

## Executive Summary

**Critical Discovery**: Live markets have **dramatically better granularity** than resolved markets:

- **prices-history**: Can achieve **1-minute resolution** for recent windows (last 24 hours)
- **prices-history (max)**: Provides **10-minute resolution** over ~31 days of history
- **trades API**: Provides **sub-minute granularity** (true per-trade timestamps)

This is a **game-changer** for strategy design compared to resolved markets (daily-only).

---

## Key Findings

### 1. prices-history: Two Resolution Tiers

#### Tier 1: Recent Window (1-minute resolution)
- **Config**: `interval=1d` with `fidelity=1`
- **Resolution**: **1.00 minute** median step
- **Coverage**: Last 24 hours (~1,437 points)
- **All 5 markets tested**: Consistent 1-minute resolution

#### Tier 2: Extended History (10-minute resolution)
- **Config**: `interval=max` with `fidelity=1, 5, or 10`
- **Resolution**: **10.00 minute** median step
- **Coverage**: ~31 days (~4,447 points)
- **Time range**: October 18 - November 18, 2025

**Observation**: The `fidelity` parameter (1, 5, or 10) doesn't change the actual resolution when using `interval=max` - it's always 10 minutes. This suggests Polymarket stores historical data in 10-minute buckets.

### 2. Trades API: True Per-Trade Granularity

The Data-API `/trades` endpoint provides the finest granularity:

| Market | Median Inter-Trade Gap | Time Range | Trades |
|--------|------------------------|------------|--------|
| Tesla Nov 30 | 0.77 minutes | 116.86 hours | 500 |
| Tesla Dec 31 | 0.70 minutes | 30.96 hours | 500 |
| Miami Dolphins | 2.23 minutes | 50.42 hours | 500 |
| NY Jets | 2.83 minutes | 71.06 hours | 500 |
| Fed Rates | **0.20 minutes** | 4.02 hours | 500 |

**Key Insights**:
- **Busiest market** (Fed Rates): Trades every **12 seconds** on average (0.20 min = 12 sec)
- **Less active markets**: Trades every 1-3 minutes
- **Time range**: Varies by market activity (4-117 hours for 500 trades)
- **True microstructure**: This is actual trade-by-trade data, not aggregated candles

### 3. Comparison: Live vs Resolved Markets

| Aspect | Resolved Markets | Live Markets |
|--------|------------------|--------------|
| **Best prices-history** | Daily (1440 min) | 1-minute (recent) or 10-minute (extended) |
| **Historical depth** | Weeks/months | ~31 days max |
| **Trades API** | Limited/no data | Full per-trade data |
| **Strategy feasibility** | Daily-only strategies | Intraday strategies possible |

---

## Implications for Strategy Design

### 1. Historical Backtesting: Now Possible at 10-Minute Level

**Good News**: You can backtest strategies on live markets using:
- **10-minute candles** over ~31 days via `interval=max, fidelity=1`
- This is **144x more granular** than daily bars

**Limitation**: This only works for markets that are **currently live** or were live recently. Once a market resolves, you're back to daily-only.

### 2. Real-Time Trading: 1-Minute or Per-Trade

For active markets, you have two options:

**Option A: 1-Minute Candles** (via prices-history)
- Use `interval=1d, fidelity=1` for last 24 hours
- 1,437 data points per day
- Good for strategies that need OHLC-style data

**Option B: Per-Trade Data** (via trades API)
- True trade-by-trade timestamps
- Can see exact execution prices and sizes
- Best for high-frequency or microstructure strategies
- Requires more complex data handling

### 3. Strategy Architecture Recommendations

#### For Historical Backtesting:
1. **Use `interval=max, fidelity=1`** for live markets
   - Gets you 10-minute resolution over ~31 days
   - This is the best you can get historically

2. **Fall back to daily** for resolved markets
   - Use `interval=max, fidelity=1440`
   - Accept that you can't backtest intraday strategies on old markets

#### For Live Trading:
1. **Use `interval=1d, fidelity=1`** for recent price history
   - Gets 1-minute candles for last 24 hours
   - Update frequently (every minute or so)

2. **Use trades API** for execution-level strategies
   - Monitor trades in real-time
   - Can react to individual trade events

### 4. Data Collection Strategy

**Critical Insight**: Polymarket's granularity degrades over time:
- **Live markets**: 1-minute (recent) or 10-minute (extended)
- **Resolved markets**: Daily only

**Recommendation**: 
- **Collect and store** fine-grained data yourself while markets are live
- This gives you true historical intraday data for backtesting
- Otherwise, you're limited to what Polymarket retains

---

## Technical Details

### prices-history Configurations That Work

| Config | Resolution | Coverage | Points | Notes |
|--------|------------|----------|--------|-------|
| `max_f1` | 10 min | ~31 days | ~4,447 | Best for historical backtesting |
| `max_f5` | 10 min | ~31 days | ~4,447 | Same as f1 |
| `max_f10` | 10 min | ~31 days | ~4,447 | Same as f1 |
| `max_f60` | 60 min | ~31 days | ~741 | Hourly bars |
| `1d_f1` | 1 min | Last 24h | ~1,437 | Best for recent data |
| `1d_f5` | 5 min | Last 24h | ~287 | 5-minute bars |
| `6h_f1` | 1 min | Last 6h | ~357 | 6-hour window |
| `1h_f1` | 1 min | Last 1h | ~61 | 1-hour window |
| `1m_noFid` | N/A | N/A | 0 | HTTP 400 error |

### Trades API Details

- **Endpoint**: `https://data-api.polymarket.com/trades`
- **Parameters**: `market` (conditionId), `limit`, `takerOnly`
- **Returns**: Array of trade objects with:
  - `timestamp` (unix seconds)
  - `side` (BUY/SELL)
  - `price`, `size`
  - `outcome`, `conditionId`, `transactionHash`

### Why 10 Minutes for `interval=max`?

The fact that `fidelity=1, 5, or 10` all yield 10-minute resolution suggests:
- Polymarket stores historical data in **10-minute buckets**
- The `fidelity` parameter may be a "minimum" request, but the API returns the nearest available granularity
- For `interval=max`, the system defaults to 10-minute buckets regardless of fidelity request

---

## Recommendations

### Immediate Actions

1. **Update Data Fetching Logic**
   - For live markets: Use `interval=max, fidelity=1` for historical backtesting
   - For live markets: Use `interval=1d, fidelity=1` for recent 1-minute data
   - For resolved markets: Continue using `interval=max, fidelity=1440` (daily)

2. **Re-evaluate Strategy Assumptions**
   - You CAN design intraday strategies for live markets
   - You CANNOT backtest intraday strategies on resolved markets
   - Design strategies that work at both 10-minute and daily levels

3. **Consider Trades API Integration**
   - For high-frequency strategies, trades API provides true per-trade granularity
   - Can see exact execution prices and timing
   - More complex but more realistic for live trading

### Long-Term Strategy

1. **Build Data Collection Pipeline**
   - Continuously collect 1-minute or per-trade data for live markets
   - Store in your own database
   - This preserves granularity after markets resolve

2. **Hybrid Approach**
   - Use Polymarket's 10-minute history for initial backtesting
   - Use your own collected data for deeper historical analysis
   - Use trades API for real-time execution strategies

3. **Strategy Validation**
   - Test strategies on both 10-minute and daily data
   - Ensure strategies are robust to different granularities
   - Document which strategies require which data resolution

---

## Conclusion

**Bottom Line**: Live markets offer **144x better granularity** than resolved markets (10-minute vs daily). This opens up significant possibilities for intraday strategy development and backtesting.

However, this granularity is **temporary** - once markets resolve, you're back to daily-only. The solution is to collect and store fine-grained data yourself while markets are active.

The trades API provides even finer granularity (per-trade) for markets with high activity, enabling true high-frequency strategy development.

