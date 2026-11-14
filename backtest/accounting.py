"""
Portfolio & Position Accounting for Quant_Bot Backtest Engine
Maintains cash ledger, asset positions, executed trade logs, and daily equity tracking.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd

from .cost_model import CostModel, TradeCost, ZeroCostModel


@dataclass
class Trade:
    """Record of an executed buy or sell transaction."""
    trade_id: int
    date: str
    symbol: str
    order_type: str        # 'BUY' or 'SELL'
    quantity: int
    base_price: float
    execution_price: float # Price after slippage
    gross_value: float     # quantity * execution_price
    taxes_and_fees: float  # Brokerage, STT, GST, etc.
    net_cash_flow: float   # Negative for BUY, Positive for SELL
    realized_pnl: float = 0.0


@dataclass
class Position:
    """Holding state for an individual asset."""
    symbol: str
    quantity: int = 0
    average_cost: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.quantity > 0

    def market_value(self, current_price: float) -> float:
        return self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        if self.quantity == 0:
            return 0.0
        return (current_price - self.average_cost) * self.quantity

    def update_on_buy(self, buy_qty: int, buy_price: float) -> None:
        """Updates weighted average cost and increases position."""
        if buy_qty <= 0:
            return
        total_cost = (self.quantity * self.average_cost) + (buy_qty * buy_price)
        self.quantity += buy_qty
        self.average_cost = total_cost / self.quantity

    def update_on_sell(self, sell_qty: int, sell_price: float) -> float:
        """Decreases position and returns realized PnL."""
        if sell_qty <= 0 or self.quantity <= 0:
            return 0.0
        executed_qty = min(sell_qty, self.quantity)
        realized_pnl = (sell_price - self.average_cost) * executed_qty
        self.quantity -= executed_qty
        if self.quantity == 0:
            self.average_cost = 0.0
        return realized_pnl


class PortfolioAccount:
    """
    Manages portfolio cash, open asset positions, and historical equity progression.
    Enforces solvency (cash balance cannot fall below zero).
    """

    def __init__(self, initial_cash: float = 1000000.0, cost_model: Optional[CostModel] = None):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.cost_model = cost_model or ZeroCostModel()
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_history: List[Dict[str, float]] = []
        self._next_trade_id = 1

    def get_position(self, symbol: str) -> Position:
        """Retrieve or create position object for a symbol."""
        sym = symbol.strip().upper()
        if sym not in self.positions:
            self.positions[sym] = Position(symbol=sym)
        return self.positions[sym]

    def get_realized_pnl(self) -> float:
        """Total cumulative realized profit/loss from all closed sell trades."""
        return sum(t.realized_pnl for t in self.trades if t.order_type == "SELL")

    def get_unrealized_pnl(self, current_prices: Dict[str, float]) -> float:
        """Total current mark-to-market unrealized profit/loss across all open holdings."""
        total = 0.0
        for sym, pos in self.positions.items():
            if pos.is_open and sym in current_prices:
                total += pos.unrealized_pnl(current_prices[sym])
        return total

    def get_invested_value(self, current_prices: Dict[str, float]) -> float:
        """Total current market value of all open positions."""
        total = 0.0
        for sym, pos in self.positions.items():
            if pos.is_open and sym in current_prices:
                total += pos.market_value(current_prices[sym])
        return total

    def get_total_equity(self, current_prices: Dict[str, float]) -> float:
        """Total portfolio net liquidation value (Cash + Open Holdings)."""
        return self.cash + self.get_invested_value(current_prices)

    def execute_order(
        self,
        date: str,
        symbol: str,
        order_type: str,
        quantity: int,
        price: float,
    ) -> Optional[Trade]:
        """
        Executes an order, calculates costs, updates cash and positions, and logs trade.
        Rejects buy orders if insufficient cash; truncates sell orders if quantity exceeds holdings.
        """
        otype = order_type.strip().upper()
        clean_symbol = symbol.strip().upper()
        pos = self.get_position(clean_symbol)

        if quantity <= 0 or price <= 0:
            return None

        # Sanitize sell quantity against available holdings
        if otype == "SELL":
            if pos.quantity <= 0:
                return None
            quantity = min(quantity, pos.quantity)

        # Compute transaction costs and effective execution price
        cost: TradeCost = self.cost_model.calculate_cost(
            order_type=otype,
            price=price,
            quantity=quantity,
        )

        # Check cash solvency for BUY
        if otype == "BUY":
            required_cash = cost.gross_value + cost.total_taxes_and_charges
            if required_cash > self.cash:
                # Calculate exact per-share cash needed (including effective price and statutory fees)
                per_share_cash_needed = (cost.gross_value + cost.total_taxes_and_charges) / float(quantity)
                affordable_qty = int(self.cash // per_share_cash_needed)
                if affordable_qty <= 0:
                    return None
                quantity = affordable_qty
                # Recompute cost with reduced quantity
                cost = self.cost_model.calculate_cost(
                    order_type=otype,
                    price=price,
                    quantity=quantity,
                )

        # Apply cash delta
        self.cash += cost.net_cash_impact
        # Prevent floating precision slight negatives
        if self.cash < 0 and abs(self.cash) < 1e-4:
            self.cash = 0.0

        # Update position
        realized_pnl = 0.0
        if otype == "BUY":
            pos.update_on_buy(buy_qty=quantity, buy_price=cost.effective_price)
        else:
            realized_pnl = pos.update_on_sell(sell_qty=quantity, sell_price=cost.effective_price)

        trade = Trade(
            trade_id=self._next_trade_id,
            date=date,
            symbol=clean_symbol,
            order_type=otype,
            quantity=quantity,
            base_price=cost.base_price,
            execution_price=cost.effective_price,
            gross_value=cost.gross_value,
            taxes_and_fees=cost.total_taxes_and_charges,
            net_cash_flow=cost.net_cash_impact,
            realized_pnl=round(realized_pnl, 2),
        )
        self._next_trade_id += 1
        self.trades.append(trade)
        return trade

    def record_daily_snapshot(self, date: str, current_prices: Dict[str, float]) -> Dict[str, float]:
        """Snapshots daily portfolio equity, cash, and holdings value."""
        invested = self.get_invested_value(current_prices)
        total_equity = self.cash + invested

        snapshot = {
            "date": date,
            "cash": round(self.cash, 2),
            "invested_value": round(invested, 2),
            "total_equity": round(total_equity, 2),
        }
        self.equity_history.append(snapshot)
        return snapshot

    def to_equity_dataframe(self) -> pd.DataFrame:
        """Returns the daily equity curve as a pandas DataFrame."""
        if not self.equity_history:
            return pd.DataFrame(columns=["date", "cash", "invested_value", "total_equity", "daily_return"])
        df = pd.DataFrame(self.equity_history)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(by="date").reset_index(drop=True)
        df["daily_return"] = df["total_equity"].pct_change().fillna(0.0)
        return df

    def to_trades_dataframe(self) -> pd.DataFrame:
        """Returns all executed trades as a pandas DataFrame."""
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.__dict__ for t in self.trades])
