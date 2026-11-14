"""
Risk Rules and Price Target Calculations for Decision Engine
Calculates dynamically sized Stop-Loss and Target levels using ATR / Volatility,
enforcing strict financial invariants.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def calculate_entry_sl_target(
    decision: str,
    current_price: float,
    indicators: Dict[str, Any],
    atr_multiplier_sl: float = 1.5,
    risk_reward_ratio: float = 2.0,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[str]]:
    """
    Calculates suggested entry, stop-loss, and target prices.
    Returns:
        (entry_price, stop_loss_price, target_price, validation_error)
    """
    if decision == "HOLD":
        return None, None, None, None

    if current_price <= 0:
        return None, None, None, f"Invalid current price: {current_price}"

    # Use ATR from indicators if available, else derive from 20d volatility
    vol20 = float(indicators.get("volatility_20d", 0.02))
    # Daily estimated volatility dollar range
    daily_vol_range = current_price * (vol20 / (252 ** 0.5) if vol20 > 0.1 else max(0.015, vol20))

    sl_distance = max(daily_vol_range * atr_multiplier_sl, current_price * 0.015)
    tp_distance = sl_distance * risk_reward_ratio

    entry_price = round(current_price, 2)

    if decision == "BUY":
        stop_loss = round(entry_price - sl_distance, 2)
        target_price = round(entry_price + tp_distance, 2)

        # Invariant checks
        if stop_loss >= entry_price:
            return None, None, None, f"Validation failure: Stop-Loss ({stop_loss}) >= Entry ({entry_price}) for BUY"
        if target_price <= entry_price:
            return None, None, None, f"Validation failure: Target ({target_price}) <= Entry ({entry_price}) for BUY"

    elif decision == "SELL":
        stop_loss = round(entry_price + sl_distance, 2)
        target_price = round(entry_price - tp_distance, 2)

        # Invariant checks
        if stop_loss <= entry_price:
            return None, None, None, f"Validation failure: Stop-Loss ({stop_loss}) <= Entry ({entry_price}) for SELL"
        if target_price >= entry_price:
            return None, None, None, f"Validation failure: Target ({target_price}) >= Entry ({entry_price}) for SELL"
        if target_price <= 0:
            target_price = round(entry_price * 0.85, 2)

    else:
        return None, None, None, f"Unrecognized decision type: {decision}"

    return entry_price, stop_loss, target_price, None

