"""
Order and Position Monitor for Paper Trading
Monitors active holdings against live market prices and OHLC candle intervals.
Evaluates Stop-Loss and Target triggers, and detects Ambiguous Candle scenarios.
"""

from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional
from paper_trading.portfolio import PaperPortfolio
from paper_trading.paper_broker import LocalPaperBroker

logger = logging.getLogger(__name__)


@dataclass
class TriggerEvent:
    symbol: str
    trigger_type: str  # "STOP_LOSS", "TARGET", "AMBIGUOUS"
    trigger_price: float
    candle_high: float
    candle_low: float
    quantity: int
    executed_order: Optional[Dict[str, Any]] = None
    warning: Optional[str] = None


class PositionMonitor:
    """
    Monitors open paper positions against incoming market quotes and candles.
    """

    def __init__(self, portfolio: PaperPortfolio, broker: Optional[LocalPaperBroker] = None):
        self.portfolio = portfolio
        self.broker = broker or LocalPaperBroker(portfolio)

    def check_candle(
        self,
        symbol: str,
        high: float,
        low: float,
        close: float,
        conservative_on_ambiguity: bool = True,
    ) -> Optional[TriggerEvent]:
        """
        Evaluates whether the given OHLC bar triggers Stop-Loss or Profit Target
        for an open long position.
        
        Ambiguous Candle Handling:
        If Low <= SL AND High >= Target:
        Both exit boundaries were crossed within the same bar.
        If conservative_on_ambiguity is True, assumes Stop-Loss hit first.
        """
        pos = self.portfolio.holdings.get(symbol.upper())
        if not pos:
            return None

        qty = pos["quantity"]
        sl_price = pos.get("sl_price")
        tp_price = pos.get("target_price")

        if not sl_price and not tp_price:
            return None

        sl_hit = sl_price is not None and low <= sl_price
        tp_hit = tp_price is not None and high >= tp_price

        # Case 1: Ambiguous Candle (Both triggered)
        if sl_hit and tp_hit:
            logger.warning(
                "Ambiguous candle detected for %s: Low (%.2f) <= SL (%.2f) AND High (%.2f) >= Target (%.2f)",
                symbol, low, sl_price, high, tp_price
            )
            trigger_price = sl_price if conservative_on_ambiguity else tp_price
            trigger_type = "AMBIGUOUS_SL_PRIORITY" if conservative_on_ambiguity else "AMBIGUOUS_TP_PRIORITY"

            # Execute exit trade
            trade_rec = self.portfolio.apply_trade(
                symbol=symbol,
                side="SELL",
                quantity=qty,
                executed_price=trigger_price,
                taxes_and_charges=self.broker.cost_model.calculate_cost("SELL", trigger_price, qty).total_taxes_and_charges,
                notes=f"Auto-exit: {trigger_type} (Low: {low}, High: {high})",
            )
            return TriggerEvent(
                symbol=symbol,
                trigger_type=trigger_type,
                trigger_price=trigger_price,
                candle_high=high,
                candle_low=low,
                quantity=qty,
                executed_order=trade_rec,
                warning="Ambiguous candle: Both Stop-Loss and Target levels were breached during the same trading interval.",
            )

        # Case 2: Stop-Loss Triggered
        if sl_hit:
            trade_rec = self.portfolio.apply_trade(
                symbol=symbol,
                side="SELL",
                quantity=qty,
                executed_price=sl_price,
                taxes_and_charges=self.broker.cost_model.calculate_cost("SELL", sl_price, qty).total_taxes_and_charges,
                notes=f"Auto-exit: Stop-Loss breached at {sl_price:.2f}",
            )
            return TriggerEvent(
                symbol=symbol,
                trigger_type="STOP_LOSS",
                trigger_price=sl_price,
                candle_high=high,
                candle_low=low,
                quantity=qty,
                executed_order=trade_rec,
            )

        # Case 3: Target Price Triggered
        if tp_hit:
            trade_rec = self.portfolio.apply_trade(
                symbol=symbol,
                side="SELL",
                quantity=qty,
                executed_price=tp_price,
                taxes_and_charges=self.broker.cost_model.calculate_cost("SELL", tp_price, qty).total_taxes_and_charges,
                notes=f"Auto-exit: Target reached at {tp_price:.2f}",
            )
            return TriggerEvent(
                symbol=symbol,
                trigger_type="TARGET",
                trigger_price=tp_price,
                candle_high=high,
                candle_low=low,
                quantity=qty,
                executed_order=trade_rec,
            )

        return None
