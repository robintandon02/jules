import pandas as pd

def calculate_camarilla_pivots(high, low, close):
    """
    Calculates Camarilla pivot points based on the previous day's data.
    """
    p = (high + low + close) / 3
    r4 = close + ((high - low) * 1.5000)
    r3 = close + ((high - low) * 1.2500)
    s3 = close - ((high - low) * 1.2500)
    s4 = close - ((high - low) * 1.5000)

    return {
        "p": p,
        "r3": r3,
        "r4": r4,
        "s3": s3,
        "s4": s4
    }

def calculate_sma(prices: pd.Series, period: int):
    """
    Calculates the latest Simple Moving Average (SMA) value.
    Returns None if there are not enough data points.
    """
    if len(prices) < period:
        return None
    return prices.rolling(window=period).mean().iloc[-1]

def calculate_ema(prices: pd.Series, period: int):
    """
    Calculates the latest Exponential Moving Average (EMA) value.
    Returns None if there are not enough data points.
    """
    if len(prices) < period:
        return None
    return prices.ewm(span=period, adjust=False).mean().iloc[-1]

def get_all_levels(previous_day_data, historical_candles_df):
    """
    Calculates and aggregates all required levels for the strategy.
    Handles cases where previous_day_data may not be available.

    :param previous_day_data: An optional dictionary with keys 'high', 'low', 'close'.
    :param historical_candles_df: A pandas DataFrame with historical candle data.
                                  It must have a 'close' column.
    :return: A dictionary containing all calculated levels.
    """
    pdh, pdl, pdc, camarilla_pivots = None, None, None, {}

    # Static daily levels are derived from previous day's data, if available
    if previous_day_data:
        pdh = previous_day_data.get('high')
        pdl = previous_day_data.get('low')
        pdc = previous_day_data.get('close')
        # Ensure all H/L/C values are present before calculating pivots
        if all((pdh, pdl, pdc)):
            camarilla_pivots = calculate_camarilla_pivots(pdh, pdl, pdc)
        else:
            # If any value is missing, invalidate all of them to be safe
            pdh, pdl, pdc = None, None, None

    # Dynamic levels (moving averages) are calculated from historical candles
    close_prices = historical_candles_df['close']
    ema200 = calculate_ema(close_prices, 200)
    sma200 = calculate_sma(close_prices, 200)
    ema21 = calculate_ema(close_prices, 21)

    # Combine all levels into a single dictionary for easy access
    levels = {
        "pdh": pdh,
        "pdl": pdl,
        "pdc": pdc,
        "ema200": ema200,
        "sma200": sma200,
        "ema21": ema21,
        **camarilla_pivots
    }

    # The list of key levels for the strategy, excluding the 21 EMA which is a filter
    key_levels_for_trade = {
        'r4': camarilla_pivots.get('r4'),
        'r3': camarilla_pivots.get('r3'),
        'pdh': pdh,
        'p': camarilla_pivots.get('p'),
        'pdc': pdc,
        's3': camarilla_pivots.get('s3'),
        's4': camarilla_pivots.get('s4'),
        'pdl': pdl,
        'ma200_lower': min(ema200, sma200) if ema200 and sma200 else None,
        'ma200_higher': max(ema200, sma200) if ema200 and sma200 else None
    }

    # IMPORTANT: Filter out any levels that are None, so the strategy doesn't act on them
    levels['key_levels'] = {k: v for k, v in key_levels_for_trade.items() if v is not None}

    return levels
