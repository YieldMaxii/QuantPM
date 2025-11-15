# META-PM POC

A self-contained, offline simulator for the META-PM (Meta Prediction Market) concept. This proof-of-concept runs a Python backtesting engine on historical prediction market data, simulates multiple trading strategies as "test miners," paper-trades them to resolution, and computes profit/loss (PnL) plus risk and calibration metrics.

## Project Overview

The META-PM POC is designed to evaluate trading strategies on historical prediction market data (currently Polymarket). It provides:

- **Backtesting Engine**: Simulates strategy execution on historical price data
- **Built-in Strategies**: Four baseline strategies for comparison
- **Plugin System**: Framework for external strategies to submit trade logs
- **Performance Metrics**: PnL, Brier scores, maximum drawdown, and per-market breakdowns
- **Visualization**: Streamlit dashboard and Jupyter notebook for analysis

### Use Cases

- Test trading strategies on historical prediction market data
- Compare strategy performance across multiple markets
- Evaluate external strategy implementations via trade logs
- Analyze risk metrics and calibration of probability predictions
- Develop and prototype new trading strategies

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    Data Acquisition Layer                        │
│  fetch_polymarket_data.py                                       │
│  - Fetches market metadata from Polymarket Gamma API            │
│  - Retrieves price history from Polymarket CLOB API             │
│  - Saves raw JSON to data/raw/                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Data Transformation Layer                     │
│  transform_to_engine_format.py                                  │
│  - Converts JSON to CSV format                                  │
│  - Normalizes prices to [0,1] range                             │
│  - Generates markets_meta.csv and prices_*.csv                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core Backtesting Engine (Backend)            │
│  engine.py                                                      │
│  - Loads market data (MarketSeries)                             │
│  - Executes built-in strategies                                 │
│  - Computes PnL from trade decisions                           │
│  - Calculates metrics (Brier, drawdown)                        │
│  - Writes CSV outputs to outputs/                             │
└──────────────┬──────────────────────────────┬───────────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│   Built-in Strategies        │  │   Plugin Strategy Path       │
│   (PriceFollower, Momentum,   │  │   example_complex_strategy.py│
│    FilteredMomentum, Oracle) │  │   multi_strategies.py        │
│                              │  │   → logs/*.csv               │
│                              │  │   → evaluate_trade_logs.py  │
└──────────────────────────────┘  └──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Output Layer (CSV Files)                      │
│  outputs/                                                       │
│  - trades.csv, scores.csv (built-in strategies)                │
│  - trades_from_logs.csv, scores_from_logs.csv (plugin)         │
│  - scores_by_market.csv (per-market breakdowns)                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend Visualization Layer                 │
│  dashboard.py (Streamlit) - Read-only web dashboard              │
│  analysis.ipynb (Jupyter) - Interactive analysis                │
│  - Reads CSV files from outputs/                                │
│  - Combines built-in + plugin strategy data                     │
│  - Interactive performance dashboards                            │
│  - Equity curves and leaderboards                              │
│  - Per-market breakdowns                                       │
└─────────────────────────────────────────────────────────────────┘
```

### Frontend/Backend Architecture

The system follows a **file-based architecture** where the backend (backtesting engine) writes results to CSV files, and the frontend (dashboard) reads those files for visualization.

**Backend (engine.py, evaluate_trade_logs.py):**
- Executes strategies and computes metrics
- Writes results to CSV files in `outputs/` directory
- No direct API or database connection
- Stateless: each run generates fresh output files

**Frontend (dashboard.py):**
- **Read-only visualization layer** that reads CSV files
- Uses Streamlit framework for web-based interactive dashboards
- Automatically combines data from:
  - Built-in strategies: `outputs/trades.csv`, `outputs/scores.csv`
  - Plugin strategies: `outputs/trades_from_logs.csv`, `outputs/scores_from_logs.csv`
- Provides real-time filtering and visualization without modifying data
- Caches loaded data using Streamlit's `@st.cache_data` for performance

**Data Flow:**
1. Backend runs → writes CSV files to `outputs/`
2. Frontend starts → reads CSV files from `outputs/`
3. Frontend displays → interactive charts, tables, filters
4. User interacts → filters, selects strategies/markets (no data modification)

**Connection Method:**
- **File-based**: Frontend reads from the same filesystem where backend writes
- **No API calls**: Direct file I/O using pandas
- **No live connection**: Dashboard shows results from last backend run
- **Refresh**: Restart dashboard or use Streamlit's auto-refresh to see new results

This architecture allows:
- Backend to run independently (CLI scripts)
- Frontend to be started/stopped independently
- Multiple users to view the same results
- Easy debugging (inspect CSV files directly)

### Data Models

The engine uses several core data structures:

- **`MarketSeries`**: Represents a single market with price history
  - `market_id`, `name`, `outcome` (0 or 1)
  - `ts`: List of timestamps
  - `price`: List of prices (normalized to [0,1])
  - Optional: `bid`, `ask`, `volume` arrays

- **`StrategyDecision`**: A trading decision made by a strategy
  - `strategy_name`, `market_id`, `entry_index`
  - `side`: "BUY_YES" or "SELL_YES"
  - `size`: Fraction of bankroll to risk
  - `p_hat`: Strategy's predicted probability of YES outcome

- **`TradeRecord`**: A completed trade with PnL
  - All fields from `StrategyDecision`
  - `entry_time`, `entry_price`
  - `outcome`: Actual market outcome
  - `pnl`: Computed profit/loss

- **`StrategyScores`**: Aggregated performance metrics
  - `total_pnl`: Sum of all trade PnLs
  - `brier_mean`: Mean Brier score (calibration metric)
  - `max_drawdown`: Maximum drawdown from equity curve
  - `n_trades`: Number of trades executed

## Data Pipeline

### 1. Data Acquisition (`fetch_polymarket_data.py`)

Fetches historical market data from Polymarket APIs:

```bash
python fetch_polymarket_data.py
```

**Process:**
1. For each market in `MARKETS` config:
   - Fetches market metadata from Gamma API (`/markets/slug/{slug}`)
   - Extracts YES token ID from market structure
   - Fetches price history from CLOB API (`/prices-history`)
   - Determines price scaling factor (typically 1.0 for CLOB API)
   - Saves raw JSON to `data/raw/{market_id}_market.json` and `data/raw/{market_id}_prices.json`

**Key Functions:**
- `fetch_market_metadata_polymarket(slug)`: Gets market metadata
- `extract_yes_token_id(market_data)`: Extracts YES token ID from market structure
- `fetch_price_history_polymarket(token_id, fidelity)`: Gets price history (tries multiple fidelity levels)
- `determine_price_scale_polymarket(token_id)`: Determines price scaling factor

**Output:** Raw JSON files in `data/raw/`

### 2. Data Transformation (`transform_to_engine_format.py`)

Converts raw JSON to engine-compatible CSV format:

```bash
python transform_to_engine_format.py
```

**Process:**
1. Loads raw JSON files from `data/raw/`
2. Transforms price history:
   - Converts Unix timestamps to ISO format
   - Normalizes prices to [0,1] range (applies price scaling)
   - Generates synthetic bid/ask spreads (0.01) if not present
   - Generates synthetic volume if not present
3. Creates `data/prices_{market_id}.csv` for each market
4. Creates `data/markets_meta.csv` with market metadata and outcomes

**CSV Schema:**

`prices_{market_id}.csv`:
```csv
timestamp,price,bid,ask,volume
2024-01-01T00:00:00,0.42,0.41,0.43,1000.0
```

`markets_meta.csv`:
```csv
market_id,name,outcome
M1,"Market question",1
```

**Key Functions:**
- `transform_price_history()`: Converts price history JSON to CSV rows
- `write_price_csv()`: Writes price CSV file
- `write_markets_meta_csv()`: Creates markets metadata CSV

**Output:** CSV files in `data/`

### 3. Backtesting (`engine.py`)

Runs built-in strategies on historical data:

```bash
python engine.py --meta data/markets_meta.csv --prices-dir data --out-dir outputs
```

**Process:**
1. Loads markets from CSV files (`load_markets()`)
2. For each strategy:
   - Calls `strategy.decide(market)` for each market
   - Creates `TradeRecord` from `StrategyDecision`
   - Computes PnL using `compute_trade_pnl()`
3. Aggregates metrics per strategy:
   - Total PnL
   - Mean Brier score
   - Maximum drawdown
   - Trade count
4. Writes outputs to CSV files

**PnL Calculation:**
- **BUY_YES**: `pnl = (outcome - entry_price) * (size * bankroll)`
- **SELL_YES**: `pnl = (entry_price - outcome) * (size * bankroll)`

**Metrics:**
- **Brier Score**: `(p_hat - outcome)²` (lower is better, measures calibration)
- **Max Drawdown**: Maximum peak-to-trough decline in cumulative PnL

**Output:** `outputs/trades.csv`, `outputs/scores.csv`, `outputs/scores_by_market.csv`

### 4. Plugin Strategy Evaluation (`evaluate_trade_logs.py`)

Evaluates external strategies that submit trade logs:

```bash
python evaluate_trade_logs.py \
    --meta data/markets_meta.csv \
    --prices-dir data \
    --log-file logs/swing_v1_trades.csv \
    --out-dir outputs \
    --bankroll 100.0
```

**Process:**
1. Loads markets (same as backtesting)
2. Reads trade log CSV with columns: `strategy_name`, `market_id`, `entry_index`, `side`, `size`, `p_hat`
3. For each trade spec:
   - Looks up canonical price from market data at `entry_index`
   - Computes PnL using canonical price (ignores any price in log)
   - Uses actual outcome from market metadata
4. Aggregates metrics same as built-in strategies
5. Writes outputs with `_from_logs` suffix

**Trade Log Format:**
```csv
strategy_name,market_id,entry_index,side,size,p_hat
swing_v1,M1,5,BUY_YES,0.1,0.55
```

**Output:** `outputs/trades_from_logs.csv`, `outputs/scores_from_logs.csv`, `outputs/scores_by_market_from_logs.csv`

### 5. Visualization (Frontend)

**Streamlit Dashboard (Frontend):**
```bash
streamlit run dashboard.py
```

The dashboard is a **read-only frontend** that reads CSV files generated by the backend engine. It provides interactive visualization of:
- Strategy leaderboard (sorted by total PnL)
- Per-market P&L breakdowns
- Individual strategy detail views
- Equity curves over time
- Trade scatter plots

**How it connects to backend:**
- Reads CSV files directly from `outputs/` directory (file-based connection)
- Automatically combines data from built-in strategies (`trades.csv`, `scores.csv`) and plugin strategies (`trades_from_logs.csv`, `scores_from_logs.csv`)
- No API or database required - pure file I/O
- Shows results from the most recent backend run
- Use Streamlit's refresh or restart dashboard to see new results after running engine

**Jupyter Notebook:**
```bash
jupyter notebook analysis.ipynb
```

Contains analysis cells for:
- Inspecting raw price data
- Plotting price convergence
- Loading and displaying engine outputs
- Equity curve visualization

**Note:** The notebook also reads from CSV files in the same way as the dashboard, providing an alternative analysis interface.

## Project Structure

```
quantpm/
├── engine.py                      # Core backtesting engine
├── fetch_polymarket_data.py       # Polymarket API data fetcher
├── transform_to_engine_format.py  # JSON to CSV transformer
├── evaluate_trade_logs.py         # Plugin strategy evaluator
├── example_complex_strategy.py    # Example plugin strategy
├── multi_strategies.py            # Multiple strategy implementations
├── dashboard.py                   # Streamlit visualization dashboard
├── analysis.ipynb                 # Jupyter analysis notebook
├── requirements.txt              # Python dependencies
├── README.md                      # This file
├── TEST_RESULTS.md                # Test results documentation
│
├── data/                          # Market data
│   ├── markets_meta.csv          # Market metadata and outcomes
│   ├── prices_M1.csv             # Price history for market M1
│   ├── prices_M2.csv             # Price history for market M2
│   └── ...                       # Additional market price files
│   └── raw/                      # Raw JSON data from APIs
│       ├── M1_market.json        # Raw market metadata
│       ├── M1_prices.json        # Raw price history
│       └── ...                   # Additional raw data files
│
├── logs/                          # Strategy trade logs
│   ├── swing_v1_trades.csv       # Example plugin strategy log
│   └── strategies_suite_trades.csv # Multi-strategy log
│
└── outputs/                       # Engine outputs (auto-generated)
    ├── trades.csv                 # Built-in strategy trades
    ├── scores.csv                 # Built-in strategy scores
    ├── scores_by_market.csv       # Per-market breakdown (built-in)
    ├── trades_from_logs.csv       # Plugin strategy trades
    ├── scores_from_logs.csv       # Plugin strategy scores
    └── scores_by_market_from_logs.csv # Per-market breakdown (plugin)
```

## Component Documentation

### engine.py

The core backtesting engine that simulates strategy execution.

**Key Classes:**
- `BaseStrategy`: Abstract base class for strategies
  - `decide(market: MarketSeries) -> Optional[StrategyDecision]`
- `PriceFollowerStrategy`: Baseline that follows current market price
- `MomentumStrategy`: Simple momentum based on price drift
- `FilteredMomentumStrategy`: Momentum with liquidity/spread filters
- `OracleStrategy`: Cheating baseline using true outcome (for comparison)

**Key Functions:**
- `load_markets(meta_csv, prices_dir) -> List[MarketSeries]`: Loads market data from CSV
- `run_backtest(markets, strategies, bankroll) -> Tuple[List[TradeRecord], List[StrategyScores]]`: Runs backtest
- `evaluate_trade_log(markets, trade_specs, bankroll) -> Tuple[List[TradeRecord], List[StrategyScores]]`: Evaluates external trade log
- `compute_trade_pnl(side, entry_price, outcome, size_fraction, bankroll) -> float`: Computes PnL for a trade
- `brier_score(p_hat, outcome) -> float`: Computes Brier score
- `compute_equity_and_drawdown(trades) -> Tuple[List[float], float]`: Computes equity curve and max drawdown
- `compute_scores_by_market(trades) -> List[StrategyMarketScores]`: Aggregates per-market scores

**Data Models:**
- `MarketSeries`: Market with price history
- `StrategyDecision`: Trading decision
- `TradeRecord`: Completed trade with PnL
- `StrategyScores`: Aggregated strategy metrics
- `StrategyMarketScores`: Per-market strategy metrics

### fetch_polymarket_data.py

Fetches historical market data from Polymarket APIs.

**Configuration:**
- `MARKETS`: Dictionary mapping market IDs to Polymarket slugs
- `GAMMA_API_BASE`: Base URL for Gamma API (market metadata)
- `CLOB_API_BASE`: Base URL for CLOB API (price history)

**Key Functions:**
- `fetch_market_metadata_polymarket(slug) -> Dict`: Fetches market metadata
- `extract_yes_token_id(market_data) -> Optional[str]`: Extracts YES token ID
- `fetch_price_history_polymarket(token_id, fidelity) -> Dict`: Fetches price history
- `determine_price_scale_polymarket(token_id) -> float`: Determines price scaling
- `fetch_polymarket_market_data(market_id, slug, force_refresh) -> Tuple`: Main fetch workflow
- `save_raw_data()` / `load_raw_data()`: Persistence helpers

**Features:**
- Automatic fidelity fallback (tries hourly, daily, etc.)
- Caching of fetched data to avoid redundant API calls
- Price scale detection and normalization

### transform_to_engine_format.py

Transforms raw JSON data to engine-compatible CSV format.

**Key Functions:**
- `transform_price_history(price_data, market_data, price_scale, window_days) -> List[Dict]`: Converts price history
- `write_price_csv(market_id, rows) -> None`: Writes price CSV
- `write_markets_meta_csv() -> None`: Creates markets metadata CSV
- `transform_market(market_id, window_days) -> None`: Transforms single market

**Features:**
- Timestamp conversion (Unix → ISO format)
- Price normalization to [0,1] range
- Synthetic bid/ask generation if missing
- Optional time window filtering (e.g., 14 days before resolution)

### evaluate_trade_logs.py

Evaluates external strategy trade logs using canonical market data.

**Key Functions:**
- `read_trade_log(log_path) -> List[StrategyDecision]`: Reads trade log CSV
- Uses `evaluate_trade_log()` from engine.py for evaluation

**Workflow:**
1. Load markets from canonical CSV files
2. Read trade log with strategy decisions
3. Evaluate each trade using canonical prices (not prices from log)
4. Compute PnL and metrics
5. Write evaluated outputs

### example_complex_strategy.py

Example plugin strategy that generates multi-trade logs.

**Strategy:** Swing momentum strategy
- Compares price vs previous step
- BUY_YES if price increases by > threshold
- SELL_YES if price decreases by > threshold

**Key Functions:**
- `generate_swing_trades(markets, strategy_name, up_threshold, down_threshold, trade_size_fraction) -> List[StrategyDecision]`: Generates trades
- `write_trade_log_csv(decisions, out_path) -> None`: Writes trade log

**Usage:**
```bash
python example_complex_strategy.py \
    --meta data/markets_meta.csv \
    --prices-dir data \
    --out-log logs/swing_v1_trades.csv
```

### multi_strategies.py

Implements multiple strategy types for comparison.

**Strategies:**
1. **baseline_hold**: One trade per market at first timestamp
2. **swing_v1**: Price-swing momentum (same as example_complex_strategy)
3. **mean_revert_v1**: Mean-reversion vs rolling window
4. **cross_section_value_v1**: Cross-sectional value across markets
5. **risk_managed_momo_v1**: Momentum with risk controls

**Key Functions:**
- `generate_baseline_hold_trades()`: Baseline strategy
- `generate_swing_trades()`: Swing momentum
- `generate_mean_reversion_trades()`: Mean reversion
- `generate_cross_section_value_trades()`: Cross-sectional value
- `generate_risk_managed_momo_trades()`: Risk-managed momentum

### dashboard.py

Streamlit web dashboard for strategy performance visualization. This is the **frontend component** that provides an interactive web interface for analyzing backtest results.

**Purpose:**
- Visualize strategy performance metrics in an interactive web interface
- Compare multiple strategies side-by-side
- Analyze performance across different markets
- Explore equity curves and trade patterns
- Filter and drill down into specific strategies or markets

**Backend Connection:**
- **Read-only file-based connection**: Reads CSV files from `outputs/` directory
- **No direct engine interaction**: Dashboard does not call engine functions
- **Data sources**: Automatically loads and combines:
  - Built-in strategy results: `outputs/trades.csv`, `outputs/scores.csv`, `outputs/scores_by_market.csv`
  - Plugin strategy results: `outputs/trades_from_logs.csv`, `outputs/scores_from_logs.csv`, `outputs/scores_by_market_from_logs.csv`
  - Market metadata: `data/markets_meta.csv` (for market names)
- **Caching**: Uses Streamlit's `@st.cache_data` to cache loaded data for performance
- **Auto-refresh**: Streamlit automatically refreshes when files change (if running)

**Key Functions:**
- `load_scores()`: Loads and combines strategy scores from both built-in and plugin sources
- `load_scores_by_market()`: Loads per-market breakdowns
- `load_trades()`: Loads all trades with proper date parsing
- `load_markets_meta()`: Loads market names for display

**Features:**
- Strategy leaderboard with sorting by total PnL
- Per-market P&L breakdowns and heatmaps
- Individual strategy detail views with metrics
- Equity curves over time (global and per-market)
- Trade scatter plots showing entry points
- Interactive filters for:
  - Data sources (built-in vs plugin)
  - Strategies
  - Markets

**Tabs:**
1. **Leaderboard**: Overall strategy rankings with bar charts
2. **Per Market**: P&L breakdown by market with heatmaps
3. **Strategy Detail**: Detailed view for selected strategy with equity curves
4. **Performance Over Time**: Time-series equity curves and trade analysis

**Usage:**
```bash
# Start the dashboard (reads from outputs/ directory)
streamlit run dashboard.py
```

The dashboard will automatically detect and display results from the most recent backend run. If no data is found, it displays an error message prompting the user to run the engine first.

## Strategy Development Guide

### Creating Built-in Strategies

To add a new built-in strategy to `engine.py`:

1. Create a class inheriting from `BaseStrategy`:
```python
class MyStrategy(BaseStrategy):
    def __init__(self, param1: float, param2: int):
        self.name = "my_strategy"
        self.param1 = param1
        self.param2 = param2
    
    def decide(self, market: MarketSeries) -> Optional[StrategyDecision]:
        # Your strategy logic here
        if should_trade:
            return StrategyDecision(
                strategy_name=self.name,
                market_id=market.market_id,
                entry_index=idx,
                side="BUY_YES",  # or "SELL_YES"
                size=0.1,  # fraction of bankroll
                p_hat=0.6,  # predicted probability
            )
        return None
```

2. Add to strategies list in `main()`:
```python
strategies: List[BaseStrategy] = [
    # ... existing strategies ...
    MyStrategy(param1=0.05, param2=3),
]
```

### Creating Plugin Strategies

To create an external strategy that generates trade logs:

1. Create a script that:
   - Loads markets using `load_markets()` from engine.py
   - Generates `StrategyDecision` objects
   - Writes trade log CSV

2. Example structure:
```python
from engine import MarketSeries, StrategyDecision, load_markets
import csv
from pathlib import Path

def generate_my_strategy_trades(markets: List[MarketSeries]) -> List[StrategyDecision]:
    decisions = []
    for market in markets:
        # Your strategy logic
        decisions.append(StrategyDecision(...))
    return decisions

def main():
    markets = load_markets(meta_csv, prices_dir)
    decisions = generate_my_strategy_trades(markets)
    write_trade_log_csv(decisions, out_path)
```

3. Generate trade log:
```bash
python my_strategy.py \
    --meta data/markets_meta.csv \
    --prices-dir data \
    --out-log logs/my_strategy_trades.csv
```

4. Evaluate the log:
```bash
python evaluate_trade_logs.py \
    --meta data/markets_meta.csv \
    --prices-dir data \
    --log-file logs/my_strategy_trades.csv \
    --out-dir outputs
```

**Trade Log CSV Format:**
```csv
strategy_name,market_id,entry_index,side,size,p_hat
my_strategy,M1,5,BUY_YES,0.1,0.55
my_strategy,M1,10,SELL_YES,0.1,0.45
```

**Important Notes:**
- `entry_index` must be valid (0 <= entry_index < len(market.price))
- Engine uses canonical prices from market data, not prices from log
- Engine uses actual outcomes from market metadata
- Multiple trades per market are allowed

## API Reference

### Core Engine Functions

#### `load_markets(meta_csv: Path, prices_dir: Path) -> List[MarketSeries]`
Loads market data from CSV files.

**Parameters:**
- `meta_csv`: Path to `markets_meta.csv`
- `prices_dir`: Directory containing `prices_*.csv` files

**Returns:** List of `MarketSeries` objects

#### `run_backtest(markets: Iterable[MarketSeries], strategies: Iterable[BaseStrategy], bankroll: float) -> Tuple[List[TradeRecord], List[StrategyScores]]`
Runs backtest with built-in strategies.

**Parameters:**
- `markets`: Iterable of market data
- `strategies`: Iterable of strategy objects
- `bankroll`: Reference bankroll for sizing

**Returns:** Tuple of (trades, scores)

#### `evaluate_trade_log(markets: Iterable[MarketSeries], trade_specs: Iterable[StrategyDecision], bankroll: float) -> Tuple[List[TradeRecord], List[StrategyScores]]`
Evaluates external trade log.

**Parameters:**
- `markets`: Iterable of market data
- `trade_specs`: Iterable of `StrategyDecision` objects from log
- `bankroll`: Reference bankroll for sizing

**Returns:** Tuple of (trades, scores)

#### `compute_trade_pnl(side: str, entry_price: float, outcome: int, size_fraction: float, bankroll: float) -> float`
Computes PnL for a single trade.

**Parameters:**
- `side`: "BUY_YES" or "SELL_YES"
- `entry_price`: Entry price (0-1)
- `outcome`: Actual outcome (0 or 1)
- `size_fraction`: Fraction of bankroll risked
- `bankroll`: Reference bankroll

**Returns:** PnL value

#### `brier_score(p_hat: float, outcome: int) -> float`
Computes Brier score for calibration.

**Parameters:**
- `p_hat`: Predicted probability (0-1)
- `outcome`: Actual outcome (0 or 1)

**Returns:** Brier score (lower is better)

#### `compute_equity_and_drawdown(trades: List[TradeRecord]) -> Tuple[List[float], float]`
Computes equity curve and maximum drawdown.

**Parameters:**
- `trades`: List of trades (should be sorted by time)

**Returns:** Tuple of (equity curve list, max drawdown)

### Data Models

#### `MarketSeries`
```python
@dataclass
class MarketSeries:
    market_id: str
    name: str
    outcome: int  # 0 or 1
    ts: List[datetime]
    price: List[float]
    bid: Optional[List[float]] = None
    ask: Optional[List[float]] = None
    volume: Optional[List[float]] = None
```

#### `StrategyDecision`
```python
@dataclass
class StrategyDecision:
    strategy_name: str
    market_id: str
    entry_index: int
    side: str  # "BUY_YES" or "SELL_YES"
    size: float  # fraction of bankroll
    p_hat: float  # predicted probability (0-1)
```

#### `TradeRecord`
```python
@dataclass
class TradeRecord:
    strategy_name: str
    market_id: str
    entry_time: datetime
    side: str
    entry_price: float
    size: float
    p_hat: float
    outcome: int
    pnl: float
```

#### `StrategyScores`
```python
@dataclass
class StrategyScores:
    strategy_name: str
    total_pnl: float
    brier_mean: Optional[float]
    max_drawdown: Optional[float]
    n_trades: int
```

## Workflow Examples

### Complete Workflow: Fetch Data → Backtest → Analyze

1. **Fetch market data:**
```bash
python fetch_polymarket_data.py
```

2. **Transform to CSV:**
```bash
python transform_to_engine_format.py
```

3. **Run backtest:**
```bash
python engine.py --meta data/markets_meta.csv --prices-dir data --out-dir outputs
```

4. **View results in dashboard:**
```bash
streamlit run dashboard.py
```

5. **Or analyze in Jupyter:**
```bash
jupyter notebook analysis.ipynb
```

### Plugin Strategy Workflow

1. **Create strategy script** (e.g., `my_strategy.py`)

2. **Generate trade log:**
```bash
python my_strategy.py \
    --meta data/markets_meta.csv \
    --prices-dir data \
    --out-log logs/my_strategy_trades.csv
```

3. **Evaluate trade log:**
```bash
python evaluate_trade_logs.py \
    --meta data/markets_meta.csv \
    --prices-dir data \
    --log-file logs/my_strategy_trades.csv \
    --out-dir outputs \
    --bankroll 100.0
```

4. **View in dashboard** (plugin strategies appear with "plugin" source tag)

### Multi-Strategy Comparison

1. **Generate multiple strategies:**
```bash
python multi_strategies.py \
    --meta data/markets_meta.csv \
    --prices-dir data \
    --out-log logs/strategies_suite_trades.csv
```

2. **Evaluate all:**
```bash
python evaluate_trade_logs.py \
    --meta data/markets_meta.csv \
    --prices-dir data \
    --log-file logs/strategies_suite_trades.csv \
    --out-dir outputs
```

3. **Compare in dashboard** (filter by strategy name)

## Setup

### 1. Create and Activate Virtual Environment

```bash
cd ~/Desktop/Projects/quantpm

# Create virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate    # On Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `pandas` - Data manipulation and CSV handling
- `requests` - HTTP requests for Polymarket APIs
- `matplotlib` - Static plotting for analysis
- `plotly` - Interactive plotting for dashboard
- `streamlit` - Web dashboard framework
- `jupyter` - Jupyter notebook environment

### 3. Prepare Data

Run the data pipeline:

```bash
# Fetch raw data from Polymarket
python fetch_polymarket_data.py

# Transform to CSV format
python transform_to_engine_format.py
```

This creates:
- `data/markets_meta.csv` - Market metadata with outcomes
- `data/prices_*.csv` - Price history files for each market

## Usage

### Run the Engine

From the project root directory (with virtual environment activated):

```bash
python engine.py --meta data/markets_meta.csv --prices-dir data --out-dir outputs
```

**Options:**
- `--meta`: Path to markets_meta.csv
- `--prices-dir`: Directory containing prices_*.csv files
- `--out-dir`: Output directory for results
- `--bankroll`: Reference bankroll for sizing (default: 100.0)

**Outputs:**
- `outputs/trades.csv` - One row per trade
- `outputs/scores.csv` - One row per strategy with aggregated metrics
- `outputs/scores_by_market.csv` - Per-strategy, per-market breakdown

### Analyze Results

**Streamlit Dashboard:**
```bash
streamlit run dashboard.py
```

**Jupyter Notebook:**
```bash
jupyter notebook
# Then open analysis.ipynb
```

## Built-in Strategies

1. **PriceFollowerStrategy** - Baseline that follows current market price
   - If price >= 0.5, buy YES; else sell YES
   - Entry at fixed index (default: 0)

2. **MomentumStrategy** - Simple momentum based on price drift
   - Compares current price vs lookback window
   - Trades if drift exceeds threshold

3. **FilteredMomentumStrategy** - Momentum with liquidity/spread filters
   - Same as MomentumStrategy
   - Additional filters: max spread, min volume

4. **OracleStrategy** - Cheating baseline using true outcome
   - Always bets correctly (for comparison)
   - Uses earliest timestamp

## Output Files

### trades.csv

One row per trade with columns:
- `strategy_name` - Which strategy made the trade
- `market_id` - Which market was traded
- `entry_time` - When the trade was entered (ISO format)
- `side` - "BUY_YES" or "SELL_YES"
- `entry_price` - Price at entry (0-1)
- `size` - Fraction of bankroll risked
- `p_hat` - Strategy's predicted probability of YES
- `outcome` - Actual outcome (0 or 1)
- `pnl` - Profit/loss for this trade

### scores.csv

One row per strategy with columns:
- `strategy_name` - Strategy identifier
- `total_pnl` - Sum of all trade PnLs
- `brier_mean` - Mean Brier score across trades
- `max_drawdown` - Maximum drawdown from equity curve
- `n_trades` - Number of trades generated

### scores_by_market.csv

One row per (strategy, market) combination with same columns as scores.csv plus:
- `market_id` - Market identifier

## Dependencies

See `requirements.txt` for complete list. Key dependencies:

- **pandas** - Data manipulation and CSV handling
- **requests** - HTTP requests for Polymarket APIs
- **matplotlib** - Static plotting for analysis notebook
- **plotly** - Interactive plotting for Streamlit dashboard
- **streamlit** - Web dashboard framework
- **jupyter** - Jupyter notebook environment

All standard library modules (argparse, csv, dataclasses, datetime, pathlib, typing) are built-in and require no installation.

## Next Steps

- Swap toy CSVs for a small set of real Polymarket markets (already done)
- Turn notebook checks into automated tests
- Add more sophisticated strategies
- Implement additional risk metrics (Sharpe ratio, etc.)
- Extend to handle slippage, full order book, etc.
- Add support for multiple venues beyond Polymarket
