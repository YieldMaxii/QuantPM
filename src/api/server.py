"""
API Server for the Trading Dashboard.

Serves real-time strategy performance data by reading from the live logs.
Uses standard library http.server to avoid dependency issues in restricted environments.
"""

import csv
import json
import subprocess
import sys
import http.server
import socketserver
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

PORT = 8002

LOGS_DIR = Path("logs_live")
DATA_DIR = Path("data_live")
TRADES_CSV = LOGS_DIR / "live_trades.csv"
TIMER_FILE = LOGS_DIR / "timer_state.json"
MARKETS_META = DATA_DIR / "markets_live_meta.csv"

# Mapping internal strategy names to display names
STRATEGY_DISPLAY_NAMES = {
    "live_trend_fast": "Trend Fast",
    "live_trend_slow": "Trend Slow",
    "live_mean_revert": "Mean Reversion",
    "live_range_reversion": "Range Reversion",
    "live_cross_section_spread": "Cross Section",
}

# Store process handles
PROCESSES: Dict[str, subprocess.Popen] = {}

def start_background_process(module_name: str, log_name: str):
    """Start a python module as a background process."""
    # Check if already running
    if module_name in PROCESSES:
        if PROCESSES[module_name].poll() is None:
            print(f"Process {module_name} is already running.")
            return

    LOGS_DIR.mkdir(exist_ok=True)
    log_file = open(LOGS_DIR / f"{log_name}.log", "a")
    
    # Determine Python executable: use the current interpreter
    python_exe = sys.executable
    cwd = Path.cwd()
    print(f"Server CWD: {cwd}")
    print(f"Using Python: {python_exe}")

    print(f"Starting {module_name} using {python_exe}")
    cmd = [python_exe, "-u", "-m", module_name]
    
    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=Path.cwd()
    )
    PROCESSES[module_name] = proc
    print(f"Started {module_name} with PID {proc.pid}")

class TradingHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def _set_headers(self, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_GET(self):
        path = self.path.rstrip('/')
        if path == '/stats':
            self.handle_stats()
        elif path == '/health':
            self._set_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode())

    def do_POST(self):
        path = self.path.rstrip('/')
        if path == '/start':
            self.handle_start()
        elif path == '/reset':
            self.handle_reset()
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode())

    def handle_start(self):
        """Handle POST /start"""
        try:
            LOGS_DIR.mkdir(exist_ok=True)
            
            # 1. Set Start Time
            start_time = datetime.now(timezone.utc)
            with open(TIMER_FILE, "w") as f:
                json.dump({"start_time": start_time.isoformat()}, f)
            
            # 2. Check/Run Fetcher
            if not MARKETS_META.exists():
                print("Markets meta not found. Running fetcher initialization...")
                subprocess.run([sys.executable, "-m", "src.data.fetcher"], check=True)
            
            # 3. Start Services
            start_background_process("src.data.service", "service")
            start_background_process("src.trading.engine", "engine")
            
            response = {"status": "started", "start_time": start_time.isoformat()}
            self._set_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"Error starting competition: {e}")
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def handle_reset(self):
        """Handle POST /reset"""
        try:
            # 1. Delete timer state (stops the active flag)
            if TIMER_FILE.exists():
                TIMER_FILE.unlink()
            
            # 2. Delete trade logs (clears history)
            if TRADES_CSV.exists():
                TRADES_CSV.unlink()
                
            # 3. Signal services to reset
            signal_file = LOGS_DIR / "reset_signal"
            signal_file.touch()
            
            response = {"status": "reset"}
            self._set_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"Error resetting competition: {e}")
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def handle_stats(self):
        """Handle GET /stats"""
        strategies = {}
        
        # Initialize defaults
        for internal_name, display_name in STRATEGY_DISPLAY_NAMES.items():
            strategies[internal_name] = {
                "id": internal_name,
                "name": display_name,
                "pnl": 0.0,
                "trades": 0,
                "last_active": None
            }
        
        # Read trades
        if TRADES_CSV.exists():
            try:
                with TRADES_CSV.open("r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        strat = row.get("strategy_name")
                        try:
                            pnl = float(row.get("pnl", 0.0))
                        except ValueError:
                            pnl = 0.0
                        
                        if strat in strategies:
                            strategies[strat]["pnl"] += pnl
                            strategies[strat]["trades"] += 1
                            strategies[strat]["last_active"] = row.get("entry_time")
            except Exception as e:
                print(f"Error reading trades: {e}")

        # Read timer
        competition_time = None
        is_active = False
        if TIMER_FILE.exists():
            try:
                with TIMER_FILE.open("r") as f:
                    data = json.load(f)
                    competition_time = data.get("start_time")
                    is_active = bool(competition_time)
            except Exception:
                pass

        # Sort
        sorted_strategies = sorted(
            strategies.values(), 
            key=lambda x: x["pnl"], 
            reverse=True
        )
        
        response = {
            "strategies": sorted_strategies,
            "competition_time": competition_time,
            "is_active": is_active
        }
        
        self._set_headers()
        self.wfile.write(json.dumps(response).encode())

if __name__ == "__main__":
    print(f"Starting Trading API Server on port {PORT}...")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), TradingHTTPRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping server...")
