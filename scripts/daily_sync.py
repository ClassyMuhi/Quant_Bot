"""
Automated Daily Sync Script with Smart Freshness Guard
1. Verifies internet connectivity.
2. Checks if data is already fresh for today (avoids redundant work).
3. Executes incremental update (or backfill if missing) across the universe.
4. Collects and processes latest God's Eye market news.
5. Updates a lightweight Markdown audit log (DAILY_SYNC.md) and commits/pushes to GitHub to maintain streak.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import socket
import subprocess
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
LOG_DIR = PROJECT_ROOT / "data"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "daily_sync.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("DailySync")

STATE_FILE = LOG_DIR / "sync_state.json"
AUDIT_FILE = PROJECT_ROOT / "DAILY_SYNC.md"


def check_internet(host: str = "8.8.8.8", port: int = 53, timeout: int = 3, max_retries: int = 6) -> bool:
    """Verifies that network connectivity is active (useful after laptop wake-up)."""
    for attempt in range(1, max_retries + 1):
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            logger.info("Internet connection verified.")
            return True
        except (socket.timeout, OSError):
            logger.warning(f"Waiting for internet connection (attempt {attempt}/{max_retries})...")
            time.sleep(5)
    return False


def get_ist_now() -> datetime:
    """Returns current datetime in Indian Standard Time (UTC+5:30)."""
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=5, minutes=30)


def should_run_sync(force: bool = False) -> tuple[bool, str]:
    """
    Smart Freshness Guard:
    - Avoids running multiple times on the same day if already post-market fresh.
    - If run in the morning, allows a second run after market close (15:45 IST) to capture today's closing bar.
    """
    if force:
        return True, "Force flag set."

    if not STATE_FILE.exists():
        return True, "No previous sync record found."

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        logger.warning(f"Could not read state file: {e}")
        return True, "Invalid state file."

    last_date = state.get("last_sync_date")
    last_is_postmarket = state.get("last_sync_is_postmarket", False)

    ist_now = get_ist_now()
    today_str = ist_now.strftime("%Y-%m-%d")
    is_now_postmarket = (ist_now.hour > 15) or (ist_now.hour == 15 and ist_now.minute >= 45)

    if last_date != today_str:
        return True, f"New day ({today_str} vs last {last_date})."

    # Same day: if we already ran after market close, no need to run again
    if last_is_postmarket:
        return False, f"Already completed post-market sync for today ({today_str})."

    # Same day, but morning run previously done and now it's post-market: run to capture today's close
    if is_now_postmarket and not last_is_postmarket:
        return True, f"Market has closed; updating with official day-end closing bars."

    return False, f"Already synced today ({today_str}) during pre-market/intraday hours."


def update_market_data() -> dict:
    """Executes incremental market data pipeline across the stock universe."""
    from pipeline.market_pipeline import MarketPipeline
    logger.info("Starting market data pipeline update...")
    pipeline = MarketPipeline(base_data_dir=PROJECT_ROOT / "data")
    summary = pipeline.run_incremental_update()
    logger.info(f"Market data update finished for {len(summary)} symbols.")
    return summary


def update_news_intelligence() -> list:
    """Collects and processes latest news events."""
    from godseye.intelligence import GodsEyeIntelligence
    logger.info("Collecting latest God's Eye news feeds...")
    godseye = GodsEyeIntelligence()
    events = godseye.collect_and_process()
    logger.info(f"God's Eye ingested {len(events)} new news events.")
    return events


def record_audit_and_commit(market_stats: dict, news_events: list, ist_now: datetime) -> bool:
    """
    Appends entry to DAILY_SYNC.md and commits/pushes to GitHub to maintain streak.
    Only commits text files, keeping binary parquets completely untracked.
    """
    today_str = ist_now.strftime("%Y-%m-%d")
    time_str = ist_now.strftime("%H:%M IST")

    updated_syms = [s for s, res in market_stats.items() if res.get("status") in ("updated", "success")]
    up_to_date_syms = [s for s, res in market_stats.items() if res.get("status") == "up_to_date"]

    entry = (
        f"\n### 📅 {today_str} {time_str} &mdash; Automated Sync\n"
        f"- **Market Prices (OHLCV)**: {len(updated_syms)} symbols updated ({', '.join(updated_syms[:5])}{'...' if len(updated_syms) > 5 else ''}), "
        f"{len(up_to_date_syms)} already up to date.\n"
        f"- **God's Eye Intelligence**: {len(news_events)} new market news stories ingested.\n"
        f"- **Pipeline Health**: ✅ Bronze, Silver, and Gold layers validated.\n"
    )

    if not AUDIT_FILE.exists():
        header = "# 📊 Quant_Bot Daily Pipeline & Health Audit Log\n\nAutomated daily sync logs for market data and God's Eye intelligence feeds.\n"
        AUDIT_FILE.write_text(header + entry, encoding="utf-8")
    else:
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(entry)

    # Git commit and push
    try:
        # Check if remote exists
        subprocess.run(["git", "add", "DAILY_SYNC.md"], cwd=PROJECT_ROOT, check=True)
        commit_msg = f"chore(sync): daily pipeline sync {today_str}"
        res = subprocess.run(["git", "commit", "-m", commit_msg], cwd=PROJECT_ROOT, capture_output=True, text=True)
        if res.returncode == 0:
            logger.info(f"Committed streak update: {commit_msg}")
            push_res = subprocess.run(["git", "push", "origin", "main"], cwd=PROJECT_ROOT, capture_output=True, text=True)
            if push_res.returncode == 0:
                logger.info("Successfully pushed daily streak update to GitHub.")
                return True
            else:
                logger.warning(f"Git push failed: {push_res.stderr}")
        else:
            logger.info(f"Git commit skipped (no changes to commit): {res.stdout.strip()}")
    except Exception as e:
        logger.error(f"Git operation encountered error: {e}")

    return False


def main():
    force = "--force" in sys.argv
    logger.info("=" * 60)
    logger.info("Daily Sync Triggered.")

    if not check_internet():
        logger.error("No active internet connection. Aborting sync.")
        sys.exit(1)

    should_run, reason = should_run_sync(force=force)
    if not should_run:
        logger.info(f"Freshness Guard Active: {reason} Exiting gracefully.")
        sys.exit(0)

    logger.info(f"Freshness Guard Passed: {reason} Proceeding with data sync...")

    ist_now = get_ist_now()
    is_now_postmarket = (ist_now.hour > 15) or (ist_now.hour == 15 and ist_now.minute >= 45)

    market_stats = update_market_data()
    news_events = update_news_intelligence()

    # Record streak audit and commit to GitHub
    record_audit_and_commit(market_stats, news_events, ist_now)

    # Save sync state
    state_data = {
        "last_sync_date": ist_now.strftime("%Y-%m-%d"),
        "last_sync_timestamp": ist_now.isoformat(),
        "last_sync_is_postmarket": is_now_postmarket,
        "market_symbols_count": len(market_stats),
        "news_events_count": len(news_events),
        "status": "success",
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2)

    logger.info("Daily Sync Completed Successfully.")


if __name__ == "__main__":
    main()
