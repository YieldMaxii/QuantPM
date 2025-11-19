"""
Dashboard UI components for Streamlit.

Provides reusable components for timer, market display, trade feed, and performance charts.
"""

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
# import plotly.express as px  # COMMENTED OUT TO TEST IF THIS CAUSES HANG
import streamlit as st

from ..trading.timer import get_timer_start_time, save_timer_state


def render_timer_component(timer_state_file: Path) -> None:
    """Render the 24-hour competition timer component using Streamlit-native components."""
    # Get timer start time
    timer_start_time = get_timer_start_time(timer_state_file)
    
    # Check if expired and reset if needed
    elapsed_check = datetime.now(timezone.utc) - timer_start_time
    elapsed_seconds_check = elapsed_check.total_seconds()
    
    # If timer expired (>= 24 hours) or is negative (timezone issue), reset it
    if elapsed_seconds_check >= 86400 or elapsed_seconds_check < 0:
        new_start = datetime.now(timezone.utc)
        save_timer_state(timer_state_file, new_start)
        timer_start_time = new_start
        st.info("⏱️ Timer expired. Starting new 24-hour session.")
        try:
            st.experimental_rerun()
        except AttributeError:
            st.rerun()
    
    # Calculate remaining time for display
    elapsed_for_display = datetime.now(timezone.utc) - timer_start_time
    remaining_seconds_display = max(0, 86400 - elapsed_for_display.total_seconds())
    hours_display = int(remaining_seconds_display // 3600)
    minutes_display = int((remaining_seconds_display % 3600) // 60)
    seconds_display = int(remaining_seconds_display % 60)
    progress_display = min(100, (elapsed_for_display.total_seconds() / 86400) * 100)
    
    # Show timer status
    st.info(f"⏱️ **Competition Timer**: Started at {timer_start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC | "
            f"Timer file: `{timer_state_file.name}`")
    
    # Use Streamlit-native components (CSP-compliant)
    st.markdown("### Timer Display")
    
    # Timer display using columns and metrics
    timer_cols = st.columns(3)
    with timer_cols[0]:
        st.metric("Hours", f"{hours_display:02d}")
    with timer_cols[1]:
        st.metric("Minutes", f"{minutes_display:02d}")
    with timer_cols[2]:
        st.metric("Seconds", f"{seconds_display:02d}")
    
    # Progress bar
    st.markdown("**Session Progress**")
    st.progress(progress_display / 100)
    st.caption(f"{progress_display:.1f}% complete | {hours_display:02d}h {minutes_display:02d}m {seconds_display:02d}s remaining")


def render_control_panel(timer_state_file: Path) -> None:
    """Render the control panel with auto-refresh and timer controls."""
    # Initialize session state for live trading config
    if "live_auto_refresh" not in st.session_state:
        st.session_state.live_auto_refresh = True
    if "last_refresh_time" not in st.session_state:
        st.session_state.last_refresh_time = time.time()
    if "refresh_interval" not in st.session_state:
        st.session_state.refresh_interval = 5
    
    # Handle reset message
    if "reset_message" in st.session_state:
        msg_type, msg = st.session_state.reset_message
        if msg_type == "success":
            st.toast(msg, icon="🔄")
        else:
            st.error(msg)
        del st.session_state.reset_message
    
    # Control panel
    col_control1, col_control2, col_control3, col_control4 = st.columns(4)
    
    with col_control1:
        auto_refresh_checkbox = st.checkbox("🔄 Auto-refresh", value=st.session_state.live_auto_refresh)
        if auto_refresh_checkbox != st.session_state.live_auto_refresh:
            st.session_state.live_auto_refresh = auto_refresh_checkbox
            st.session_state.last_refresh_time = time.time()
            # st.rerun() removed to prevent double-rerun crash
    
    with col_control2:
        interval_options = [3, 5, 10, 15, 30, 60]
        current_interval = st.session_state.refresh_interval
        try:
            current_index = interval_options.index(current_interval)
        except ValueError:
            current_index = 1
        
        refresh_interval = st.selectbox(
            "Refresh interval",
            options=interval_options,
            index=current_index,
            format_func=lambda x: f"{x}s",
            key="refresh_interval_select"
        )
        if refresh_interval != st.session_state.refresh_interval:
            st.session_state.refresh_interval = refresh_interval
            st.session_state.last_refresh_time = time.time()
            # st.rerun() removed to prevent double-rerun crash
    
    with col_control3:
        if st.button("🔄 Refresh Now", key="btn_refresh_now"):
            st.session_state.last_refresh_time = time.time()
            st.session_state.refresh_requested = True
            st.session_state.force_refresh = True
            # Use experimental_rerun which is faster and less likely to cause blank pages
            try:
                st.experimental_rerun()
            except AttributeError:
                st.rerun()
    
    with col_control4:
        if st.button("⏱️ Reset System", key="btn_reset_system"):
            # Show immediate feedback
            reset_status = st.empty()
            reset_status.info("🔄 Resetting system...")
            
            try:
                # Clear all Streamlit caches first to speed up reload
                from src.dashboard.utils import get_base_directories, _read_csv_with_cache
                try:
                    # Clear CSV cache
                    _read_csv_with_cache.clear()
                except:
                    pass
                
                # Perform reset operations
                new_start = datetime.now(timezone.utc)
                save_timer_state(timer_state_file, new_start)
                
                # Create reset signal for engine
                reset_signal_path = timer_state_file.parent / "reset_signal"
                with open(reset_signal_path, 'w') as f:
                    f.write("reset")
                
                # Clear all price data CSVs to start fresh
                _, _, data_live_dir = get_base_directories()
                # Delete all price CSV files (prices_L*.csv)
                price_files = list(data_live_dir.glob("prices_L*.csv"))
                deleted_count = 0
                for price_file in price_files:
                    try:
                        if price_file.exists():
                            price_file.unlink()
                            deleted_count += 1
                    except Exception as e:
                        print(f"Warning: Could not delete {price_file}: {e}")
                
                # Also ensure markets_live_meta.csv is cleared of old outcome data
                # (but keep the file structure - just reset outcomes)
                meta_path = data_live_dir / "markets_live_meta.csv"
                if meta_path.exists():
                    try:
                        import pandas as pd
                        df = pd.read_csv(meta_path)
                        # Reset outcome column to 0.5 (neutral) for all markets
                        if "outcome" in df.columns:
                            df["outcome"] = 0.5
                            df.to_csv(meta_path, index=False)
                    except Exception as e:
                        print(f"Warning: Could not reset market metadata: {e}")
                
                # Clear trades CSV
                trades_path = timer_state_file.parent / "live_trades.csv"
                trades_deleted = False
                if trades_path.exists():
                    try:
                        trades_path.unlink()
                        trades_deleted = True
                    except Exception as e:
                        print(f"Warning: Could not delete {trades_path}: {e}")
                
                # Update session state
                st.session_state.last_refresh_time = time.time()
                st.session_state.reset_message = ("success", f"System reset! Deleted {deleted_count} price files. Timer reset to {new_start.strftime('%H:%M:%S')} UTC.")
                st.session_state.refresh_requested = True
                st.session_state.force_refresh = True
                st.session_state.reset_complete = True
                
                # Clear status and show success before rerun
                reset_status.success("✅ Reset complete! Reloading...")
                time.sleep(0.1)  # Brief pause to show message
                
                # Use experimental_rerun which is faster
                try:
                    st.experimental_rerun()
                except AttributeError:
                    st.rerun()
            except Exception as e:
                reset_status.error(f"❌ Reset failed: {e}")
                st.session_state.reset_message = ("error", f"Reset failed: {e}")
                st.session_state.refresh_requested = True
                st.session_state.force_refresh = True
                time.sleep(0.5)  # Show error message
                try:
                    st.experimental_rerun()
                except AttributeError:
                    st.rerun()
    
    # Auto-refresh status display
    auto_refresh = st.session_state.live_auto_refresh
    refresh_status_placeholder = st.empty()
    
    if auto_refresh:
        current_time = time.time()
        time_since_refresh = current_time - st.session_state.last_refresh_time
        time_until_refresh = max(0, st.session_state.refresh_interval - time_since_refresh)
        
        refresh_status_placeholder.info(
            f"🔄 Auto-refreshing every {st.session_state.refresh_interval}s. "
            f"Next refresh in {int(time_until_refresh)}s | "
            f"Last update: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
        )
        
        # Check for auto-refresh AFTER rendering controls
        if time_since_refresh >= st.session_state.refresh_interval:
            st.session_state.last_refresh_time = current_time
            st.session_state.refresh_requested = True
            st.session_state.force_refresh = True
            try:
                st.experimental_rerun()
            except AttributeError:
                st.rerun()
    else:
        refresh_status_placeholder.empty()


def render_markets(live_markets_meta: pd.DataFrame) -> None:
    """Render live markets grouped by event."""
    st.markdown("### Live Markets")
    
    # Group by event_slug (preferred) or slug
    group_col = "event_slug" if "event_slug" in live_markets_meta.columns else "slug"
    
    if group_col in live_markets_meta.columns:
        grouped = live_markets_meta.groupby(group_col)
        for group_name, group in grouped:
            # Use group name as header
            header_name = str(group_name).replace("-", " ").title()
            
            # Sort group by outcome probability desc
            if "outcome" in group.columns:
                group["outcome_val"] = pd.to_numeric(group["outcome"], errors="coerce").fillna(0)
                group = group.sort_values("outcome_val", ascending=False)
            
            with st.expander(f"{header_name} ({len(group)} outcomes)", expanded=True):
                market_cols = st.columns(min(4, len(group)))
                for idx, (_, market) in enumerate(group.iterrows()):
                    with market_cols[idx % len(market_cols)]:
                        outcome = float(market.get("outcome", 0)) if market.get("outcome") else 0.0
                        # Use Question/Outcome name
                        name = market.get("name", market.get("market_id", "Unknown"))
                        # Truncate long names but keep them identifiable
                        if "will-the-" in name.lower():
                            name = name.lower().replace("will-the-", "").replace("-win-super-bowl-2026", "").title()
                        elif "will-" in name.lower():
                            name = name.lower().replace("will-", "").replace("-win-the-chilean-presidential-election", "").title()
                            
                        st.metric(
                            name[:40],
                            f"{outcome:.3f}",
                            delta=None,
                            help=f"Last updated: {market.get('last_updated', 'N/A')}"
                        )
    else:
        # Fallback if no slug
        market_cols = st.columns(min(5, len(live_markets_meta)))
        for idx, (_, market) in enumerate(live_markets_meta.iterrows()):
            with market_cols[idx % len(market_cols)]:
                outcome = float(market.get("outcome", 0)) if market.get("outcome") else 0.0
                st.metric(
                    market.get("name", market.get("market_id", "Unknown"))[:30],
                    f"{outcome:.3f}",
                    delta=None,
                )


def render_trade_feed(live_trades_df: pd.DataFrame) -> None:
    """Render recent trades feed."""
    st.markdown("### Recent Trades")
    
    if live_trades_df.empty:
        st.info("No trades yet. Waiting for strategies to generate trades...")
    else:
        # Process trades
        for col in ["entry_price", "size", "p_hat", "outcome", "pnl", "capital_at_entry"]:
            if col in live_trades_df.columns:
                live_trades_df[col] = pd.to_numeric(live_trades_df[col], errors="coerce")
        
        # Show last 20 trades
        recent_trades = live_trades_df.tail(20).sort_values("entry_time", ascending=False)
        
        # Trade feed table
        st.dataframe(
            recent_trades[
                ["strategy_name", "market_id", "entry_time", "side", "entry_price", "pnl", "capital_at_entry"]
            ],
            use_container_width=True,
            height=400,
        )


def render_strategy_performance(live_trades_df: pd.DataFrame) -> None:
    """Render strategy performance metrics and charts."""
    st.markdown("### Strategy Performance (Live)")
    
    if live_trades_df.empty:
        st.info("No trades yet.")
        return
    
    # Calculate cumulative P&L per strategy
    live_trades_sorted = live_trades_df.sort_values("entry_time")
    strategy_perf = []
    
    for strategy in live_trades_sorted["strategy_name"].unique():
        strat_trades = live_trades_sorted[live_trades_sorted["strategy_name"] == strategy]
        total_pnl = strat_trades["pnl"].sum()
        n_trades = len(strat_trades)
        # Calculate current capital
        if len(strat_trades) > 0:
            last_capital = strat_trades["capital_at_entry"].iloc[-1]
            last_pnl = strat_trades["pnl"].iloc[-1]
            current_capital = last_capital + last_pnl
        else:
            current_capital = 100.0
        
        strategy_perf.append({
            "strategy_name": strategy,
            "total_pnl": total_pnl,
            "current_capital": current_capital,
            "n_trades": n_trades,
        })
    
    perf_df = pd.DataFrame(strategy_perf)
    perf_df = perf_df.sort_values("total_pnl", ascending=False)
    
    # Performance metrics
    perf_cols = st.columns(4)
    with perf_cols[0]:
        st.metric("Total Strategies", len(perf_df))
    with perf_cols[1]:
        st.metric("Total Trades", int(perf_df["n_trades"].sum()))
    with perf_cols[2]:
        st.metric("Total P&L", f"{perf_df['total_pnl'].sum():.3f}")
    with perf_cols[3]:
        best_strat = perf_df.iloc[0]["strategy_name"] if not perf_df.empty else "N/A"
        st.metric("Best Strategy", best_strat[:20])
    
    # Leaderboard
    st.dataframe(
        perf_df,
        use_container_width=True,
        height=300,
    )
    
    # Live equity curves
    st.markdown("### Live Equity Curves")
    
    live_trades_sorted["cum_pnl"] = live_trades_sorted.groupby("strategy_name")["pnl"].cumsum()
    
    try:
        import plotly.express as px
        fig_live = px.line(
            live_trades_sorted,
            x="entry_time",
            y="cum_pnl",
            color="strategy_name",
            title="Cumulative P&L Over Time (Live)",
        )
        fig_live.update_layout(
            xaxis_title="Time",
            yaxis_title="Cumulative P&L",
        )
        # Use static image mode to avoid CSP issues with JavaScript
        try:
            st.plotly_chart(fig_live, use_container_width=True, config={"displayModeBar": False, "staticPlot": True})
        except Exception:
            # Fallback: try without static mode
            st.plotly_chart(fig_live, use_container_width=True, config={"displayModeBar": False})
    except ImportError:
        st.warning("Plotly not available - charts disabled")
    except Exception as e:
        st.warning(f"Error rendering chart: {e}")
    
    # Per-strategy breakdown
    st.markdown("### Per-Strategy Breakdown")
    
    selected_live_strategy = st.selectbox(
        "Select strategy",
        options=perf_df["strategy_name"].tolist(),
        key="live_strategy_select",
    )
    
    if selected_live_strategy:
        strat_trades_live = live_trades_sorted[
            live_trades_sorted["strategy_name"] == selected_live_strategy
        ]
        
        if not strat_trades_live.empty:
            col_live1, col_live2 = st.columns(2)
            
            with col_live1:
                try:
                    import plotly.express as px
                    fig_strat_pnl = px.line(
                        strat_trades_live,
                        x="entry_time",
                        y="cum_pnl",
                        title=f"{selected_live_strategy} - Equity Curve",
                    )
                    fig_strat_pnl.update_layout(
                        xaxis_title="Time",
                        yaxis_title="Cumulative P&L",
                    )
                    # Use static image mode to avoid CSP issues
                    try:
                        st.plotly_chart(fig_strat_pnl, use_container_width=True, config={"displayModeBar": False, "staticPlot": True})
                    except Exception:
                        st.plotly_chart(fig_strat_pnl, use_container_width=True, config={"displayModeBar": False})
                except ImportError:
                    st.warning("Plotly not available")
                except Exception as e:
                    st.warning(f"Error rendering chart: {e}")
            
            with col_live2:
                try:
                    import plotly.express as px
                    fig_strat_trades = px.scatter(
                        strat_trades_live,
                        x="entry_time",
                        y="entry_price",
                        size="size",
                        color="pnl",
                        symbol="side",
                        title=f"{selected_live_strategy} - Trades",
                        color_continuous_scale="RdYlGn",
                    )
                    fig_strat_trades.update_layout(
                        xaxis_title="Time",
                        yaxis_title="Entry Price",
                    )
                    # Use static image mode to avoid CSP issues
                    try:
                        st.plotly_chart(fig_strat_trades, use_container_width=True, config={"displayModeBar": False, "staticPlot": True})
                    except Exception:
                        st.plotly_chart(fig_strat_trades, use_container_width=True, config={"displayModeBar": False})
                except ImportError:
                    st.warning("Plotly not available")
                except Exception as e:
                    st.warning(f"Error rendering chart: {e}")

