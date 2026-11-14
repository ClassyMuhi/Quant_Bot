"""
User-Friendly Web Interface & Dashboard for Quant_Bot Backtesting Results
Provides an interactive web dashboard with equity curves, drawdown analysis,
comparative metrics, and trade ledgers. Powered by standard Python http.server.
"""

from __future__ import annotations
import http.server
import json
import logging
import socketserver
import webbrowser
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

from pipeline.bronze_writer import read_parquet
from pipeline.symbol_universe import SymbolUniverse
from .engine import BacktestEngine
from .strategy import SMACrossoverStrategy, RSIMeanReversionStrategy, FinRLStrategyAdapter
from .cost_model import IndianEquityCostModel
from finrl_adapter import FinRLBaseStrategy, StrategyConfig, StrategyResult

logger = logging.getLogger(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quant_Bot - Backtesting Analytics Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --border-color: #334155;
            --accent-color: #38bdf8;
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
        }
        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin-bottom: 50px;
        }
        .navbar {
            background-color: var(--card-bg);
            border-bottom: 1px solid var(--border-color);
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            color: var(--text-color);
            margin-bottom: 20px;
        }
        .card-header {
            background-color: rgba(255, 255, 255, 0.03);
            border-bottom: 1px solid var(--border-color);
            font-weight: 600;
        }
        .stat-card {
            padding: 15px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
        }
        .stat-val {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--accent-color);
        }
        .stat-label {
            font-size: 0.8rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .form-control, .form-select {
            background-color: #0f172a;
            border: 1px solid var(--border-color);
            color: var(--text-color);
        }
        .form-control:focus, .form-select:focus {
            background-color: #0f172a;
            border-color: var(--accent-color);
            color: var(--text-color);
            box-shadow: none;
        }
        .table {
            color: var(--text-color);
            border-color: var(--border-color);
        }
        .table-striped>tbody>tr:nth-of-type(odd)>* {
            background-color: rgba(255, 255, 255, 0.02);
            color: var(--text-color);
        }
        .badge-short {
            background-color: #f59e0b;
            color: #000;
            font-size: 0.75rem;
            padding: 3px 6px;
            border-radius: 4px;
        }
        .chart-container {
            position: relative;
            height: 350px;
            width: 100%;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark px-4 py-3">
        <span class="navbar-brand mb-0 h1 d-flex align-items-center">
            <span style="color: #38bdf8; font-weight: 800; font-size: 1.4rem; margin-right: 8px;">Quant_Bot</span>
            <span style="color: var(--text-muted); font-size: 0.9rem;">| Institutional Backtesting Analytics</span>
        </span>
        <span class="badge bg-secondary">Indian Equity (NSE)</span>
    </nav>

    <div class="container-fluid px-4 py-4">
        <div class="row">
            <!-- Sidebar / Control Panel -->
            <div class="col-lg-3">
                <div class="card">
                    <div class="card-header">Backtest Configuration</div>
                    <div class="card-body">
                        <form id="configForm">
                            <div class="mb-3">
                                <label class="form-label text-muted small">Select Stock(s)</label>
                                <select id="stockSelect" class="form-select" multiple size="4">
                                    <option value="RELIANCE" selected>RELIANCE</option>
                                    <option value="TCS" selected>TCS</option>
                                </select>
                                <div class="form-text text-muted small">Hold Ctrl to select multiple</div>
                            </div>

                            <div class="mb-3">
                                <label class="form-label text-muted small">Trading Strategy</label>
                                <select id="strategySelect" class="form-select" onchange="toggleStrategyParams()">
                                    <option value="sma">SMA Crossover</option>
                                    <option value="rsi">RSI Mean Reversion</option>
                                    <option value="finrl">FinRL Equal Allocation</option>
                                </select>
                            </div>

                            <!-- SMA Params -->
                            <div id="smaParams">
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label class="form-label text-muted small">Short SMA</label>
                                        <input type="number" id="shortWindow" class="form-control" value="5">
                                    </div>
                                    <div class="col-6">
                                        <label class="form-label text-muted small">Long SMA</label>
                                        <input type="number" id="longWindow" class="form-control" value="10">
                                    </div>
                                </div>
                            </div>

                            <!-- RSI Params -->
                            <div id="rsiParams" style="display: none;">
                                <div class="row mb-3">
                                    <div class="col-6">
                                        <label class="form-label text-muted small">RSI Lower (Buy)</label>
                                        <input type="number" id="rsiLower" class="form-control" value="30">
                                    </div>
                                    <div class="col-6">
                                        <label class="form-label text-muted small">RSI Upper (Sell)</label>
                                        <input type="number" id="rsiUpper" class="form-control" value="70">
                                    </div>
                                </div>
                            </div>

                            <div class="mb-3">
                                <label class="form-label text-muted small">Initial Capital (Rs)</label>
                                <input type="number" id="initialCapital" class="form-control" value="1000000">
                            </div>

                            <div class="mb-3">
                                <label class="form-label text-muted small">Slippage (bps)</label>
                                <select id="slippageSelect" class="form-select">
                                    <option value="5" selected>5 bps (0.05%)</option>
                                    <option value="10">10 bps (0.10%)</option>
                                    <option value="20">20 bps (0.20%)</option>
                                    <option value="50">50 bps (0.50%)</option>
                                </select>
                            </div>

                            <div class="mb-3">
                                <label class="form-label text-muted small">Volume Participation Cap</label>
                                <select id="volCapSelect" class="form-select">
                                    <option value="0" selected>Unconstrained (100%)</option>
                                    <option value="0.10">10% of Daily Volume</option>
                                    <option value="0.25">25% of Daily Volume</option>
                                </select>
                            </div>

                            <button type="button" class="btn btn-primary w-100 fw-bold" onclick="runBacktest()">
                                Run Historical Backtest
                            </button>
                        </form>
                    </div>
                </div>
            </div>

            <!-- Main Results Area -->
            <div class="col-lg-9">
                <!-- KPI Stat Cards -->
                <div class="row mb-3" id="kpiRow">
                    <div class="col-md-3 col-6 mb-2">
                        <div class="stat-card">
                            <div class="stat-label">Total Return</div>
                            <div class="stat-val" id="kpiReturn">-</div>
                        </div>
                    </div>
                    <div class="col-md-3 col-6 mb-2">
                        <div class="stat-card">
                            <div class="stat-label">CAGR</div>
                            <div class="stat-val" id="kpiCAGR">-</div>
                        </div>
                    </div>
                    <div class="col-md-3 col-6 mb-2">
                        <div class="stat-card">
                            <div class="stat-label">Sharpe / Sortino</div>
                            <div class="stat-val" id="kpiRatios">-</div>
                        </div>
                    </div>
                    <div class="col-md-3 col-6 mb-2">
                        <div class="stat-card">
                            <div class="stat-label">Max Drawdown</div>
                            <div class="stat-val" id="kpiMDD">-</div>
                        </div>
                    </div>
                </div>

                <!-- Secondary KPI: PnL Breakdown -->
                <div class="row mb-3" id="pnlRow">
                    <div class="col-md-4 col-6 mb-2">
                        <div class="stat-card">
                            <div class="stat-label">Total P&L</div>
                            <div class="stat-val text-info" id="kpiTotalPnl">-</div>
                        </div>
                    </div>
                    <div class="col-md-4 col-6 mb-2">
                        <div class="stat-card">
                            <div class="stat-label">Realized P&L</div>
                            <div class="stat-val text-success" id="kpiRealizedPnl">-</div>
                        </div>
                    </div>
                    <div class="col-md-4 col-6 mb-2">
                        <div class="stat-card">
                            <div class="stat-label">Unrealized P&L</div>
                            <div class="stat-val text-warning" id="kpiUnrealizedPnl">-</div>
                        </div>
                    </div>
                </div>

                <!-- Equity Curve Chart -->
                <div class="card mb-4">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>Portfolio Equity Curve (vs Buy & Hold)</span>
                        <span id="periodBadge" class="badge-short" style="display:none;">Short Period Warning</span>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="equityChart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- Summary Metrics Table -->
                <div class="card mb-4">
                    <div class="card-header">Detailed Comparative Metrics</div>
                    <div class="card-body p-0">
                        <div class="table-responsive">
                            <table class="table table-striped table-hover mb-0" id="metricsTable">
                                <thead>
                                    <tr>
                                        <th>Metric</th>
                                        <th>Strategy</th>
                                        <th>Buy & Hold (Universe)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr><td colspan="3" class="text-center text-muted py-3">Run a backtest to see metrics</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Trade Ledger -->
                <div class="card">
                    <div class="card-header">Executed Trades Log</div>
                    <div class="card-body p-0">
                        <div class="table-responsive" style="max-height: 300px; overflow-y: auto;">
                            <table class="table table-sm table-striped mb-0" id="tradesTable">
                                <thead>
                                    <tr>
                                        <th>ID</th>
                                        <th>Date</th>
                                        <th>Symbol</th>
                                        <th>Type</th>
                                        <th>Qty</th>
                                        <th>Exec Price</th>
                                        <th>Gross Value</th>
                                        <th>Taxes & Fees</th>
                                        <th>Realized P&L</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr><td colspan="9" class="text-center text-muted py-3">No trades executed</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let equityChart = null;

        function toggleStrategyParams() {
            const strat = document.getElementById("strategySelect").value;
            document.getElementById("smaParams").style.display = strat === "sma" ? "block" : "none";
            document.getElementById("rsiParams").style.display = strat === "rsi" ? "block" : "none";
        }

        async function loadStocks() {
            try {
                const res = await fetch("/api/stocks");
                const stocks = await res.json();
                const sel = document.getElementById("stockSelect");
                sel.innerHTML = "";
                stocks.forEach((s, idx) => {
                    const opt = document.createElement("option");
                    opt.value = s;
                    opt.textContent = s;
                    if (idx < 2) opt.selected = true;
                    sel.appendChild(opt);
                });
            } catch(e) {
                console.error("Failed to load stocks:", e);
            }
        }

        async function runBacktest() {
            const selectedStocks = Array.from(document.getElementById("stockSelect").selectedOptions).map(o => o.value);
            if (selectedStocks.length === 0) {
                alert("Please select at least one stock!");
                return;
            }

            const payload = {
                symbols: selectedStocks,
                strategy: document.getElementById("strategySelect").value,
                short_window: parseInt(document.getElementById("shortWindow").value) || 5,
                long_window: parseInt(document.getElementById("longWindow").value) || 10,
                rsi_lower: parseFloat(document.getElementById("rsiLower").value) || 30,
                rsi_upper: parseFloat(document.getElementById("rsiUpper").value) || 70,
                initial_capital: parseFloat(document.getElementById("initialCapital").value) || 1000000,
                slippage_bps: parseFloat(document.getElementById("slippageSelect").value) || 5.0,
                vol_cap: parseFloat(document.getElementById("volCapSelect").value) || 0.0,
            };

            const btn = document.querySelector("button[onclick='runBacktest()']");
            btn.disabled = true;
            btn.textContent = "Simulating...";

            try {
                const res = await fetch("/api/run", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.error) {
                    alert("Backtest Error: " + data.error);
                } else {
                    renderDashboard(data);
                }
            } catch(e) {
                alert("Request failed: " + e);
            } finally {
                btn.disabled = false;
                btn.textContent = "Run Historical Backtest";
            }
        }

        function renderDashboard(data) {
            const m = data.strategy_metrics;
            const bh = data.buy_hold_metrics;

            // KPI Cards
            document.getElementById("kpiReturn").textContent = m.total_return_pct + "%";
            document.getElementById("kpiReturn").style.color = m.total_return_pct >= 0 ? "#4ade80" : "#f87171";
            document.getElementById("kpiCAGR").textContent = m.cagr_pct + "%";
            document.getElementById("kpiRatios").textContent = `${m.sharpe_ratio} / ${m.sortino_ratio}`;
            document.getElementById("kpiMDD").textContent = m.max_drawdown_pct + "%";
            document.getElementById("kpiTotalPnl").textContent = "Rs. " + Number(m.total_pnl).toLocaleString();
            document.getElementById("kpiRealizedPnl").textContent = "Rs. " + Number(m.realized_pnl).toLocaleString();
            document.getElementById("kpiUnrealizedPnl").textContent = "Rs. " + Number(m.unrealized_pnl).toLocaleString();

            const badge = document.getElementById("periodBadge");
            if (m.is_short_period) {
                badge.style.display = "inline-block";
                badge.textContent = `Short Period: ${m.trading_days} Days (<6M)`;
            } else {
                badge.style.display = "none";
            }

            // Render Chart
            renderChart(data.equity_series, data.buy_hold_series);

            // Render Summary Table
            renderTable(data.summary_table);

            // Render Trades
            renderTrades(data.trades);
        }

        function renderChart(stratData, bhData) {
            const ctx = document.getElementById("equityChart").getContext("2d");
            if (equityChart) equityChart.destroy();

            const labels = stratData.map(d => d.date);
            const stratVals = stratData.map(d => d.total_equity);
            const bhVals = bhData.map(d => d.total_equity);

            equityChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Strategy Equity',
                            data: stratVals,
                            borderColor: '#38bdf8',
                            backgroundColor: 'rgba(56, 189, 248, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1
                        },
                        {
                            label: 'Buy & Hold Equity',
                            data: bhVals,
                            borderColor: '#94a3b8',
                            borderWidth: 1.5,
                            borderDash: [5, 5],
                            fill: false,
                            tension: 0.1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: '#f8fafc' } },
                        tooltip: { mode: 'index', intersect: false }
                    },
                    scales: {
                        x: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } },
                        y: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } }
                    }
                }
            });
        }

        function renderTable(tableRows) {
            const tbody = document.querySelector("#metricsTable tbody");
            tbody.innerHTML = "";
            tableRows.forEach(row => {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td><strong>${row.Metric}</strong></td><td>${row.Strategy}</td><td>${row.BuyHold}</td>`;
                tbody.appendChild(tr);
            });
        }

        function renderTrades(trades) {
            const tbody = document.querySelector("#tradesTable tbody");
            tbody.innerHTML = "";
            if (!trades || trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-3">No trades executed</td></tr>';
                return;
            }
            trades.forEach(t => {
                const tr = document.createElement("tr");
                const pnlClass = t.realized_pnl > 0 ? "text-success" : (t.realized_pnl < 0 ? "text-danger" : "text-muted");
                tr.innerHTML = `
                    <td>${t.trade_id}</td>
                    <td>${t.date}</td>
                    <td>${t.symbol}</td>
                    <td><span class="badge ${t.order_type === 'BUY' ? 'bg-success' : 'bg-danger'}">${t.order_type}</span></td>
                    <td>${t.quantity}</td>
                    <td>Rs. ${t.execution_price.toFixed(2)}</td>
                    <td>Rs. ${t.gross_value.toLocaleString()}</td>
                    <td>Rs. ${t.taxes_and_fees.toFixed(2)}</td>
                    <td class="${pnlClass}">Rs. ${t.realized_pnl.toFixed(2)}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        window.onload = () => {
            loadStocks();
            runBacktest();
        };
    </script>
</body>
</html>
"""


class BacktestAPIHandler(http.server.SimpleHTTPRequestHandler):
    """Handles API requests and serves dashboard HTML."""

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif self.path == "/api/stocks":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            gold_dir = Path("data/gold")
            if gold_dir.exists():
                symbols = sorted([p.stem for p in gold_dir.glob("*.parquet")])
            else:
                symbols = SymbolUniverse().get_symbols()
            if not symbols:
                symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
            self.wfile.write(json.dumps(symbols).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/run":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(body)
                resp = self._handle_run(payload)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode("utf-8"))
            except Exception as e:
                logger.error(f"Error handling backtest request: {e}", exc_info=True)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        symbols = payload.get("symbols", ["RELIANCE", "TCS"])
        strat_type = payload.get("strategy", "sma")
        capital = float(payload.get("initial_capital", 1000000.0))
        slippage_bps = float(payload.get("slippage_bps", 5.0))
        vol_cap = float(payload.get("vol_cap", 0.0))
        vol_cap = vol_cap if vol_cap > 0 else None

        # Load Gold parquet data for requested symbols
        data: Dict[str, pd.DataFrame] = {}
        for sym in symbols:
            p = Path(f"data/gold/{sym}.parquet")
            if p.exists():
                data[sym] = read_parquet(p)

        if not data:
            raise ValueError(f"No Gold data found for symbols: {symbols}. Run pipeline backfill first!")

        # Initialize strategy
        if strat_type == "sma":
            sw = int(payload.get("short_window", 5))
            lw = int(payload.get("long_window", 10))
            strategy = SMACrossoverStrategy(short_window=sw, long_window=lw)
        elif strat_type == "rsi":
            lower = float(payload.get("rsi_lower", 30))
            upper = float(payload.get("rsi_upper", 70))
            strategy = RSIMeanReversionStrategy(rsi_lower=lower, rsi_upper=upper)
        else:
            # FinRL Equal Weight
            class EqualWeightFinRL(FinRLBaseStrategy):
                def generate_weights(self, d, target_date=None):
                    syms = list(data.keys())
                    w = 1.0 / len(syms)
                    return StrategyResult("FinRL_EqualWeight", pd.DataFrame([{"symbol": s, "weight": w} for s in syms]))
            strategy = FinRLStrategyAdapter(EqualWeightFinRL())

        cost_model = IndianEquityCostModel(slippage_bps=slippage_bps)
        engine = BacktestEngine(
            strategy=strategy,
            initial_capital=capital,
            cost_model=cost_model,
            max_volume_participation_pct=vol_cap,
        )

        result = engine.run(data)

        # Build response payload
        strat_eq = [
            {"date": str(row["date"])[:10], "total_equity": round(float(row["total_equity"]), 2)}
            for _, row in result.equity_df.iterrows()
        ]
        bh_eq = [
            {"date": str(row["date"])[:10], "total_equity": round(float(row["total_equity"]), 2)}
            for _, row in result.buy_hold_equity_df.iterrows()
        ]

        summary_df = result.summary_table()
        # Convert summary df to rows
        summary_rows = []
        col_strat = summary_df.columns[1]
        col_bh = summary_df.columns[2]
        for _, r in summary_df.iterrows():
            summary_rows.append({
                "Metric": r["Metric"],
                "Strategy": r[col_strat],
                "BuyHold": r[col_bh],
            })

        trades_list = result.trades_df.to_dict(orient="records") if not result.trades_df.empty else []

        return {
            "strategy_name": result.strategy_name,
            "strategy_metrics": result.metrics,
            "buy_hold_metrics": result.buy_hold_metrics,
            "equity_series": strat_eq,
            "buy_hold_series": bh_eq,
            "summary_table": summary_rows,
            "trades": trades_list,
        }


def launch_dashboard(port: int = 8501, open_browser: bool = True):
    """Starts the Backtesting Dashboard web server."""
    handler = BacktestAPIHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}"
        print(f"\n" + "=" * 60)
        print(f"[*] Quant_Bot Backtesting Dashboard is running at:")
        print(f"    -> {url}")
        print(f"[*] Press Ctrl+C in terminal to stop server.")
        print("=" * 60 + "\n")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard server stopped.")


if __name__ == "__main__":
    launch_dashboard()

