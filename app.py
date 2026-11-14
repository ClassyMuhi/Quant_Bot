"""
Quant_Bot - Unified Streamlit Interface
Hallmark Minimalist Dark Zinc Aesthetic
Integrates:
1. Paper Trading Order Terminal & Portfolio Ledger
2. God's Eye Market Intelligence Feed
3. Decision Engine Multi-Factor Recommendations
4. Backtest Engine Lab
"""

from datetime import datetime, timezone
import os
import streamlit as st
import pandas as pd

from pipeline.symbol_universe import SymbolUniverse
from godseye.intelligence import GodsEyeIntelligence
from decision_engine.engine import DecisionEngine
from paper_trading.portfolio import PaperPortfolio
from paper_trading.position_sizer import PositionSizer
from paper_trading.order_manager import OrderManager
from paper_trading.paper_broker import LocalPaperBroker, PaperExecutionGateway, SIMULATED_EXECUTION_NOTICE
from paper_trading.order_monitor import PositionMonitor
from paper_trading.autopilot import AutoPilotConfig, IntradayAutoPilot, ScanLogEntry
from backtest.engine import BacktestEngine
from backtest.strategy import SMACrossoverStrategy, RSIMeanReversionStrategy
from backtest.cost_model import IndianEquityCostModel

# Streamlit Page Config
st.set_page_config(
    page_title="Quant_Bot | Intelligence & Paper Trading",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Hallmark Zinc Design System
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Dark Zinc Palette */
    .stApp {
        background-color: #09090b;
        color: #f4f4f5;
    }
    
    /* Cards and Surfaces */
    .zinc-card {
        background-color: #18181b;
        border: 1px solid #27272a;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 16px;
    }
    
    .zinc-stat {
        background-color: #18181b;
        border: 1px solid #27272a;
        border-radius: 8px;
        padding: 14px 18px;
    }
    
    .stat-label {
        font-size: 0.75rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #a1a1aa;
        margin-bottom: 4px;
    }
    
    .stat-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.45rem;
        font-weight: 600;
        color: #f4f4f5;
    }
    
    /* Pill Badges */
    .pill-bullish {
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }
    
    .pill-bearish {
        background-color: rgba(244, 63, 94, 0.15);
        color: #f43f5e;
        border: 1px solid rgba(244, 63, 94, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }
    
    .pill-neutral {
        background-color: rgba(161, 161, 170, 0.15);
        color: #d4d4d8;
        border: 1px solid rgba(161, 161, 170, 0.3);
        border-radius: 9999px;
        padding: 3px 10px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }
    
    .pill-mode {
        background-color: rgba(59, 130, 246, 0.15);
        color: #60a5fa;
        border: 1px solid rgba(59, 130, 246, 0.3);
        border-radius: 9999px;
        padding: 4px 12px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.04em;
    }

    /* Disclaimer alert */
    .disclaimer-box {
        background-color: rgba(245, 158, 11, 0.08);
        border: 1px solid rgba(245, 158, 11, 0.25);
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 0.82rem;
        color: #fbbf24;
        margin-top: 10px;
        margin-bottom: 16px;
    }

    /* Hallmark Zinc Table (Pure HTML - Zero PyArrow) */
    .zinc-table-wrapper {
        border: 1px solid #27272a;
        border-radius: 8px;
        overflow-x: auto;
        margin-top: 10px;
        margin-bottom: 16px;
    }
    .zinc-table {
        width: 100%;
        border-collapse: collapse;
        background-color: #18181b;
        color: #f4f4f5;
        font-size: 0.86rem;
    }
    .zinc-table th {
        background-color: #202024;
        color: #a1a1aa;
        font-weight: 600;
        text-align: left;
        padding: 10px 14px;
        border-bottom: 1px solid #3f3f46;
        text-transform: uppercase;
        font-size: 0.72rem;
        letter-spacing: 0.05em;
    }
    .zinc-table td {
        padding: 10px 14px;
        border-bottom: 1px solid #27272a;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.84rem;
    }
    .zinc-table tr:hover {
        background-color: #27272a;
    }
</style>
""", unsafe_allow_html=True)


def render_zinc_table(df: pd.DataFrame, max_height: int | None = None) -> None:
    """
    Renders DataFrame as pure HTML table with Hallmark dark zinc styling.
    Zero PyArrow dependency to guarantee 100% Windows AppLocker compatibility.
    """
    if df is None or df.empty:
        st.info("No records to display.")
        return

    styled_df = df.copy()
    for col in styled_df.columns:
        col_str = str(col).lower()
        if "sentiment" in col_str:
            styled_df[col] = styled_df[col].apply(
                lambda s: f"<span class='pill-bullish'>{s}</span>" if str(s).upper() == "BULLISH"
                else (f"<span class='pill-bearish'>{s}</span>" if str(s).upper() == "BEARISH"
                else f"<span class='pill-neutral'>{s}</span>")
            )
        elif "side" in col_str:
            styled_df[col] = styled_df[col].apply(
                lambda s: f"<span class='pill-bullish'>{s}</span>" if str(s).upper() == "BUY"
                else f"<span class='pill-bearish'>{s}</span>"
            )

    html = styled_df.to_html(classes="zinc-table", index=False, escape=False)
    height_style = f"max-height: {max_height}px; overflow-y: auto;" if max_height else ""
    st.markdown(f"<div class='zinc-table-wrapper' style='{height_style}'>{html}</div>", unsafe_allow_html=True)


# Initialize Session State Singletons
@st.cache_resource
def get_universe() -> SymbolUniverse:
    return SymbolUniverse()

@st.cache_resource
def get_godseye() -> GodsEyeIntelligence:
    return GodsEyeIntelligence()

@st.cache_resource
def get_decision_engine() -> DecisionEngine:
    return DecisionEngine()

def get_portfolio() -> PaperPortfolio:
    if "portfolio" not in st.session_state:
        st.session_state.portfolio = PaperPortfolio()
    return st.session_state.portfolio

def get_order_manager(port: PaperPortfolio) -> OrderManager:
    return OrderManager(portfolio=port)

def get_gateway(port: PaperPortfolio) -> PaperExecutionGateway:
    return PaperExecutionGateway(portfolio=port)

universe = get_universe()
godseye = get_godseye()
decision_engine = get_decision_engine()
portfolio = get_portfolio()
order_manager = get_order_manager(portfolio)
gateway = get_gateway(portfolio)
monitor = PositionMonitor(portfolio)

# Pre-fetch fallback quotes from Gold data if live API unavailable
def get_current_stock_quote(symbol: str) -> float:
    try:
        import duckdb
        path = f"data/gold/{symbol.upper()}.parquet"
        if os.path.exists(path):
            con = duckdb.connect()
            df = con.execute(f"SELECT close FROM read_parquet('{path}') ORDER BY date DESC LIMIT 1").df()
            con.close()
            if not df.empty:
                return float(df.iloc[0]["close"])
    except Exception:
        pass
    defaults = {"RELIANCE": 2480.0, "TCS": 3520.0, "INFY": 1460.0, "HDFCBANK": 1520.0, "ICICIBANK": 1050.0}
    return defaults.get(symbol.upper(), 1000.0)


# Header & Active Mode Badge
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("### ⚡ QUANT_BOT &mdash; Intelligent Trading System")
    st.caption("Event-Aware AI Quantitative Research & Indian Equity Paper Trading")
with col_h2:
    st.markdown(f"<div style='text-align: right;'><span class='pill-mode'>MODE: {gateway.mode_label}</span></div>", unsafe_allow_html=True)

# Main Navigation Tabs
tab_paper, tab_autopilot, tab_decision, tab_godseye, tab_backtest = st.tabs([
    "📈 Paper Trading Terminal",
    "🤖 Intraday Auto-Pilot",
    "🧠 Decision Engine",
    "👁️ God's Eye Intelligence",
    "📊 Backtest Lab",
])


# -------------------------------------------------------------
# TAB 1: PAPER TRADING TERMINAL
# -------------------------------------------------------------
with tab_paper:
    st.markdown("#### Paper Trading Order Workstation")

    summary = portfolio.get_summary()

    # Portfolio KPI Strip
    kpi_cols = st.columns(5)
    with kpi_cols[0]:
        st.markdown(f"<div class='zinc-stat'><div class='stat-label'>Total Equity</div><div class='stat-value'>₹{summary['total_equity']:,.2f}</div></div>", unsafe_allow_html=True)
    with kpi_cols[1]:
        st.markdown(f"<div class='zinc-stat'><div class='stat-label'>Available Cash</div><div class='stat-value'>₹{summary['cash']:,.2f}</div></div>", unsafe_allow_html=True)
    with kpi_cols[2]:
        st.markdown(f"<div class='zinc-stat'><div class='stat-label'>Invested Value</div><div class='stat-value'>₹{summary['invested_value']:,.2f}</div></div>", unsafe_allow_html=True)
    with kpi_cols[3]:
        pnl_color = "#10b981" if summary['realized_pnl'] >= 0 else "#f43f5e"
        st.markdown(f"<div class='zinc-stat'><div class='stat-label'>Realized P&L</div><div class='stat-value' style='color:{pnl_color}'>₹{summary['realized_pnl']:+,.2f}</div></div>", unsafe_allow_html=True)
    with kpi_cols[4]:
        un_color = "#10b981" if summary['unrealized_pnl'] >= 0 else "#f43f5e"
        st.markdown(f"<div class='zinc-stat'><div class='stat-label'>Unrealized P&L</div><div class='stat-value' style='color:{un_color}'>₹{summary['unrealized_pnl']:+,.2f}</div></div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)

    # Order Form & Live Calculation Columns
    col_form, col_calc = st.columns([1.1, 1.3])

    available_symbols = universe.get_symbols()
    default_sym_idx = 0

    with col_form:
        st.markdown("<div class='zinc-card'>", unsafe_allow_html=True)
        st.markdown("##### ⚙️ Manual Order Configuration")

        c1, c2 = st.columns(2)
        with c1:
            stock_symbol = st.selectbox("Stock Symbol (NSE)", available_symbols, index=default_sym_idx)
        with c2:
            order_side = st.radio("Order Side", ["BUY", "SELL"], horizontal=True)

        c3, c4 = st.columns(2)
        with c3:
            trading_style = st.selectbox("Trading Style", ["DELIVERY", "INTRADAY"])
        with c4:
            order_type = st.selectbox("Order Type", ["MARKET", "LIMIT"])

        current_quote = get_current_stock_quote(stock_symbol)

        limit_price = None
        if order_type == "LIMIT":
            limit_price = st.number_input("Limit Price (₹)", min_value=1.0, value=float(current_quote), step=1.0)

        effective_entry = limit_price if (order_type == "LIMIT" and limit_price) else current_quote

        c5, c6 = st.columns(2)
        with c5:
            investment_amount = st.number_input("Investment Amount (₹)", min_value=1000.0, max_value=10000000.0, value=50000.0, step=5000.0)
        with c6:
            risk_percent = st.slider("Risk Budget (% of Investment)", min_value=0.5, max_value=10.0, value=2.0, step=0.5)

        # SL and Target configuration mode
        sl_mode = st.radio("Stop-Loss Mode", ["Percentage (%)", "Exact Price (₹)"], horizontal=True)
        if sl_mode == "Percentage (%)":
            sl_pct = st.number_input("Stop-Loss (%)", min_value=0.5, max_value=25.0, value=2.5, step=0.5)
            sl_price = round(effective_entry * (1.0 - (sl_pct / 100.0) if order_side == "BUY" else 1.0 + (sl_pct / 100.0)), 2)
        else:
            default_sl = effective_entry * 0.975 if order_side == "BUY" else effective_entry * 1.025
            sl_price = st.number_input("Stop-Loss Price (₹)", min_value=0.5, value=float(round(default_sl, 2)), step=1.0)

        tp_mode = st.radio("Target Mode", ["Percentage (%)", "Exact Price (₹)"], horizontal=True)
        if tp_mode == "Percentage (%)":
            tp_pct = st.number_input("Target Profit (%)", min_value=0.5, max_value=50.0, value=5.0, step=0.5)
            target_price = round(effective_entry * (1.0 + (tp_pct / 100.0) if order_side == "BUY" else 1.0 - (tp_pct / 100.0)), 2)
        else:
            default_tp = effective_entry * 1.05 if order_side == "BUY" else effective_entry * 0.95
            target_price = st.number_input("Target Price (₹)", min_value=0.5, value=float(round(default_tp, 2)), step=1.0)

        c7, c8 = st.columns(2)
        with c7:
            time_in_force = st.selectbox("Validity (TIF)", ["DAY", "IOC", "GTC"])
        with c8:
            max_duration = st.selectbox("Max Holding Duration", ["None", "3 Days", "7 Days", "30 Days"])

        st.markdown("</div>", unsafe_allow_html=True)

    with col_calc:
        st.markdown("<div class='zinc-card'>", unsafe_allow_html=True)
        st.markdown("##### 📐 Real-Time Position Sizing & Risk Assessment")

        # Live calculation
        sizer = PositionSizer()
        sizing_result = sizer.calculate_sizing(
            symbol=stock_symbol,
            side=order_side,
            investment_amount=investment_amount,
            risk_percent=risk_percent,
            entry_price=effective_entry,
            stop_loss_price=sl_price,
            target_price=target_price,
            available_cash=portfolio.cash,
        )

        st.markdown(f"**Current Quote:** `₹{current_quote:,.2f}` | **Timestamp:** `{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}`")

        rc1, rc2 = st.columns(2)
        with rc1:
            st.metric("Proposed Entry", f"₹{effective_entry:,.2f}")
            st.metric("Stop-Loss Price", f"₹{sl_price:,.2f}")
            st.metric("Max Potential Loss", f"₹{sizing_result.max_loss_inr:,.2f}" if sizing_result.is_valid else "N/A")
            st.metric("Estimated Taxes & Fees", f"₹{sizing_result.estimated_costs:,.2f}" if sizing_result.is_valid else "N/A")
        with rc2:
            st.metric("Quantity of Shares", f"{sizing_result.quantity} shares" if sizing_result.is_valid else "0")
            st.metric("Target Price", f"₹{target_price:,.2f}")
            st.metric("Expected Profit", f"₹{sizing_result.expected_profit_inr:,.2f}" if sizing_result.is_valid else "N/A")
            st.metric("Risk-to-Reward Ratio", f"1 : {sizing_result.risk_to_reward_ratio:.2f}" if sizing_result.is_valid else "N/A")

        st.divider()
        st.metric("Total Capital Required", f"₹{sizing_result.total_capital_required:,.2f}" if sizing_result.is_valid else "N/A")

        if not sizing_result.is_valid:
            st.error(f"⚠️ Order Validation: {sizing_result.error_message}")
        else:
            st.success("✅ Risk constraints satisfied. Integer share sizing calculated.")

        st.markdown(f"<div class='disclaimer-box'><b>⚠️ Execution Disclaimer:</b> {SIMULATED_EXECUTION_NOTICE}</div>", unsafe_allow_html=True)

        # Submit button
        submit_disabled = not sizing_result.is_valid
        if st.button("🚀 Submit Paper Order", disabled=submit_disabled, use_container_width=True, type="primary"):
            order, err = order_manager.validate_and_create_order(
                symbol=stock_symbol,
                side=order_side,
                investment_amount=investment_amount,
                risk_percent=risk_percent,
                entry_price=effective_entry,
                stop_loss_price=sl_price,
                target_price=target_price,
                order_type=order_type,
                trading_style=trading_style,
                limit_price=limit_price,
                time_in_force=time_in_force,
                requested_quantity=sizing_result.quantity,
            )
            if err:
                st.error(f"Order Rejected: {err}")
            else:
                filled_order, trade_rec = gateway.execute(order, current_market_price=effective_entry)
                st.success(f"🎉 Order {filled_order.order_id} successfully FILLED: {filled_order.side} {filled_order.quantity} shares of {filled_order.symbol} @ ₹{filled_order.executed_price:,.2f}")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # Open Positions & Trade History
    st.markdown("---")
    c_holdings, c_history = st.columns([1.2, 1.0])

    with c_holdings:
        st.markdown("##### 💼 Open Holdings & Active Positions")
        if not portfolio.holdings:
            st.info("No active open positions in paper portfolio.")
        else:
            h_rows = []
            for s, pos in portfolio.holdings.items():
                curr_p = get_current_stock_quote(s)
                qty = pos["quantity"]
                avg_p = pos["avg_price"]
                market_val = qty * curr_p
                unrealized = (curr_p - avg_p) * qty
                h_rows.append({
                    "Symbol": s,
                    "Quantity": qty,
                    "Avg Price": f"₹{avg_p:,.2f}",
                    "Current": f"₹{curr_p:,.2f}",
                    "Market Value": f"₹{market_val:,.2f}",
                    "Unrealized P&L": f"₹{unrealized:+,.2f}",
                    "Stop-Loss": f"₹{pos.get('sl_price', 0):,.2f}",
                    "Target": f"₹{pos.get('target_price', 0):,.2f}",
                    "Style": pos.get("trading_style", "DELIVERY"),
                })
            render_zinc_table(pd.DataFrame(h_rows))

            # Manual Tick Simulator to test SL/TP triggers
            st.markdown("###### 🔍 Simulate Candle Exit Trigger")
            sim_cols = st.columns([2, 1, 1, 1])
            with sim_cols[0]:
                test_sym = st.selectbox("Position to Test", list(portfolio.holdings.keys()))
            with sim_cols[1]:
                test_high = st.number_input("Simulated High", value=float(get_current_stock_quote(test_sym) * 1.05))
            with sim_cols[2]:
                test_low = st.number_input("Simulated Low", value=float(get_current_stock_quote(test_sym) * 0.95))
            with sim_cols[3]:
                if st.button("Simulate Tick", use_container_width=True):
                    trigger = monitor.check_candle(test_sym, test_high, test_low, close=(test_high+test_low)/2)
                    if trigger:
                        st.warning(f"Trigger Fired: {trigger.trigger_type} at ₹{trigger.trigger_price:,.2f}!")
                        st.rerun()
                    else:
                        st.info("Candle remained within SL and Target boundaries.")

    with c_history:
        st.markdown("##### 📜 Executed Paper Trades History")
        if not portfolio.trades:
            st.info("No trades executed yet.")
        else:
            t_rows = []
            for t in reversed(portfolio.trades[-10:]):
                t_rows.append({
                    "Time": t.get("timestamp", "")[11:19],
                    "ID": t.get("order_id", ""),
                    "Symbol": t.get("symbol", ""),
                    "Side": t.get("side", ""),
                    "Qty": t.get("quantity", 0),
                    "Price": f"₹{t.get('price', 0):,.2f}",
                    "P&L": f"₹{t.get('realized_pnl', 0):+,.2f}",
                })
            render_zinc_table(pd.DataFrame(t_rows))

        if st.button("🔄 Reset Paper Account to Default (₹10,00,000)"):
            portfolio.reset()
            st.success("Paper portfolio reset!")
            st.rerun()


# -------------------------------------------------------------
# TAB 2: INTRADAY AUTO-PILOT
# -------------------------------------------------------------
with tab_autopilot:
    st.markdown("#### 🤖 Intraday Systematic Auto-Pilot")
    st.caption("Autonomous multi-stock intraday scanning and paper execution engine (Minimum 10-minute cycle)")

    if "autopilot_active" not in st.session_state:
        st.session_state.autopilot_active = False

    col_cfg, col_telemetry = st.columns([1.1, 1.3])

    with col_cfg:
        st.markdown("<div class='zinc-card'>", unsafe_allow_html=True)
        st.markdown("##### ⚙️ Auto-Pilot Parameters")

        # 1. Amount User Willing to Put In
        auto_capital = st.number_input(
            "Capital Allocated to Auto-Pilot (₹)",
            min_value=10000.0,
            max_value=10000000.0,
            value=100000.0,
            step=10000.0,
            help="Total cash budget the auto-pilot is allowed to deploy into intraday positions."
        )

        # 2. Frequency Time (Strict Minimum 10 Mins)
        freq_option = st.selectbox(
            "Scan & Trade Frequency",
            ["10 Minutes", "15 Minutes", "20 Minutes", "30 Minutes", "45 Minutes", "60 Minutes"],
            index=0,
            help="Enforces a minimum interval of 10 minutes to allow market price formation and prevent excessive churn."
        )
        freq_mins = int(freq_option.split()[0])

        # 3. Execution Window: Start to End Time
        w_c1, w_c2 = st.columns(2)
        with w_c1:
            start_time_opt = st.selectbox(
                "Daily Start Time (IST)",
                ["09:15 AM", "09:30 AM", "10:00 AM", "10:30 AM"],
                index=0,
                help="When the Auto-Pilot begins scanning for new intraday entry setups."
            )
        with w_c2:
            end_time_opt = st.selectbox(
                "Daily End Time / Cutoff (IST)",
                ["02:30 PM", "02:45 PM", "03:00 PM", "03:15 PM"],
                index=3,
                help="Cutoff time after which NO new intraday positions will be opened."
            )

        start_hh_mm = {
            "09:15 AM": "09:15", "09:30 AM": "09:30", "10:00 AM": "10:00", "10:30 AM": "10:30"
        }[start_time_opt]
        end_hh_mm = {
            "02:30 PM": "14:30", "02:45 PM": "14:45", "03:00 PM": "15:00", "03:15 PM": "15:15"
        }[end_time_opt]

        st.markdown(
            "<div style='font-size: 0.78rem; color: #a1a1aa; margin-top: 4px;'>"
            "🛡️ <b>Mandatory Square-off:</b> Open intraday positions will automatically close at <b>03:20 PM IST</b>."
            "</div>",
            unsafe_allow_html=True
        )

        st.divider()

        # Risk Controls
        r_c1, r_c2 = st.columns(2)
        with r_c1:
            auto_risk_pct = st.slider("Risk Per Trade (%)", min_value=0.5, max_value=3.0, value=1.5, step=0.5)
        with r_c2:
            auto_max_pos = st.selectbox("Max Concurrent Positions", [1, 2, 3, 5], index=2)

        min_conf = st.slider("Min Signal Confidence Threshold", min_value=0.50, max_value=0.90, value=0.60, step=0.05)

        # Initialize / Update AutoPilot Object
        ap_config = AutoPilotConfig(
            allocated_capital=auto_capital,
            frequency_minutes=freq_mins,
            start_time_str=start_hh_mm,
            end_time_str=end_hh_mm,
            square_off_time_str="15:20",
            risk_per_trade_pct=auto_risk_pct,
            max_active_positions=auto_max_pos,
            min_confidence=min_conf,
        )

        if "autopilot" not in st.session_state:
            st.session_state.autopilot = IntradayAutoPilot(
                config=ap_config,
                portfolio=portfolio,
                universe=universe,
                godseye=godseye,
                decision_engine=decision_engine,
            )
        else:
            st.session_state.autopilot.config = ap_config

        pilot = st.session_state.autopilot

        st.divider()

        # Main Activation Toggle
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if not st.session_state.autopilot_active:
                if st.button("▶️ Activate Auto-Pilot", type="primary", use_container_width=True):
                    st.session_state.autopilot_active = True
                    pilot.is_running = True
                    cycle_res = pilot.execute_cycle(price_lookup_func=get_current_stock_quote)
                    st.success(f"Auto-Pilot Activated! Executed Cycle #{cycle_res['cycle_number']}")
                    st.rerun()
            else:
                if st.button("⏹️ Stop Auto-Pilot", type="secondary", use_container_width=True):
                    st.session_state.autopilot_active = False
                    pilot.is_running = False
                    st.warning("Auto-Pilot Paused.")
                    st.rerun()

        with btn_c2:
            if st.button("⚡ Run Scan Cycle Now", use_container_width=True):
                cycle_res = pilot.execute_cycle(price_lookup_func=get_current_stock_quote)
                st.info(f"Manual scan complete: {cycle_res['trades_placed']} trades placed.")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with col_telemetry:
        st.markdown("<div class='zinc-card'>", unsafe_allow_html=True)
        st.markdown("##### 📡 Live Auto-Pilot Telemetry")

        ist_now = pilot.get_ist_now()
        is_window, win_msg = pilot.is_within_trading_window(ist_now)

        if st.session_state.autopilot_active:
            status_html = "<span class='pill-bullish'>● ACTIVE (SYSTEMATIC POLLING)</span>"
        else:
            status_html = "<span class='pill-neutral'>○ STANDBY (STOPPED)</span>"

        t_c1, t_c2 = st.columns([1.5, 1])
        with t_c1:
            st.markdown(f"**Engine Status:** {status_html}", unsafe_allow_html=True)
            st.caption(f"Current IST Time: **{ist_now.strftime('%I:%M:%S %p')}** | Window: {win_msg}")
        with t_c2:
            st.metric("Total Cycles Executed", pilot.cycle_count)

        st.divider()

        intraday_invested = sum(
            p["quantity"] * p.get("current_price", p["avg_price"])
            for p in portfolio.holdings.values()
            if p.get("trading_style") == "INTRADAY"
        )
        remaining_cap = max(0.0, auto_capital - intraday_invested)

        m_c1, m_c2, m_c3 = st.columns(3)
        with m_c1:
            st.metric("Allocated Budget", f"₹{auto_capital:,.2f}")
        with m_c2:
            st.metric("Currently Deployed", f"₹{intraday_invested:,.2f}")
        with m_c3:
            st.metric("Available Pool", f"₹{remaining_cap:,.2f}")

        st.divider()
        if pilot.next_cycle_time:
            st.markdown(f"**Next Scheduled Scan:** `{pilot.next_cycle_time.strftime('%I:%M:%S %p IST')}` (every {freq_mins} mins)")
        else:
            st.markdown(f"**Scan Interval:** Every `{freq_mins} minutes` (Starts upon activation)")

        st.markdown(
            f"<div class='disclaimer-box'>"
            f"<b>⚙️ Auto-Pilot Protocol:</b> At each {freq_mins}-min interval, the bot refreshes God's Eye market news, "
            f"scans the NSE universe for high-confidence confluence signals (&ge;{min_conf:.0%}), sizes risk-managed integer shares, "
            f"routes paper orders automatically, and guarantees 03:20 PM IST auto-square-off."
            f"</div>",
            unsafe_allow_html=True
        )

        st.markdown("</div>", unsafe_allow_html=True)

    # Active Intraday Holdings & Square-off
    st.markdown("---")
    ih_c1, ih_c2 = st.columns([2, 1])
    with ih_c1:
        st.markdown("##### 💼 Active Auto-Pilot Intraday Positions")
    with ih_c2:
        if st.button("🚨 Emergency Square-Off All Intraday", use_container_width=True):
            closed = pilot.square_off_all_intraday(price_lookup_func=get_current_stock_quote)
            st.warning(f"Squared off {len(closed)} open intraday positions.")
            st.rerun()

    intraday_holdings = {
        s: pos for s, pos in portfolio.holdings.items()
        if pos.get("trading_style") == "INTRADAY"
    }

    if not intraday_holdings:
        st.info("No active open intraday positions managed by Auto-Pilot.")
    else:
        ap_rows = []
        for s, pos in intraday_holdings.items():
            curr_p = get_current_stock_quote(s)
            qty = pos["quantity"]
            avg_p = pos["avg_price"]
            market_val = qty * curr_p
            unrealized = (curr_p - avg_p) * qty
            ap_rows.append({
                "Symbol": s,
                "Qty": qty,
                "Avg Entry": f"₹{avg_p:,.2f}",
                "Current": f"₹{curr_p:,.2f}",
                "Market Value": f"₹{market_val:,.2f}",
                "Unrealized P&L": f"₹{unrealized:+,.2f}",
                "Stop-Loss": f"₹{pos.get('sl_price', 0):,.2f}",
                "Target": f"₹{pos.get('target_price', 0):,.2f}",
                "Opened At": pos.get("opened_at", "")[11:19],
            })
        render_zinc_table(pd.DataFrame(ap_rows))

    # Real-Time Telemetry & Audit Logs
    st.markdown("##### 📜 Auto-Pilot Scan & Decision Audit Log")
    if not pilot.scan_logs:
        st.info("No scan activity recorded yet. Activate Auto-Pilot or click 'Run Scan Cycle Now'.")
    else:
        log_data = []
        for log in pilot.scan_logs[:20]:
            log_data.append({
                "Time (IST)": log.timestamp,
                "Symbol": log.symbol,
                "Signal": log.decision,
                "Score": f"{log.score:+.2f}",
                "Confidence": f"{log.confidence:.0%}",
                "Action": log.action,
                "Details": log.details,
            })
        render_zinc_table(pd.DataFrame(log_data), max_height=320)


# -------------------------------------------------------------
# TAB 3: DECISION ENGINE
# -------------------------------------------------------------
with tab_decision:
    st.markdown("#### Decision Engine & Technical-Event Confluence")

    dec_sym = st.selectbox("Select Stock to Analyze", universe.get_symbols(), index=0, key="dec_sym_select")
    curr_px = get_current_stock_quote(dec_sym)

    decision = decision_engine.evaluate(dec_sym, current_price=curr_px)

    st.markdown("<div class='zinc-card'>", unsafe_allow_html=True)
    d_c1, d_c2, d_c3, d_c4 = st.columns([1.5, 1, 1, 1])

    with d_c1:
        if decision.decision == "BUY":
            st.markdown(f"<h2>{dec_sym} <span class='pill-bullish'>BUY</span></h2>", unsafe_allow_html=True)
        elif decision.decision == "SELL":
            st.markdown(f"<h2>{dec_sym} <span class='pill-bearish'>SELL</span></h2>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h2>{dec_sym} <span class='pill-neutral'>HOLD</span></h2>", unsafe_allow_html=True)
        st.caption(f"Evaluated at {decision.timestamp}")

    with d_c2:
        st.metric("Combined Score", f"{decision.combined_score:+.2f}")
    with d_c3:
        st.metric("Conviction / Confidence", f"{decision.confidence:.0%}")
    with d_c4:
        st.metric("Technical Signal", decision.technical_signal)

    st.markdown("##### 📝 Rationale & Institutional Breakdown")
    st.write(decision.explanation)

    if decision.suggested_entry_price and decision.suggested_stop_loss and decision.suggested_target_price:
        st.markdown("##### 🎯 Suggested Setup Levels")
        lvl_cols = st.columns(4)
        with lvl_cols[0]:
            st.metric("Suggested Entry", f"₹{decision.suggested_entry_price:,.2f}")
        with lvl_cols[1]:
            st.metric("Suggested Stop-Loss", f"₹{decision.suggested_stop_loss:,.2f}")
        with lvl_cols[2]:
            st.metric("Suggested Target", f"₹{decision.suggested_target_price:,.2f}")
        with lvl_cols[3]:
            rr = abs(decision.suggested_target_price - decision.suggested_entry_price) / abs(decision.suggested_entry_price - decision.suggested_stop_loss)
            st.metric("Risk : Reward", f"1 : {rr:.2f}")

    st.markdown("</div>", unsafe_allow_html=True)

    if decision.recent_events:
        st.markdown("##### 📰 Recent God's Eye Events Considered")
        e_df = pd.DataFrame(decision.recent_events)[["published_at", "title", "sentiment", "importance", "confidence", "source"]]
        render_zinc_table(e_df)


# -------------------------------------------------------------
# TAB 3: GOD'S EYE MARKET INTELLIGENCE
# -------------------------------------------------------------
with tab_godseye:
    st.markdown("#### God's Eye — Real-Time Indian Market Intelligence")
    st.caption("Scrapes and normalizes RSS feeds from Economic Times, Moneycontrol, Livemint, and RBI")

    col_btn, col_stats = st.columns([1, 3])
    with col_btn:
        if st.button("📡 Ingest Live News Feeds Now", use_container_width=True):
            with st.spinner("Connecting to RSS feeds & classifying events..."):
                new_events = godseye.collect_and_process()
                st.success(f"Ingested & processed {len(new_events)} news stories!")
                st.rerun()

    market_summary = godseye.get_market_sentiment_summary()

    with col_stats:
        ms_cols = st.columns(4)
        ms_cols[0].metric("Total Events Ingested", market_summary["total_events"])
        ms_cols[1].metric("Bullish Events", market_summary["bullish_count"])
        ms_cols[2].metric("Bearish Events", market_summary["bearish_count"])
        ms_cols[3].metric("Neutral / Macro", market_summary["neutral_count"])

    st.markdown("##### 🗞️ Latest Classified Market Events")
    if not market_summary["events"]:
        st.info("No market events stored yet. Click 'Ingest Live News Feeds Now' to fetch initial intelligence.")
    else:
        events_df = pd.DataFrame(market_summary["events"])
        display_cols = ["published_at", "title", "sentiment", "importance", "confidence", "affected_symbols", "source"]
        present_cols = [c for c in display_cols if c in events_df.columns]
        render_zinc_table(events_df[present_cols], max_height=420)


# -------------------------------------------------------------
# TAB 4: BACKTEST LAB
# -------------------------------------------------------------
with tab_backtest:
    st.markdown("#### Backtesting Engine Analytics")
    st.caption("Zero Look-Ahead Bias Simulation with Indian Market Transaction Costs & Slippage")

    b_col1, b_col2, b_col3 = st.columns(3)
    with b_col1:
        bt_stock = st.selectbox("Stock", universe.get_symbols(), index=0, key="bt_stock")
    with b_col2:
        bt_strategy = st.selectbox("Strategy", ["SMA Crossover (20/50)", "RSI Mean Reversion (30/70)"])
    with b_col3:
        bt_capital = st.number_input("Initial Capital (₹)", value=1000000.0, step=100000.0)

    if st.button("▶️ Run Backtest Simulation", type="primary"):
        with st.spinner("Running historical backtest simulation..."):
            engine = BacktestEngine(initial_capital=bt_capital, cost_model=IndianEquityCostModel())
            if bt_strategy == "SMA Crossover (20/50)":
                strat = SMACrossoverStrategy(fast_period=20, slow_period=50)
            else:
                strat = RSIMeanReversionStrategy(rsi_period=14, oversold_threshold=30, overbought_threshold=70)

            res = engine.run_symbol(bt_stock, strat)

            st.markdown("<div class='zinc-card'>", unsafe_allow_html=True)
            st.markdown(f"##### Results for {bt_stock} &mdash; {bt_strategy}")

            m_cols = st.columns(5)
            m_cols[0].metric("CAGR", f"{res.strategy_metrics.cagr*100:.2f}%")
            m_cols[1].metric("Sharpe Ratio", f"{res.strategy_metrics.sharpe_ratio:.2f}")
            m_cols[2].metric("Sortino Ratio", f"{res.strategy_metrics.sortino_ratio:.2f}")
            m_cols[3].metric("Max Drawdown", f"{res.strategy_metrics.max_drawdown*100:.2f}%")
            m_cols[4].metric("Win Rate", f"{res.strategy_metrics.win_rate*100:.1f}%")

            # Comparative Metrics Table
            comp_data = {
                "Metric": ["Initial Capital", "Final Equity", "CAGR", "Sharpe", "Sortino", "Max Drawdown", "Trades"],
                "Strategy": [
                    f"₹{res.strategy_metrics.initial_equity:,.2f}",
                    f"₹{res.strategy_metrics.final_equity:,.2f}",
                    f"{res.strategy_metrics.cagr*100:.2f}%",
                    f"{res.strategy_metrics.sharpe_ratio:.2f}",
                    f"{res.strategy_metrics.sortino_ratio:.2f}",
                    f"{res.strategy_metrics.max_drawdown*100:.2f}%",
                    str(res.strategy_metrics.total_trades),
                ],
                "Buy & Hold": [
                    f"₹{res.benchmark_metrics.initial_equity:,.2f}",
                    f"₹{res.benchmark_metrics.final_equity:,.2f}",
                    f"{res.benchmark_metrics.cagr*100:.2f}%",
                    f"{res.benchmark_metrics.sharpe_ratio:.2f}",
                    f"{res.benchmark_metrics.sortino_ratio:.2f}",
                    f"{res.benchmark_metrics.max_drawdown*100:.2f}%",
                    str(res.benchmark_metrics.total_trades),
                ],
            }
            render_zinc_table(pd.DataFrame(comp_data))
            st.markdown("</div>", unsafe_allow_html=True)

