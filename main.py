"""
main.py — Entry point for The Sentinel.

Usage:
    python main.py            # start the full scheduler (runs forever)
    python main.py --test     # run one anomaly check cycle and exit
    python main.py --summary  # send daily summary now and exit
"""

import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="The Sentinel — Sentiment Trading Alert Bot")
    parser.add_argument("--test",    action="store_true", help="Run one anomaly check cycle and exit")
    parser.add_argument("--summary", action="store_true", help="Send daily summary now and exit")
    args = parser.parse_args()

    from sentinel.database import init_database
    init_database()

    if args.test:
        print("Running test cycle (one anomaly check)...")
        from sentinel.scheduler import job_anomaly_check
        job_anomaly_check()
        print("Test cycle complete.")

    elif args.summary:
        print("Sending daily summary...")
        from sentinel.scheduler import job_daily_summary
        job_daily_summary()
        print("Summary sent.")

    else:
        from sentinel.scheduler import run
        run()


if __name__ == "__main__":
    main()
