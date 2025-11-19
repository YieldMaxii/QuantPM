"""
run_live_trading.py

Main script to run the live trading system.

This script:
1. Runs the live data service (fetches prices from Polymarket)
2. Runs the live trading engine (generates and evaluates trades)
3. Can be run in separate processes or threads

Usage:
    python run_live_trading.py --data-interval 60 --engine-interval 30
"""

import argparse
import threading
import time
from pathlib import Path

from live_data_service import run_live_data_service, fetch_and_update_live_data
from live_trading_engine import LiveTradingEngine

DATA_LIVE_DIR = Path("data_live")
LOGS_LIVE_DIR = Path("logs_live")
LOGS_LIVE_DIR.mkdir(parents=True, exist_ok=True)


def run_data_service_thread(interval: int, stop_event: threading.Event):
    """Run data service in a separate thread."""
    print(f"[Data Service] Starting with {interval}s interval")
    while not stop_event.is_set():
        try:
            result = fetch_and_update_live_data()
            print(f"[Data Service] Updated {result['updated']}/{result['total']} markets")
            if result.get("errors"):
                for error in result["errors"]:
                    print(f"[Data Service] Error: {error}")
        except Exception as e:
            print(f"[Data Service] Error: {e}")
        
        # Wait for interval, checking stop_event periodically
        for _ in range(interval):
            if stop_event.is_set():
                break
            time.sleep(1)
    print("[Data Service] Stopped")


def run_trading_engine_thread(interval: int, stop_event: threading.Event, bankroll: float):
    """Run trading engine in a separate thread."""
    print(f"[Trading Engine] Starting with {interval}s interval")
    engine = LiveTradingEngine(bankroll=bankroll)
    
    # Wait a bit for initial data
    time.sleep(5)
    
    while not stop_event.is_set():
        try:
            result = engine.run_cycle()
            if result["status"] == "success":
                if result["new_trades"] > 0:
                    print(f"[Trading Engine] Generated {result['new_trades']} new trades (total: {result['total_trades']})")
                
                # Print performance summary every 10 cycles
                if result["total_trades"] % 10 == 0 and result["total_trades"] > 0:
                    perf = engine.get_strategy_performance()
                    print("\n[Trading Engine] Performance Summary:")
                    for strat, metrics in perf.items():
                        print(f"  {strat}: P&L={metrics['total_pnl']:.3f}, Capital={metrics['current_capital']:.3f}, Trades={metrics['n_trades']}")
                    print()
        except Exception as e:
            print(f"[Trading Engine] Error: {e}")
        
        # Wait for interval, checking stop_event periodically
        for _ in range(interval):
            if stop_event.is_set():
                break
            time.sleep(1)
    print("[Trading Engine] Stopped")


def main():
    parser = argparse.ArgumentParser(description="Run live trading system")
    parser.add_argument(
        "--data-interval",
        type=int,
        default=60,
        help="Data service update interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--engine-interval",
        type=int,
        default=30,
        help="Trading engine cycle interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=100.0,
        help="Initial bankroll per strategy (default: 100.0)",
    )
    args = parser.parse_args()
    
    # Check if markets are configured
    meta_path = DATA_LIVE_DIR / "markets_live_meta.csv"
    if not meta_path.exists():
        print("ERROR: No live markets configured.")
        print("Please run: python fetch_polymarket_live_24h.py")
        return
    
    print("=" * 60)
    print("Live Trading System")
    print("=" * 60)
    print(f"Data update interval: {args.data_interval}s")
    print(f"Engine cycle interval: {args.engine_interval}s")
    print(f"Initial bankroll: ${args.bankroll:.2f}")
    print("=" * 60)
    print("Press Ctrl+C to stop")
    print()
    
    # Create stop event for threads
    stop_event = threading.Event()
    
    # Start threads
    data_thread = threading.Thread(
        target=run_data_service_thread,
        args=(args.data_interval, stop_event),
        daemon=True,
    )
    engine_thread = threading.Thread(
        target=run_trading_engine_thread,
        args=(args.engine_interval, stop_event, args.bankroll),
        daemon=True,
    )
    
    data_thread.start()
    engine_thread.start()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("Stopping live trading system...")
        print("=" * 60)
        stop_event.set()
        data_thread.join(timeout=5)
        engine_thread.join(timeout=5)
        print("Stopped.")


if __name__ == "__main__":
    main()

