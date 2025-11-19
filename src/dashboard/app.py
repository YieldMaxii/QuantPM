"""
Main Streamlit dashboard application.

Orchestrates all dashboard components to display live trading data.
"""

# Import streamlit FIRST - no other imports before this
import streamlit as st
import time

# Basic app config - MUST be first Streamlit command
try:
    st.set_page_config(
        page_title="META-PM Strategy Dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

# CRITICAL: Render something IMMEDIATELY
# This ensures the user sees something even if imports hang
placeholder = st.empty()
with placeholder.container():
    st.markdown("# META-PM Live Trading Dashboard")
    st.markdown("---")
    st.info("🚀 Initializing dashboard...")

# Now import other modules
try:
    import pandas as pd
    import traceback
    from pathlib import Path
    
    # Import local modules - use lazy imports to avoid Streamlit reload issues
    from src.dashboard.utils import get_base_directories, read_csv_if_exists
    from src.trading.timer import get_timer_start_time
    
    # Clear the loading message
    placeholder.empty()
    
    # Main execution
    BASE_DIR, LOGS_LIVE_DIR, DATA_LIVE_DIR = get_base_directories()
    TIMER_STATE_FILE = LOGS_LIVE_DIR / "timer_state.json"
    live_meta_path = DATA_LIVE_DIR / "markets_live_meta.csv"
    live_trades_path = LOGS_LIVE_DIR / "live_trades.csv"

    # Render Header
    st.markdown("# META-PM Live Trading Dashboard")
    st.markdown("---")

    # Lazy import components - import only when needed to avoid Streamlit reload locks
    # Render control panel
    try:
        from src.dashboard.components import render_control_panel
        render_control_panel(TIMER_STATE_FILE)
    except Exception as e:
        st.error(f"Error rendering control panel: {e}")

    # Render timer
    try:
        from src.dashboard.components import render_timer_component
        if TIMER_STATE_FILE.exists():
            render_timer_component(TIMER_STATE_FILE)
        else:
            st.info("⏱️ Timer not initialized. Press Reset System to start.")
    except Exception as e:
        st.error(f"Error rendering timer: {e}")

    # Load data
    if not live_meta_path.exists():
        st.warning("No live market data found. Run the data fetcher first.")
    else:
        # Load data directly
        try:
            live_markets_meta = read_csv_if_exists(live_meta_path)
        except Exception:
            live_markets_meta = pd.DataFrame()
            
        try:
            live_trades_df = read_csv_if_exists(live_trades_path, parse_dates=["entry_time"])
            
            # Filter trades
            if not live_trades_df.empty:
                try:
                    timer_start = get_timer_start_time(TIMER_STATE_FILE)
                    if live_trades_df["entry_time"].dt.tz is None:
                        live_trades_df["entry_time"] = live_trades_df["entry_time"].dt.tz_localize("UTC")
                    else:
                        live_trades_df["entry_time"] = live_trades_df["entry_time"].dt.tz_convert("UTC")
                    live_trades_df = live_trades_df[live_trades_df["entry_time"] >= timer_start]
                except Exception:
                    pass
        except Exception:
            live_trades_df = pd.DataFrame()

        # Render components - lazy import to avoid hangs
        if live_markets_meta.empty:
            st.warning("No live markets configured.")
        else:
            try:
                from src.dashboard.components import render_markets, render_trade_feed, render_strategy_performance
                col1, col2 = st.columns(2)
                with col1:
                    render_markets(live_markets_meta)
                with col2:
                    render_trade_feed(live_trades_df)
                
                if not live_trades_df.empty:
                    render_strategy_performance(live_trades_df)
            except Exception as e:
                st.error(f"Error rendering components: {e}")
                st.code(traceback.format_exc())

except Exception as e:
    st.error(f"Critical Error: {e}")
    st.code(traceback.format_exc())
