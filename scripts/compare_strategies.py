"""Fee-aware vectorised backtester to compare candidate strategies on real Binance data.

Usage:
    python scripts/compare_strategies.py            # uses cached CSVs in data/bars, downloads if missing
    python scripts/compare_strategies.py --refresh  # force re-download

Positions are decided on bar close and applied to the NEXT bar's return (no look-ahead).
Costs: taker fee + slippage charged on every unit of position change.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
FEE = 0.00075        # Binance taker fee per side
SLIPPAGE = 0.0002    # conservative slippage per side
COST = FEE + SLIPPAGE
BARS_DIR = Path(__file__).resolve().parent.parent / "data" / "bars"
PERIODS_PER_YEAR = {"15m": 35040, "1h": 8760, "4h": 2190}


# ----------------------------------------------------------------------------- data
def fetch(symbol: str, timeframe: str, days: int, refresh: bool) -> pd.DataFrame:
    BARS_DIR.mkdir(parents=True, exist_ok=True)
    path = BARS_DIR / f"{symbol.replace('/', '')}_{timeframe}_{days}d.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)

    import ccxt

    ex = ccxt.binance({"enableRateLimit": True})
    since = ex.milliseconds() - days * 86_400_000
    rows: list[list] = []
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
        time.sleep(ex.rateLimit / 1000)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("ts")
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop(columns="ts")
    df.to_csv(path)
    return df


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()


# ----------------------------------------------------------------------- indicators
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def adx(df, n=14):
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, n)
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def supertrend(df, n=10, mult=3.0) -> pd.Series:
    """Returns +1 (bullish) / -1 (bearish) direction series."""
    a = atr(df, n).values
    hl2 = ((df["high"] + df["low"]) / 2).values
    close = df["close"].values
    ub, lb = hl2 + mult * a, hl2 - mult * a
    fub, flb = ub.copy(), lb.copy()
    d = np.ones(len(df))
    for i in range(1, len(df)):
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or close[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or close[i - 1] < flb[i - 1]) else flb[i - 1]
        if close[i] > fub[i - 1]:
            d[i] = 1
        elif close[i] < flb[i - 1]:
            d[i] = -1
        else:
            d[i] = d[i - 1]
    return pd.Series(d, index=df.index)


# ----------------------------------------------------------------------- strategies
# Each returns a position Series in {-1, 0, 1} decided at bar close.

def s_buy_hold(df):
    return pd.Series(1.0, index=df.index)


def s_ma_cross(df, fast=9, slow=21, atr_mult=2.5):
    """Replica of current ma_crossover agent: flip on cross, ATR stop."""
    f, s, a = ema(df.close, fast).values, ema(df.close, slow).values, atr(df).values
    c = df.close.values
    pos = np.zeros(len(df)); p = 0; stop = np.nan
    for i in range(1, len(df)):
        if f[i - 1] <= s[i - 1] and f[i] > s[i]:
            p, stop = 1, c[i] - atr_mult * a[i]
        elif f[i - 1] >= s[i - 1] and f[i] < s[i]:
            p, stop = -1, c[i] + atr_mult * a[i]
        elif (p == 1 and c[i] < stop) or (p == -1 and c[i] > stop):
            p = 0
        pos[i] = p
    return pd.Series(pos, index=df.index)


def s_donchian(df, entry=20, exit_=10):
    """Replica of current momentum_breakout agent (long only)."""
    hi = df.high.rolling(entry).max().shift()
    lo = df.low.rolling(exit_).min().shift()
    c = df.close.values
    pos = np.zeros(len(df)); p = 0
    for i in range(len(df)):
        if p == 0 and c[i] > hi.iat[i]:
            p = 1
        elif p == 1 and c[i] < lo.iat[i]:
            p = 0
        pos[i] = p
    return pd.Series(pos, index=df.index)


def s_bb_mr(df, n=20, k=2.0, os_=25, ob=75, adx_max=None):
    """Bollinger mean reversion; optional ADX<adx_max regime filter (range-only)."""
    mid = df.close.rolling(n).mean(); sd = df.close.rolling(n).std()
    lo, up = mid - k * sd, mid + k * sd
    r = rsi(df.close); ax = adx(df) if adx_max else None
    c = df.close.values
    pos = np.zeros(len(df)); p = 0
    for i in range(n, len(df)):
        ok = adx_max is None or ax.iat[i] < adx_max
        if p == 0 and ok:
            if c[i] < lo.iat[i] and r.iat[i] < os_:
                p = 1
            elif c[i] > up.iat[i] and r.iat[i] > ob:
                p = -1
        elif p == 1 and (c[i] >= mid.iat[i] or (adx_max and ax.iat[i] > adx_max + 10)):
            p = 0
        elif p == -1 and (c[i] <= mid.iat[i] or (adx_max and ax.iat[i] > adx_max + 10)):
            p = 0
        pos[i] = p
    return pd.Series(pos, index=df.index)


def s_supertrend_regime(df, n=10, mult=3.0, adx_min=22, sma=200, long_only=False):
    """Supertrend direction, entered only when ADX confirms a trend and price is on the right side of SMA.
    Exit on Supertrend flip (acts as trailing stop)."""
    d = supertrend(df, n, mult).values
    ax = adx(df).values; sm = df.close.rolling(sma).mean().values; c = df.close.values
    pos = np.zeros(len(df)); p = 0
    for i in range(1, len(df)):
        if (p == 1 and d[i] == -1) or (p == -1 and d[i] == 1):
            p = 0
        if p == 0 and ax[i] > adx_min:
            if d[i] == 1 and c[i] > sm[i]:
                p = 1
            elif not long_only and d[i] == -1 and c[i] < sm[i]:
                p = -1
        pos[i] = p
    return pd.Series(pos, index=df.index)


def s_ema_trend(df, fast=50, slow=200, long_only=False):
    """Slow trend filter: in the market only when EMA stack and price agree."""
    f, s = ema(df.close, fast), ema(df.close, slow)
    long_ = (f > s) & (df.close > f)
    short = (f < s) & (df.close < f)
    pos = long_.astype(float) - (0 if long_only else short.astype(float))
    return pos


def s_turtle(df, entry=55, exit_=20, long_only=False):
    hi = df.high.rolling(entry).max().shift(); lo = df.low.rolling(entry).min().shift()
    xlo = df.low.rolling(exit_).min().shift(); xhi = df.high.rolling(exit_).max().shift()
    c = df.close.values
    pos = np.zeros(len(df)); p = 0
    for i in range(len(df)):
        if p == 0:
            if c[i] > hi.iat[i]:
                p = 1
            elif not long_only and c[i] < lo.iat[i]:
                p = -1
        elif (p == 1 and c[i] < xlo.iat[i]) or (p == -1 and c[i] > xhi.iat[i]):
            p = 0
        pos[i] = p
    return pd.Series(pos, index=df.index)


# --------------------------------------------------------------------------- engine
def run(df: pd.DataFrame, pos: pd.Series) -> pd.Series:
    """Per-bar net returns of a strategy."""
    ret = df.close.pct_change().fillna(0)
    pos = pos.fillna(0)
    held = pos.shift().fillna(0)
    costs = pos.diff().abs().fillna(pos.abs()) * COST
    return held * ret - costs


def run_pairs(a: pd.DataFrame, b: pd.DataFrame, lookback=90, entry=2.0, exit_=0.0, stop=3.5):
    """Market-neutral log-spread z-score (replica of pairs_trading agent)."""
    idx = a.index.intersection(b.index)
    a, b = a.loc[idx], b.loc[idx]
    spread = np.log(a.close) - np.log(b.close)
    z = (spread - spread.rolling(lookback).mean()) / spread.rolling(lookback).std()
    pos = np.zeros(len(idx)); p = 0
    for i in range(len(idx)):
        zi = z.iat[i]
        if np.isnan(zi):
            continue
        if p == 0:
            p = -1 if zi > entry else (1 if zi < -entry else 0)
        elif abs(zi) > stop or (p == 1 and zi >= exit_) or (p == -1 and zi <= -exit_):
            p = 0
        pos[i] = p
    pos = pd.Series(pos, index=idx)
    ra, rb = a.close.pct_change().fillna(0), b.close.pct_change().fillna(0)
    held = pos.shift().fillna(0)
    costs = pos.diff().abs().fillna(0) * COST  # both legs, half capital each
    return 0.5 * held * (ra - rb) - costs, pos


def stats(r: pd.Series, pos: pd.Series, tf: str) -> dict:
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    pos = pos.fillna(0)
    grp = (pos != pos.shift()).cumsum()
    side = pos.groupby(grp).first()
    # attribute each bar's return to the position held during it (pos shifted)
    held_grp = grp.shift().fillna(grp.iloc[0])
    trade_r = r.groupby(held_grp).sum()
    trade_r = trade_r[side.reindex(trade_r.index).fillna(0) != 0]
    wins = (trade_r > 0).sum()
    gp, gl = trade_r[trade_r > 0].sum(), -trade_r[trade_r < 0].sum()
    sharpe = r.mean() / r.std() * np.sqrt(PERIODS_PER_YEAR[tf]) if r.std() > 0 else 0
    half = len(r) // 2
    return {
        "ret%": (eq.iat[-1] - 1) * 100,
        "H1%": ((1 + r.iloc[:half]).prod() - 1) * 100,
        "H2%": ((1 + r.iloc[half:]).prod() - 1) * 100,
        "maxDD%": dd * 100,
        "sharpe": sharpe,
        "trades": len(trade_r),
        "win%": wins / max(len(trade_r), 1) * 100,
        "PF": gp / gl if gl > 0 else np.inf,
        "expo%": (pos != 0).mean() * 100,
    }


STRATS = {
    "buy_hold": s_buy_hold,
    "ma_cross 9/21 (current)": s_ma_cross,
    "donchian 20/10 (current)": s_donchian,
    "bb_mr (current)": s_bb_mr,
    "bb_mr + ADX<20 filter": lambda d: s_bb_mr(d, adx_max=20),
    "supertrend+ADX+SMA200": s_supertrend_regime,
    "supertrend+ADX+SMA200 long": lambda d: s_supertrend_regime(d, long_only=True),
    "ema 50/200 trend": s_ema_trend,
    "ema 50/200 trend long": lambda d: s_ema_trend(d, long_only=True),
    "turtle 55/20": s_turtle,
    "turtle 55/20 long": lambda d: s_turtle(d, long_only=True),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--days15", type=int, default=180)
    ap.add_argument("--days1h", type=int, default=730)
    args = ap.parse_args()

    data = {}
    for sym in SYMBOLS:
        m15 = fetch(sym, "15m", args.days15, args.refresh)
        h1 = fetch(sym, "1h", args.days1h, args.refresh)
        data[sym] = {"15m": m15, "1h": h1, "4h": resample(h1, "4h")}
        print(f"{sym}: 15m {m15.index[0].date()}->{m15.index[-1].date()} ({len(m15)} bars), "
              f"1h {h1.index[0].date()}->{h1.index[-1].date()} ({len(h1)} bars)", file=sys.stderr)

    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:8.2f}")
    print(f"\nCosts per side: fee {FEE*100:.3f}% + slippage {SLIPPAGE*100:.3f}%. "
          "Directional rows = equal-weight average across BTC/ETH/SOL/BNB (trades summed). "
          "H1/H2 = first/second half of the period (robustness check).\n")

    for tf in ["15m", "1h", "4h"]:
        rows = []
        for name, fn in STRATS.items():
            per = []
            for s in SYMBOLS:
                df = data[s][tf]
                pos = fn(df)
                per.append(stats(run(df, pos), pos, tf))
            row = pd.DataFrame(per).mean()
            row["trades"] = sum(p["trades"] for p in per)
            row["sym+"] = sum(p["ret%"] > 0 for p in per)
            row.name = name
            rows.append(row)
        for a, b in [("BTC/USDT", "ETH/USDT"), ("ETH/USDT", "SOL/USDT")]:
            r, pos = run_pairs(data[a][tf], data[b][tf])
            row = pd.Series(stats(r, pos, tf), name=f"pairs {a[:3]}/{b[:3]} z")
            row["sym+"] = np.nan
            rows.append(row)
        span = data["BTC/USDT"][tf].index
        print(f"=== {tf}  ({span[0].date()} -> {span[-1].date()}) ===")
        print(pd.DataFrame(rows).sort_values("ret%", ascending=False).to_string())
        print()


if __name__ == "__main__":
    main()
