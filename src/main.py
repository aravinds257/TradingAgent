"""Entry point — starts the trading system for one market.

    python -m src.main                                          # crypto (config/settings.yaml)
    python -m src.main --config config/markets/us_stocks.yaml   # US stocks
"""

import argparse
import asyncio

from src.core.config import load_settings
from src.core.supervisor import Supervisor


def main():
    parser = argparse.ArgumentParser(description="Run the trading engine for one market.")
    parser.add_argument("--config", default=None,
                        help="Path to a settings YAML (default: config/settings.yaml)")
    args = parser.parse_args()

    supervisor = Supervisor(load_settings(args.config))
    try:
        asyncio.run(supervisor.start())
    except KeyboardInterrupt:
        print("\nShutdown requested via keyboard.")


if __name__ == "__main__":
    main()
