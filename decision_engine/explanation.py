"""
Explanation Generator for Decision Engine
Synthesizes transparent, human-readable explanations of trade decisions.
"""

from __future__ import annotations
from typing import Any, Dict, Optional


def generate_explanation(
    symbol: str,
    decision: str,
    scoring_result: Dict[str, Any],
    tech_components: Dict[str, Any],
    entry_price: Optional[float],
    stop_loss: Optional[float],
    target_price: Optional[float],
) -> str:
    """
    Produces a clear, professional narrative explaining why the decision was generated.
    """
    tech_sig = scoring_result.get("technical_signal", "NEUTRAL")
    event_sent = scoring_result.get("event_sentiment", "NEUTRAL")
    combined_score = scoring_result.get("combined_score", 0.0)
    confidence = scoring_result.get("confidence", 0.0)
    is_conflict = scoring_result.get("is_conflict", False)
    is_confluence = scoring_result.get("is_confluence", False)
    reason_rule = scoring_result.get("reason_rule", "")

    lines = []
    # 1. Headline summary
    if decision == "HOLD":
        lines.append(f"HOLD recommendation for {symbol} (Score: {combined_score:+.2f}, Confidence: {confidence:.0%}).")
    elif decision == "BUY":
        lines.append(f"BUY recommendation for {symbol} (Score: {combined_score:+.2f}, Confidence: {confidence:.0%}).")
    else:
        lines.append(f"SELL recommendation for {symbol} (Score: {combined_score:+.2f}, Confidence: {confidence:.0%}).")

    # 2. Rule explanation
    lines.append(f"Rationale: {reason_rule}")

    # 3. Technical Breakdown
    rsi_info = tech_components.get("rsi", {})
    trend_info = tech_components.get("trend", {})
    macd_info = tech_components.get("macd", {})

    tech_details = (
        f"Technicals ({tech_sig}): RSI={rsi_info.get('value', 0):.1f} ({rsi_info.get('signal', 'N/A')}), "
        f"Trend={trend_info.get('signal', 'N/A')} (SMA20={trend_info.get('sma20', 0):.1f} vs SMA50={trend_info.get('sma50', 0):.1f}), "
        f"MACD={macd_info.get('type', 'N/A')}."
    )
    lines.append(tech_details)

    # 4. Event Intelligence & Confluence / Conflict
    if is_conflict:
        lines.append(
            f"Event Context: CONFLICT DETECTED. Technicals are {tech_sig} while God's Eye intelligence is {event_sent}. "
            "Confidence penalised by 50% to prevent unhedged exposure."
        )
    elif is_confluence:
        lines.append(
            f"Event Context: CONFLUENCE CONFIRMED. Both Technicals and God's Eye event intelligence are aligned ({tech_sig}). "
            "High conviction setup."
        )
    else:
        lines.append(f"Event Context: God's Eye sentiment is {event_sent} (Event Score: {scoring_result.get('event_score', 0):+.2f}).")

    # 5. Execution parameters if actionable
    if decision in ("BUY", "SELL") and entry_price and stop_loss and target_price:
        rr = abs(target_price - entry_price) / abs(entry_price - stop_loss) if abs(entry_price - stop_loss) > 0 else 0
        lines.append(
            f"Setup Levels: Entry ~ INR {entry_price:,.2f} | Stop-Loss = INR {stop_loss:,.2f} | Target = INR {target_price:,.2f} (R:R {rr:.1f}:1)."
        )

    return " ".join(lines)

