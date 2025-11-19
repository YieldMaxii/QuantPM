from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import pandas as pd
from pathlib import Path
import json
import os
from datetime import datetime, timezone
import shutil

from src.api.data import get_market_data, get_trades_data, get_system_status, get_base_directories

app = FastAPI(title="QuantPM Voxel API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Market(BaseModel):
    market_id: str
    name: str
    outcome: Optional[float] = 0.5
    event_slug: Optional[str] = None
    slug: Optional[str] = None
    last_updated: Optional[str] = None

class Trade(BaseModel):
    strategy_name: str
    market_id: str
    entry_time: str
    side: str
    entry_price: float
    size: float
    pnl: float
    capital_at_entry: float

class SystemStatus(BaseModel):
    is_running: bool
    start_time: Optional[str] = None
    elapsed: float

@app.get("/api/markets", response_model=List[Dict[str, Any]])
async def read_markets():
    return get_market_data()

@app.get("/api/trades", response_model=List[Dict[str, Any]])
async def read_trades():
    return get_trades_data()

@app.get("/api/status", response_model=SystemStatus)
async def read_status():
    return get_system_status()

@app.post("/api/control/reset")
async def reset_system():
    try:
        base_dir, logs_dir, data_dir = get_base_directories()
        timer_state_file = logs_dir / "timer_state.json"
        
        # 1. Reset Timer
        new_start = datetime.now(timezone.utc)
        timer_data = {
            "start_time": new_start.isoformat(),
            "is_running": True,
            "elapsed": 0
        }
        with open(timer_state_file, "w") as f:
            json.dump(timer_data, f)
            
        # 2. Create reset signal
        reset_signal_path = logs_dir / "reset_signal"
        with open(reset_signal_path, "w") as f:
            f.write("reset")
            
        # 3. Delete price files
        price_files = list(data_dir.glob("prices_L*.csv"))
        deleted_count = 0
        for price_file in price_files:
            try:
                if price_file.exists():
                    price_file.unlink()
                    deleted_count += 1
            except Exception as e:
                print(f"Warning: Could not delete {price_file}: {e}")
                
        # 4. Reset market meta outcomes
        meta_path = data_dir / "markets_live_meta.csv"
        if meta_path.exists():
            try:
                df = pd.read_csv(meta_path)
                if "outcome" in df.columns:
                    df["outcome"] = 0.5
                    df.to_csv(meta_path, index=False)
            except Exception as e:
                print(f"Warning: Could not reset market metadata: {e}")
                
        # 5. Clear trades
        trades_path = logs_dir / "live_trades.csv"
        if trades_path.exists():
            try:
                trades_path.unlink()
            except Exception as e:
                print(f"Warning: Could not delete {trades_path}: {e}")
                
        return {"status": "success", "message": f"System reset. Deleted {deleted_count} price files."}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/performance")
async def read_performance():
    trades = get_trades_data()
    if not trades:
        return []
        
    df = pd.DataFrame(trades)
    
    # Calculate performance metrics per strategy
    strategies = df["strategy_name"].unique()
    performance = []
    
    for strategy in strategies:
        strat_trades = df[df["strategy_name"] == strategy]
        total_pnl = strat_trades["pnl"].sum()
        n_trades = len(strat_trades)
        
        performance.append({
            "strategy_name": strategy,
            "total_pnl": total_pnl,
            "n_trades": n_trades
        })
        
    return performance

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

