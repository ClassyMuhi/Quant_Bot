"""
Convenience launcher for Quant_Bot Backtest Dashboard.
Run:
    python run_dashboard.py
"""

from backtest.dashboard import launch_dashboard

if __name__ == "__main__":
    launch_dashboard(port=8501, open_browser=True)

