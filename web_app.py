"""
Quant_Bot - Next-Gen High Performance Quantitative Dashboard
Built with Starlette + Vanilla JS / Modern Dark Zinc Tailwind styling.
Features:
- Real-time 2-second telemetry polling without page flickering
- Live P&L Command Center with MegaBull cloud synchronization
- Autonomous Auto-Pilot background daemon with live countdown timer
- Real-time scrolling audit log terminal
- Live Decision Engine & 1-click MegaBull order execution
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
import uvicorn

from pipeline.symbol_universe import SymbolUniverse
from decision_engine.engine import DecisionEngine
from godseye.intelligence import GodsEyeIntelligence
from paper_trading.portfolio import PaperPortfolio
from paper_trading.paper_broker import PaperExecutionGateway
from paper_trading.autopilot import get_global_autopilot, AutoPilotConfig
from paper_trading.order_manager import PaperOrder

logger = logging.getLogger("QuantBotWeb")

# Initialize Singletons
universe = SymbolUniverse()
portfolio = PaperPortfolio()
gateway = PaperExecutionGateway(portfolio=portfolio)
decision_engine = DecisionEngine()
pilot = get_global_autopilot(config=AutoPilotConfig(allocated_capital=100000.0), portfolio=portfolio)


def get_current_stock_quote(symbol: str) -> float:
    try:
        import duckdb
        path = Path(f"data/gold/{symbol.upper()}.parquet")
        if path.exists():
            con = duckdb.connect()
            df = con.execute(f"SELECT close FROM read_parquet('{path.as_posix()}') ORDER BY date DESC LIMIT 1").df()
            con.close()
            if not df.empty:
                return float(df.iloc[0]["close"])
    except Exception:
        pass
    defaults = {"RELIANCE": 2480.0, "TCS": 3520.0, "INFY": 1460.0, "HDFCBANK": 812.0, "MARUTI": 12660.0, "ITC": 291.0}
    return defaults.get(symbol.upper(), 1000.0)


async def api_state(request):
    """Returns the complete real-time state of the trading bot."""
    mb_connected = gateway.megabull_client is not None
    mb_profile = {}
    mb_positions = []
    
    if mb_connected:
        try:
            mb_profile = gateway.megabull_client.get_user_profile()
            mb_positions = gateway.megabull_client.get_positions()
        except Exception as e:
            logger.warning(f"Error fetching MegaBull state: {e}")

    summary = portfolio.get_summary()

    # Calculate countdown to next cycle
    ist_now = pilot.get_ist_now()
    countdown_seconds = 0
    if pilot.next_cycle_time:
        diff = (pilot.next_cycle_time - ist_now).total_seconds()
        countdown_seconds = max(0, int(diff))

    # Compile positions with live quotes
    holdings_list = []
    for sym, h in portfolio.holdings.items():
        curr_px = get_current_stock_quote(sym)
        qty = h.get("quantity", 0)
        avg_px = h.get("avg_price", 0.0)
        mkt_val = round(qty * curr_px, 2)
        unrealized = round((curr_px - avg_px) * qty, 2)
        unrealized_pct = round(((curr_px - avg_px) / avg_px * 100.0) if avg_px else 0.0, 2)
        holdings_list.append({
            "symbol": sym,
            "quantity": qty,
            "avg_price": avg_px,
            "current_price": curr_px,
            "market_value": mkt_val,
            "unrealized_pnl": unrealized,
            "unrealized_pct": unrealized_pct,
            "style": h.get("trading_style", "INTRADAY"),
            "sl_price": h.get("sl_price", 0.0),
            "target_price": h.get("target_price", 0.0),
        })

    # Scan logs formatted
    logs = [
        {
            "timestamp": l.timestamp,
            "symbol": l.symbol,
            "decision": l.decision,
            "score": l.score,
            "confidence": l.confidence,
            "action": l.action,
            "details": l.details,
        }
        for l in pilot.scan_logs[:35]
    ]

    return JSONResponse({
        "megabull_connected": mb_connected,
        "mode_label": gateway.mode_label,
        "megabull_profile": mb_profile,
        "megabull_positions": mb_positions,
        "summary": summary,
        "holdings": holdings_list,
        "symbols": universe.get_symbols(),
        "autopilot": {
            "is_running": pilot.is_running,
            "cycle_count": pilot.cycle_count,
            "countdown_seconds": countdown_seconds,
            "last_cycle": pilot.last_cycle_time.strftime("%I:%M:%S %p") if pilot.last_cycle_time else "None",
            "next_cycle": pilot.next_cycle_time.strftime("%I:%M:%S %p") if pilot.next_cycle_time else "None",
            "logs": logs,
        }
    })


async def api_autopilot_toggle(request):
    """Start or stop the Auto-Pilot background daemon."""
    body = await request.json()
    action = body.get("action")
    if action == "start":
        pilot.start(price_lookup_func=get_current_stock_quote)
        return JSONResponse({"status": "success", "is_running": True})
    elif action == "stop":
        pilot.stop()
        return JSONResponse({"status": "success", "is_running": False})
    return JSONResponse({"status": "error", "message": "Invalid action"}, status_code=400)


async def api_autopilot_scan(request):
    """Trigger an immediate manual scan cycle."""
    res = pilot.execute_cycle(price_lookup_func=get_current_stock_quote)
    return JSONResponse({"status": "success", "result": res})


async def api_autopilot_squareoff(request):
    """Emergency square off all intraday positions."""
    closed = pilot.square_off_all_intraday(price_lookup_func=get_current_stock_quote)
    return JSONResponse({"status": "success", "closed_count": len(closed)})


async def api_sync_megabull(request):
    """Sync balance and positions from MegaBull."""
    res = gateway.sync_portfolio_from_megabull()
    return JSONResponse(res)


async def api_evaluate_stock(request):
    """Evaluate stock technical indicators and God's Eye intelligence."""
    symbol = request.path_params["symbol"]
    px = get_current_stock_quote(symbol)
    decision = decision_engine.evaluate(symbol, current_price=px)
    return JSONResponse({
        "symbol": decision.selected_stock,
        "decision": decision.decision,
        "technical_signal": decision.technical_signal,
        "event_sentiment": decision.event_sentiment,
        "score": decision.combined_score,
        "confidence": decision.confidence,
        "explanation": decision.explanation,
        "entry_price": decision.suggested_entry_price or px,
        "stop_loss": decision.suggested_stop_loss,
        "target_price": decision.suggested_target_price,
        "current_price": px,
    })


async def api_place_order(request):
    """Place manual order routing directly to MegaBull / local broker."""
    data = await request.json()
    symbol = data.get("symbol", "").upper()
    side = data.get("side", "BUY").upper()
    qty = int(data.get("quantity", 1))
    trading_style = data.get("style", "INTRADAY").upper()
    order_type = data.get("type", "MARKET").upper()
    curr_px = get_current_stock_quote(symbol)

    order = PaperOrder(
        order_id=f"ORD-MAN-{symbol}-{int(datetime.now().timestamp())}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol=symbol,
        side=side,
        order_type=order_type,
        trading_style=trading_style,
        quantity=qty,
        entry_price=curr_px,
        limit_price=float(data.get("price")) if order_type == "LIMIT" else None,
        stop_loss=float(data.get("sl", 0.0)) or None,
        target_price=float(data.get("target", 0.0)) or None,
        time_in_force="DAY",
        status="PENDING",
    )

    filled, rec = gateway.execute(order, current_market_price=curr_px)
    return JSONResponse({
        "status": "success",
        "order_id": filled.order_id,
        "executed_price": filled.executed_price,
        "side": filled.side,
        "quantity": filled.quantity,
        "symbol": filled.symbol,
        "notes": rec.get("notes"),
    })


# -------------------------------------------------------------
# HIGH PERFORMANCE SINGLE-PAGE DASHBOARD TEMPLATE
# -------------------------------------------------------------
INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quant_Bot | Real-Time Intelligent Trading Station</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        zinc: {
                            950: '#09090b',
                            900: '#18181b',
                            850: '#202024',
                            800: '#27272a',
                            700: '#3f3f46',
                        },
                        emerald: { 500: '#10b981', 400: '#34d399' },
                        rose: { 500: '#f43f5e', 400: '#fb7185' }
                    },
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                        mono: ['JetBrains Mono', 'monospace']
                    }
                }
            }
        }
    </script>
    <style>
        body { background-color: #09090b; color: #f4f4f5; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #18181b; }
        ::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 3px; }
        .pill-pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
    </style>
</head>
<body class="min-h-screen flex flex-col font-sans antialiased text-sm">

    <!-- Top Navigation Bar -->
    <header class="border-b border-zinc-800 bg-zinc-900/90 backdrop-blur sticky top-0 z-50 px-6 py-3.5 flex items-center justify-between">
        <div class="flex items-center gap-3">
            <span class="text-xl">⚡</span>
            <div>
                <h1 class="text-base font-bold tracking-tight text-white flex items-center gap-2">
                    QUANT_BOT <span class="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-mono">v2.4 PRO</span>
                </h1>
                <p class="text-xs text-zinc-400">Autonomous Quantitative Engine & Live Paper Terminal</p>
            </div>
        </div>

        <div class="flex items-center gap-4">
            <div id="mode-badge" class="px-3 py-1 rounded-full text-xs font-mono font-medium bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full bg-emerald-400 pill-pulse"></span>
                <span id="mode-text">MEGABULL CONNECTED</span>
            </div>
            <button onclick="syncMegaBull()" class="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 border border-zinc-700 transition flex items-center gap-1.5">
                <span>🔄</span> Sync MegaBull
            </button>
            <div id="current-clock" class="text-xs font-mono text-zinc-400">--:--:-- IST</div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">

        <!-- 1. P&L & Capital Strip -->
        <section class="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                <span class="text-xs font-medium text-zinc-400">Virtual Portfolio Capital</span>
                <div id="kpi-total" class="text-2xl font-bold font-mono text-white mt-1">₹5,00,000.00</div>
                <span class="text-[11px] text-zinc-500">Total Allocated Limit</span>
            </div>
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                <span class="text-xs font-medium text-zinc-400">Available Liquid Cash</span>
                <div id="kpi-cash" class="text-2xl font-bold font-mono text-emerald-400 mt-1">₹2,79,026.00</div>
                <span class="text-[11px] text-zinc-500">Ready to Deploy</span>
            </div>
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                <span class="text-xs font-medium text-zinc-400">Blocked Margin</span>
                <div id="kpi-margin" class="text-2xl font-bold font-mono text-amber-400 mt-1">₹2,20,973.55</div>
                <span class="text-[11px] text-zinc-500">In Active Positions</span>
            </div>
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                <span class="text-xs font-medium text-zinc-400">Unrealized P&L</span>
                <div id="kpi-unrealized" class="text-2xl font-bold font-mono text-white mt-1">₹0.00</div>
                <span id="kpi-unrealized-pct" class="text-[11px] text-zinc-400">0.00% return</span>
            </div>
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                <span class="text-xs font-medium text-zinc-400">Realized P&L Today</span>
                <div id="kpi-realized" class="text-2xl font-bold font-mono text-white mt-1">₹0.00</div>
                <span class="text-[11px] text-zinc-500">Booked Profit/Loss</span>
            </div>
        </section>

        <!-- 2. Auto-Pilot & Control Dashboard -->
        <section class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            <!-- Left: Auto-Pilot Mission Control -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
                <div class="flex items-center justify-between border-b border-zinc-800 pb-3">
                    <div class="flex items-center gap-2">
                        <span class="text-base">🤖</span>
                        <h2 class="font-bold text-white">Intraday Auto-Pilot</h2>
                    </div>
                    <span id="ap-status-badge" class="px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
                        STANDBY
                    </span>
                </div>

                <!-- Countdown & Cycle Stats -->
                <div class="bg-zinc-950/80 border border-zinc-800/80 rounded-lg p-3.5 space-y-2">
                    <div class="flex justify-between items-center text-xs">
                        <span class="text-zinc-400">Next 10-Min Autonomous Scan:</span>
                        <span id="ap-countdown" class="font-mono text-emerald-400 font-bold text-sm">--:--</span>
                    </div>
                    <div class="w-full bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                        <div id="ap-progress-bar" class="bg-emerald-500 h-full w-0 transition-all duration-1000"></div>
                    </div>
                    <div class="flex justify-between text-[11px] text-zinc-500 font-mono">
                        <span>Cycles Run: <b id="ap-cycles" class="text-zinc-300">0</b></span>
                        <span>Window: <b class="text-zinc-300">09:15 - 15:15 IST</b></span>
                    </div>
                </div>

                <!-- Action Buttons -->
                <div class="grid grid-cols-2 gap-2.5 pt-1">
                    <button id="btn-toggle-ap" onclick="toggleAutoPilot()" class="w-full py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 font-medium text-white text-xs transition shadow-lg shadow-emerald-950/30 flex items-center justify-center gap-1.5">
                        <span>▶️</span> Start Auto-Pilot
                    </button>
                    <button onclick="scanNow()" class="w-full py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 font-medium text-zinc-200 text-xs border border-zinc-700 transition flex items-center justify-center gap-1.5">
                        <span>⚡</span> Scan Now
                    </button>
                </div>

                <button onclick="emergencySquareOff()" class="w-full py-2 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-xs font-medium transition flex items-center justify-center gap-1.5">
                    <span>🚨</span> Emergency Square-Off All Intraday
                </button>
            </div>

            <!-- Right: Live Scrolling Activity Terminal -->
            <div class="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-xl p-5 flex flex-col">
                <div class="flex items-center justify-between border-b border-zinc-800 pb-3 mb-3">
                    <div class="flex items-center gap-2">
                        <span class="text-base">📜</span>
                        <h2 class="font-bold text-white">Live Decision & Activity Stream</h2>
                    </div>
                    <span class="text-xs text-zinc-500 font-mono">Real-Time Telemetry</span>
                </div>

                <div id="terminal-logs" class="flex-1 max-h-64 overflow-y-auto space-y-1.5 font-mono text-xs bg-zinc-950 border border-zinc-800/80 rounded-lg p-3">
                    <div class="text-zinc-500">Initializing live stream connection...</div>
                </div>
            </div>
        </section>

        <!-- 3. Open Positions & Active Holdings Table -->
        <section class="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
            <div class="flex items-center justify-between border-b border-zinc-800 pb-3">
                <div class="flex items-center gap-2">
                    <span class="text-base">💼</span>
                    <h2 class="font-bold text-white">Open Holdings & Real-Time Profit / Loss</h2>
                </div>
                <span id="positions-count" class="text-xs font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">0 Positions</span>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-left font-mono text-xs">
                    <thead>
                        <tr class="text-zinc-400 border-b border-zinc-800 pb-2">
                            <th class="py-2 px-3 font-semibold">Symbol</th>
                            <th class="py-2 px-3 font-semibold">Style</th>
                            <th class="py-2 px-3 font-semibold text-right">Quantity</th>
                            <th class="py-2 px-3 font-semibold text-right">Avg Price</th>
                            <th class="py-2 px-3 font-semibold text-right">Current Price</th>
                            <th class="py-2 px-3 font-semibold text-right">Market Value</th>
                            <th class="py-2 px-3 font-semibold text-right">Unrealized P&L</th>
                            <th class="py-2 px-3 font-semibold text-right">Return %</th>
                            <th class="py-2 px-3 font-semibold text-center">Action</th>
                        </tr>
                    </thead>
                    <tbody id="positions-tbody" class="divide-y divide-zinc-800/60">
                        <tr><td colspan="9" class="py-6 text-center text-zinc-500">No open positions. Ready to trade.</td></tr>
                    </tbody>
                </table>
            </div>
        </section>

        <!-- 4. Decision Engine & Manual Order Workstation -->
        <section class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- Stock Decision Inspector -->
            <div class="lg:col-span-2 bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
                <div class="flex items-center justify-between border-b border-zinc-800 pb-3">
                    <div class="flex items-center gap-2">
                        <span class="text-base">🧠</span>
                        <h2 class="font-bold text-white">Decision Engine & Confluence Inspector</h2>
                    </div>
                    <select id="select-stock" onchange="evaluateStock()" class="bg-zinc-800 border border-zinc-700 text-xs text-white rounded-lg px-3 py-1 font-mono">
                        <option value="HDFCBANK">HDFCBANK</option>
                        <option value="TCS">TCS</option>
                        <option value="RELIANCE">RELIANCE</option>
                        <option value="INFY">INFY</option>
                        <option value="ITC">ITC</option>
                        <option value="MARUTI">MARUTI</option>
                        <option value="TATASTEEL">TATASTEEL</option>
                        <option value="TATAMOTORS">TATAMOTORS</option>
                    </select>
                </div>

                <div class="grid grid-cols-3 gap-3">
                    <div class="bg-zinc-950 p-3 rounded-lg border border-zinc-800">
                        <span class="text-[11px] text-zinc-500">Signal Rating</span>
                        <div id="dec-signal" class="text-base font-bold font-mono mt-1 text-emerald-400">BUY</div>
                    </div>
                    <div class="bg-zinc-950 p-3 rounded-lg border border-zinc-800">
                        <span class="text-[11px] text-zinc-500">Conviction / Score</span>
                        <div id="dec-score" class="text-base font-bold font-mono mt-1 text-white">+0.75 (85%)</div>
                    </div>
                    <div class="bg-zinc-950 p-3 rounded-lg border border-zinc-800">
                        <span class="text-[11px] text-zinc-500">Market Quote</span>
                        <div id="dec-quote" class="text-base font-bold font-mono mt-1 text-white">₹812.00</div>
                    </div>
                </div>

                <div class="bg-zinc-950 p-3.5 rounded-lg border border-zinc-800 space-y-2">
                    <span class="text-xs font-semibold text-zinc-400">Institutional Confluence Rationale</span>
                    <p id="dec-rationale" class="text-xs text-zinc-300 leading-relaxed font-sans">
                        Select a stock above to generate transparent technical & news evaluation.
                    </p>
                    <div class="grid grid-cols-3 gap-2 pt-2 border-t border-zinc-800/80 text-xs font-mono">
                        <div>Entry: <span id="dec-entry" class="text-zinc-200">--</span></div>
                        <div>SL: <span id="dec-sl" class="text-rose-400">--</span></div>
                        <div>TP: <span id="dec-tp" class="text-emerald-400">--</span></div>
                    </div>
                </div>
            </div>

            <!-- Manual Quick-Order Terminal -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
                <div class="flex items-center gap-2 border-b border-zinc-800 pb-3">
                    <span class="text-base">⚡</span>
                    <h2 class="font-bold text-white">Instant Order Dispatch</h2>
                </div>

                <div class="space-y-3">
                    <div>
                        <label class="text-[11px] text-zinc-400 block mb-1">Stock Instrument</label>
                        <input id="order-symbol" type="text" readonly value="HDFCBANK" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs font-mono text-zinc-200">
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="text-[11px] text-zinc-400 block mb-1">Quantity</label>
                            <input id="order-qty" type="number" value="1" min="1" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs font-mono text-white">
                        </div>
                        <div>
                            <label class="text-[11px] text-zinc-400 block mb-1">Style</label>
                            <select id="order-style" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-white font-mono">
                                <option value="INTRADAY">MIS (Intraday)</option>
                                <option value="DELIVERY">CNC (Delivery)</option>
                            </select>
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-2 pt-2">
                    <button onclick="placeManualOrder('BUY')" class="w-full py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 font-bold text-white text-xs transition">
                        BUY ORDER
                    </button>
                    <button onclick="placeManualOrder('SELL')" class="w-full py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 font-bold text-white text-xs transition">
                        SELL ORDER
                    </button>
                </div>
                <p class="text-[11px] text-zinc-500 text-center">Orders route live to MegaBull REST API.</p>
            </div>
        </section>

    </main>

    <!-- Client-Side Real-Time Script -->
    <script>
        let currentIsRunning = false;
        let lastCountdown = 0;

        function updateClock() {
            const now = new Date();
            const ist = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (330 * 60000));
            document.getElementById('current-clock').textContent = ist.toLocaleTimeString('en-US', { hour12: false }) + ' IST';
        }
        setInterval(updateClock, 1000);
        updateClock();

        async function fetchState() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                renderState(data);
            } catch (err) {
                console.error("Fetch state error:", err);
            }
        }

        function renderState(data) {
            // 1. Header & Mode Badge
            const mbText = document.getElementById('mode-text');
            if (data.megabull_connected) {
                mbText.textContent = 'MEGABULL CONNECTED';
                mbText.parentElement.className = 'px-3 py-1 rounded-full text-xs font-mono font-medium bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center gap-1.5';
            } else {
                mbText.textContent = 'LOCAL SIMULATION';
                mbText.parentElement.className = 'px-3 py-1 rounded-full text-xs font-mono font-medium bg-zinc-800 text-zinc-400 border border-zinc-700 flex items-center gap-1.5';
            }

            // 2. Capital Strip
            const prof = data.megabull_profile || {};
            const totalMoney = prof.virtualMoney || data.summary.total_equity || 500000;
            const leftCash = prof.virtualMoneyLeft !== undefined ? prof.virtualMoneyLeft : data.summary.cash;
            const blocked = prof.virtualMoneyBlocked || 0;

            document.getElementById('kpi-total').textContent = '₹' + Number(totalMoney).toLocaleString('en-IN', { minimumFractionDigits: 2 });
            document.getElementById('kpi-cash').textContent = '₹' + Number(leftCash).toLocaleString('en-IN', { minimumFractionDigits: 2 });
            document.getElementById('kpi-margin').textContent = '₹' + Number(blocked).toLocaleString('en-IN', { minimumFractionDigits: 2 });

            // Calculate total unrealized P&L from positions
            let totalUnrealized = 0;
            let totalInvested = 0;
            data.holdings.forEach(h => {
                totalUnrealized += h.unrealized_pnl;
                totalInvested += h.market_value;
            });

            const unEl = document.getElementById('kpi-unrealized');
            const unPctEl = document.getElementById('kpi-unrealized-pct');
            unEl.textContent = (totalUnrealized >= 0 ? '+₹' : '-₹') + Math.abs(totalUnrealized).toLocaleString('en-IN', { minimumFractionDigits: 2 });
            unEl.className = 'text-2xl font-bold font-mono mt-1 ' + (totalUnrealized >= 0 ? 'text-emerald-400' : 'text-rose-400');
            
            const pct = totalInvested > 0 ? (totalUnrealized / totalInvested * 100).toFixed(2) : '0.00';
            unPctEl.textContent = (totalUnrealized >= 0 ? '+' : '') + pct + '% live return';
            unPctEl.className = 'text-[11px] ' + (totalUnrealized >= 0 ? 'text-emerald-500' : 'text-rose-400');

            const realEl = document.getElementById('kpi-realized');
            const realVal = data.summary.realized_pnl || 0;
            realEl.textContent = (realVal >= 0 ? '+₹' : '-₹') + Math.abs(realVal).toLocaleString('en-IN', { minimumFractionDigits: 2 });
            realEl.className = 'text-2xl font-bold font-mono mt-1 ' + (realVal >= 0 ? 'text-emerald-400' : 'text-rose-400');

            // 3. Auto-Pilot State
            const ap = data.autopilot;
            currentIsRunning = ap.is_running;
            const apBadge = document.getElementById('ap-status-badge');
            const btnAp = document.getElementById('btn-toggle-ap');

            if (ap.is_running) {
                apBadge.textContent = 'RUNNING';
                apBadge.className = 'px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 pill-pulse';
                btnAp.innerHTML = '<span>⏹️</span> Pause Auto-Pilot';
                btnAp.className = 'w-full py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 font-medium text-amber-300 text-xs border border-zinc-700 transition flex items-center justify-center gap-1.5';
            } else {
                apBadge.textContent = 'STANDBY';
                apBadge.className = 'px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-zinc-800 text-zinc-400 border border-zinc-700';
                btnAp.innerHTML = '<span>▶️</span> Start Auto-Pilot';
                btnAp.className = 'w-full py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 font-medium text-white text-xs transition shadow-lg shadow-emerald-950/30 flex items-center justify-center gap-1.5';
            }

            document.getElementById('ap-cycles').textContent = ap.cycle_count;

            const mins = Math.floor(ap.countdown_seconds / 60);
            const secs = ap.countdown_seconds % 60;
            document.getElementById('ap-countdown').textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
            
            const pctProg = Math.min(100, Math.max(0, 100 - (ap.countdown_seconds / 600 * 100)));
            document.getElementById('ap-progress-bar').style.width = pctProg + '%';

            // 4. Activity Logs
            const logBox = document.getElementById('terminal-logs');
            if (ap.logs && ap.logs.length > 0) {
                logBox.innerHTML = ap.logs.map(l => {
                    let color = 'text-zinc-400';
                    if (l.action.includes('ORDER')) color = 'text-emerald-400 font-bold';
                    else if (l.action.includes('EXIT') || l.action.includes('SQUARE')) color = 'text-amber-400';
                    else if (l.action.includes('REJECT')) color = 'text-rose-400';
                    return `<div><span class="text-zinc-600">[${l.timestamp}]</span> <span class="${color}">${l.action}</span> <span class="text-zinc-300">${l.symbol}</span>: ${l.details}</div>`;
                }).join('');
            }

            // 5. Positions Table
            document.getElementById('positions-count').textContent = `${data.holdings.length} Positions`;
            const tbody = document.getElementById('positions-tbody');
            if (data.holdings.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" class="py-6 text-center text-zinc-500 font-sans">No open positions. Ready to trade.</td></tr>';
            } else {
                tbody.innerHTML = data.holdings.map(h => {
                    const pnlColor = h.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400';
                    const pnlSign = h.unrealized_pnl >= 0 ? '+' : '';
                    return `
                        <tr class="hover:bg-zinc-800/40 transition">
                            <td class="py-2.5 px-3 font-bold text-white">${h.symbol}</td>
                            <td class="py-2.5 px-3"><span class="px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] text-zinc-300">${h.style}</span></td>
                            <td class="py-2.5 px-3 text-right font-medium">${h.quantity}</td>
                            <td class="py-2.5 px-3 text-right text-zinc-400">₹${h.avg_price.toFixed(2)}</td>
                            <td class="py-2.5 px-3 text-right text-white">₹${h.current_price.toFixed(2)}</td>
                            <td class="py-2.5 px-3 text-right text-zinc-300">₹${h.market_value.toLocaleString('en-IN')}</td>
                            <td class="py-2.5 px-3 text-right font-bold ${pnlColor}">${pnlSign}₹${h.unrealized_pnl.toFixed(2)}</td>
                            <td class="py-2.5 px-3 text-right ${pnlColor}">${pnlSign}${h.unrealized_pct}%</td>
                            <td class="py-2.5 px-3 text-center">
                                <button onclick="squareOffSingle('${h.symbol}', ${h.quantity})" class="px-2 py-0.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-[11px] transition">
                                    Close
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        async function toggleAutoPilot() {
            const nextAction = currentIsRunning ? 'stop' : 'start';
            await fetch('/api/autopilot/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: nextAction })
            });
            fetchState();
        }

        async function scanNow() {
            await fetch('/api/autopilot/scan', { method: 'POST' });
            fetchState();
        }

        async function emergencySquareOff() {
            if (confirm("Are you sure you want to close ALL active intraday positions?")) {
                await fetch('/api/autopilot/squareoff', { method: 'POST' });
                fetchState();
            }
        }

        async function squareOffSingle(symbol, qty) {
            await fetch('/api/trade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol: symbol, side: 'SELL', quantity: qty, style: 'INTRADAY', type: 'MARKET' })
            });
            fetchState();
        }

        async function syncMegaBull() {
            await fetch('/api/sync_megabull', { method: 'POST' });
            fetchState();
        }

        async function evaluateStock() {
            const sym = document.getElementById('select-stock').value;
            document.getElementById('order-symbol').value = sym;
            try {
                const res = await fetch(`/api/evaluate/${sym}`);
                const data = await res.json();
                document.getElementById('dec-signal').textContent = data.decision;
                document.getElementById('dec-signal').className = 'text-base font-bold font-mono mt-1 ' + (data.decision === 'BUY' ? 'text-emerald-400' : (data.decision === 'SELL' ? 'text-rose-400' : 'text-zinc-400'));
                document.getElementById('dec-score').textContent = (data.score >= 0 ? '+' : '') + data.score.toFixed(2) + ` (${(data.confidence * 100).toFixed(0)}%)`;
                document.getElementById('dec-quote').textContent = '₹' + data.current_price.toFixed(2);
                document.getElementById('dec-rationale').textContent = data.explanation;
                document.getElementById('dec-entry').textContent = '₹' + data.entry_price.toFixed(2);
                document.getElementById('dec-sl').textContent = data.stop_loss ? '₹' + data.stop_loss.toFixed(2) : '--';
                document.getElementById('dec-tp').textContent = data.target_price ? '₹' + data.target_price.toFixed(2) : '--';
            } catch (e) {
                console.error(e);
            }
        }

        async function placeManualOrder(side) {
            const sym = document.getElementById('order-symbol').value;
            const qty = document.getElementById('order-qty').value;
            const style = document.getElementById('order-style').value;
            const res = await fetch('/api/trade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol: sym, side: side, quantity: qty, style: style, type: 'MARKET' })
            });
            const data = await res.json();
            alert(`Order Dispatched: ${side} ${qty} ${sym} -> Filled @ ₹${data.executed_price}`);
            fetchState();
        }

        // Auto-poll state every 2 seconds
        setInterval(fetchState, 2000);
        fetchState();
        evaluateStock();
    </script>
</body>
</html>
"""

async def homepage(request):
    return HTMLResponse(INDEX_HTML)

app = Starlette(
    routes=[
        Route("/", homepage),
        Route("/api/state", api_state),
        Route("/api/autopilot/toggle", api_autopilot_toggle, methods=["POST"]),
        Route("/api/autopilot/scan", api_autopilot_scan, methods=["POST"]),
        Route("/api/autopilot/squareoff", api_autopilot_squareoff, methods=["POST"]),
        Route("/api/sync_megabull", api_sync_megabull, methods=["POST"]),
        Route("/api/evaluate/{symbol}", api_evaluate_stock),
        Route("/api/trade", api_place_order, methods=["POST"]),
    ]
)

if __name__ == "__main__":
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=False)
