#!/usr/bin/env python3
"""Runner script to launch both the Trading Engine and Streamlit Dashboard.

Usage:
    python start.py            # Start both without resetting
    python start.py --reset    # Reset all database history, then start both
    python start.py -r         # Short flag for --reset
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


def reset_data():
    """Clear database files to start completely fresh."""
    print("=" * 60)
    print("🗑️  Resetting database and trade history...")
    db_file = PROJECT_ROOT / "data" / "trading_system.db"
    for ext in ["", "-wal", "-shm"]:
        p = Path(f"{db_file}{ext}")
        if p.exists():
            try:
                p.unlink()
                print(f"   Removed: {p.name}")
            except Exception as e:
                print(f"   Warning: could not remove {p.name}: {e}")
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
        description="Launch Trading Engine and Streamlit Dashboard simultaneously."
    )
    parser.add_argument(
        "-r",
        "--reset",
        action="store_true",
        help="Clear all database trades, signals, and equity history before starting.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port to run the Streamlit dashboard on (default: 8501).",
    )
    args = parser.parse_args()

    if args.reset:
        reset_data()

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
    print(f"📊 Dashboard : http://localhost:{args.port}")
    if args.reset:
        print("🔄 Mode      : Fresh Start (Database Reset)")
    else:
        print("💾 Mode      : Preserving Existing History")
    print("=" * 60)
    print("Press Ctrl+C at any time to stop both processes cleanly.\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    engine_proc = None
    dashboard_proc = None

    def cleanup(signum=None, frame=None):
        print("\n\n🛑 Stopping all services...")
        for proc, name in [(dashboard_proc, "Dashboard"), (engine_proc, "Trading Engine")]:
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
        # 1. Start Trading Engine
        print("⚙️  Launching Trading Engine (src.main)...")
        engine_proc = subprocess.Popen(
            [python_bin, "-m", "src.main"],
            cwd=str(PROJECT_ROOT),
            env=env,
        )

        # Small pause so engine connects and warms up
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

        print("\n✨ Both services are running!")
        print(f"👉 Open http://localhost:{args.port} to view the dashboard.\n")

        # Monitor processes
        while True:
            time.sleep(1)
            if engine_proc.poll() is not None:
                print(f"⚠️  Trading Engine exited unexpectedly with code {engine_proc.returncode}")
                cleanup()
            if dashboard_proc.poll() is not None:
                print(f"⚠️  Dashboard exited unexpectedly with code {dashboard_proc.returncode}")
                cleanup()

    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
