import numpy as np
import pandas as pd


def ema(series, period):
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean()
    avg_loss = loss.ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))

    # A run of gains with no losses has RSI 100; a flat run has RSI 50.
    no_losses = avg_loss.eq(0) & avg_gain.gt(0)
    flat = avg_loss.eq(0) & avg_gain.eq(0)
    out = out.mask(no_losses, 100.0).mask(flat, 50.0)
    # Preserve warm-up NaNs instead of disguising missing history as neutral.
    return out


def macd(series):
    fast = ema(series, 12)
    slow = ema(series, 26)
    line = fast - slow
    signal = ema(line, 9)
    return line, signal, line - signal


def atr(df, period=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def bollinger_width(series, period=20, num_std=2):
    mid = series.rolling(period, min_periods=period).mean()
    std = series.rolling(period, min_periods=period).std(ddof=0)
    upper, lower = mid + num_std * std, mid - num_std * std
    return (upper - lower) / mid.replace(0, np.nan)


def obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def add_indicators(df):
    df = df.copy()
    for p in (20, 50, 200):
        df[f"ema{p}"] = ema(df["close"], p)
    df["rsi14"] = rsi(df["close"], 14)
    df["macd"], df["macd_signal"], df["macd_hist"] = macd(df["close"])
    df["volume_ma20"] = df["volume"].rolling(20, min_periods=20).mean()
    df["relative_volume"] = df["volume"] / df["volume_ma20"].replace(0, np.nan)
    df["obv"] = obv(df["close"], df["volume"])
    df["obv_slope20"] = df["obv"].diff(20)
    df["atr14"] = atr(df, 14)
    df["atr_pct"] = df["atr14"] / df["close"] * 100
    df["bbw"] = bollinger_width(df["close"], 20)
    return df
