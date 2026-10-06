import os
import sys
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finrl_adapter import (
    FinRLBaseStrategy,
    StrategyConfig,
    StrategyResult,
    compute_portfolio_allocation,
    validate_market_data,
)


class DummyIndianStockStrategy(FinRLBaseStrategy):
    """
    A minimal custom strategy implementing FinRL-Trading's strategy abstraction.
    Allocates fixed target weights across top selected Indian equities.
    """

    def generate_weights(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str] = None
    ) -> StrategyResult:
        # Validate data against FinRL contract
        validate_market_data(data)

        prices_df = data["prices"]
        symbols = prices_df["symbol"].unique().tolist()

        # Allocate synthetic target weights (e.g. 20% RELIANCE, 15% TCS, 10% INFY)
        base_weights = {
            "RELIANCE": 0.20,
            "TCS": 0.15,
            "INFY": 0.10,
        }

        weights_list = []
        for sym in symbols:
            w = base_weights.get(sym, 0.05)
            weights_list.append({"symbol": sym, "weight": w})

        weights_df = pd.DataFrame(weights_list)

        return StrategyResult(
            strategy_name=self.config.name,
            weights=weights_df,
            metadata={"target_date": target_date or "latest", "num_assets": len(symbols)}
        )


def generate_synthetic_data() -> Dict[str, pd.DataFrame]:
    """Generates synthetic multi-asset Indian OHLCV price series."""
    dates = pd.date_range("2026-01-01", periods=10, freq="B")
    tickers = ["RELIANCE", "TCS", "INFY"]

    rows = []
    np.random.seed(42)
    for tic in tickers:
        base_price = 2500.0 if tic == "RELIANCE" else (3500.0 if tic == "TCS" else 1500.0)
        for d in dates:
            change = np.random.normal(0, 10)
            close = base_price + change
            rows.append({
                "date": d.strftime("%Y-%m-%d"),
                "symbol": tic,
                "open": round(close - 5, 2),
                "high": round(close + 10, 2),
                "low": round(close - 10, 2),
                "close": round(close, 2),
                "volume": int(np.random.randint(50000, 200000)),
            })

    prices_df = pd.DataFrame(rows)
    return {"prices": prices_df}


def test_finrl_strategy_pipeline():
    print("=" * 60)
    print("Running FinRL-X Integration Smoke Test")
    print("=" * 60)

    # 1. Initialize custom strategy
    config = StrategyConfig(name="IndianEquityFinRLDemo", max_weight_per_stock=0.25)
    strategy = DummyIndianStockStrategy(config)
    print(f"[+] Strategy initialized: {strategy.config.name}")

    # 2. Generate and validate synthetic market data
    synthetic_data = generate_synthetic_data()
    print("[+] Synthetic dataset generated:")
    print(synthetic_data["prices"].head(6).to_string(index=False))

    # 3. Execute strategy weight generation
    result = strategy.generate_weights(synthetic_data, target_date="2026-01-15")
    print(f"\n[+] Strategy executed successfully. Result Type: {type(result).__name__}")
    print(f"[+] Strategy Name: {result.strategy_name}")
    print(f"[+] Metadata: {result.metadata}")
    print("\n[+] Raw Generated Weights:")
    print(result.weights.to_string(index=False))

    # Assertions
    assert isinstance(result, StrategyResult), "Result must be an instance of StrategyResult"
    assert "symbol" in result.weights.columns, "Weights must contain 'symbol' column"
    assert "weight" in result.weights.columns, "Weights must contain 'weight' column"

    # 4. Convert weights to final portfolio allocations (including Cash)
    allocations = compute_portfolio_allocation(result.weights)
    print("\n[+] Normalized Portfolio Allocation (Asset + Cash Breakdown):")
    for asset, weight in allocations.items():
        print(f"    - {asset:<10}: {weight * 100:>6.2f}% ({weight:.4f})")

    # Verify allocation sums to 1.0 (100%)
    total_allocation = sum(allocations.values())
    print(f"\n[+] Total Allocation Sum: {total_allocation:.4f} (100%)")
    assert abs(total_allocation - 1.0) < 1e-4, "Portfolio allocations must sum to 1.0 (100%)"

    print("\n" + "=" * 60)
    print("FINRL INTEGRATION TEST PASSED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    test_finrl_strategy_pipeline()
