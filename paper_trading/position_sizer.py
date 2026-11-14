"""
Risk-Based Position Sizer for Paper Trading
Implements dual-constraint integer share sizing (investment budget and risk budget),
transaction friction estimates, and cash solvency limits.
"""

from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Optional, Tuple
from backtest.cost_model import IndianEquityCostModel

logger = logging.getLogger(__name__)


@dataclass
class SizingResult:
    """Detailed calculation results for position sizing."""
    is_valid: bool
    quantity: int
    entry_price: float
    stop_loss_price: float
    target_price: float
    investment_amount: float
    risk_budget: float
    risk_per_share: float
    risk_based_quantity: int
    budget_based_quantity: int
    total_capital_required: float
    estimated_costs: float
    max_loss_inr: float
    expected_profit_inr: float
    risk_to_reward_ratio: float
    error_message: Optional[str] = None


class PositionSizer:
    """
    Computes prudent risk-adjusted share sizing for Indian equities.
    """

    def __init__(self, cost_model: Optional[IndianEquityCostModel] = None):
        self.cost_model = cost_model or IndianEquityCostModel(brokerage_pct=0.0003, brokerage_max_per_order=20.0)

    def calculate_sizing(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        investment_amount: float,
        risk_percent: float,
        entry_price: float,
        stop_loss_price: float,
        target_price: float,
        available_cash: float,
        is_intraday: bool = False,
    ) -> SizingResult:
        """
        Calculates integer share quantity and risk parameters under strict safety checks:
        1. Validates entry, stop-loss, and target relationship.
        2. Applies dual-constraint sizing: min(risk_budget / risk_per_share, investment / entry).
        3. Docks estimated statutory charges (STT, GST, Stamp Duty, Brokerage).
        4. Verifies capital requirements do not exceed available cash balance.
        """
        side_clean = side.upper()

        # Invariant Validations
        if entry_price <= 0:
            return self._invalid_result("Entry price must be positive.", entry_price, stop_loss_price, target_price)

        if investment_amount <= 0:
            return self._invalid_result("Investment amount must be positive.", entry_price, stop_loss_price, target_price)

        if risk_percent <= 0 or risk_percent > 100:
            return self._invalid_result("Risk percentage must be between 0.1% and 100%.", entry_price, stop_loss_price, target_price)

        if side_clean == "BUY":
            if stop_loss_price >= entry_price:
                return self._invalid_result(
                    f"Invalid Stop-Loss ({stop_loss_price:.2f}) for BUY: must be strictly below Entry ({entry_price:.2f}).",
                    entry_price, stop_loss_price, target_price
                )
            if target_price <= entry_price:
                return self._invalid_result(
                    f"Invalid Target ({target_price:.2f}) for BUY: must be strictly above Entry ({entry_price:.2f}).",
                    entry_price, stop_loss_price, target_price
                )
        elif side_clean == "SELL":
            if stop_loss_price <= entry_price:
                return self._invalid_result(
                    f"Invalid Stop-Loss ({stop_loss_price:.2f}) for SELL: must be strictly above Entry ({entry_price:.2f}).",
                    entry_price, stop_loss_price, target_price
                )
            if target_price >= entry_price:
                return self._invalid_result(
                    f"Invalid Target ({target_price:.2f}) for SELL: must be strictly below Entry ({entry_price:.2f}).",
                    entry_price, stop_loss_price, target_price
                )
        else:
            return self._invalid_result(f"Unsupported order side: {side}", entry_price, stop_loss_price, target_price)

        # Core calculations
        risk_budget = investment_amount * (risk_percent / 100.0)
        risk_per_share = abs(entry_price - stop_loss_price)

        if risk_per_share <= 0:
            return self._invalid_result("Stop-loss price cannot equal entry price.", entry_price, stop_loss_price, target_price)

        risk_based_qty = int(risk_budget / risk_per_share)
        budget_based_qty = int(investment_amount / entry_price)
        candidate_qty = min(risk_based_qty, budget_based_qty)

        if candidate_qty <= 0:
            return self._invalid_result(
                "Calculated quantity is 0 shares. Increase investment amount or adjust stop-loss distance.",
                entry_price, stop_loss_price, target_price
            )

        # Check transaction cost and solvency against available cash (for BUY orders)
        qty = candidate_qty
        trade_cost = self.cost_model.calculate_cost(side_clean, entry_price, qty)
        required_capital = abs(trade_cost.net_cash_impact) if side_clean == "BUY" else trade_cost.total_taxes_and_charges

        if side_clean == "BUY":
            # If required capital exceeds available cash, step down quantity
            if required_capital > available_cash:
                max_cash_qty = int(available_cash / (entry_price * 1.002))  # buffer for taxes
                qty = min(qty, max_cash_qty)

            if qty <= 0:
                return self._invalid_result(
                    f"Insufficient funds: Capital required exceeds available cash INR {available_cash:,.2f}.",
                    entry_price, stop_loss_price, target_price
                )

            # Recalculate cost with final qty
            trade_cost = self.cost_model.calculate_cost(side_clean, entry_price, qty)
            required_capital = abs(trade_cost.net_cash_impact)

        # Expected Profit & Loss in INR
        reward_per_share = abs(target_price - entry_price)
        max_loss_inr = round(qty * risk_per_share + trade_cost.total_taxes_and_charges, 2)
        expected_profit_inr = round(qty * reward_per_share - trade_cost.total_taxes_and_charges, 2)
        rr_ratio = round(reward_per_share / risk_per_share, 2)

        return SizingResult(
            is_valid=True,
            quantity=qty,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            investment_amount=investment_amount,
            risk_budget=round(risk_budget, 2),
            risk_per_share=round(risk_per_share, 2),
            risk_based_quantity=risk_based_qty,
            budget_based_quantity=budget_based_qty,
            total_capital_required=round(required_capital, 2),
            estimated_costs=round(trade_cost.total_taxes_and_charges, 2),
            max_loss_inr=max_loss_inr,
            expected_profit_inr=expected_profit_inr,
            risk_to_reward_ratio=rr_ratio,
            error_message=None,
        )

    def _invalid_result(
        self,
        err_msg: str,
        entry: float,
        sl: float,
        target: float,
    ) -> SizingResult:
        return SizingResult(
            is_valid=False,
            quantity=0,
            entry_price=entry,
            stop_loss_price=sl,
            target_price=target,
            investment_amount=0.0,
            risk_budget=0.0,
            risk_per_share=0.0,
            risk_based_quantity=0,
            budget_based_quantity=0,
            total_capital_required=0.0,
            estimated_costs=0.0,
            max_loss_inr=0.0,
            expected_profit_inr=0.0,
            risk_to_reward_ratio=0.0,
            error_message=err_msg,
        )
