let allTrades = [];
        let megabullOrders = [];
        let currentFilter = 'ALL';
        let currentTab = 'ledger';

        function updateClock() {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false });
            const clockEl = document.getElementById('current-clock');
            if (clockEl) clockEl.textContent = `${timeStr} IST`;
        }

        function formatIST(isoStr) {
            if (!isoStr) return '--';
            try {
                const d = new Date(isoStr);
                return d.toLocaleString('en-IN', {
                    timeZone: 'Asia/Kolkata',
                    day: '2-digit',
                    month: 'short',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: true
                });
            } catch (e) {
                return isoStr.slice(0, 19).replace('T', ' ');
            }
        }

        async function fetchOrders() {
            try {
                const res = await fetch('/api/orders');
                const data = await res.json();
                allTrades = data.trades || [];
                megabullOrders = (data.megabull_orders && data.megabull_orders.executed) ? data.megabull_orders.executed : [];

                // 1. Update Connection Badge
                const modeText = document.getElementById('mode-text');
                if (data.megabull_connected) {
                    modeText.textContent = data.mode_label || 'MEGABULL CONNECTED';
                    modeText.parentElement.className = 'px-3 py-1 rounded-full text-xs font-mono font-medium bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center gap-1.5';
                } else {
                    modeText.textContent = 'LOCAL SIMULATION';
                    modeText.parentElement.className = 'px-3 py-1 rounded-full text-xs font-mono font-medium bg-zinc-800 text-zinc-400 border border-zinc-700 flex items-center gap-1.5';
                }

                // 2. Render KPIs
                const s = data.summary;
                const netEl = document.getElementById('kpi-net-pnl');
                const netSign = s.net_pnl >= 0 ? '+' : '';
                netEl.textContent = `${netSign}₹${s.net_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
                netEl.className = 'text-2xl font-bold font-mono mt-1 ' + (s.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400');

                document.getElementById('kpi-pnl-breakdown').textContent = `+₹${s.gross_profit.toLocaleString('en-IN')} Profit / -₹${Math.abs(s.gross_loss).toLocaleString('en-IN')} Loss`;

                document.getElementById('kpi-win-rate').textContent = `${s.win_rate}%`;
                document.getElementById('kpi-win-ratio').textContent = `${s.winning_trades_count} Wins / ${s.losing_trades_count} Losses (${s.closed_trades_count} Closed)`;

                document.getElementById('kpi-taxes').textContent = `₹${s.total_taxes_and_charges.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
                document.getElementById('kpi-total-orders').textContent = s.total_trades;
                document.getElementById('kpi-orders-breakdown').textContent = `${s.buy_trades_count} Buys | ${s.closed_trades_count} Sells`;
                document.getElementById('kpi-cash').textContent = `₹${s.cash_balance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

                // 3. Tab & Pill counts
                document.getElementById('count-ledger').textContent = allTrades.length;
                document.getElementById('count-megabull').textContent = megabullOrders.length;
                document.getElementById('pill-count-all').textContent = allTrades.length;
                document.getElementById('pill-count-profit').textContent = s.winning_trades_count;
                document.getElementById('pill-count-loss').textContent = s.losing_trades_count;
                document.getElementById('pill-count-sell').textContent = s.closed_trades_count;
                document.getElementById('pill-count-buy').textContent = s.buy_trades_count;

                applyFilters();
                renderMegaBullTable();
            } catch (err) {
                console.error("Error fetching orders:", err);
            }
        }

        function setFilter(filter) {
            currentFilter = filter;
            const buttons = ['all', 'profit', 'loss', 'sell', 'buy'];
            buttons.forEach(b => {
                const el = document.getElementById(`filter-${b}`);
                if (!el) return;
                if (b.toUpperCase() === filter.toUpperCase()) {
                    el.className = 'px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-zinc-700 text-white border border-zinc-600 transition';
                } else {
                    el.className = 'px-2.5 py-1 rounded-full text-xs font-mono font-medium text-zinc-400 hover:bg-zinc-800 border border-zinc-800 transition';
                }
            });
            applyFilters();
        }

        function applyFilters() {
            const query = (document.getElementById('search-input').value || '').trim().toUpperCase();
            let filtered = allTrades.filter(t => {
                // Filter pill
                if (currentFilter === 'PROFIT' && t.status !== 'PROFIT') return false;
                if (currentFilter === 'LOSS' && t.status !== 'LOSS') return false;
                if (currentFilter === 'SELL' && t.side !== 'SELL') return false;
                if (currentFilter === 'BUY' && t.side !== 'BUY') return false;

                // Search query
                if (query) {
                    const matchSymbol = t.symbol.toUpperCase().includes(query);
                    const matchId = t.order_id.toUpperCase().includes(query);
                    const matchNotes = (t.notes || '').toUpperCase().includes(query);
                    if (!matchSymbol && !matchId && !matchNotes) return false;
                }
                return true;
            });

            renderLedgerTable(filtered);
        }

        function renderLedgerTable(trades) {
            const tbody = document.getElementById('tbody-ledger');
            if (!trades || trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="13" class="py-12 text-center text-zinc-500 font-sans">No orders match the selected filter.</td></tr>';
                return;
            }

            tbody.innerHTML = trades.map(t => {
                const isSell = t.side === 'SELL';
                const sideColor = isSell ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30' : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
                
                let outcomeBadge = '';
                let pnlColor = 'text-zinc-400';
                let pnlText = '--';
                let roiText = '--';

                if (isSell) {
                    if (t.status === 'PROFIT') {
                        outcomeBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">PROFIT</span>';
                        pnlColor = 'text-emerald-400 font-bold';
                        pnlText = `+₹${t.realized_pnl.toFixed(2)}`;
                        roiText = `+${t.pnl_pct.toFixed(2)}%`;
                    } else if (t.status === 'LOSS') {
                        outcomeBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30">LOSS</span>';
                        pnlColor = 'text-rose-400 font-bold';
                        pnlText = `-₹${Math.abs(t.realized_pnl).toFixed(2)}`;
                        roiText = `${t.pnl_pct.toFixed(2)}%`;
                    } else {
                        outcomeBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-zinc-800 text-zinc-400 border border-zinc-700">EVEN</span>';
                        pnlText = '₹0.00';
                        roiText = '0.00%';
                    }
                } else {
                    outcomeBadge = '<span class="px-2 py-0.5 rounded-full text-[10px] font-medium bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">OPEN LEG</span>';
                    pnlText = '<span class="text-zinc-600">--</span>';
                    roiText = t.pnl_pct !== 0.0 ? `<span class="${t.pnl_pct >= 0 ? 'text-emerald-500' : 'text-rose-400'}">${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(2)}%</span>` : '<span class="text-zinc-600">--</span>';
                }

                return `
                    <tr class="hover:bg-zinc-800/40 transition">
                        <td class="py-2.5 px-3 text-zinc-400 text-[11px] whitespace-nowrap">${formatIST(t.timestamp)}</td>
                        <td class="py-2.5 px-3 text-zinc-500 text-[11px] font-mono">${t.order_id}</td>
                        <td class="py-2.5 px-3 font-bold text-white">${t.symbol}</td>
                        <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded text-[10px] font-semibold ${sideColor}">${t.side}</span></td>
                        <td class="py-2.5 px-3"><span class="px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] text-zinc-400">${t.trading_style}</span></td>
                        <td class="py-2.5 px-3 text-right font-medium">${t.quantity}</td>
                        <td class="py-2.5 px-3 text-right text-zinc-300">₹${t.price.toFixed(2)}</td>
                        <td class="py-2.5 px-3 text-right text-zinc-400">₹${t.gross_value.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                        <td class="py-2.5 px-3 text-right text-zinc-500">₹${t.taxes_and_charges.toFixed(2)}</td>
                        <td class="py-2.5 px-3 text-right font-mono ${pnlColor}">${pnlText}</td>
                        <td class="py-2.5 px-3 text-right font-mono ${pnlColor}">${roiText}</td>
                        <td class="py-2.5 px-3 text-center whitespace-nowrap">${outcomeBadge}</td>
                        <td class="py-2.5 px-3 text-zinc-400 text-[11px] truncate max-w-xs" title="${t.notes || ''}">${t.notes || 'Executed'}</td>
                    </tr>
                `;
            }).join('');
        }

        function renderMegaBullTable() {
            const tbody = document.getElementById('tbody-megabull');
            if (!megabullOrders || megabullOrders.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" class="py-12 text-center text-zinc-500 font-sans">No cloud orders returned by MegaBull API.</td></tr>';
                return;
            }

            tbody.innerHTML = megabullOrders.map(o => {
                const isBuy = o.type === 'BUY';
                const sideColor = isBuy ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30' : 'bg-amber-500/10 text-amber-400 border border-amber-500/30';
                const val = (o.qty || 0) * (o.price || 0);

                return `
                    <tr class="hover:bg-zinc-800/40 transition">
                        <td class="py-2.5 px-3 font-mono text-zinc-400">${o.id}</td>
                        <td class="py-2.5 px-3 text-zinc-400 text-[11px] whitespace-nowrap">${formatIST(o.createdTimestamp)}</td>
                        <td class="py-2.5 px-3 font-bold text-white">${o.instrumentName || o.instrumentToken}</td>
                        <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded text-[10px] font-semibold ${sideColor}">${o.type}</span></td>
                        <td class="py-2.5 px-3"><span class="px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] text-zinc-400">${o.duration || 'MIS'}</span></td>
                        <td class="py-2.5 px-3 text-right font-medium">${o.qty}</td>
                        <td class="py-2.5 px-3 text-right text-zinc-300">₹${Number(o.price || 0).toFixed(2)}</td>
                        <td class="py-2.5 px-3 text-right text-zinc-400">₹${val.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                        <td class="py-2.5 px-3 text-center"><span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">${o.status}</span></td>
                    </tr>
                `;
            }).join('');
        }

        function switchTab(tab) {
            currentTab = tab;
            const btnLedger = document.getElementById('tab-ledger');
            const btnMb = document.getElementById('tab-megabull');
            const tableLedger = document.getElementById('table-ledger');
            const tableMb = document.getElementById('table-megabull');
            const filterBar = document.getElementById('filter-pills-bar');

            if (tab === 'ledger') {
                btnLedger.className = 'px-3.5 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 text-white border border-zinc-700 transition flex items-center gap-1.5';
                btnMb.className = 'px-3.5 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition flex items-center gap-1.5';
                tableLedger.classList.remove('hidden');
                tableMb.classList.add('hidden');
                filterBar.classList.remove('hidden');
            } else {
                btnMb.className = 'px-3.5 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 text-white border border-zinc-700 transition flex items-center gap-1.5';
                btnLedger.className = 'px-3.5 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition flex items-center gap-1.5';
                tableMb.classList.remove('hidden');
                tableLedger.classList.add('hidden');
                filterBar.classList.add('hidden');
            }
        }

        function exportCSV() {
            if (!allTrades || allTrades.length === 0) {
                alert("No orders to export.");
                return;
            }
            const headers = ["Order ID", "Timestamp", "Symbol", "Side", "Style", "Quantity", "Price", "Gross Value", "Charges", "Realized P&L", "Return %", "Status", "Notes"];
            const rows = allTrades.map(t => [
                t.order_id,
                t.timestamp,
                t.symbol,
                t.side,
                t.trading_style,
                t.quantity,
                t.price,
                t.gross_value,
                t.taxes_and_charges,
                t.realized_pnl,
                t.pnl_pct,
                t.status,
                `"${(t.notes || '').replace(/"/g, '""')}"`
            ]);
            const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
            const encodedUri = encodeURI(csvContent);
            const link = document.createElement("a");
            link.setAttribute("href", encodedUri);
            link.setAttribute("download", `quant_bot_orders_${new Date().toISOString().slice(0, 10)}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        setInterval(fetchOrders, 4000);
        setInterval(updateClock, 1000);
        updateClock();
        fetchOrders();