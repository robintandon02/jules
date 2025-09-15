from datetime import time

def _get_allowed_sl(price: float) -> float:
    """Determines the maximum allowed stop-loss based on the option's price."""
    if price < 200:
        return 10.0
    elif 200 <= price < 300:
        return 15.0
    elif 300 <= price < 400:
        return 20.0
    elif 400 <= price < 500:
        return 30.0
    else:  # price >= 500
        return 40.0

def _check_ema_filter(candle: dict, ema21: float, is_morning_session: bool) -> bool:
    """
    Checks if the 21 EMA filter condition is met as per the strategy rules.
    """
    if ema21 is None:
        return False  # Cannot trade if EMA is not available

    price = candle['close']

    # Reversal Scenario: 21 EMA is "far" above the price
    if ema21 > price:
        if (ema21 - price) > 10:
            return True

    # Trending Scenario: 21 EMA is "close" below the price
    else:  # ema21 <= price
        if (price - ema21) < 10:
            return True
        # Morning exception allows for a far EMA in a trending scenario
        elif is_morning_session:
            return True

    return False

def check_for_trade_signal(current_candle: dict, levels: dict, trade_attempts: dict):
    """
    Checks for a trade signal based on the v3 strategy rules.

    :param current_candle: Dict with 'open', 'high', 'low', 'close', 'timestamp'.
                           Timestamp must be a datetime object.
    :param levels: Dict of all calculated levels from indicators.py.
    :param trade_attempts: Dict tracking failed trades for each level, e.g., {'S3': 1}.
    :return: A signal dict if a trade is found, otherwise None.
    """
    price = current_candle['close']
    ema21 = levels.get('ema21')

    candle_time = current_candle['timestamp'].time()
    is_morning_session = (time(9, 15) <= candle_time <= time(9, 30))

    key_levels_for_trade = levels.get('key_levels', {})

    for level_name, level_price in key_levels_for_trade.items():
        if level_price is None:
            continue

        # Risk Management: Skip level if max attempts reached
        if trade_attempts.get(level_name, 0) >= 3:
            continue

        is_bounce_trade = False
        is_breakout_trade = False

        # Core Principle: Determine if level is Support or Resistance
        if price > level_price:
            # Level is SUPPORT, look for a BOUNCE
            if current_candle['low'] <= level_price and current_candle['close'] > level_price:
                is_bounce_trade = True
        else:  # price <= level_price
            # Level is RESISTANCE, look for a BREAKOUT
            if current_candle['open'] < level_price and current_candle['close'] > level_price:
                is_breakout_trade = True

        if is_bounce_trade or is_breakout_trade:
            # A potential signal is found, now check filters

            # 1. EMA Filter
            if not _check_ema_filter(current_candle, ema21, is_morning_session):
                continue  # EMA filter failed, check next level

            # 2. Stop-Loss Filter
            allowed_sl = _get_allowed_sl(price)
            actual_risk = price - current_candle['low']
            # The trade is valid, but may require immediate action if risk is high
            immediate_entry = actual_risk > allowed_sl

            # If all filters pass, return the trade signal
            return {
                'signal': 'BUY',
                'entry_price': price,
                'stop_loss': current_candle['low'],
                'entry_type': 'bounce' if is_bounce_trade else 'breakout',
                'level_name': level_name,
                'level_price': level_price,
                'immediate_entry_required': immediate_entry,
                'timestamp': current_candle['timestamp']
            }

    return None  # No signal found after checking all levels

def check_for_trailing_sl_update(current_price: float, current_sl: float, levels: dict) -> float:
    """
    Checks if the trailing stop-loss needs to be updated.
    The trailing SL moves up to the next key resistance/target level as the price rises.
    """
    new_sl = current_sl

    # These are the potential targets to trail the SL to.
    trailing_targets = {
        'r3': levels['key_levels'].get('r3'),
        'r4': levels['key_levels'].get('r4'),
        'pdh': levels['key_levels'].get('pdh'),
        'p': levels['key_levels'].get('p'),
        'pdc': levels['key_levels'].get('pdc'),
        'ma200_higher': levels['key_levels'].get('ma200_higher')
    }

    # Sort the valid target levels by price to ensure we trail upwards correctly
    sorted_targets = sorted([v for v in trailing_targets.values() if v is not None])

    for level_price in sorted_targets:
        # If the current price has crossed a target level, and that level is
        # higher than our current stop-loss, update the SL to that level.
        if current_price > level_price and level_price > new_sl:
            new_sl = level_price

    return new_sl
