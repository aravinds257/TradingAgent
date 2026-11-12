#!/usr/bin/env python3
"""Runner script to launch the Trading Engines (one per market) and the Streamlit Dashboard.

Usage:
    python start.py                      # Start all markets (crypto, us, india) + dashboard
    python start.py --markets crypto,us  # Start only selected markets
    python start.py --reset              # Reset DB history of the selected markets, then start
    python start.py -r                   # Short flag for --reset
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.markets import MARKETS, market_db_path  # noqa: E402


def reset_data(markets: list[str]):
    """Clear database files of the selected markets to start completely fresh."""
    print("=" * 60)
    print("🗑️  Resetting database and trade history...")
    for market in markets:
        db_file = market_db_path(market)
        for ext in ["", "-wal", "-shm"]:
            p = Path(f"{db_file}{ext}")
            if p.exists():
                try:
                    p.unlink()
                    print(f"   [{market}] Removed: {p.name}")
                except Exception as e:
                    print(f"   [{market}] Warning: could not remove {p.name}: {e}")
    print("✅ Database reset complete.")
    print("=" * 60)


def ensure_port_free(port: int):
    """Check if the port is already bound and kill the stale process if needed."""
    try:
        res = subprocess.run(["lsof", "-t", f"-i:{port}"], capture_output=True, text=True)
        pids = res.stdout.strip().split()
        for p in pids:
            if p and p != str(os.getpid()):
                print(f"⚠️  Port {port} in use by PID {p}. Terminating stale process...")
                subprocess.run(["kill", "-9", p], check=False)
        if pids:
            time.sleep(1)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Launch Trading Engines and Streamlit Dashboard simultaneously."
    )
    parser.add_argument(
        "-r",
        "--reset",
        action="store_true",
        help="Clear all database trades, signals, and equity history before starting.",
    )
    parser.add_argument(
        "--markets",
        default=",".join(MARKETS),
        help=f"Comma-separated markets to run (default: {','.join(MARKETS)}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port to run the Streamlit dashboard on (default: 8501).",
    )
    args = parser.parse_args()

    markets = [m.strip() for m in args.markets.split(",") if m.strip()]
    unknown = [m for m in markets if m not in MARKETS]
    if unknown:
        parser.error(f"Unknown market(s): {unknown}. Choose from {list(MARKETS)}")

    if args.reset:
        reset_data(markets)

    # Free up port if an old Streamlit process is still running
    ensure_port_free(args.port)

    # Determine Python executable
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable

    # Determine Streamlit executable
    venv_streamlit = PROJECT_ROOT / ".venv" / "bin" / "streamlit"
    streamlit_bin = str(venv_streamlit) if venv_streamlit.exists() else "streamlit"

    print("\n" + "=" * 60)
    print("🚀 STARTING MULTI-AGENT TRADING SYSTEM")
    print("=" * 60)
    print(f"📂 Workspace : {PROJECT_ROOT}")
    print(f"🐍 Python    : {python_bin}")
    print(f"🌍 Markets   : {', '.join(markets)}")
    print(f"📊 Dashboard : http://localhost:{args.port}")
    if args.reset:
        print("🔄 Mode      : Fresh Start (Database Reset)")
    else:
        print("💾 Mode      : Preserving Existing History")
    print("=" * 60)
    print("Press Ctrl+C at any time to stop all processes cleanly.\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    engines: dict[str, subprocess.Popen] = {}
    dashboard_proc = None

    def cleanup(signum=None, frame=None):
        print("\n\n🛑 Stopping all services...")
        procs = [(dashboard_proc, "Dashboard")] + [(p, f"Engine [{m}]") for m, p in engines.items()]
        for proc, name in procs:
            if proc and proc.poll() is None:
                print(f"   Shutting down {name} (PID: {proc.pid})...")
                try:
                    proc.terminate()
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                except Exception:
                    pass
        print("✅ All services stopped. Goodbye!\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        # 1. Start one Trading Engine per market
        for market in markets:
            print(f"⚙️  Launching Trading Engine [{market}] ({MARKETS[market].name})...")
            engines[market] = subprocess.Popen(
                [python_bin, "-m", "src.main", "--config", str(MARKETS[market])],
                cwd=str(PROJECT_ROOT),
                env=env,
            )

        # Small pause so engines connect and warm up
        time.sleep(2)

        # 2. Start Streamlit Dashboard in headless mode
        print(f"📊 Launching Dashboard on port {args.port}...")
        dashboard_proc = subprocess.Popen(
            [
                streamlit_bin,
                "run",
                "dashboard/app.py",
                "--server.port",
                str(args.port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
        )

        print("\n✨ All services are running!")
        print(f"👉 Open http://localhost:{args.port} to view the dashboard.\n")

        # Monitor processes: a crashed engine is reported but doesn't stop other markets
        while True:
            time.sleep(1)
            for market, proc in list(engines.items()):
                if proc.poll() is not None:
                    print(f"⚠️  Trading Engine [{market}] exited with code {proc.returncode}")
                    del engines[market]
            if not engines:
                print("⚠️  All trading engines have stopped.")
                cleanup()
            if dashboard_proc.poll() is not None:
                print(f"⚠️  Dashboard exited unexpectedly with code {dashboard_proc.returncode}")
                cleanup()

    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
