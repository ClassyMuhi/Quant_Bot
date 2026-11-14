"""
Paper Trading Portfolio and Account Persistence
Maintains local paper account balance, holdings, realized/unrealized P&L,
and persistent ledger state in data/paper_trading/paper_account.json.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNT_FILE = Path("data/paper_trading/paper_account.json")
DEFAULT_INITIAL_CASH = 1_000_000.0  # 10 Lakhs INR


class PaperPortfolio:
    """
    Simulated local paper trading account ledger.
    """

    def __init__(self, account_file: Optional[Path] = None, initial_cash: float = DEFAULT_INITIAL_CASH):
        self.account_file = Path(account_file or DEFAULT_ACCOUNT_FILE)
        self.account_file.parent.mkdir(parents=True, exist_ok=True)
        self.initial_cash = initial_cash

        self.cash: float = initial_cash
        self.holdings: Dict[str, Dict[str, Any]] = {}
        self.realized_pnl: float = 0.0
        self.trades: List[Dict[str, Any]] = []
        self.pending_orders: List[Dict[str, Any]] = []

        self.load()

    def reset(self, initial_cash: Optional[float] = None) -> None:
        """Resets the paper account to a fresh state."""
        self.cash = initial_cash or self.initial_cash
        self.holdings = {}
        self.realized_pnl = 0.0
        self.trades = []
        self.pending_orders = []
        self.save()
        logger.info("Paper account reset with cash INR %s", f"{self.cash:,.2f}")

    def load(self) -> None:
        """Loads state from disk if exists, otherwise initializes fresh."""
        if not self.account_file.exists():
            self.save()
            return

        try:
            with open(self.account_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.cash = float(data.get("cash", self.initial_cash))
            self.holdings = data.get("holdings", {})
            self.realized_pnl = float(data.get("realized_pnl", 0.0))
            self.trades = data.get("trades", [])
            self.pending_orders = data.get("pending_orders", [])
            logger.info("Loaded paper account from %s (Cash: INR %s)", self.account_file, f"{self.cash:,.2f}")
        except Exception as e:
            logger.error("Failed to load paper account from %s: %s. Using default state.", self.account_file, e)
            self.save()

    def save(self) -> None:
        """Persists the account ledger to JSON."""
        state = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "cash": round(self.cash, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "holdings": self.holdings,
            "trades": self.trades,
            "pending_orders": self.pending_orders,
        }
        with open(self.account_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def update_market_prices(self, price_map: Dict[str, float]) -> None:
        """Updates current price and unrealized P&L for all open positions."""
        for sym, pos in self.holdings.items():
            if sym in price_map and price_map[sym] > 0:
                current_p = price_map[sym]
                qty = pos["quantity"]
                avg_p = pos["avg_price"]
                market_val = qty * current_p
                unrealized = (current_p - avg_p) * qty
                pos["current_price"] = round(current_p, 2)
                pos["market_value"] = round(market_val, 2)
                pos["unrealized_pnl"] = round(unrealized, 2)
        self.save()

    def apply_trade(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        quantity: int,
        executed_price: float,
        taxes_and_charges: float,
        sl_price: Optional[float] = None,
        target_price: Optional[float] = None,
        trading_style: str = "DELIVERY",
        order_id: Optional[str] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Executes a trade against the paper account:
        - Updates cash and holdings.
        - Computes realized PnL on SELL.
        - Records trade history.
        """
        side_clean = side.upper()
        now_iso = datetime.now(timezone.utc).isoformat()
        gross_value = quantity * executed_price

        trade_pnl = 0.0

        if side_clean == "BUY":
            total_cash_outlay = gross_value + taxes_and_charges
            self.cash -= total_cash_outlay

            if symbol in self.holdings:
                curr_qty = self.holdings[symbol]["quantity"]
                curr_avg = self.holdings[symbol]["avg_price"]
                new_qty = curr_qty + quantity
                new_avg = ((curr_qty * curr_avg) + gross_value) / new_qty
                self.holdings[symbol]["quantity"] = new_qty
                self.holdings[symbol]["avg_price"] = round(new_avg, 2)
                self.holdings[symbol]["current_price"] = round(executed_price, 2)
                self.holdings[symbol]["market_value"] = round(new_qty * executed_price, 2)
                self.holdings[symbol]["unrealized_pnl"] = round((executed_price - new_avg) * new_qty, 2)
                if sl_price:
                    self.holdings[symbol]["sl_price"] = sl_price
                if target_price:
                    self.holdings[symbol]["target_price"] = target_price
            else:
                self.holdings[symbol] = {
                    "quantity": quantity,
                    "avg_price": round(executed_price, 2),
                    "current_price": round(executed_price, 2),
                    "market_value": round(gross_value, 2),
                    "unrealized_pnl": 0.0,
                    "sl_price": sl_price,
                    "target_price": target_price,
                    "trading_style": trading_style,
                    "opened_at": now_iso,
                }

        elif side_clean == "SELL":
            total_cash_inflow = gross_value - taxes_and_charges
            self.cash += total_cash_inflow

            pos = self.holdings[symbol]
            curr_qty = pos["quantity"]
            avg_p = pos["avg_price"]

            # Realized P&L = (Sell Gross - Buy Gross Basis) - taxes
            basis_cost = quantity * avg_p
            trade_pnl = round((gross_value - basis_cost) - taxes_and_charges, 2)
            self.realized_pnl += trade_pnl

            remaining_qty = curr_qty - quantity
            if remaining_qty <= 0:
                del self.holdings[symbol]
            else:
                pos["quantity"] = remaining_qty
                pos["market_value"] = round(remaining_qty * executed_price, 2)
                pos["unrealized_pnl"] = round((executed_price - avg_p) * remaining_qty, 2)

        record = {
            "order_id": order_id or f"ORD_{int(datetime.now(timezone.utc).timestamp()*1000)}",
            "timestamp": now_iso,
            "symbol": symbol,
            "side": side_clean,
            "quantity": quantity,
            "price": round(executed_price, 2),
            "gross_value": round(gross_value, 2),
            "taxes_and_charges": round(taxes_and_charges, 2),
            "realized_pnl": trade_pnl,
            "trading_style": trading_style,
            "notes": notes,
        }
        self.trades.append(record)
        self.save()
        return record

    def get_summary(self) -> Dict[str, Any]:
        """Calculates current portfolio summary and equity."""
        total_market_val = sum(p["quantity"] * p.get("current_price", p["avg_price"]) for p in self.holdings.values())
        total_unrealized = sum(p.get("unrealized_pnl", 0.0) for p in self.holdings.values())
        total_equity = self.cash + total_market_val

        return {
            "total_equity": round(total_equity, 2),
            "cash": round(self.cash, 2),
            "invested_value": round(total_market_val, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "total_pnl": round(self.realized_pnl + total_unrealized, 2),
            "open_positions_count": len(self.holdings),
            "total_trades_count": len(self.trades),
        }

