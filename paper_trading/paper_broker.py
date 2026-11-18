"""
Paper Broker Execution Adapter
Executes simulated paper orders against the local ledger using Indian transaction costs,
and provides seamless failover / routing between Local Paper Simulation and MegaBull Virtual Paper.
"""

from __future__ import annotations
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
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


# Pre-mapped tokens for standard NSE Universe on MegaBull
KNOWN_MEGABULL_TOKENS: Dict[str, str] = {
    "HDFCBANK": "341249",
    "ICICIBANK": "1270529",
    "SBIN": "779521",
    "TCS": "2953217",
    "INFY": "408065",
    "WIPRO": "969473",
    "RELIANCE": "738561",
    "ONGC": "633601",
    "TATAMOTORS": "884737",
    "TMPV": "884737",
    "MARUTI": "2815745",
    "ITC": "424961",
    "HINDUNILVR": "356865",
    "TATASTEEL": "895745",
    "LT": "2939649",
    "BHARTIARTL": "2714625",
}


class PaperExecutionGateway:
    """
    Unified Paper Trading Gateway that routes orders to either LocalPaperBroker
    or MegaBull Virtual Paper API depending on availability and user configuration.
    """

    def __init__(self, portfolio: Optional[PaperPortfolio] = None):
        self.portfolio = portfolio or PaperPortfolio()
        self.local_broker = LocalPaperBroker(self.portfolio)
        self.megabull_client = None
        self._token_cache: Dict[str, str] = dict(KNOWN_MEGABULL_TOKENS)
        self._check_megabull_status()

    def _check_megabull_status(self) -> None:
        """
        Inspects whether MegaBull API client has valid active credentials.
        Uses an absolute path for .env so it works regardless of Streamlit's
        working directory at startup.
        """
        # In unit test environments, operate in safe local mock mode
        if "PYTEST_CURRENT_TEST" in os.environ:
            self.megabull_client = None
            return

        try:
            from dotenv import load_dotenv
            # Resolve .env relative to this file, not the CWD (Streamlit changes CWD)
            _env_path = Path(__file__).resolve().parent.parent / ".env"
            load_dotenv(dotenv_path=_env_path, override=False)
            from broker.megabull import MegaBull
            api_key = os.getenv("MEGABULL_API_KEY", "")
            if not api_key or len(api_key.strip()) <= 10:
                logger.info("Using Local Paper Simulation Broker (MEGABULL_API_KEY not configured).")
                return
            client = MegaBull()
            client.get_user_profile()
            self.megabull_client = client
            logger.info("MegaBull client authenticated successfully in Virtual Paper mode.")
        except Exception as exc:
            # Log the actual reason so it's never silently swallowed again
            logger.warning(f"MegaBull connection failed ({type(exc).__name__}: {exc}). "
                           "Falling back to Local Paper Simulation Broker.")

    def _resolve_instrument_token(self, symbol: str) -> Optional[str]:
        """Resolves the MegaBull numeric instrument token for a given NSE ticker."""
        clean_sym = symbol.upper().replace(".NS", "").strip()
        if clean_sym in self._token_cache:
            return self._token_cache[clean_sym]

        if self.megabull_client is not None:
            try:
                inst_df = self.megabull_client.get_instruments(as_dataframe=True)
                match = inst_df[inst_df["tradingSymbol"] == clean_sym]
                if not match.empty:
                    token = str(match.iloc[0]["instrumentToken"])
                    self._token_cache[clean_sym] = token
                    return token
            except Exception as e:
                logger.warning(f"Error resolving token from master instrument list for {clean_sym}: {e}")

        return None

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
        Routes the validated order to the active broker:
        - When MegaBull is connected: Dispatches the order live to the MegaBull Virtual Paper API,
          synchronizing fills and execution IDs with the remote server.
        - Fallback: Executes against local paper simulation ledger.
        """
        if self.megabull_client is not None:
            token = self._resolve_instrument_token(order.symbol)
            if token:
                order_type_str = "LIMIT" if order.order_type == "LIMIT" else "MKT"
                effective_px = float(order.limit_price or order.entry_price or current_market_price or 100.0)
                duration_str = "CNC" if order.trading_style == "DELIVERY" else "MIS"

                payload = {
                    "instrumentToken": str(token),
                    "qty": int(order.quantity),
                    "type": order.side.upper(),
                    "duration": duration_str,
                    "orderType": order_type_str,
                    "price": effective_px,
                }

                try:
                    logger.info(f"Routing live order to MegaBull API: {order.side} {order.quantity} {order.symbol} @ ₹{effective_px:,.2f}")
                    mb_res = self.megabull_client.place_order(payload)
                    fill_px = float(mb_res.get("price") or effective_px)
                    mb_order_id = str(mb_res.get("id") or order.order_id)
                    logger.info(f"MegaBull Order Placed Successfully: Order #{mb_order_id} filled @ ₹{fill_px:,.2f}")

                    # Update order object with real MegaBull execution feedback
                    order.executed_price = fill_px
                    order.order_id = f"MB-{mb_order_id}"

                    # Also update local ledger to preserve audit log and P&L monitoring
                    _, trade_record = self.local_broker.execute_order(order, market_price=fill_px)
                    trade_record["megabull_id"] = mb_order_id
                    trade_record["notes"] = f"MegaBull API Order #{mb_order_id} filled @ ₹{fill_px:,.2f}"
                    return order, trade_record

                except Exception as exc:
                    logger.error(f"MegaBull order execution failed ({exc}). Falling back to local simulation.")

            else:
                logger.warning(f"Could not resolve MegaBull token for {order.symbol}. Executing locally.")

        # Local Paper Broker execution
        return self.local_broker.execute_order(order, market_price=current_market_price)

    def sync_portfolio_from_megabull(self) -> Dict[str, Any]:
        """
        Synchronizes the local PaperPortfolio ledger (cash balance and open positions)
        directly with the live MegaBull cloud account.
        """
        if self.megabull_client is None:
            return {"status": "error", "message": "MegaBull client not connected"}

        try:
            profile = self.megabull_client.get_user_profile()
            positions = self.megabull_client.get_positions()

            # Update cash balance from MegaBull's actual available funds
            live_cash = float(profile.get("virtualMoneyLeft", self.portfolio.cash))
            self.portfolio.cash = live_cash

            # Mirror active holdings
            new_holdings = {}
            if isinstance(positions, list):
                for p in positions:
                    sym = p.get("instrumentName", "").upper()
                    qty = int(p.get("qty", 0))
                    if qty > 0 and sym:
                        avg_p = float(p.get("priceAvg", 0.0))
                        dur = p.get("duration", "MIS")
                        trading_style = "INTRADAY" if dur == "MIS" else "DELIVERY"
                        new_holdings[sym] = {
                            "quantity": qty,
                            "avg_price": avg_p,
                            "current_price": avg_p,
                            "market_value": round(qty * avg_p, 2),
                            "unrealized_pnl": float(p.get("pl", 0.0)),
                            "trading_style": trading_style,
                            "sl_price": round(avg_p * 0.97, 2),
                            "target_price": round(avg_p * 1.06, 2),
                            "opened_at": datetime.now(timezone.utc).isoformat(),
                        }

            self.portfolio.holdings = new_holdings
            self.portfolio.save()
            logger.info("Successfully synced local portfolio with MegaBull: Cash ₹%.2f, %d positions", live_cash, len(new_holdings))
            return {
                "status": "success",
                "cash": live_cash,
                "positions_count": len(new_holdings),
                "profile": profile,
            }
        except Exception as e:
            logger.error("Failed to sync portfolio from MegaBull: %s", e)
            return {"status": "error", "message": str(e)}
