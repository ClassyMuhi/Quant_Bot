"""
Decision Engine for Quant_Bot
Combines Technical Indicators with God's Eye Event Intelligence.
"""

from decision_engine.engine import DecisionEngine, TradeDecision
from decision_engine.scoring import compute_technical_score, evaluate_confluence
from decision_engine.signal_generator import MarketDataFetcher
from decision_engine.risk_rules import calculate_entry_sl_target
from decision_engine.explanation import generate_explanation

__all__ = [
    "DecisionEngine",
    "TradeDecision",
    "compute_technical_score",
    "evaluate_confluence",
    "MarketDataFetcher",
    "calculate_entry_sl_target",
    "generate_explanation",
]

