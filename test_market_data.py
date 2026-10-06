"""
Test script for MegaBull Market Data & Instruments.
Retrieves market watch items and the tradable instrument master list.
"""

from broker.megabull import MegaBull, MegaBullAPIError


def main():
    print("=" * 60)
    print("MegaBull Market Data & Instrument Inspection")
    print("=" * 60)

    try:
        mb = MegaBull()

        # 1. Inspect Market Watch List (GET /api/marketwatch/my)
        print("\n--- 1. Fetching User's Market Watch List ---")
        mw_df = mb.get_marketwatch(as_dataframe=True)
        print(f"[+] Total symbols in Market Watch: {len(mw_df)}")

        display_cols = [
            "tradingSymbol",
            "exchange",
            "segment",
            "lastPrice",
            "lotSize",
            "tickSize",
            "instrumentToken",
        ]
        # Keep only existing columns for clean display
        valid_cols = [col for col in display_cols if col in mw_df.columns]
        print(mw_df[valid_cols].to_string(index=False))

        # 2. Test Individual Symbol Lookup
        test_symbols = ["RELIANCE", "INFY", "NIFTY 50", "UNKNOWN_XYZ"]
        print("\n--- 2. Testing Symbol Quote Lookup ---")
        for sym in test_symbols:
            quote = mb.get_marketwatch_quote(sym)
            if quote:
                print(
                    f"  [FOUND] {sym:<10} | Exchange: {quote.get('exchange')} | "
                    f"Segment: {quote.get('segment')} | Last Price: {quote.get('lastPrice')} | "
                    f"Token: {quote.get('instrumentToken')}"
                )
            else:
                print(f"  [NOT FOUND] {sym:<10} (not in current market watch)")

        # 3. Inspect Master Tradable Instruments List (GET /api/marketwatch/instruments)
        print("\n--- 3. Fetching Master Tradable Instruments CSV ---")
        inst_df = mb.get_instruments(as_dataframe=True)
        print(f"[+] Total tradable instruments loaded: {len(inst_df)}")
        print("\nSample top 5 instruments:")
        print(inst_df.head(5).to_string(index=False))

        # Search for popular stocks in master list
        print("\nSearching for 'TATA' instruments in master list (sample 5):")
        tata_df = inst_df[inst_df["tradingSymbol"].str.contains("TATA", case=False, na=False)]
        print(tata_df.head(5).to_string(index=False))

        print("\n" + "=" * 60)
        print("MARKET DATA INSPECTION COMPLETED SUCCESSFULLY")
        print("=" * 60)

    except MegaBullAPIError as e:
        print(f"[!] MegaBull API Error: {e}")
    except Exception as e:
        print(f"[!] Error: {e}")


if __name__ == "__main__":
    main()
