"""Technical indicator computation helpers wrapping pandas-ta.

All functions accept a pandas DataFrame with columns: open, high, low, close, volume.
All functions return the same DataFrame with new indicator columns appended.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta as ta


def add_ema(df: pd.DataFrame, period: int, col: str = "close") -> pd.DataFrame:
    """Add Exponential Moving Average column."""
    df[f"ema_{period}"] = ta.ema(df[col], length=period)
    return df


def add_sma(df: pd.DataFrame, period: int, col: str = "close") -> pd.DataFrame:
    """Add Simple Moving Average column."""
    df[f"sma_{period}"] = ta.sma(df[col], length=period)
    return df


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add RSI column."""
    df[f"rsi_{period}"] = ta.rsi(df["close"], length=period)
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add Average True Range column."""
    df[f"atr_{period}"] = ta.atr(df["high"], df["low"], df["close"], length=period)
    return df


def add_bollinger_bands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    """Add Bollinger Bands columns: bb_lower, bb_mid, bb_upper."""
    bbands = ta.bbands(df["close"], length=period, std=std)
    if bbands is not None and not bbands.empty:
        df["bb_lower"] = bbands.iloc[:, 0]
        df["bb_mid"] = bbands.iloc[:, 1]
        df["bb_upper"] = bbands.iloc[:, 2]
    return df


def add_keltner_channels(df: pd.DataFrame, period: int = 20,
                          atr_multiplier: float = 1.5) -> pd.DataFrame:
    """Add Keltner Channel columns: kc_lower, kc_mid, kc_upper."""
    kc = ta.kc(df["high"], df["low"], df["close"],
               length=period, scalar=atr_multiplier)
    if kc is not None and not kc.empty:
        df["kc_lower"] = kc.iloc[:, 0]
        df["kc_mid"] = kc.iloc[:, 1]
        df["kc_upper"] = kc.iloc[:, 2]
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26,
             signal: int = 9) -> pd.DataFrame:
    """Add MACD columns: macd, macd_signal, macd_histogram."""
    macd = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
    if macd is not None and not macd.empty:
        df["macd"] = macd.iloc[:, 0]
        df["macd_signal"] = macd.iloc[:, 1]
        df["macd_histogram"] = macd.iloc[:, 2]
    return df


def add_donchian_channels(df: pd.DataFrame, upper_period: int = 20,
                           lower_period: int = 10) -> pd.DataFrame:
    """Add Donchian Channel columns: dc_upper (N-period high), dc_lower (M-period low)."""
    df[f"dc_upper_{upper_period}"] = df["high"].rolling(window=upper_period).max()
    df[f"dc_lower_{lower_period}"] = df["low"].rolling(window=lower_period).min()
    return df


def compute_zscore(series: pd.Series, lookback: int = 90) -> pd.Series:
    """Compute rolling Z-score of a series."""
    mean = series.rolling(window=lookback).mean()
    std = series.rolling(window=lookback).std()
    return (series - mean) / std.replace(0, np.nan)


def detect_divergence(prices: pd.Series, indicator: pd.Series,
                       lookback: int = 5) -> pd.Series:
    """Detect bullish and bearish divergences.

    Returns a Series with values:
      +1 = bullish divergence (price lower low, indicator higher low)
      -1 = bearish divergence (price higher high, indicator lower high)
       0 = no divergence

    Args:
        prices: Close price series.
        indicator: Indicator series (e.g., RSI).
        lookback: Number of bars to look back for swing points.
    """
    result = pd.Series(0, index=prices.index)

    for i in range(lookback * 2, len(prices)):
        # Find swing lows in lookback window
        window_prices = prices.iloc[i - lookback:i + 1]
        window_ind = indicator.iloc[i - lookback:i + 1]

        price_min_idx = window_prices.idxmin()
        prev_window_prices = prices.iloc[i - lookback * 2:i - lookback + 1]

        if len(prev_window_prices) == 0:
            continue

        prev_price_min_idx = prev_window_prices.idxmin()

        # Bullish divergence: price makes lower low, indicator makes higher low
        if (prices.loc[price_min_idx] < prices.loc[prev_price_min_idx] and
                indicator.loc[price_min_idx] > indicator.loc[prev_price_min_idx]):
            result.iloc[i] = 1

        # Bearish divergence: price makes higher high, indicator makes lower high
        price_max_idx = window_prices.idxmax()
        prev_price_max_idx = prev_window_prices.idxmax()

        if (prices.loc[price_max_idx] > prices.loc[prev_price_max_idx] and
                indicator.loc[price_max_idx] < indicator.loc[prev_price_max_idx]):
            result.iloc[i] = -1

    return result
