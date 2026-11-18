"""
Intraday Auto-Pilot Engine for Quant_Bot
Executes systematic intraday trading cycles across the NSE stock universe:
- Configurable allocated capital budget
- Scan frequency with a strict minimum of 10 minutes
- User-defined execution window (Start Time to End Time IST)
- Automated position monitoring (Stop-Loss / Profit-Target triggers)
- Automated mandatory square-off before market close (e.g. 15:20 IST)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, time, timezone, timedelta
import logging
import threading
import time as stdlib_time
from typing import Any, Dict, List, Optional, Tuple

from pipeline.symbol_universe import SymbolUniverse
from godseye.intelligence import GodsEyeIntelligence
from decision_engine.engine import DecisionEngine, TradeDecision
from paper_trading.portfolio import PaperPortfolio
from paper_trading.order_manager import OrderManager, PaperOrder
from paper_trading.paper_broker import PaperExecutionGateway
from paper_trading.order_monitor import PositionMonitor
from paper_trading.position_sizer import PositionSizer

logger = logging.getLogger(__name__)


@dataclass
class AutoPilotConfig:
    """User-configured parameters for Intraday Auto-Pilot."""
    allocated_capital: float = 100_000.0   # Total amount user is willing to put in
    frequency_minutes: int = 10            # Strict minimum of 10 minutes
    start_time_str: str = "09:15"          # Daily start time (HH:MM IST)
    end_time_str: str = "15:15"            # Daily new entry cutoff (HH:MM IST)
    square_off_time_str: str = "15:20"     # Mandatory intraday square-off time (HH:MM IST)
    risk_per_trade_pct: float = 1.5        # Max risk budget per trade
    max_active_positions: int = 3          # Max concurrent open intraday positions
    min_confidence: float = 0.60           # Minimum signal confidence to trigger order

    def __post_init__(self):
        # Enforce minimum frequency requirement of 10 minutes
        if self.frequency_minutes < 10:
            logger.warning("AutoPilot frequency %d min is below minimum 10 min. Setting to 10 min.", self.frequency_minutes)
            self.frequency_minutes = 10


@dataclass
class ScanLogEntry:
    timestamp: str
    symbol: str
    decision: str
    score: float
    confidence: float
    action: str  # e.g., "ORDER_PLACED", "SKIPPED_LOW_CONFIDENCE", "SKIPPED_EXISTING_POS", "SKIPPED_BUDGET"
    details: str


class IntradayAutoPilot:
    """
    Coordinates autonomous intraday scanning, decision evaluation,
    order routing, and mandatory square-off.
    """

    def __init__(
        self,
        config: AutoPilotConfig,
        portfolio: Optional[PaperPortfolio] = None,
        universe: Optional[SymbolUniverse] = None,
        godseye: Optional[GodsEyeIntelligence] = None,
        decision_engine: Optional[DecisionEngine] = None,
    ):
        self.config = config
        self.portfolio = portfolio or PaperPortfolio()
        self.universe = universe or SymbolUniverse()
        self.godseye = godseye or GodsEyeIntelligence()
        self.decision_engine = decision_engine or DecisionEngine(godseye=self.godseye)
        self.gateway = PaperExecutionGateway(self.portfolio)
        self.order_manager = OrderManager(self.portfolio)
        self.position_sizer = PositionSizer()
        self.monitor = PositionMonitor(self.portfolio)

        self.is_running: bool = False
        self.last_cycle_time: Optional[datetime] = None
        self.next_cycle_time: Optional[datetime] = None
        self.cycle_count: int = 0
        self.scan_logs: List[ScanLogEntry] = []
        self.active_intraday_orders: List[Dict[str, Any]] = []

        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self, price_lookup_func=None) -> None:
        """
        Launches the autonomous Auto-Pilot background thread.
        Runs cycles continuously every `frequency_minutes` without needing UI interaction.
        """
        if self.is_running and self._worker_thread and self._worker_thread.is_alive():
            logger.info("AutoPilot is already running in background thread.")
            return

        self.is_running = True
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._run_loop,
            args=(price_lookup_func,),
            daemon=True,
            name="AutoPilot-WorkerThread"
        )
        self._worker_thread.start()
        logger.info("AutoPilot autonomous background daemon thread successfully started.")

    def stop(self) -> None:
        """Stops the autonomous background worker loop."""
        self.is_running = False
        self._stop_event.set()
        logger.info("AutoPilot autonomous background worker requested to stop.")

    def _run_loop(self, price_lookup_func=None) -> None:
        """
        Continuous background daemon loop:
        1. Executes initial cycle immediately upon starting.
        2. Ticks every second; when next_cycle_time arrives, executes cycle automatically.
        3. Enforces automatic square-off at 03:20 PM IST.
        """
        logger.info("AutoPilot background worker loop initialized.")
        try:
            self.execute_cycle(price_lookup_func=price_lookup_func)
        except Exception as e:
            logger.error("Error during initial AutoPilot cycle: %s", e, exc_info=True)

        while self.is_running and not self._stop_event.is_set():
            ist_now = self.get_ist_now()

            # 1. Mandatory Market Close Square-Off check
            if self.is_past_square_off(ist_now):
                logger.info("Past square-off time (03:20 PM IST). Executing mandatory square-off.")
                try:
                    self.square_off_all_intraday(price_lookup_func)
                except Exception as e:
                    logger.error("Error during automatic square-off: %s", e)
                self.stop()
                break

            # 2. Check if next scheduled cycle time has arrived
            if self.next_cycle_time and ist_now >= self.next_cycle_time:
                logger.info("Scheduled cycle interval reached. Executing cycle #%d...", self.cycle_count + 1)
                try:
                    self.execute_cycle(price_lookup_func=price_lookup_func)
                except Exception as e:
                    logger.error("Error in scheduled AutoPilot cycle: %s", e, exc_info=True)

            # Sleep in 1-second intervals for immediate responsiveness on stop()
            self._stop_event.wait(1.0)

        logger.info("AutoPilot background worker loop exited.")

    def get_ist_now(self) -> datetime:
        """Returns current timestamp in Indian Standard Time (UTC+05:30)."""
        utc_now = datetime.now(timezone.utc)
        ist_offset = timedelta(hours=5, minutes=30)
        return utc_now + ist_offset

    def is_within_trading_window(self, check_dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Validates if check_dt falls between start_time and end_time.
        """
        dt = check_dt or self.get_ist_now()
        current_t = dt.time()

        start_h, start_m = map(int, self.config.start_time_str.split(":"))
        end_h, end_m = map(int, self.config.end_time_str.split(":"))
        sq_h, sq_m = map(int, self.config.square_off_time_str.split(":"))

        t_start = time(start_h, start_m)
        t_end = time(end_h, end_m)
        t_sq = time(sq_h, sq_m)

        if current_t < t_start:
            return False, f"Pre-Market: Trading window opens at {self.config.start_time_str} IST"
        if current_t >= t_sq:
            return False, f"Post-Market: Past mandatory square-off time ({self.config.square_off_time_str} IST)"
        if current_t >= t_end:
            return False, f"Entry Cutoff: Past new entry window ({self.config.end_time_str} IST). Monitoring exits only."

        return True, "Within Active Trading Window"

    def is_past_square_off(self, check_dt: Optional[datetime] = None) -> bool:
        """Checks if current time has crossed mandatory square-off time."""
        dt = check_dt or self.get_ist_now()
        sq_h, sq_m = map(int, self.config.square_off_time_str.split(":"))
        return dt.time() >= time(sq_h, sq_m)

    def square_off_all_intraday(self, price_lookup_func=None) -> List[Dict[str, Any]]:
        """
        Closes all open INTRADAY positions at current market quotes.
        Prevents overnight risk. Routes exit orders through self.gateway.execute
        so they are closed live on MegaBull when connected.
        """
        closed_records = []
        now_iso = datetime.now(timezone.utc).isoformat()

        intraday_symbols = [
            s for s, pos in list(self.portfolio.holdings.items())
            if pos.get("trading_style") == "INTRADAY"
        ]

        for s in intraday_symbols:
            pos = self.portfolio.holdings[s]
            qty = pos["quantity"]
            curr_price = price_lookup_func(s) if price_lookup_func else pos.get("current_price", pos["avg_price"])

            order = PaperOrder(
                order_id=f"ORD-SQOFF-{s}-{int(datetime.now().timestamp())}",
                timestamp=now_iso,
                symbol=s,
                side="SELL",
                order_type="MARKET",
                trading_style="INTRADAY",
                quantity=qty,
                entry_price=curr_price,
                limit_price=None,
                stop_loss=None,
                target_price=None,
                time_in_force="DAY",
                status="PENDING",
            )
            filled_order, trade_rec = self.gateway.execute(order, current_market_price=curr_price)
            closed_records.append(trade_rec)
            self._log(s, "SELL", 0.0, 1.0, "AUTO_SQUARE_OFF", f"Closed {qty} shares @ ₹{filled_order.executed_price:,.2f}")

        logger.info("Auto-Pilot: Squared off %d intraday positions.", len(closed_records))
        return closed_records

    def execute_cycle(self, price_lookup_func=None) -> Dict[str, Any]:
        """
        Executes one complete Auto-Pilot scan and trade cycle:
        1. Checks trading window & square-off condition.
        2. Monitors open positions against latest prices.
        3. Scans configured symbol universe with Decision Engine.
        4. Auto-sizes and places orders within allocated capital limit.
        5. Updates cycle schedule.
        """
        ist_now = self.get_ist_now()
        now_iso = datetime.now(timezone.utc).isoformat()
        self.cycle_count += 1
        self.last_cycle_time = ist_now
        self.next_cycle_time = ist_now + timedelta(minutes=self.config.frequency_minutes)

        results = {
            "cycle_number": self.cycle_count,
            "timestamp": now_iso,
            "ist_time": ist_now.strftime("%Y-%m-%d %H:%M:%S IST"),
            "status": "COMPLETED",
            "trades_placed": 0,
            "positions_monitored": len(self.portfolio.holdings),
            "actions": [],
        }

        # 1. Check Mandatory Square-off
        if self.is_past_square_off(ist_now):
            closed = self.square_off_all_intraday(price_lookup_func)
            results["status"] = "SQUARED_OFF"
            results["squared_off_count"] = len(closed)
            return results

        # 2. Check Trading Window for New Entries
        can_enter, reason = self.is_within_trading_window(ist_now)

        # 3. Monitor Active Holdings for SL / TP exits
        for sym, pos in list(self.portfolio.holdings.items()):
            if pos.get("trading_style") == "INTRADAY":
                curr_p = price_lookup_func(sym) if price_lookup_func else pos.get("current_price", pos["avg_price"])
                # Approximate 10m high/low bar around current quote
                bar_h = curr_p * 1.002
                bar_l = curr_p * 0.998
                trigger = self.monitor.check_candle(sym, high=bar_h, low=bar_l, close=curr_p)
                if trigger:
                    # If in MegaBull mode, route live SELL order to close the cloud position
                    if self.gateway.megabull_client is not None:
                        exit_order = PaperOrder(
                            order_id=f"ORD-EXIT-{sym}-{int(datetime.now().timestamp())}",
                            timestamp=now_iso,
                            symbol=sym,
                            side="SELL",
                            order_type="MARKET",
                            trading_style="INTRADAY",
                            quantity=pos["quantity"],
                            entry_price=trigger.trigger_price,
                            limit_price=None,
                            stop_loss=None,
                            target_price=None,
                            time_in_force="DAY",
                            status="PENDING",
                        )
                        self.gateway.execute(exit_order, current_market_price=trigger.trigger_price)

                    self._log(sym, "EXIT", 0.0, 1.0, f"TRIGGER_{trigger.trigger_type}", f"Exit hit at ₹{trigger.trigger_price:,.2f}")
                    results["actions"].append(f"{sym} exited via {trigger.trigger_type}")

        if not can_enter:
            results["status"] = f"SKIPPED_OUTSIDE_WINDOW ({reason})"
            return results

        # 4. Check Available Intraday Budget & Position Slots
        current_intraday_positions = sum(
            1 for p in self.portfolio.holdings.values() if p.get("trading_style") == "INTRADAY"
        )
        available_slots = self.config.max_active_positions - current_intraday_positions

        if available_slots <= 0:
            results["status"] = f"MAX_POSITIONS_REACHED ({self.config.max_active_positions})"
            return results

        # Capital available for auto-pilot = allocated_capital - current invested in intraday
        current_intraday_invested = sum(
            p["quantity"] * p.get("current_price", p["avg_price"])
            for p in self.portfolio.holdings.values()
            if p.get("trading_style") == "INTRADAY"
        )
        remaining_budget = max(0.0, self.config.allocated_capital - current_intraday_invested)

        # Cap by available paper cash (or live MegaBull cash if connected)
        available_cash = self.portfolio.cash
        if self.gateway.megabull_client is not None:
            try:
                prof = self.gateway.megabull_client.get_user_profile()
                available_cash = float(prof.get("virtualMoneyLeft", available_cash))
            except Exception:
                pass

        effective_budget = min(remaining_budget, available_cash)

        if effective_budget < 5000.0:
            results["status"] = "INSUFFICIENT_ALLOCATED_CAPITAL"
            return results

        per_trade_investment = effective_budget / available_slots

        # 5. Scan Universe with Decision Engine
        symbols = self.universe.get_symbols()
        candidates: List[Tuple[TradeDecision, float]] = []

        for sym in symbols:
            # Skip if already holding this stock
            if sym in self.portfolio.holdings:
                continue

            curr_price = price_lookup_func(sym) if price_lookup_func else 1000.0
            dec = self.decision_engine.evaluate(sym, current_price=curr_price)

            if dec.decision == "BUY" and dec.confidence >= self.config.min_confidence:
                candidates.append((dec, curr_price))
            else:
                self._log(sym, dec.decision, dec.combined_score, dec.confidence, "SKIPPED", dec.explanation[:80])

        # Sort candidates by combined_score descending (strongest setups first)
        candidates.sort(key=lambda x: (x[0].combined_score, x[0].confidence), reverse=True)

        # 6. Execute Top Candidates up to available slots
        for dec, curr_price in candidates[:available_slots]:
            sym = dec.selected_stock
            entry_p = dec.suggested_entry_price or curr_price
            sl_p = dec.suggested_stop_loss or (entry_p * 0.985)
            tp_p = dec.suggested_target_price or (entry_p * 1.03)

            order, err = self.order_manager.validate_and_create_order(
                symbol=sym,
                side="BUY",
                investment_amount=per_trade_investment,
                risk_percent=self.config.risk_per_trade_pct,
                entry_price=entry_p,
                stop_loss_price=sl_p,
                target_price=tp_p,
                order_type="MARKET",
                trading_style="INTRADAY",
            )

            if err:
                self._log(sym, "BUY", dec.combined_score, dec.confidence, "REJECTED", err)
            else:
                filled, rec = self.gateway.execute(order, current_market_price=entry_p)
                results["trades_placed"] += 1
                results["actions"].append(f"BUY {filled.quantity} {sym} @ ₹{filled.executed_price:,.2f}")
                self._log(
                    sym, "BUY", dec.combined_score, dec.confidence, "ORDER_PLACED",
                    f"Filled {filled.quantity} shares @ ₹{filled.executed_price:,.2f} | SL=₹{sl_p:,.2f} TP=₹{tp_p:,.2f}"
                )

        return results

    def _log(self, symbol: str, decision: str, score: float, conf: float, action: str, details: str):
        entry = ScanLogEntry(
            timestamp=self.get_ist_now().strftime("%H:%M:%S"),
            symbol=symbol,
            decision=decision,
            score=round(score, 2),
            confidence=round(conf, 2),
            action=action,
            details=details,
        )
        self.scan_logs.insert(0, entry)
        if len(self.scan_logs) > 100:
            self.scan_logs.pop()


GLOBAL_AUTOPILOT: Optional[IntradayAutoPilot] = None


def get_global_autopilot(
    config: Optional[AutoPilotConfig] = None,
    portfolio: Optional[PaperPortfolio] = None,
) -> IntradayAutoPilot:
    """Returns a shared, persistent singleton AutoPilot instance."""
    global GLOBAL_AUTOPILOT
    if GLOBAL_AUTOPILOT is None:
        cfg = config or AutoPilotConfig()
        GLOBAL_AUTOPILOT = IntradayAutoPilot(config=cfg, portfolio=portfolio)
    elif config is not None:
        GLOBAL_AUTOPILOT.config = config
    return GLOBAL_AUTOPILOT

