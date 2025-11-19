# Polymarket Granularity Test Results - Interpretation

## Executive Summary

**Key Finding**: Polymarket's historical price data granularity is **severely limited for resolved markets** (daily only), but **much better for active markets** (10-minute intervals).

This has critical implications for strategy design and backtesting realism.

---

## Detailed Findings

### 1. Resolved Markets (M1-M4): Daily Data Only

All four resolved markets (M1, M2, M3, M4) show the same pattern:

| Market | Best Resolution | Median Step | Data Points | Time Range |
|--------|----------------|-------------|-------------|------------|
| M1 | Daily (1440 min) | 1440.00 min | 48 | Dec 2023 - Jan 2024 |
| M2 | Daily (1440 min) | 1440.00 min | 67 | Nov 2024 - Jan 2025 |
| M3 | Daily (1440 min) | 1440.00 min | 16 | Jul 2024 - Aug 2024 |
| M4 | Daily (1440 min) | 1440.00 min | 175 | Nov 2024 - Apr 2025 |

**Critical Observation**: 
- **ALL** attempts to get finer resolution (1m, 5m, 15m, 60m intervals with any fidelity) returned **0 data points**
- Only `interval=max` with `fidelity=1440` (daily) returned data
- This suggests Polymarket **does not retain fine-grained historical data** for resolved markets

### 2. Active Market (M5): 10-Minute Resolution Available

M5 (active market) shows dramatically different behavior:

| Configuration | Median Step | Data Points | Time Range |
|---------------|-------------|-------------|------------|
| `max` + `fidelity=1` | **10.00 min** | 105 | Nov 12-13, 2025 |
| `max` + `fidelity=5` | **10.00 min** | 105 | Nov 12-13, 2025 |
| `max` + `fidelity=15` | 14.95 min | 70 | Nov 12-13, 2025 |
| `max` + `fidelity=60` | 59.98 min | 17 | Nov 12-13, 2025 |
| `max` + `fidelity=1440` | N/A (1 point) | 1 | Nov 13, 2025 |

**Key Insights**:
- Active markets **DO** have fine-grained data (10-minute intervals)
- The actual resolution is **10 minutes**, regardless of whether `fidelity=1` or `fidelity=5` is requested
- This suggests Polymarket stores real-time data at ~10-minute granularity for active markets
- The data only covers a **very recent window** (last ~17 hours for M5)

### 3. API Behavior Patterns

#### Invalid Combinations
- `interval=1m` with `fidelity=1` or `fidelity=5` → **HTTP 400** (Bad Request)
- This suggests Polymarket's API enforces constraints on interval/fidelity combinations

#### Empty Responses
- Most combinations return empty arrays (`n_points=0`) even with HTTP 200
- This indicates the API accepts the request but has no data to return
- Likely due to:
  1. **Data retention policy**: Fine-grained data is not stored long-term
  2. **Market state**: Resolved markets may have data purged or archived differently

#### Working Combinations
- **Resolved markets**: Only `interval=max` + `fidelity=1440` works
- **Active markets**: `interval=max` + `fidelity=1` or `5` gives best resolution (10 min)

---

## Implications for Strategy Design

### 1. Historical Backtesting Limitations

**Reality Check**: Your current POC strategies are likely **over-optimized** if they assume:
- Minute-by-minute price movements
- Intraday volatility patterns
- Sub-hourly entry/exit signals

**What's Actually Available**:
- **Daily bars only** for resolved markets
- Maximum of 1 data point per day
- No intraday price action visibility

**Recommendation**: 
- Re-evaluate strategies that rely on intraday signals
- Focus on **daily-level** strategies for historical backtesting
- Consider that real-time execution might have been different than daily snapshots suggest

### 2. Live Trading vs Backtesting Discrepancy

**The Gap**:
- **Backtesting**: Daily data (1440 min resolution)
- **Live trading**: 10-minute data available

**Problem**: 
- Strategies optimized on daily data may behave differently with 10-minute granularity
- You can't backtest the "real" intraday behavior you'll experience live

**Mitigation**:
- Design strategies that work at **both** daily and 10-minute levels
- Use daily data for backtesting, but ensure logic doesn't depend on sub-daily precision
- Consider adding "realistic execution delay" models to account for this gap

### 3. Data Availability Windows

**Observation**: 
- M5 (active) has data for ~17 hours
- Resolved markets have data spanning weeks/months, but only daily

**Implication**:
- Fine-grained data may only be available for a **rolling window** (e.g., last 24-48 hours)
- Historical fine-grained data is likely **not accessible** via the prices-history endpoint
- For true intraday historical analysis, you'd need to:
  - Continuously collect and store data yourself
  - Use alternative endpoints (trades API, order book history) if available

---

## Recommendations

### Immediate Actions

1. **Audit Current Strategies**
   - Review `example_complex_strategy.py` and `multi_strategies.py`
   - Identify any assumptions about sub-daily granularity
   - Document which strategies are "realistic" vs "theoretical"

2. **Update Data Fetching Logic**
   - Modify `fetch_polymarket_data.py` to:
     - Use `interval=max, fidelity=1440` for resolved markets (current approach is correct)
     - Use `interval=max, fidelity=1` for active markets (to get 10-min resolution)
     - Add logic to detect market state (active vs resolved)

3. **Strategy Validation**
   - Re-run backtests with awareness that daily data is the limit
   - Mark strategies that require intraday data as "live-only" or "theoretical"
   - Consider adding a "granularity check" to strategy validation

### Long-Term Considerations

1. **Data Collection Strategy**
   - Consider building a real-time data collection system
   - Store fine-grained data yourself for future backtesting
   - This would enable true intraday strategy development

2. **Alternative Data Sources**
   - Explore Polymarket's trades API for per-trade data
   - Consider order book snapshots if available
   - May provide better historical granularity than prices-history

3. **Strategy Architecture**
   - Design strategies with "granularity awareness"
   - Have different logic paths for daily vs intraday data
   - Make strategies adaptable to available data resolution

---

## Technical Notes

### Why 10 Minutes?

The fact that both `fidelity=1` and `fidelity=5` return 10-minute intervals suggests:
- Polymarket's internal storage uses ~10-minute buckets
- The `fidelity` parameter may be a "minimum" rather than "exact" resolution
- The API may round up to the nearest available granularity

### Data Retention Policy

The complete absence of fine-grained data for resolved markets suggests:
- Polymarket likely purges or archives fine-grained data after market resolution
- Daily aggregates are retained for longer periods
- This is a common pattern in financial data systems (cost/performance tradeoff)

### API Constraints

The HTTP 400 errors for `interval=1m` + `fidelity=1` suggest:
- Polymarket's API validates interval/fidelity combinations
- Some combinations are explicitly disallowed
- The API documentation may not fully reflect these constraints

---

## Conclusion

**Bottom Line**: Your strategies need to be designed around **daily data for historical backtesting**, with the understanding that live trading will have 10-minute granularity. This is a significant constraint that affects strategy realism and optimization.

The good news: You now have concrete data about what's actually available, so you can make informed decisions about strategy design and data requirements.

