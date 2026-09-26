"""Utility script to reset the database and clear all old trade/equity history."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3

def reset_database(db_path: str = "data/trading_system.db"):
    db_file = Path(db_path)
    # Remove database and any WAL/SHM files
    for ext in ["", "-wal", "-shm"]:
        p = Path(f"{db_file}{ext}")
        if p.exists():
            p.unlink()
            print(f"Removed {p}")
    print("Database cleared successfully. Start the trading engine to initialize fresh tables.")

if __name__ == "__main__":
    reset_database()
