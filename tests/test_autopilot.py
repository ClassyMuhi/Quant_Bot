"""
Unit Tests for Intraday Auto-Pilot Engine
"""

from datetime import datetime, time, timezone
import pytest
from paper_trading.portfolio import PaperPortfolio
from paper_trading.autopilot import AutoPilotConfig, IntradayAutoPilot


def test_autopilot_minimum_10_minutes_frequency():
    # If user tries to configure frequency < 10 mins, it must enforce minimum 10 mins
    cfg = AutoPilotConfig(frequency_minutes=5)
    assert cfg.frequency_minutes == 10

    cfg_valid = AutoPilotConfig(frequency_minutes=15)
    assert cfg_valid.frequency_minutes == 15


def test_autopilot_trading_window_validation():
    cfg = AutoPilotConfig(
        start_time_str="09:15",
        end_time_str="15:15",
        square_off_time_str="15:20",
    )
    pilot = IntradayAutoPilot(config=cfg)

    # 08:30 IST is pre-market
    pre_market = datetime(2024, 1, 15, 8, 30, 0)
    is_active, msg = pilot.is_within_trading_window(pre_market)
    assert is_active is False
    assert "pre-market" in msg.lower()

    # 11:30 IST is active market
    active_time = datetime(2024, 1, 15, 11, 30, 0)
    is_active, msg = pilot.is_within_trading_window(active_time)
    assert is_active is True

    # 15:18 IST is past new entry cutoff
    post_cutoff = datetime(2024, 1, 15, 15, 18, 0)
    is_active, msg = pilot.is_within_trading_window(post_cutoff)
    assert is_active is False
    assert "entry cutoff" in msg.lower()

    # 15:25 IST is post-market past square-off
    post_market = datetime(2024, 1, 15, 15, 25, 0)
    assert pilot.is_past_square_off(post_market) is True


def test_autopilot_cycle_execution_and_intraday_tag(tmp_path):
    acc_file = tmp_path / "autopilot_acc.json"
    port = PaperPortfolio(account_file=acc_file, initial_cash=100000.0)

    cfg = AutoPilotConfig(
        allocated_capital=50000.0,
        frequency_minutes=10,
        start_time_str="00:00",  # Allow 24/7 in test
        end_time_str="23:59",
        square_off_time_str="23:59",
        min_confidence=0.50,
        max_active_positions=2,
    )
    pilot = IntradayAutoPilot(config=cfg, portfolio=port)

    # Mock price lookup
    price_map = {"RELIANCE": 2400.0, "TCS": 3500.0, "INFY": 1500.0}
    def mock_price(sym):
        return price_map.get(sym, 1000.0)

    res = pilot.execute_cycle(price_lookup_func=mock_price)
    assert res["cycle_number"] == 1
    assert pilot.cycle_count == 1
    assert pilot.next_cycle_time is not None
    assert len(pilot.scan_logs) > 0


def test_autopilot_mandatory_square_off(tmp_path):
    acc_file = tmp_path / "autopilot_sq.json"
    port = PaperPortfolio(account_file=acc_file, initial_cash=100000.0)

    # Open an intraday position
    port.apply_trade(
        symbol="TCS",
        side="BUY",
        quantity=10,
        executed_price=3500.0,
        taxes_and_charges=25.0,
        trading_style="INTRADAY",
    )
    assert "TCS" in port.holdings
    assert port.holdings["TCS"]["trading_style"] == "INTRADAY"

    cfg = AutoPilotConfig(allocated_capital=50000.0, frequency_minutes=10)
    pilot = IntradayAutoPilot(config=cfg, portfolio=port)

    # Square off
    closed = pilot.square_off_all_intraday(price_lookup_func=lambda s: 3550.0)
    assert len(closed) == 1
    assert "TCS" not in port.holdings
    assert port.realized_pnl > 400.0  # Profitable close
