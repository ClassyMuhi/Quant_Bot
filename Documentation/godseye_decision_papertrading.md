# Quant_Bot — God's Eye, Decision Engine & Paper Trading System

## Executive Overview

Quant_Bot has been upgraded with three interconnected, production-ready modules designed specifically for Indian National Stock Exchange (NSE) equities:
1. **God's Eye — Market Intelligence:** Real-time collection, entity extraction, sentiment analysis, and Medallion persistence of Indian financial news.
2. **Decision Engine:** Transparent rule-based confluence engine combining Gold-layer technical indicators with news intelligence to produce actionable recommendations with strict risk boundaries.
3. **Paper Trading Terminal & Broker Adapter:** Minimalist dark-zinc trading workstation featuring dual-constraint risk position sizing, Indian statutory transaction cost modeling, local ledger persistence, and ambiguous candle monitoring.

---

## 1. God's Eye — Market Intelligence

### 1.1 Purpose
God's Eye provides continuous market awareness by capturing financial news, earnings announcements, macroeconomic data, and regulatory releases affecting Indian markets.

### 1.2 Data Collection Sources
The system monitors reliable, high-integrity RSS feeds:
- **Economic Times:** Markets and Stocks feeds
- **Moneycontrol:** Market reports and top news feeds
- **Livemint:** Markets feed
- **Reserve Bank of India (RBI):** Official press releases and monetary policy notifications

### 1.3 Entity Extraction & Sector Mapping
Unstructured headlines and descriptions are mapped to NSE equities and sectors:
- **Company Alias Mapping:** Recognizes informal and corporate variations (e.g., "RIL" or "Reliance Industries" $\to$ `RELIANCE`, "State Bank of India" $\to$ `SBIN`, "HUL" $\to$ `HINDUNILVR`).
- **Sector Themes:** Assigns sector classifications such as Financial Services, Information Technology, Energy, Automobile, Consumer Goods, Metals, Telecommunications, and Macro & Policy.
- **Deduplication:** Uses Jaccard token set similarity to detect and collapse syndicated or repetitive headlines across news sources.

### 1.4 Sentiment, Importance & Confidence Scoring
- **Sentiment:** Classified as `BULLISH`, `BEARISH`, or `NEUTRAL` using a curated Indian financial market lexicon (earnings surges, order wins, deal wins, dividend declarations vs profit drops, SEBI probes, penalties, rating cuts).
- **Importance Score (1–10):** High-impact corporate/macro catalysts (RBI repo rate decisions, quarterly earnings, SEBI investigations) receive top priority.
- **Confidence Score (0–1):** Derived from keyword density and matched ticker specificity.

### 1.5 Medallion Storage Architecture
- **Bronze (`data/news/bronze/`):** Preserves immutable raw JSON news payloads.
- **Silver (`data/news/silver/events.parquet`):** Structured, deduplicated events table written safely using DuckDB.
- **Gold (`data/news/gold/news_features.parquet`):** Symbol-level daily aggregate features (sentiment score $[-1, +1]$, event count, max importance, confidence-weighted impact).

### 1.6 Strict Zero Look-Ahead Bias
During historical backtesting or decision playback, historical event queries enforce $T_{\text{published}} \le T_{\text{decision}}$, preventing future news leakage into trading signals.

---

## 2. Decision Engine

### 2.1 Inputs
The decision engine synthesizes inputs across multiple quantitative dimensions:
- **RSI (14-day):** Overbought (>70), Oversold (<30), and momentum zones.
- **Moving Averages:** Trend alignment (SMA 20 vs SMA 50).
- **MACD:** MACD line vs Signal line crossovers.
- **Momentum:** 20-day return.
- **Volatility:** 20-day annualized volatility / ATR.
- **God's Eye Sentiment:** Event sentiment score $[-1, +1]$, importance, and confidence.

### 2.2 Core Governance Rules
1. **News Cannot Independently Trigger Trades:** If technical indicators are neutral ($|S_{\text{tech}}| < 0.20$), the recommendation is strictly `HOLD`, even under extreme positive or negative news.
2. **Conflicting Signal Dampening:** If technical indicators and news sentiment point in opposite directions (e.g., Bullish Technicals vs Bearish News), overall confidence is penalized by 50% and the combined score is dampened.
3. **Concordance Conviction Boost:** When technicals and news align (Bullish + Bullish or Bearish + Bearish), conviction is boosted up to 95%.
4. **Stale Data Guard:** Missing or stale market data automatically forces a `HOLD`.
5. **Threshold Filter:** Decisions require a minimum confidence threshold ($\ge 50\%$) to qualify as actionable recommendations.

### 2.3 Dynamic Risk Boundaries & Explanations
For actionable `BUY` or `SELL` decisions, the engine computes:
- **Suggested Entry:** Latest available market quote.
- **Suggested Stop-Loss:** Calculated dynamically using ATR/volatility distance ($1.5 \times \text{ATR}$).
- **Suggested Target Price:** Scaled to enforce a minimum 1:2 risk-to-reward ratio ($3.0 \times \text{ATR}$).
- **Human-Readable Rationale:** Transparent breakdown explaining the technical posture, news impact, and risk boundaries.

---

## 3. Paper Trading System & Hallmark UI

### 3.1 Dual-Constraint Position Sizing
Quantity is sized conservatively using both the capital investment budget and the risk budget:
$$\text{Risk Budget} = \text{Investment Amount} \times \frac{\text{Risk } \%}{100}$$
$$\text{Risk Per Share} = |\text{Entry Price} - \text{Stop-Loss Price}|$$
$$\text{Quantity} = \min\left( \left\lfloor \frac{\text{Risk Budget}}{\text{Risk Per Share}} \right\rfloor, \left\lfloor \frac{\text{Investment Amount}}{\text{Entry Price}} \right\rfloor \right)$$

Integer share quantities are strictly enforced.

### 3.2 Indian Statutory Friction Modeling
Execution and position sizing incorporate the full Indian equity cost schedule:
- Brokerage: 0.03% or ₹20 cap per order
- STT (Securities Transaction Tax): 0.1% on delivery
- Exchange Charges: 0.00325%
- GST: 18% on (Brokerage + Exchange Charges)
- Stamp Duty: 0.015% on BUY
- SEBI Turnover Charges: ₹10 per crore

### 3.3 Pre-Trade Risk Validations
The order manager rejects invalid submissions:
- Stop-loss on the wrong side of entry (for BUY: $\text{SL} \ge \text{Entry}$; for SELL: $\text{SL} \le \text{Entry}$).
- Target on the wrong side of entry.
- Zero or negative share quantities.
- Insufficient cash funds.
- **Naked Short Selling Guard:** SELL orders require pre-existing holdings in cash delivery mode.
- Duplicate order submission within a short time window.

### 3.4 Persistent Ledger
Paper account state is persisted in `data/paper_trading/paper_account.json`, tracking:
- Cash balance (default ₹10,00,000)
- Active holdings and real-time unrealized P&L
- Realized P&L
- Complete audit trail of executed orders

### 3.5 Position Monitoring & Ambiguous Candle Handling
The order monitor tracks open positions against market bars:
- **Ambiguous Candle Detection:** If a single candle's Low $\le$ Stop-Loss AND High $\ge$ Target Price, both exit boundaries were breached. The system flags this ambiguity and prudently assumes the adverse Stop-Loss was triggered first.

### 3.6 Hallmark Minimalist Streamlit Interface (Zero-PyArrow Architecture)
Designed with a dark zinc aesthetic (`#09090b`):
- **Zero PyArrow Dependency:** `st.dataframe` and `st.table` natively trigger `pyarrow` C++ DLL imports that are blocked by Windows Application Control / AppLocker policies. Quant_Bot replaces these with `render_zinc_table`, an HTML/CSS table generator with monospace metrics, sentiment pills, and responsive overflow wrappers, eliminating all `pyarrow` execution hurdles.
- **Paper Trading Terminal:** Interactive order configuration, live reactive sizing metrics, execution submission, active mode badge (`[LOCAL PAPER SIMULATION]`), open positions table, and trade ledger.
- **Decision Engine View:** Multi-factor analysis, conviction gauges, and entry/SL/TP setup cards.
- **God's Eye Feed:** Real-time news table with sentiment pills and manual ingestion trigger.
- **Backtest Lab:** Integrated simulation runner comparing strategy metrics against Buy & Hold.

---

## 4. Verification and Test Results
All modules are covered by unit and integration tests under `tests/`:
- `tests/test_godseye.py`: RSS parsing, entity extraction, deduplication, sentiment classification, zero look-ahead bias.
- `tests/test_decision_engine.py`: Multi-factor scoring, news-only guardrails, conflict dampening, invariant checks.
- `tests/test_paper_trading.py`: Dual-constraint sizing, integer math, cash solvency, wrong-side rejections, naked short guard, persistence, ambiguous candles.

**Suite Status:** 73 passed in 2.05s (`python -m pytest -v`).

