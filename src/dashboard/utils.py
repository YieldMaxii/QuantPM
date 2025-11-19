"""
Dashboard utility functions for data loading and path management.
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st


@st.cache_data
def get_base_directories() -> tuple[Path, Path, Path]:
    """Get base directory and data/logs directories. Cached to avoid recalculation."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    logs_live_dir = base_dir / "logs_live"
    logs_live_dir.mkdir(parents=True, exist_ok=True)
    data_live_dir = base_dir / "data_live"
    return base_dir, logs_live_dir, data_live_dir


def _read_csv_cached(path_str: str, mtime: float, max_rows: int = None, **kwargs) -> pd.DataFrame:
    """Internal cached function that reads CSV. mtime is used to invalidate cache on file changes."""
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()
    
    try:
        # For large files, use efficient tail-based reading
        if max_rows and max_rows > 0:
            # Use nrows parameter to limit reading, but we need tail, so read all and tail
            # For very large files, this could be optimized further with file seeking
            df = pd.read_csv(path, **kwargs)
            if len(df) > max_rows:
                return df.tail(max_rows).reset_index(drop=True)
            return df
        
        # For regular reading, use low_memory=False for better performance on small files
        # and add error handling for file locks
        try:
            return pd.read_csv(path, low_memory=False, **kwargs)
        except (pd.errors.EmptyDataError, FileNotFoundError):
            return pd.DataFrame()
        except PermissionError:
            # File might be locked by another process, return empty and try again next time
            print(f"Warning: File {path} is locked, skipping this read")
            return pd.DataFrame()
    except Exception as e:
        print(f"Warning: Error reading CSV {path}: {e}")
        return pd.DataFrame()


# Removed st.cache_data to prevent locking issues on refresh
# For files of this size (<10k rows), direct reading is faster and safer
def _read_csv_with_cache(path_str: str, mtime: float, max_rows: int = None, **kwargs) -> pd.DataFrame:
    """Wrapper that reads CSV directly. Cache removed to prevent locking."""
    return _read_csv_cached(path_str, mtime, max_rows=max_rows, **kwargs)


def read_csv_if_exists(path: Path, max_rows: int = None, **kwargs) -> pd.DataFrame:
    """
    Read CSV file if it exists, return empty DataFrame otherwise.
    
    Uses Streamlit caching with 5-second TTL to improve performance.
    Cache key includes file modification time to detect changes.
    
    Args:
        path: Path to CSV file
        max_rows: If specified, only read the last N rows for large files
        **kwargs: Additional arguments passed to pd.read_csv
    """
    try:
        path_str = str(path)
        mtime = os.path.getmtime(path) if path.exists() else 0
        
        # Clear cache if force_refresh is set
        if st.session_state.get("force_refresh", False):
            _read_csv_with_cache.clear()
            st.session_state.force_refresh = False
        
        return _read_csv_with_cache(path_str, mtime, max_rows=max_rows, **kwargs)
    except Exception as e:
        # If anything fails, return empty DataFrame
        print(f"Warning: Error in read_csv_if_exists for {path}: {e}")
        return pd.DataFrame()
