"""
Phase 2 End-to-End Pipeline Integration Test.
Ingests historical Indian equity data for a sample universe, validates, cleans,
maps canonical symbols, and transforms into the FinRL-X data contract.
"""

import sys
from pathlib import Path
import pandas as pd

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from india_data import (
    load_or_download,
    to_finrl_format,
    save_processed_data,
    validate_market_dataframe,
    MegaBullSymbolMapper,
)
from finrl_adapter.data_contract import validate_market_data


def run_phase2_pipeline():
    print("=" * 60)
    print("PHASE 2 - INDIA MARKET DATA ENGINE PIPELINE")
    print("=" * 60)

    # 1. Select Sample Universe (Small Sample: RELIANCE, TCS, INFY)
    sample_symbols = ["RELIANCE", "TCS", "INFY"]
    print(f"\n[+] Ingesting data for sample universe: {sample_symbols}")

    data_map = {}
    for sym in sample_symbols:
        print(f"    - Fetching / Loading: {sym} (Yahoo: {sym}.NS, Period: 5y)...")
        df = load_or_download(sym, period="5y", force_refresh=False)
        data_map[sym] = df
        print(f"      Rows loaded: {len(df)} | Date range: {df['date'].min()} to {df['date'].max()}")

    # 2. Transform into FinRL Data Contract Long Format
    print("\n[+] Transforming into FinRL long-format schema...")
    finrl_data = to_finrl_format(data_map, validate=True)
    prices_df = finrl_data["prices"]

    # 3. Save processed dataset
    processed_path = save_processed_data(finrl_data)
    print(f"[+] Saved processed dataset to: {processed_path}")

    # 4. Pipeline Summary Metrics
    num_symbols = len(prices_df["symbol"].unique())
    num_rows = len(prices_df)
    earliest_date = prices_df["date"].min()
    latest_date = prices_df["date"].max()
    unique_symbols = list(prices_df["symbol"].unique())

    print("\n" + "-" * 40)
    print("PIPELINE EXECUTION SUMMARY")
    print("-" * 40)
    print(f"Symbols: {num_symbols}")
    print(f"Rows: {num_rows}")
    print(f"Date range: {earliest_date} -> {latest_date}")
    print("\nSymbols:")
    for sym in unique_symbols:
        print(f"{sym}")

    print("\nSchema:")
    for col in prices_df.columns:
        print(f"{col}")

    print("\nSample Transformed Rows:")
    print(prices_df.head(6).to_string(index=False))

    # 5. MegaBull Symbol Mapping Verification (Mock / Offline Tradable Instrument List)
    print("\n--- MegaBull Symbol Mapping Adapter Inspection ---")
    sample_instruments_data = pd.DataFrame([
        {"instrumentToken": 738561, "tradingSymbol": "RELIANCE", "exchange": "NSE", "instrumentName": "RELIANCE INDUSTRIES LTD"},
        {"instrumentToken": 2953217, "tradingSymbol": "TCS", "exchange": "NSE", "instrumentName": "TATA CONSULTANCY SERVICES"},
        {"instrumentToken": 408065, "tradingSymbol": "INFY", "exchange": "NSE", "instrumentName": "INFOSYS LTD"},
    ])
    mapper = MegaBullSymbolMapper(instruments_df=sample_instruments_data)
    mapping_results = mapper.batch_resolve(unique_symbols)
    print(mapping_results.to_string(index=False))

    # 6. Final Contract Validation Checks
    india_validation = validate_market_dataframe(prices_df, is_long_format=True, raise_on_error=True)
    finrl_validation = validate_market_data(finrl_data)

    print("\nValidation:")
    if india_validation["is_valid"] and finrl_validation:
        print("PASS")
    else:
        print("FAIL")

    print("=" * 60)
    print("PHASE 2 PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    run_phase2_pipeline()
