"""
Event Classifier for God's Eye Market Intelligence
Classifies financial news events into Bullish, Bearish, or Neutral sentiment,
assigns importance scores (1-10) and confidence scores (0-1).
Implements transparent rule-based analysis with optional LLM integration.
"""

from __future__ import annotations
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Indian financial market bullish lexicon
BULLISH_KEYWORDS = [
    r"\bprofit surges?\b", r"\bprofit jumps?\b", r"\bnet profit up\b", r"\brevenue up\b",
    r"\bearnings beat\b", r"\bresults beat\b", r"\bq[1-4] profit\b", r"\bupgraded?\b",
    r"\bdeal win\b", r"\border win\b", r"\bcontract awarded\b", r"\bdividend declared\b",
    r"\bbonus shares?\b", r"\bstock split\b", r"\bexpansion\b", r"\btarget raised\b",
    r"\bbuy rating\b", r"\boutperform\b", r"\brecord revenue\b", r"\brecord high\b",
    r"\brate cut\b", r"\brural demand recovery\b", r"\bmargin expansion\b", r"\bfii inflows?\b",
    r"\bgrowth accelerates?\b", r"\bpositive outlook\b", r"\bstrong guidance\b",
]

# Indian financial market bearish lexicon
BEARISH_KEYWORDS = [
    r"\bloss widens?\b", r"\bprofit slumps?\b", r"\bprofit drops?\b", r"\bnet loss\b",
    r"\bearnings miss\b", r"\bresults miss\b", r"\bdowngraded?\b", r"\bpenalty\b",
    r"\bprobe\b", r"\binvestigation\b", r"\bsebi notice\b", r"\bdefault\b",
    r"\bfraud\b", r"\blending cut\b", r"\btarget cut\b", r"\btarget slashed\b",
    r"\bsell rating\b", r"\bunderperform\b", r"\brate hike\b", r"\bmargin compression\b",
    r"\bfii outflows?\b", r"\bloss of contract\b", r"\blayoffs?\b", r"\bweak guidance\b",
    r"\bslump\b", r"\bcurbs?\b", r"\btariff hike\b", r"\bdecline\b",
]

# High-impact corporate/macro event indicators (importance booster)
HIGH_IMPORTANCE_PATTERNS = [
    (r"\brbi\b|\brepo rate\b|\bmonetary policy\b", 9),
    (r"\bq[1-4] results?\b|\bearnings\b|\bquarterly profit\b", 8),
    (r"\bsebi\b|\binvestigation\b|\braid\b|\bprobe\b", 8),
    (r"\bmerger\b|\bacquisition\b|\btakeover\b", 7),
    (r"\border win\b|\bmulti-year deal\b|\bcrore contract\b", 7),
    (r"\bdividend\b|\bbonus\b|\bbuyback\b", 6),
    (r"\btarget price\b|\bbuy rating\b|\bsell rating\b", 5),
]


class EventClassifier:
    """
    Classifies market events into standardized sentiment, importance, and confidence.
    """

    def __init__(self, use_llm_if_available: bool = True):
        self.use_llm = use_llm_if_available
        self._llm_client = None
        self._init_llm_client()

    def _init_llm_client(self) -> None:
        """Initializes LLM client only if API key is present in environment."""
        if not self.use_llm:
            return
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            try:
                # Basic check if google generative ai is available
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._llm_client = genai.GenerativeModel("gemini-1.5-flash")
                logger.info("God's Eye: Gemini LLM event classifier enabled.")
            except ImportError:
                logger.info("God's Eye: google-generativeai not installed; using rule-based classification.")
            except Exception as e:
                logger.warning(f"God's Eye: Failed to initialize Gemini LLM client: {e}")

    def _rule_based_classify(self, text: str) -> Tuple[str, int, float]:
        """
        Rule-based NLP classifier using financial lexicon and regex pattern weights.
        Returns: (sentiment, importance, confidence)
        """
        text_lower = text.lower()

        bullish_matches = 0
        for pat in BULLISH_KEYWORDS:
            if re.search(pat, text_lower):
                bullish_matches += 1

        bearish_matches = 0
        for pat in BEARISH_KEYWORDS:
            if re.search(pat, text_lower):
                bearish_matches += 1

        # Sentiment determination
        if bullish_matches > bearish_matches:
            sentiment = "BULLISH"
            diff = bullish_matches - bearish_matches
            confidence = min(0.95, 0.60 + (diff * 0.10))
        elif bearish_matches > bullish_matches:
            sentiment = "BEARISH"
            diff = bearish_matches - bullish_matches
            confidence = min(0.95, 0.60 + (diff * 0.10))
        else:
            sentiment = "NEUTRAL"
            confidence = 0.50 if (bullish_matches == 0 and bearish_matches == 0) else 0.40  # Ambiguous conflict

        # Importance calculation (1-10)
        base_importance = 4
        for pat, score in HIGH_IMPORTANCE_PATTERNS:
            if re.search(pat, text_lower):
                if score > base_importance:
                    base_importance = score

        # Adjust importance with match density
        total_signals = bullish_matches + bearish_matches
        importance = min(10, base_importance + min(2, total_signals))

        return sentiment, int(importance), round(float(confidence), 2)

    def classify_event(
        self,
        title: str,
        description: str = "",
        affected_symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Classifies an event and produces structured event metadata.
        """
        full_text = f"{title}. {description}".strip()
        sentiment, importance, confidence = self._rule_based_classify(full_text)

        # Boost confidence slightly if specific symbols were detected
        if affected_symbols and len(affected_symbols) > 0 and sentiment != "NEUTRAL":
            confidence = min(0.95, round(confidence + 0.05, 2))

        return {
            "sentiment": sentiment,
            "importance": importance,
            "confidence": confidence,
        }

    def classify_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Classifies a single normalized event dictionary and returns the enriched event."""
        res = self.classify_event(
            title=event.get("title", ""),
            description=event.get("description", ""),
            affected_symbols=event.get("affected_symbols", []),
        )
        merged = dict(event)
        merged["sentiment"] = res["sentiment"]
        merged["importance"] = res["importance"]
        merged["confidence"] = res["confidence"]
        return merged

    def classify_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Batch classifies a list of events."""
        return [self.classify_single_event(e) for e in events]
