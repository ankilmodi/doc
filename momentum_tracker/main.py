"""
main.py – Entry point for the Momentum Signal Tracker.

Usage:
    python main.py                        # scan with default interval (5-min candles)
    python main.py --interval ONE_MINUTE  # 1-minute candles
    python main.py --interval FIFTEEN_MINUTE
    python main.py --save-csv             # also write results to signals.csv
    python main.py --dry-run              # run one scan and exit

Supported --interval values (Angel One):
    ONE_MINUTE | FIVE_MINUTE | FIFTEEN_MINUTE | THIRTY_MINUTE | ONE_HOUR | ONE_DAY
"""

import argparse
import logging
import sys

import config
from scanner import run, run_single_scan
from angel_connector import AngelConnector
from symbols import refresh_tokens_from_master
import signals as sig
import formatter as fmt
from datetime import datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Intraday momentum signal tracker using Angel One SmartConnect."
    )
    parser.add_argument(
        "--interval",
        default=config.CANDLE_INTERVAL,
        choices=["ONE_MINUTE", "FIVE_MINUTE", "FIFTEEN_MINUTE",
                 "THIRTY_MINUTE", "ONE_HOUR", "ONE_DAY"],
        help="Candle interval for indicator calculations (default: %(default)s).",
    )
    parser.add_argument(
        "--save-csv",
        action="store_true",
        help="Append qualifying signals to signals.csv after each scan.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run exactly one scan cycle, print results, then exit.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=config.TOP_N,
        help=f"Maximum number of stocks in the output list (default: {config.TOP_N}).",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=config.CAPITAL_USD,
        help=f"Capital in USD for allocation suggestion (default: {config.CAPITAL_USD}).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Apply runtime overrides into config (no persistence – in-memory only)
    config.CANDLE_INTERVAL = args.interval
    config.TOP_N           = args.top
    config.CAPITAL_USD     = args.capital

    logging.basicConfig(
        level   = getattr(logging, args.log_level),
        format  = "%(asctime)s  %(levelname)-8s %(message)s",
        datefmt = "%H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    if args.dry_run:
        # ── Single scan, then exit ────────────────────────────────────────────
        logger.info("DRY-RUN mode: one scan cycle only.")
        api      = AngelConnector()
        universe = refresh_tokens_from_master()
        now      = datetime.now()
        ranked   = run_single_scan(universe, api)
        alloc    = sig.build_allocation(ranked)
        print(fmt.format_table(ranked, alloc, now))
        if args.save_csv:
            fmt.save_csv(ranked, alloc, now, path="signals.csv")
            logger.info("Saved to signals.csv")
        sys.exit(0)

    # ── Continuous scan loop ──────────────────────────────────────────────────
    run(save_csv=args.save_csv)


if __name__ == "__main__":
    main()
