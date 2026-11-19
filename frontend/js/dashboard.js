let currentIsRunning = false;
        let lastCountdown = 0;
        let currentOrderType = 'MARKET';
        let currentOrderRisk = 1.5;
        let lastLiveQuote = 1000.0;

        function updateClock() {
            const now = new Date();
            const ist = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (330 * 60000));
            document.getElementById('current-clock').textContent = ist.toLocaleTimeString('en-US', { hour12: false }) + ' IST';
        }
        setInterval(updateClock, 1000);
        updateClock();

        function setOrderType(type) {
            currentOrderType = type;
            const btnMkt = document.getElementById('btn-type-market');
            const btnLmt = document.getElementById('btn-type-limit');
            const badge = document.getElementById('order-type-badge');
            const priceInput = document.getElementById('order-price');

            if (type === 'MARKET') {
                btnMkt.className = 'py-1 rounded-md bg-zinc-800 text-white font-bold transition';
                btnLmt.className = 'py-1 rounded-md text-zinc-400 hover:text-white transition';
                badge.textContent = 'MARKET';
                badge.className = 'text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700';
                priceInput.placeholder = 'Market execution';
                priceInput.value = '';
            } else {
                btnLmt.className = 'py-1 rounded-md bg-emerald-600 text-white font-bold transition';
                btnMkt.className = 'py-1 rounded-md text-zinc-400 hover:text-white transition';
                badge.textContent = 'LIMIT';
                badge.className = 'text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30';
                if (!priceInput.value) {
                    priceInput.value = lastLiveQuote.toFixed(2);
                }
                priceInput.focus();
            }
            recalcBoundaries('BUY');
        }

        function useCurrentQuote() {
            setOrderType('LIMIT');
            document.getElementById('order-price').value = lastLiveQuote.toFixed(2);
            recalcBoundaries('BUY');
        }

        function applyOrderRisk(riskPct) {
            currentOrderRisk = riskPct;
            ['10', '15', '25', 'custom'].forEach(k => {
                const btn = document.getElementById(`risk-btn-${k}`);
                if (btn) btn.className = 'py-1 rounded bg-zinc-800 text-zinc-400 hover:text-white border border-zinc-700 transition';
            });

            const badge = document.getElementById('order-risk-badge');
            if (riskPct === 1.0) {
                document.getElementById('risk-btn-10').className = 'py-1 rounded bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/40 transition';
                badge.textContent = '1.0% Risk';
            } else if (riskPct === 1.5) {
                document.getElementById('risk-btn-15').className = 'py-1 rounded bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/40 transition';
                badge.textContent = '1.5% Risk';
            } else if (riskPct === 2.5) {
                document.getElementById('risk-btn-25').className = 'py-1 rounded bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/40 transition';
                badge.textContent = '2.5% Risk';
            } else {
                document.getElementById('risk-btn-custom').className = 'py-1 rounded bg-amber-500/20 text-amber-400 font-bold border border-amber-500/40 transition';
                badge.textContent = 'Custom R:R';
            }

            if (riskPct > 0) {
                recalcBoundaries('BUY');
            }
        }

        function recalcBoundaries(side) {
            const rawPx = parseFloat(document.getElementById('order-price').value) || lastLiveQuote || 1000.0;
            if (currentOrderRisk > 0 && rawPx > 0) {
                const delta = rawPx * (currentOrderRisk / 100);
                const sl = side === 'BUY' ? (rawPx - delta) : (rawPx + delta);
                const tp = side === 'BUY' ? (rawPx + delta * 2.0) : (rawPx - delta * 2.0);
                document.getElementById('order-sl').value = sl.toFixed(2);
                document.getElementById('order-target').value = tp.toFixed(2);
            }
            recalcCustomRR();
        }

        function recalcCustomRR() {
            const rawPx = parseFloat(document.getElementById('order-price').value) || lastLiveQuote || 1000.0;
            const sl = parseFloat(document.getElementById('order-sl').value);
            const tp = parseFloat(document.getElementById('order-target').value);

            if (sl && tp && rawPx) {
                const risk = Math.abs(rawPx - sl);
                const reward = Math.abs(tp - rawPx);
                const ratio = risk > 0 ? (reward / risk).toFixed(1) : '0';
                document.getElementById('rr-val').textContent = `1:${ratio}`;
                document.getElementById('risk-val').textContent = `₹${risk.toFixed(2)}`;
                document.getElementById('reward-val').textContent = `₹${reward.toFixed(2)}`;
            }
        }

        async function setApRisk(pct) {
            await fetch('/api/autopilot/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ risk_per_trade_pct: pct })
            });
            fetchState();
        }

        async function updateApConfig() {
            const cap = parseFloat(document.getElementById('ap-capital-select').value);
            const slots = parseInt(document.getElementById('ap-slots-select').value);
            await fetch('/api/autopilot/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ allocated_capital: cap, max_active_positions: slots })
            });
            fetchState();
        }

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

            // Sync Auto-Pilot Config UI
            if (ap.config) {
                const riskPct = ap.config.risk_per_trade_pct || 1.5;
                const riskLbl = document.getElementById('ap-risk-label');
                if (riskLbl) riskLbl.textContent = `${riskPct.toFixed(1)}% Risk`;

                ['10', '15', '20', '30'].forEach(k => {
                    const btn = document.getElementById(`ap-risk-${k}`);
                    if (btn) btn.className = 'py-1 rounded bg-zinc-800 text-zinc-400 hover:text-white border border-zinc-700 transition';
                });
                const key = String(Math.round(riskPct * 10));
                const activeBtn = document.getElementById(`ap-risk-${key}`);
                if (activeBtn) {
                    activeBtn.className = 'py-1 rounded bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/40 transition';
                }
                const capSelect = document.getElementById('ap-capital-select');
                if (capSelect && ap.config.allocated_capital && document.activeElement !== capSelect) {
                    capSelect.value = String(parseInt(ap.config.allocated_capital));
                }
                const slotsSelect = document.getElementById('ap-slots-select');
                if (slotsSelect && ap.config.max_active_positions && document.activeElement !== slotsSelect) {
                    slotsSelect.value = String(parseInt(ap.config.max_active_positions));
                }
            }

            // 4. Activity Logs
            const logBox = document.getElementById('terminal-logs');
            const streamLogs = (data.activity_logs && data.activity_logs.length > 0)
                ? data.activity_logs
                : (ap.logs && ap.logs.length > 0 ? ap.logs : []);

            if (streamLogs.length > 0) {
                logBox.innerHTML = streamLogs.map(l => {
                    let color = 'text-zinc-400 font-medium';
                    const act = (l.action || '').toUpperCase();
                    if (act.includes('ORDER') || act.includes('BUY')) color = 'text-emerald-400 font-bold';
                    else if (act.includes('EXIT') || act.includes('SQUARE') || act.includes('SELL')) color = 'text-amber-400 font-bold';
                    else if (act.includes('REJECT')) color = 'text-rose-400 font-semibold';
                    else if (act.includes('SYSTEM') || act.includes('BROKER') || act.includes('FEED') || act.includes('SYNC')) color = 'text-cyan-400 font-semibold';
                    else if (act.includes('AUTOPILOT')) color = 'text-indigo-400 font-semibold';
                    return `<div class="leading-relaxed py-0.5"><span class="text-zinc-600 font-mono">[${l.timestamp}]</span> <span class="${color}">${l.action}</span> <span class="text-zinc-200 font-bold">${l.symbol}</span>: <span class="text-zinc-300 font-mono text-[11px]">${l.details}</span></div>`;
                }).join('');
            } else {
                logBox.innerHTML = '<div class="text-zinc-500 font-mono">🟢 Telemetry stream connected. Auto-Pilot in STANDBY. Click "Scan Now" or "Start Auto-Pilot" to trigger live scans.</div>';
            }

            // Sync stock selector dropdown
            const stockSelect = document.getElementById('select-stock');
            if (data.symbols && data.symbols.length > 0 && stockSelect.options.length <= 8) {
                const curVal = stockSelect.value;
                stockSelect.innerHTML = data.symbols.map(s => `<option value="${s}">${s}</option>`).join('');
                if (data.symbols.includes(curVal)) {
                    stockSelect.value = curVal;
                }
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

                lastLiveQuote = data.current_price;
                if (currentOrderType === 'LIMIT' && !document.getElementById('order-price').value) {
                    document.getElementById('order-price').value = data.current_price.toFixed(2);
                }
                if (data.stop_loss) {
                    document.getElementById('order-sl').value = data.stop_loss.toFixed(2);
                }
                if (data.target_price) {
                    document.getElementById('order-target').value = data.target_price.toFixed(2);
                }
                recalcCustomRR();
            } catch (e) {
                console.error(e);
            }
        }

        async function placeManualOrder(side) {
            const sym = document.getElementById('order-symbol').value;
            const qty = document.getElementById('order-qty').value;
            const style = document.getElementById('order-style').value;
            const priceVal = document.getElementById('order-price').value;
            const slVal = document.getElementById('order-sl').value;
            const targetVal = document.getElementById('order-target').value;

            const payload = {
                symbol: sym,
                side: side,
                quantity: qty,
                style: style,
                type: currentOrderType,
                price: (currentOrderType === 'LIMIT' && priceVal) ? parseFloat(priceVal) : null,
                sl: slVal ? parseFloat(slVal) : null,
                target: targetVal ? parseFloat(targetVal) : null,
                risk_percent: currentOrderRisk
            };

            const res = await fetch('/api/trade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            const pxDesc = currentOrderType === 'LIMIT' ? `LIMIT ₹${priceVal}` : `MKT @ ₹${data.executed_price}`;
            const slDesc = slVal ? ` | SL: ₹${slVal}` : '';
            const tpDesc = targetVal ? ` | TP: ₹${targetVal}` : '';
            alert(`Order Dispatched: ${side} ${qty} ${sym} [${pxDesc}${slDesc}${tpDesc}] -> Status: ${data.status}`);
            fetchState();
        }

        // ==========================================
        // OPENDASHBOARDS™ VISUAL CHARTS & COPILOT JS
        // ==========================================
        let chartEquity = null;
        let chartAllocation = null;
        let chartSymbolPnl = null;
        let currentChartMode = 'DAY2';
        let latestChartsData = null;

        function setChartMode(mode) {
            currentChartMode = mode;
            const btnD2 = document.getElementById('btn-chart-day2');
            const btnAll = document.getElementById('btn-chart-all');
            const subTitle = document.getElementById('symbol-chart-subtitle');
            const netBadge = document.getElementById('chart-net-badge');

            if (mode === 'DAY2') {
                btnD2.className = 'px-2.5 py-1 rounded-md bg-emerald-500/20 text-emerald-400 font-bold transition';
                btnAll.className = 'px-2.5 py-1 rounded-md text-zinc-400 hover:text-white transition';
                subTitle.textContent = 'MegaBull live closed trades: HINDUNILVR (+₹388.50), LT (+₹179.20), MARUTI (-₹5.00)';
                netBadge.textContent = '+₹562.70 (Day 2 Net)';
                netBadge.className = 'text-xs font-mono font-bold text-emerald-400';
            } else {
                btnAll.className = 'px-2.5 py-1 rounded-md bg-emerald-500/20 text-emerald-400 font-bold transition';
                btnD2.className = 'px-2.5 py-1 rounded-md text-zinc-400 hover:text-white transition';
                subTitle.textContent = 'Full cumulative ledger performance across all historical simulated and paper trades';
                netBadge.textContent = '-₹589.76 (All-Time Net)';
                netBadge.className = 'text-xs font-mono font-bold text-zinc-400';
            }
            if (latestChartsData) {
                renderSymbolPnlChart(latestChartsData);
            }
        }

        async function fetchChartData() {
            try {
                const res = await fetch('/api/analytics/charts');
                const data = await res.json();
                latestChartsData = data;
                renderCharts(data);
            } catch (err) {
                console.error("Fetch charts error:", err);
            }
        }

        function renderCharts(data) {
            // 1. Equity & Realized P&L Curve (Area Chart)
            const equityOptions = {
                chart: {
                    type: 'area',
                    height: 250,
                    toolbar: { show: false },
                    background: 'transparent',
                    fontFamily: 'JetBrains Mono, monospace'
                },
                theme: { mode: 'dark' },
                stroke: { curve: 'smooth', width: 2 },
                series: [
                    { name: 'Portfolio Equity (₹)', data: data.equity_curve },
                    { name: 'Cumulative P&L (₹)', data: data.pnl_curve }
                ],
                xaxis: {
                    categories: data.time_labels,
                    labels: { style: { colors: '#71717a', fontSize: '10px' } },
                    axisBorder: { color: '#27272a' },
                    axisTicks: { color: '#27272a' }
                },
                yaxis: [
                    {
                        labels: {
                            formatter: val => '₹' + Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 }),
                            style: { colors: '#a1a1aa', fontSize: '10px' }
                        }
                    },
                    {
                        opposite: true,
                        labels: {
                            formatter: val => (val >= 0 ? '+' : '') + '₹' + Number(val).toFixed(0),
                            style: { colors: '#34d399', fontSize: '10px' }
                        }
                    }
                ],
                colors: ['#3b82f6', '#10b981'],
                fill: {
                    type: 'gradient',
                    gradient: {
                        shadeIntensity: 1,
                        opacityFrom: 0.35,
                        opacityTo: 0.05,
                        stops: [0, 90, 100]
                    }
                },
                grid: { borderColor: '#27272a', strokeDashArray: 3 },
                tooltip: { theme: 'dark' }
            };

            if (chartEquity) {
                chartEquity.updateOptions(equityOptions);
            } else {
                chartEquity = new ApexCharts(document.querySelector("#chart-equity"), equityOptions);
                chartEquity.render();
            }

            // 2. Capital Allocation Donut Chart
            const allocOptions = {
                chart: {
                    type: 'donut',
                    height: 230,
                    background: 'transparent',
                    fontFamily: 'Inter, sans-serif'
                },
                theme: { mode: 'dark' },
                labels: data.allocation.labels,
                series: data.allocation.values,
                colors: ['#10b981', '#f59e0b', '#3b82f6'],
                legend: {
                    position: 'bottom',
                    fontSize: '11px',
                    labels: { colors: '#a1a1aa' }
                },
                stroke: { width: 1, colors: ['#18181b'] },
                dataLabels: { enabled: false },
                plotOptions: {
                    pie: {
                        donut: {
                            size: '72%',
                            labels: {
                                show: true,
                                name: { show: true, fontSize: '11px', color: '#71717a' },
                                value: {
                                    show: true,
                                    fontSize: '14px',
                                    fontWeight: 'bold',
                                    color: '#ffffff',
                                    formatter: val => '₹' + Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 })
                                },
                                total: {
                                    show: true,
                                    label: 'Total Capital',
                                    fontSize: '10px',
                                    color: '#71717a',
                                    formatter: w => '₹' + w.globals.seriesTotals.reduce((a, b) => a + b, 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })
                                }
                            }
                        }
                    }
                },
                tooltip: {
                    theme: 'dark',
                    y: { formatter: val => '₹' + Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2 }) }
                }
            };

            if (chartAllocation) {
                chartAllocation.updateOptions(allocOptions);
            } else {
                chartAllocation = new ApexCharts(document.querySelector("#chart-allocation"), allocOptions);
                chartAllocation.render();
            }

            // 3. Render Symbol Bar Chart
            renderSymbolPnlChart(data);
        }

        function renderSymbolPnlChart(data) {
            const items = currentChartMode === 'DAY2' ? data.day2_pnl : data.history_pnl;
            const syms = items.map(x => x.symbol);
            const vals = items.map(x => x.pnl);
            const colors = items.map(x => x.color);

            const pnlBarOptions = {
                chart: {
                    type: 'bar',
                    height: 200,
                    toolbar: { show: false },
                    background: 'transparent',
                    fontFamily: 'JetBrains Mono, monospace'
                },
                theme: { mode: 'dark' },
                series: [{ name: 'Realized P&L (₹)', data: vals }],
                colors: colors,
                plotOptions: {
                    bar: {
                        distributed: true,
                        borderRadius: 4,
                        columnWidth: '40%',
                        dataLabels: { position: 'top' }
                    }
                },
                dataLabels: {
                    enabled: true,
                    formatter: val => (val >= 0 ? '+₹' : '-₹') + Math.abs(val).toFixed(2),
                    offsetY: -18,
                    style: { fontSize: '10px', colors: ['#f4f4f5'] }
                },
                xaxis: {
                    categories: syms,
                    labels: { style: { colors: '#a1a1aa', fontSize: '11px', fontWeight: 600 } },
                    axisBorder: { color: '#27272a' }
                },
                yaxis: {
                    labels: {
                        formatter: val => (val >= 0 ? '+' : '') + '₹' + val.toFixed(0),
                        style: { colors: '#71717a', fontSize: '10px' }
                    }
                },
                grid: { borderColor: '#27272a', strokeDashArray: 3 },
                legend: { show: false },
                tooltip: {
                    theme: 'dark',
                    y: { formatter: val => (val >= 0 ? '+₹' : '-₹') + Math.abs(val).toFixed(2) }
                }
            };

            if (chartSymbolPnl) {
                chartSymbolPnl.updateOptions(pnlBarOptions);
            } else {
                chartSymbolPnl = new ApexCharts(document.querySelector("#chart-symbol-pnl"), pnlBarOptions);
                chartSymbolPnl.render();
            }
        }

        function sendQuickPrompt(promptText) {
            document.getElementById('copilot-input').value = promptText;
            submitCopilot();
        }

        async function submitCopilot() {
            const input = document.getElementById('copilot-input');
            const prompt = input.value.trim();
            if (!prompt) return;

            const history = document.getElementById('copilot-history');
            
            // Add user message
            const userMsg = document.createElement('div');
            userMsg.className = 'bg-zinc-800/80 border border-zinc-700/60 rounded-lg p-2.5 text-white ml-6 text-right space-y-0.5';
            userMsg.innerHTML = `<div class="text-[10px] font-mono text-zinc-400 font-semibold">You</div><div class="text-zinc-200">${prompt}</div>`;
            history.appendChild(userMsg);
            input.value = '';
            history.scrollTop = history.scrollHeight;

            // Add loading indicator
            const loadId = 'copilot-load-' + Date.now();
            const loadMsg = document.createElement('div');
            loadMsg.id = loadId;
            loadMsg.className = 'bg-zinc-900/80 border border-zinc-800 rounded-lg p-2.5 text-zinc-400 text-xs font-mono mr-6 flex items-center gap-1.5';
            loadMsg.innerHTML = `<span class="pill-pulse">✨</span> Thinking...`;
            history.appendChild(loadMsg);
            history.scrollTop = history.scrollHeight;

            try {
                const res = await fetch('/api/copilot/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: prompt })
                });
                const data = await res.json();
                
                // Format reply
                const formatted = data.reply
                    .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
                    .replace(/\n/g, '<br>')
                    .replace(/•/g, '&bull;');

                const botMsg = document.getElementById(loadId);
                botMsg.className = 'bg-zinc-900/90 border border-zinc-800 rounded-lg p-2.5 text-zinc-300 mr-4 space-y-1 font-sans';
                botMsg.innerHTML = `<div class="text-[10px] font-mono font-bold text-indigo-400 flex items-center gap-1"><span>🤖</span> Copilot Assistant</div><div class="leading-relaxed text-xs text-zinc-200">${formatted}</div>`;
                history.scrollTop = history.scrollHeight;
            } catch (err) {
                const botMsg = document.getElementById(loadId);
                botMsg.className = 'bg-rose-950/40 border border-rose-800/50 rounded-lg p-2 text-rose-300 text-xs mr-4';
                botMsg.textContent = 'Copilot encountered an error. Please try again.';
            }
        }

        // Auto-poll state every 2 seconds
        setInterval(fetchState, 2000);
        setInterval(fetchChartData, 8000);
        fetchState();
        fetchChartData();
        evaluateStock();