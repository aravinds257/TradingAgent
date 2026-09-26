"""Tests for technical indicator computations."""

import numpy as np
import pandas as pd
import pytest

from src.indicators.technical import (
    add_atr, add_bollinger_bands, add_donchian_channels,
    add_ema, add_macd, add_rsi, add_sma, compute_zscore,
)


@pytest.fixture
def sample_df():
    """Create a sample OHLCV DataFrame with predictable data."""
    np.random.seed(42)
    n = 100
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    return pd.DataFrame({
        "open": close - np.random.rand(n),
        "high": close + np.abs(np.random.randn(n) * 3),
        "low": close - np.abs(np.random.randn(n) * 3),
        "close": close,
        "volume": np.random.randint(100, 10000, n).astype(float),
    })


def test_ema(sample_df):
    df = add_ema(sample_df, 9)
    assert "ema_9" in df.columns
    assert not df["ema_9"].iloc[-1:].isna().any()


def test_sma(sample_df):
    df = add_sma(sample_df, 20)
    assert "sma_20" in df.columns
    assert not df["sma_20"].iloc[-1:].isna().any()


def test_rsi(sample_df):
    df = add_rsi(sample_df, 14)
    assert "rsi_14" in df.columns
    rsi_vals = df["rsi_14"].dropna()
    assert (rsi_vals >= 0).all() and (rsi_vals <= 100).all()


def test_atr(sample_df):
    df = add_atr(sample_df, 14)
    assert "atr_14" in df.columns
    assert (df["atr_14"].dropna() >= 0).all()


def test_bollinger_bands(sample_df):
    df = add_bollinger_bands(sample_df, 20, 2.0)
    assert all(c in df.columns for c in ["bb_lower", "bb_mid", "bb_upper"])
    valid = df.dropna(subset=["bb_lower", "bb_upper"])
    assert (valid["bb_lower"] <= valid["bb_upper"]).all()


def test_macd(sample_df):
    df = add_macd(sample_df, 12, 26, 9)
    assert all(c in df.columns for c in ["macd", "macd_signal", "macd_histogram"])


def test_donchian_channels(sample_df):
    df = add_donchian_channels(sample_df, 20, 10)
    assert "dc_upper_20" in df.columns
    assert "dc_lower_10" in df.columns


def test_zscore(sample_df):
    z = compute_zscore(sample_df["close"], lookback=30)
    valid = z.dropna()
    assert len(valid) > 0
    # Z-scores should generally be within -5 to 5
    assert valid.abs().max() < 10
