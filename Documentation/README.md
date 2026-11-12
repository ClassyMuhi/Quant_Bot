# Quant_Bot Documentation

Welcome to the technical and architecture documentation for **Quant_Bot** — an event-aware AI quantitative trading and paper-trading system for Indian NSE equities.

---

## Documentation Index

| Document | Topic | Description |
| :--- | :--- | :--- |
| [Market Data Pipeline](market_data_pipeline.md) | **Bronze $\rightarrow$ Silver $\rightarrow$ Gold Pipeline** | Complete guide to our Medallion market data architecture, Yahoo Finance fetching, DuckDB Parquet storage, data cleaning, and technical feature engineering. |
| [FinRL Adapter & Contracts](finrl_adapter.md) | **Strategy & Portfolio Abstractions** | Standard data contract schemas, base strategy interfaces, and portfolio allocation with cash reserves. |
| [MegaBull Broker Interface](megabull_broker.md) | **Paper Trading Execution** | Python REST API wrapper for the MegaBull paper trading platform, order submission, positions, and holdings. |

---

## System Architecture Quick Look

```
┌────────────────────────────────────────────────────────┐
│                   Market Data Sourcing                 │
│      Yahoo Finance (.NS) -> pipeline.market_fetcher     │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                  Medallion Data Pipeline               │
│  Bronze (Raw Parquet)   -> pipeline.bronze_writer      │
│  Silver (Cleaned OHLCV) -> pipeline.silver_transformer │
│  Gold   (Features: RSI) -> pipeline.gold_features      │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                 FinRL Strategy Adapter                 │
│  Data Contract Validation  -> finrl_adapter/data_contract│
│  Target Weight Generation -> finrl_adapter/strategy    │
│  Portfolio Allocation & Cash-> finrl_adapter/allocator │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               Broker & Execution Engine                │
│  MegaBull Paper Trading -> broker/megabull.py          │
└────────────────────────────────────────────────────────┘
```

