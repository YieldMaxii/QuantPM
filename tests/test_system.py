import unittest
from unittest.mock import patch, MagicMock, ANY
import sys
import tempfile
import shutil
import csv
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Mock requests module before importing project modules
# This is necessary because the test environment might not have requests installed
mock_requests = MagicMock()
sys.modules["requests"] = mock_requests
sys.modules["requests.exceptions"] = MagicMock()
sys.modules["urllib3"] = MagicMock()
sys.modules["urllib3.exceptions"] = MagicMock()

# Import modules to test
import src.data.fetcher as fetcher
import src.data.service as service
from src.trading.engine import LiveTradingEngine
import src.strategies.live_strategies as strategies
from src.core.models import MarketSeries, StrategyDecision, TradeRecord
from src.strategies.base import StrategyContext

class TestTradingSystem(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for data
        self.test_dir = tempfile.mkdtemp()
        self.test_dir_path = Path(self.test_dir)
        self.data_live_dir = self.test_dir_path / "data_live"
        self.logs_live_dir = self.test_dir_path / "logs_live"
        self.data_live_dir.mkdir()
        self.logs_live_dir.mkdir()
        
        # Create timer state file
        self.timer_file = self.logs_live_dir / "timer_state.json"
        # Default start time to now - 1 hour so competition is "active"
        self.start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        with open(self.timer_file, 'w') as f:
            json.dump({"start_time": self.start_time.isoformat()}, f)

        # Patch constants in modules
        self.patches = []
        
        # Helper to start patch
        def start_patch(target, new_value):
            p = patch(target, new_value)
            p.start()
            self.patches.append(p)
            return p

        # Patch paths in fetcher
        start_patch('src.data.fetcher.DATA_LIVE_DIR', self.data_live_dir)
        start_patch('src.data.fetcher.LOGS_LIVE_DIR', self.logs_live_dir)
        start_patch('src.data.fetcher.TIMER_STATE_FILE', self.timer_file)
        
        # Patch paths in service
        start_patch('src.data.service.DATA_LIVE_DIR', self.data_live_dir)
        start_patch('src.data.service.LOGS_LIVE_DIR', self.logs_live_dir)
        start_patch('src.data.service.TIMER_STATE_FILE', self.timer_file)
        
        # Patch paths in engine
        start_patch('src.trading.engine.DATA_LIVE_DIR', self.data_live_dir)
        start_patch('src.trading.engine.LOGS_LIVE_DIR', self.logs_live_dir)
        start_patch('src.trading.engine.META_PATH', self.data_live_dir / "markets_live_meta.csv")
        start_patch('src.trading.engine.PRICES_DIR', self.data_live_dir)
        start_patch('src.trading.engine.TIMER_STATE_FILE', self.timer_file)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.test_dir)

    @patch('src.data.fetcher.fetch_current_price')
    def test_fetcher_initialization(self, mock_fetch_price):
        """Test that fetcher initializes empty price CSVs and populates metadata."""
        print("\nRunning test_fetcher_initialization...")
        
        # Configure the global mock_requests to return sample data
        mock_response = MagicMock()
        mock_response.json.return_value = [{
            "markets": [{
                "id": "poly_123",
                "slug": "market-slug",
                "question": "Will X happen?",
                "conditionId": "cond_123",
                "tokens": [{"outcome": "YES", "tokenId": "token_yes"}],
                "volume24hr": "50000"
            }]
        }]
        mock_requests.get.return_value = mock_response
        
        # Mock fetch_current_price to return a starting price
        mock_fetch_price.return_value = 0.45

        # Run fetcher main
        # We need to mock TARGET_EVENTS in fetcher to limit scope
        with patch('src.data.fetcher.TARGET_EVENTS', ["test-event"]):
             fetcher.main()

        # Check that markets_live_meta.csv exists
        meta_file = self.data_live_dir / "markets_live_meta.csv"
        self.assertTrue(meta_file.exists(), "markets_live_meta.csv should exist")
        
        with open(meta_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['market_id'], 'L1')
            self.assertEqual(rows[0]['outcome'], '0.450000')
            self.assertEqual(rows[0]['yes_token_id'], 'token_yes')

        # Check that prices_L1.csv exists and has only header
        prices_file = self.data_live_dir / "prices_L1.csv"
        self.assertTrue(prices_file.exists(), "prices_L1.csv should exist")
        
        with open(prices_file, 'r') as f:
            content = f.read().strip()
            self.assertEqual(content, "timestamp,price,bid,ask,volume")

    @patch('src.data.service.fetch_current_price')
    def test_data_service_update(self, mock_fetch_price):
        """Test that service fetches new prices and appends them."""
        print("\nRunning test_data_service_update...")
        
        # Setup: Create metadata file manually (mimicking fetcher's job)
        meta_file = self.data_live_dir / "markets_live_meta.csv"
        with open(meta_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["market_id","name","outcome","slug","event_slug","condition_id","yes_token_id","last_updated"])
            writer.writerow(["L1","Test Q","0.50","slug","event","cond","token_yes","2025-01-01T00:00:00+00:00"])
            
        # Create empty price file
        prices_file = self.data_live_dir / "prices_L1.csv"
        with open(prices_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp","price","bid","ask","volume"])
            
        # Mock price fetch
        mock_fetch_price.return_value = 0.55
        
        # Run service update once
        result = service.fetch_and_update_live_data()
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['updated'], 1)
        
        # Verify price appended
        with open(prices_file, 'r') as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 2, "Should have header + 1 data row")
            last_row = lines[-1].strip().split(',')
            # timestamp, price, bid, ask, volume
            self.assertEqual(last_row[1], "0.550000")

    @patch('src.trading.engine.get_timer_start_time')
    def test_trading_engine_cycle(self, mock_get_timer):
        """Test that trading engine loads data and generates trades."""
        print("\nRunning test_trading_engine_cycle...")
        
        # Setup: 
        # 1. Create markets meta
        meta_file = self.data_live_dir / "markets_live_meta.csv"
        with open(meta_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["market_id","name","outcome","slug","event_slug","condition_id","yes_token_id","last_updated"])
            writer.writerow(["L1","Test Q","0.50","slug","event","cond","token_yes",datetime.now(timezone.utc).isoformat()])

        # 2. Create price history with a trend (0.50 -> 0.52 -> 0.55)
        prices_file = self.data_live_dir / "prices_L1.csv"
        with open(prices_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp","price","bid","ask","volume"])
            base_time = datetime.now(timezone.utc)
            # Add a few rows
            times = [base_time - timedelta(minutes=i) for i in range(10, 0, -1)]
            prices = [0.50 + i*0.01 for i in range(10)] # 0.50 to 0.59
            for t, p in zip(times, prices):
                writer.writerow([t.isoformat(), f"{p:.6f}", f"{p-0.01:.6f}", f"{p+0.01:.6f}", "1000"])

        # Mock timer to start before our data
        mock_get_timer.return_value = base_time - timedelta(minutes=10)

        # Initialize Engine
        engine = LiveTradingEngine()
        
        # Run one cycle
        engine.run_cycle()
        
        # Verify trades generated (trend strategy should pick up the rise)
        self.assertGreater(len(engine.all_trades), 0, "Should have generated trades")
        
        # Verify trade log file
        trades_file = self.logs_live_dir / "live_trades.csv"
        self.assertTrue(trades_file.exists())
        with open(trades_file, 'r') as f:
            lines = f.readlines()
            self.assertGreater(len(lines), 1, "Trade log should have header + trades")

    def test_strategies(self):
        """Test specific strategy logic."""
        print("\nRunning test_strategies...")
        
        # Create a synthetic market with a sharp upward trend
        times = [datetime.now(timezone.utc) - timedelta(minutes=i) for i in range(10, 0, -1)]
        # Prices rising from 0.50 to 0.60
        prices = [0.50 + i*0.01 for i in range(10)] 
        
        market = MarketSeries(
            market_id="L1",
            name="Test Market",
            outcome=0.60,
            ts=times,
            price=prices,
            bid=[p-0.01 for p in prices],
            ask=[p+0.01 for p in prices],
            volume=[1000.0]*10,
            slug="test-slug"
        )
        
        context = StrategyContext(
            strategy_name="test_strat",
            current_capital=100.0,
            initial_capital=100.0,
            trade_history=[],
            markets=[market]
        )
        
        # Test generate_trend_fast
        decisions = strategies.generate_trend_fast([market], context, lookback=5, threshold=0.02)
        
        # Should detect trend and buy
        self.assertTrue(len(decisions) > 0, "Strategy should generate decision")
        decision = decisions[0]
        self.assertEqual(decision.side, "BUY_YES")
        self.assertEqual(decision.market_id, "L1")

if __name__ == '__main__':
    unittest.main()
