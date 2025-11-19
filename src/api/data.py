import pandas as pd
from pathlib import Path
import json
import os

def get_base_directories() -> tuple[Path, Path, Path]:
    """Get base directory and data/logs directories."""
    # Assuming this file is in src/api/
    base_dir = Path(__file__).resolve().parent.parent.parent
    logs_live_dir = base_dir / "logs_live"
    data_live_dir = base_dir / "data_live"
    return base_dir, logs_live_dir, data_live_dir

def read_csv_safe(path: Path) -> pd.DataFrame:
    """Read CSV safely, returning empty DataFrame on failure."""
    if not path.exists():
        return pd.DataFrame()
    
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return pd.DataFrame()

def get_market_data():
    _, _, data_dir = get_base_directories()
    meta_path = data_dir / "markets_live_meta.csv"
    
    df = read_csv_safe(meta_path)
    if df.empty:
        return []
    
    # We might want to enrich this with current prices if they are in separate files
    # For now, just return the meta data which likely contains the latest snapshot or reference
    return df.to_dict(orient="records")

def get_trades_data():
    _, logs_dir, _ = get_base_directories()
    trades_path = logs_dir / "live_trades.csv"
    
    df = read_csv_safe(trades_path)
    if df.empty:
        return []
    
    # Sort by time desc
    if "entry_time" in df.columns:
        df = df.sort_values("entry_time", ascending=False)
        
    return df.to_dict(orient="records")

def get_system_status():
    _, logs_dir, _ = get_base_directories()
    timer_path = logs_dir / "timer_state.json"
    
    status = {
        "is_running": False,
        "start_time": None,
        "elapsed": 0
    }
    
    if timer_path.exists():
        try:
            with open(timer_path, "r") as f:
                data = json.load(f)
                status.update(data)
        except Exception:
            pass
            
    return status

