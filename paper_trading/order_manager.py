"""
Order Manager for Paper Trading
Validates incoming orders, prevents duplicates and naked short selling,
and assigns unique order identifiers.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import logging
from typing import Any, Dict, Optional, Tuple
from paper_trading.portfolio import PaperPortfolio
from paper_trading.position_sizer import PositionSizer, SizingResult

logger = logging.getLogger(__name__)


@dataclass
class PaperOrder:
    order_id: str
    timestamp: str
    symbol: str
    side: str  # "BUY" or "SELL"
    order_type: str  # "MARKET" or "LIMIT"
    trading_style: str  # "DELIVERY" or "INTRADAY"
    quantity: int
    entry_price: float
    limit_price: Optional[float]
    stop_loss: Optional[float]
    target_price: Optional[float]
    time_in_force: str  # "DAY", "IOC", "GTC"
    status: str  # "PENDING", "FILLED", "REJECTED", "CANCELLED"
    rejection_reason: Optional[str] = None
    executed_price: Optional[float] = None
    taxes_and_charges: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OrderManager:
    """
    Manages order pre-trade risk checks and lifecycle transitions.
    """

    def __init__(
        self,
        portfolio: PaperPortfolio,
        position_sizer: Optional[PositionSizer] = None,
        allow_naked_shorting: bool = False,
    ):
        self.portfolio = portfolio
        self.position_sizer = position_sizer or PositionSizer()
        self.allow_naked_shorting = allow_naked_shorting
        self._processed_hashes: set[str] = set()

    def generate_order_id(self, symbol: str, side: str) -> str:
        """Generates a human-readable unique order identifier."""
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        millis = int(datetime.now(timezone.utc).timestamp() * 1000) % 100000
        return f"ORD-{date_str}-{symbol.upper()}-{millis:05d}"

    def compute_idempotency_hash(self, symbol: str, side: str, qty: int, price: float) -> str:
        """Produces a short hash to detect accidental duplicate order clicks within seconds."""
        minute_bucket = int(datetime.now(timezone.utc).timestamp() // 15)  # 15 second window
        raw = f"{symbol}|{side}|{qty}|{price:.2f}|{minute_bucket}".encode("utf-8")
        return hashlib.md5(raw).hexdigest()

    def validate_and_create_order(
        self,
        symbol: str,
        side: str,
        investment_amount: float,
        risk_percent: float,
        entry_price: float,
        stop_loss_price: float,
        target_price: float,
        order_type: str = "MARKET",
        trading_style: str = "DELIVERY",
        limit_price: Optional[float] = None,
        time_in_force: str = "DAY",
        requested_quantity: Optional[int] = None,
    ) -> Tuple[Optional[PaperOrder], Optional[str]]:
        """
        Validates order configuration, checks cash solvency, short-selling rules,
        and duplicate submissions.
        Returns: (PaperOrder, error_message)
        """
        sym_clean = symbol.upper().replace(".NS", "")
        side_clean = side.upper()
        order_type_clean = order_type.upper()
        style_clean = trading_style.upper()

        if side_clean not in ("BUY", "SELL"):
            return None, f"Invalid side: '{side}'. Must be BUY or SELL."

        if order_type_clean not in ("MARKET", "LIMIT"):
            return None, f"Unsupported order type: '{order_type}'. Must be MARKET or LIMIT."

        effective_entry = limit_price if (order_type_clean == "LIMIT" and limit_price and limit_price > 0) else entry_price

        # 1. Determine Position Sizing
        if requested_quantity and requested_quantity > 0:
            # Explicit quantity passed: run validation
            qty = int(requested_quantity)
            sizing_res = self.position_sizer.calculate_sizing(
                symbol=sym_clean,
                side=side_clean,
                investment_amount=investment_amount,
                risk_percent=risk_percent,
                entry_price=effective_entry,
                stop_loss_price=stop_loss_price,
                target_price=target_price,
                available_cash=self.portfolio.cash,
            )
            # Override with requested qty if valid
            trade_cost = self.position_sizer.cost_model.calculate_cost(side_clean, effective_entry, qty)
            req_capital = abs(trade_cost.net_cash_impact) if side_clean == "BUY" else trade_cost.total_taxes_and_charges
            if side_clean == "BUY" and req_capital > self.portfolio.cash:
                return None, f"Insufficient funds: Capital required INR {req_capital:,.2f} > Available cash INR {self.portfolio.cash:,.2f}"
            taxes = trade_cost.total_taxes_and_charges
        else:
            # Auto-calculate risk-based sizing
            sizing_res = self.position_sizer.calculate_sizing(
                symbol=sym_clean,
                side=side_clean,
                investment_amount=investment_amount,
                risk_percent=risk_percent,
                entry_price=effective_entry,
                stop_loss_price=stop_loss_price,
                target_price=target_price,
                available_cash=self.portfolio.cash,
            )
            if not sizing_res.is_valid:
                return None, f"Position sizing rejected: {sizing_res.error_message}"
            qty = sizing_res.quantity
            taxes = sizing_res.estimated_costs

        # 2. Check Short-Selling Invariant
        if side_clean == "SELL":
            current_holding = self.portfolio.holdings.get(sym_clean, {}).get("quantity", 0)
            if current_holding < qty and not self.allow_naked_shorting:
                return None, (
                    f"Naked short selling rejected: Attempted to SELL {qty} shares of {sym_clean}, "
                    f"but current holding is only {current_holding} shares. "
                    "Quant_Bot does not permit unhedged naked short positions in cash delivery mode."
                )

        # 3. Duplicate Order Check
        idemp_hash = self.compute_idempotency_hash(sym_clean, side_clean, qty, effective_entry)
        if idemp_hash in self._processed_hashes:
            return None, f"Duplicate order detected: An identical order for {sym_clean} was submitted recently."
        self._processed_hashes.add(idemp_hash)

        order_id = self.generate_order_id(sym_clean, side_clean)
        now_iso = datetime.now(timezone.utc).isoformat()

        order = PaperOrder(
            order_id=order_id,
            timestamp=now_iso,
            symbol=sym_clean,
            side=side_clean,
            order_type=order_type_clean,
            trading_style=style_clean,
            quantity=qty,
            entry_price=round(effective_entry, 2),
            limit_price=round(limit_price, 2) if limit_price else None,
            stop_loss=round(stop_loss_price, 2) if stop_loss_price else None,
            target_price=round(target_price, 2) if target_price else None,
            time_in_force=time_in_force,
            status="PENDING",
            taxes_and_charges=round(taxes, 2),
        )

        return order, None
