"""
Test script for MegaBull API client.
Verifies authentication and read-only endpoints without placing any orders.
"""

from broker.megabull import MegaBull, MegaBullAPIError


def main():
    print("=" * 50)
    print("MegaBull Paper Trading API - Connection Test")
    print("=" * 50)

    try:
        # Initialize client (loads API key automatically from .env)
        client = MegaBull()
        print("[+] MegaBull client initialized successfully.")
        print(f"[+] Client representation: {client}")

        # 1. Test Account / Profile Information
        print("\n--- 1. Testing Account Profile (GET /api/user/my) ---")
        profile = client.get_user_profile()
        print("[+] Account details retrieved successfully:")
        print(f"    - User: {profile.get('firstName', '')} {profile.get('lastName', '')}")
        print(f"    - Email: {profile.get('emailId')}")
        print(f"    - Total Virtual Money: Rs. {profile.get('virtualMoney', 0):,}")
        print(f"    - Available Virtual Money: Rs. {profile.get('virtualMoneyLeft', 0):,}")
        print(f"    - Blocked Virtual Money: Rs. {profile.get('virtualMoneyBlocked', 0):,}")
        print(f"    - Plan / Premium Type: {profile.get('premiumType')}")

        # 2. Test Positions (Read-only)
        print("\n--- 2. Testing Open Positions (GET /api/position/my) ---")
        positions = client.get_positions()
        print(f"[+] Positions response received. Count: {len(positions) if isinstance(positions, list) else positions}")

        # 3. Test Holdings (Read-only)
        print("\n--- 3. Testing Holdings (GET /api/holding/my) ---")
        holdings = client.get_holdings()
        print(f"[+] Holdings response received. Count: {len(holdings) if isinstance(holdings, list) else holdings}")

        # 4. Test Orders (Read-only)
        print("\n--- 4. Testing Orders (GET /api/order/my) ---")
        orders = client.get_orders()
        print(f"[+] Orders response received. Count: {len(orders) if isinstance(orders, list) else orders}")

        print("\n" + "=" * 50)
        print("ALL TEST CHECKS PASSED SUCCESSFULLY (Paper Trading Mode)")
        print("=" * 50)

    except MegaBullAPIError as e:
        print(f"\n[!] MegaBull API Error: {e}")
    except ValueError as e:
        print(f"\n[!] Configuration Error: {e}")
    except Exception as e:
        print(f"\n[!] Unexpected Error: {e}")


if __name__ == "__main__":
    main()