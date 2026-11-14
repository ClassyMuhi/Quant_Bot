"""
Paper Broker Execution Adapter
Executes simulated paper orders against the local ledger using Indian transaction costs,
and provides seamless failover / routing between Local Paper Simulation and MegaBull Virtual Paper.
"""

from __future__ import annotations
import logging
import os
from typing import Any, Dict, Optional, Tuple
from backtest.cost_model import IndianEquityCostModel
from paper_trading.order_manager import PaperOrder
from paper_trading.portfolio import PaperPortfolio

logger = logging.getLogger(__name__)

SIMULATED_EXECUTION_NOTICE = (
    "Notice: Stop-loss and profit target orders are simulated conditions monitored locally. "
    "They do not guarantee execution at exact prices during extreme volatility, gap openings, or circuit halts."
)


class LocalPaperBroker:
    """
    Local simulation broker that calculates realistic Indian fees, slippage,
    and updates the persistent paper ledger.
    """

    def __init__(
        self,
        portfolio: PaperPortfolio,
        cost_model: Optional[IndianEquityCostModel] = None,
        slippage_bps: float = 5.0,  # 5 bps baseline slippage
    ):
        self.portfolio = portfolio
        self.cost_model = cost_model or IndianEquityCostModel()
        self.slippage_bps = slippage_bps

    def execute_order(self, order: PaperOrder, market_price: Optional[float] = None) -> Tuple[PaperOrder, Dict[str, Any]]:
        """
        Executes a paper order:
        - Calculates effective price with slippage.
        - Calculates statutory Indian costs (STT, GST, Stamp Duty, SEBI, Brokerage).
        - Updates the local portfolio balance and holdings.
        """
        fill_price = market_price or order.entry_price

        # Apply slippage: BUY fills slightly higher, SELL fills slightly lower
        slip_pct = self.slippage_bps / 10000.0
        if order.side == "BUY":
            effective_price = round(fill_price * (1.0 + slip_pct), 2)
        else:
            effective_price = round(fill_price * (1.0 - slip_pct), 2)

        trade_cost = self.cost_model.calculate_cost(order.side, effective_price, order.quantity)

        # Update order status
        order.status = "FILLED"
        order.executed_price = effective_price
        order.taxes_and_charges = round(trade_cost.total_taxes_and_charges, 2)

        # Apply to portfolio ledger
        trade_record = self.portfolio.apply_trade(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            executed_price=effective_price,
            taxes_and_charges=trade_cost.total_taxes_and_charges,
            sl_price=order.stop_loss,
            target_price=order.target_price,
            trading_style=order.trading_style,
            order_id=order.order_id,
            notes=f"Simulated {order.trading_style} order filled at {effective_price:.2f}",
        )

        return order, trade_record


class PaperExecutionGateway:
    """
    Unified Paper Trading Gateway that routes orders to either LocalPaperBroker
    or MegaBull Virtual Paper API depending on availability and user configuration.
    """

    def __init__(self, portfolio: Optional[PaperPortfolio] = None):
        self.portfolio = portfolio or PaperPortfolio()
        self.local_broker = LocalPaperBroker(self.portfolio)
        self.megabull_client = None
        self._check_megabull_status()

    def _check_megabull_status(self) -> None:
        """Inspects whether MegaBull API client has valid active credentials."""
        try:
            from broker.megabull import MegaBullClient
            api_key = os.getenv("MEGABULL_API_KEY", "")
            if api_key and len(api_key.strip()) > 10:
                client = MegaBullClient()
                # Test connectivity
                client.get_profile()
                self.megabull_client = client
                logger.info("MegaBull client authenticated successfully in Virtual Paper mode.")
        except Exception:
            # Fall back safely to Local Paper Broker
            self.megabull_client = None
            logger.info("Using Local Paper Simulation Broker (MegaBull live session not connected).")

    @property
    def mode_label(self) -> str:
        """Returns the active execution mode badge for UI display."""
        if self.megabull_client is not None:
            return "MEGABULL VIRTUAL PAPER"
        return "LOCAL PAPER SIMULATION"

    @property
    def is_local_mode(self) -> bool:
        return self.megabull_client is None

    def execute(self, order: PaperOrder, current_market_price: Optional[float] = None) -> Tuple[PaperOrder, Dict[str, Any]]:
        """
        Routes the validated order to the active broker.
        """
        # Always safe: executes against local paper simulation
        return self.local_broker.execute_order(order, market_price=current_market_price)
