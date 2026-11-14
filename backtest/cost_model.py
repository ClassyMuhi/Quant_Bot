"""
Cost & Slippage Models for Quant_Bot Backtest Engine
Implements realistic Indian market transaction costs, taxes, and slippage.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TradeCost:
    """Detailed breakdown of costs and execution price for a single trade."""
    order_type: str               # 'BUY' or 'SELL'
    quantity: int
    base_price: float
    effective_price: float        # Price adjusted for slippage
    gross_value: float            # quantity * effective_price
    brokerage: float
    stt: float                    # Securities Transaction Tax
    exchange_fee: float           # NSE / BSE transaction charges
    gst: float                    # 18% on (Brokerage + Exchange Fee)
    stamp_duty: float             # State Stamp Duty (BUY only)
    sebi_charges: float           # SEBI Turnover Charges
    slippage_cost: float          # Impact of slippage on total outlay
    total_taxes_and_charges: float # Sum of brokerage + taxes + statutory fees

    @property
    def total_cost(self) -> float:
        """Total friction cost = statutory fees + taxes + slippage."""
        return self.total_taxes_and_charges + self.slippage_cost

    @property
    def net_cash_impact(self) -> float:
        """
        Net cash delta from the portfolio:
        - BUY: -(gross_value + total_taxes_and_charges)
        - SELL: +(gross_value - total_taxes_and_charges)
        """
        if self.order_type.upper() == "BUY":
            return -(self.gross_value + self.total_taxes_and_charges)
        else:
            return +(self.gross_value - self.total_taxes_and_charges)


class CostModel(ABC):
    """Abstract interface for trade cost models."""

    @abstractmethod
    def calculate_cost(
        self,
        order_type: str,
        price: float,
        quantity: int,
    ) -> TradeCost:
        """Compute execution price, slippage, and statutory charges for an order."""
        pass


class IndianEquityCostModel(CostModel):
    """
    Standard Indian Equity Delivery Cost Model (NSE/BSE).
    Reflects prevailing discount broker fee structures (e.g., Zerodha, Groww):
    - Brokerage: 0.03% or Rs. 20 (whichever is lower) per order
    - STT (Securities Transaction Tax): 0.1% on delivery (BUY and SELL)
    - Exchange Turnover Charge: 0.00325% (NSE)
    - GST: 18% on (Brokerage + Exchange Turnover Charge)
    - SEBI Turnover Charge: 0.0001% (Rs. 10 per crore)
    - Stamp Duty: 0.015% on BUY only
    - Slippage: Configurable basis points (default 5 bps = 0.05%)
    """

    def __init__(
        self,
        brokerage_pct: float = 0.0003,       # 0.03%
        brokerage_max_per_order: float = 20.0, # Rs. 20 cap
        stt_pct: float = 0.001,              # 0.1%
        exchange_fee_pct: float = 0.0000325, # 0.00325%
        gst_pct: float = 0.18,               # 18%
        sebi_charges_pct: float = 0.000001,  # 0.0001%
        stamp_duty_pct: float = 0.00015,     # 0.015%
        slippage_bps: float = 5.0,           # 5 bps
    ):
        self.brokerage_pct = brokerage_pct
        self.brokerage_max_per_order = brokerage_max_per_order
        self.stt_pct = stt_pct
        self.exchange_fee_pct = exchange_fee_pct
        self.gst_pct = gst_pct
        self.sebi_charges_pct = sebi_charges_pct
        self.stamp_duty_pct = stamp_duty_pct
        self.slippage_rate = slippage_bps / 10000.0

    def calculate_cost(
        self,
        order_type: str,
        price: float,
        quantity: int,
    ) -> TradeCost:
        otype = order_type.strip().upper()
        if otype not in ("BUY", "SELL"):
            raise ValueError(f"Invalid order type: {order_type}. Must be 'BUY' or 'SELL'.")

        if quantity <= 0 or price <= 0:
            return TradeCost(
                order_type=otype,
                quantity=quantity,
                base_price=price,
                effective_price=price,
                gross_value=0.0,
                brokerage=0.0,
                stt=0.0,
                exchange_fee=0.0,
                gst=0.0,
                stamp_duty=0.0,
                sebi_charges=0.0,
                slippage_cost=0.0,
                total_taxes_and_charges=0.0,
            )

        # 1. Slippage calculation
        # BUY: price slips higher; SELL: price slips lower
        slippage_delta = price * self.slippage_rate
        if otype == "BUY":
            effective_price = price + slippage_delta
        else:
            effective_price = max(0.01, price - slippage_delta)

        gross_value = effective_price * quantity
        slippage_cost = slippage_delta * quantity

        # 2. Brokerage (e.g. min(0.03%, Rs. 20))
        raw_brokerage = gross_value * self.brokerage_pct
        brokerage = min(raw_brokerage, self.brokerage_max_per_order)

        # 3. STT (0.1% on delivery Buy and Sell)
        stt = gross_value * self.stt_pct

        # 4. Exchange Transaction Fee (0.00325%)
        exchange_fee = gross_value * self.exchange_fee_pct

        # 5. SEBI Charges (0.0001% = Rs. 10 per crore)
        sebi_charges = gross_value * self.sebi_charges_pct

        # 6. GST (18% on Brokerage + Exchange Fee + SEBI Charges)
        gst = (brokerage + exchange_fee + sebi_charges) * self.gst_pct

        # 7. Stamp Duty (0.015% on BUY only)
        stamp_duty = (gross_value * self.stamp_duty_pct) if otype == "BUY" else 0.0

        total_taxes_and_charges = brokerage + stt + exchange_fee + gst + sebi_charges + stamp_duty

        return TradeCost(
            order_type=otype,
            quantity=quantity,
            base_price=round(price, 4),
            effective_price=round(effective_price, 4),
            gross_value=round(gross_value, 2),
            brokerage=round(brokerage, 2),
            stt=round(stt, 2),
            exchange_fee=round(exchange_fee, 2),
            gst=round(gst, 2),
            stamp_duty=round(stamp_duty, 2),
            sebi_charges=round(sebi_charges, 4),
            slippage_cost=round(slippage_cost, 2),
            total_taxes_and_charges=round(total_taxes_and_charges, 2),
        )


class FlatPercentageCostModel(CostModel):
    """Simple percentage-based cost model (useful for quick sensitivity tests)."""

    def __init__(self, fee_pct: float = 0.001, slippage_bps: float = 5.0):
        self.fee_pct = fee_pct
        self.slippage_rate = slippage_bps / 10000.0

    def calculate_cost(self, order_type: str, price: float, quantity: int) -> TradeCost:
        otype = order_type.strip().upper()
        slippage_delta = price * self.slippage_rate
        effective_price = (price + slippage_delta) if otype == "BUY" else max(0.01, price - slippage_delta)
        gross_value = effective_price * quantity
        slippage_cost = slippage_delta * quantity
        taxes_and_charges = gross_value * self.fee_pct

        return TradeCost(
            order_type=otype,
            quantity=quantity,
            base_price=price,
            effective_price=round(effective_price, 4),
            gross_value=round(gross_value, 2),
            brokerage=round(taxes_and_charges, 2),
            stt=0.0,
            exchange_fee=0.0,
            gst=0.0,
            stamp_duty=0.0,
            sebi_charges=0.0,
            slippage_cost=round(slippage_cost, 2),
            total_taxes_and_charges=round(taxes_and_charges, 2),
        )


class ZeroCostModel(CostModel):
    """Zero cost and zero slippage model for theoretical benchmark comparisons."""

    def calculate_cost(self, order_type: str, price: float, quantity: int) -> TradeCost:
        otype = order_type.strip().upper()
        gross = price * quantity
        return TradeCost(
            order_type=otype,
            quantity=quantity,
            base_price=price,
            effective_price=price,
            gross_value=gross,
            brokerage=0.0,
            stt=0.0,
            exchange_fee=0.0,
            gst=0.0,
            stamp_duty=0.0,
            sebi_charges=0.0,
            slippage_cost=0.0,
            total_taxes_and_charges=0.0,
        )

