"""
Top-Level Decision Engine Coordinator
Orchestrates technical signal extraction, God's Eye intelligence,
multi-factor scoring, dynamic risk boundary calculations, and explanation synthesis.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from decision_engine.signal_generator import MarketDataFetcher
from decision_engine.scoring import compute_technical_score, evaluate_confluence
from decision_engine.risk_rules import calculate_entry_sl_target
from decision_engine.explanation import generate_explanation
from godseye.intelligence import GodsEyeIntelligence

logger = logging.getLogger(__name__)


@dataclass
class TradeDecision:
    """Standardized decision payload produced by DecisionEngine."""
    selected_stock: str
    decision: str  # BUY, SELL, HOLD
    technical_signal: str  # BULLISH, BEARISH, NEUTRAL
    event_sentiment: str  # BULLISH, BEARISH, NEUTRAL
    combined_score: float  # [-1.0, 1.0]
    confidence: float  # [0.0, 1.0]
    explanation: str
    timestamp: str
    suggested_entry_price: Optional[float] = None
    suggested_stop_loss: Optional[float] = None
    suggested_target_price: Optional[float] = None
    is_actionable: bool = False
    warning: Optional[str] = None
    raw_indicators: Optional[Dict[str, Any]] = None
    recent_events: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DecisionEngine:
    """
    Combines Gold market indicators with God's Eye event intelligence.
    """

    def __init__(
        self,
        data_fetcher: Optional[MarketDataFetcher] = None,
        godseye: Optional[GodsEyeIntelligence] = None,
        min_confidence_threshold: float = 0.50,
    ):
        self.fetcher = data_fetcher or MarketDataFetcher()
        self.godseye = godseye or GodsEyeIntelligence()
        self.min_confidence = min_confidence_threshold

    def evaluate(
        self,
        symbol: str,
        as_of: Optional[datetime | str] = None,
        override_indicators: Optional[Dict[str, Any]] = None,
        current_price: Optional[float] = None,
    ) -> TradeDecision:
        """
        Evaluates a stock and generates a transparent trading decision.
        Enforces:
        - Stale/missing data guard -> HOLD
        - News cannot trigger trade alone -> HOLD
        - Conflicting signals penalize confidence
        - Explicit distinction between recommendation and executable order
        """
        symbol_clean = symbol.upper().replace(".NS", "")
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Fetch Technical Indicators
        if override_indicators is not None:
            indicators = override_indicators
            err = None
        else:
            indicators, err = self.fetcher.get_latest_indicators(symbol_clean, as_of=as_of)

        if err or not indicators:
            return TradeDecision(
                selected_stock=symbol_clean,
                decision="HOLD",
                technical_signal="NEUTRAL",
                event_sentiment="NEUTRAL",
                combined_score=0.0,
                confidence=0.0,
                explanation=f"Cannot generate decision for {symbol_clean}: {err or 'Missing data'}",
                timestamp=now_iso,
                warning=err,
            )

        # 2. Fetch God's Eye Sentiment (Strict Zero Look-Ahead Bias)
        news_sentiment = self.godseye.get_symbol_sentiment(symbol_clean, as_of=as_of)

        # 3. Compute Technical Multi-Factor Score
        tech_score, tech_conf, tech_components = compute_technical_score(indicators)

        # 4. Evaluate Confluence & Apply Invariant Rules
        scoring = evaluate_confluence(
            technical_score=tech_score,
            technical_confidence=tech_conf,
            news_sentiment=news_sentiment,
            min_confidence_threshold=self.min_confidence,
        )

        decision = scoring["decision"]

        # 5. Price and Risk Levels
        exec_price = current_price or float(indicators.get("close", 0.0))
        entry_price, stop_loss, target_price, risk_err = calculate_entry_sl_target(
            decision=decision,
            current_price=exec_price,
            indicators=indicators,
        )

        if risk_err:
            decision = "HOLD"
            scoring["reason_rule"] += f" (Risk check failed: {risk_err})"

        # 6. Synthesize Professional Explanation
        explanation = generate_explanation(
            symbol=symbol_clean,
            decision=decision,
            scoring_result=scoring,
            tech_components=tech_components,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
        )

        is_actionable = decision in ("BUY", "SELL") and scoring["confidence"] >= self.min_confidence

        return TradeDecision(
            selected_stock=symbol_clean,
            decision=decision,
            technical_signal=scoring["technical_signal"],
            event_sentiment=scoring["event_sentiment"],
            combined_score=scoring["combined_score"],
            confidence=scoring["confidence"],
            explanation=explanation,
            timestamp=now_iso,
            suggested_entry_price=entry_price,
            suggested_stop_loss=stop_loss,
            suggested_target_price=target_price,
            is_actionable=is_actionable,
            warning=risk_err,
            raw_indicators=indicators,
            recent_events=news_sentiment.get("latest_events", []),
        )

