"""Entry point — starts the trading system."""

import asyncio

from src.core.supervisor import Supervisor


def main():
    supervisor = Supervisor()
    try:
        asyncio.run(supervisor.start())
    except KeyboardInterrupt:
        print("\nShutdown requested via keyboard.")


if __name__ == "__main__":
    main()
