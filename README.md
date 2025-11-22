# QuantPM Trading Engine

An efficient Python engine for simulating back trading strategies based on one-minute interval data from Polymarket.

## Structure

- `src/core/`: Core data models (`models.py`), metrics (`metrics.py`), and base trading engine logic (`engine.py`).
- `src/data/`: Data fetching services (`fetcher.py`, `service.py`) and Polymarket API client (`polymarket_api.py`).
- `src/strategies/`: Trading strategy implementations (`live_strategies.py`) and base classes (`base.py`).
- `src/trading/`: Live trading engine loop (`engine.py`).
- `src/api/`: FastAPI backend to serve live strategy statistics.
- `frontend/`: React + Vite frontend for visualizing the competition.

## Usage

### 1. Data Fetching

To start the live data service (fetches 1-minute price updates):

```bash
python -m src.data.service --interval 60
```

To run an initial data fetch of target markets:

```bash
python -m src.data.fetcher
```

### 2. Live Trading

To run the trading engine (processes data and generates trades):

```bash
python -m src.trading.engine
```

### 3. Dashboard & API

The project includes a React frontend and a FastAPI backend to visualize real-time performance.

**Start the API Backend:**
```bash
uvicorn src.api.server:app --reload --port 8000
```

**Start the Frontend:**
```bash
cd frontend
npm install
npm run dev
```
Then open [http://localhost:5173](http://localhost:5173) in your browser.

## Strategies

The system includes several example strategies running in parallel:
- `live_trend_fast`: Fast trend following (5-minute lookback)
- `live_trend_slow`: Slow trend following (1-hour lookback)
- `live_mean_revert`: Mean reversion against 20-minute SMA
- `live_range_reversion`: Range bound trading
- `live_cross_section_spread`: Trading against global average of monitored markets

All strategies compete on the same live data feed.
