import os
import time
import json
import logging
from datetime import datetime, timedelta, date

# Import our custom modules
from src import config
from src.auth import generate_access_token
from src.fyers_client import FyersClient
from src.indicators import get_all_levels
from src.strategy import check_for_trade_signal, check_for_trailing_sl_update

TOKEN_FILE = "access_token.txt"
STRIKE_CACHE_FILE = "weekly_strike.json"

def setup_logging():
    """Configures logging to write to a file and the console."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("trading_bot.log", mode='a'),
            logging.StreamHandler()
        ]
    )

def initialize_client():
    """Handles getting a valid Fyers client, using a cached token or generating a new one."""
    access_token = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f: access_token = f.read().strip()

    if access_token:
        try:
            client = FyersClient(client_id=config.API_ID, token=access_token)
            if client.get_profile() is not None:
                logging.info("Successfully validated access token from cache.")
                return client
        except Exception as e:
            logging.error(f"Error validating token: {e}", exc_info=True)

    logging.info("Starting new authentication...")
    access_token = generate_access_token(
        client_id=config.API_ID, secret_key=config.API_SECRET, redirect_uri=config.REDIRECT_URL
    )

    if access_token:
        with open(TOKEN_FILE, 'w') as f: f.write(access_token)
        logging.info("New access token cached.")
        return FyersClient(client_id=config.API_ID, token=access_token)
    else:
        raise Exception("Fatal: Could not generate a valid access token.")

def get_previous_trading_day_data(client: FyersClient, symbol: str):
    """
    Fetches the OHLC data for the last valid trading day for a specific symbol.
    """
    logging.info(f"Attempting to fetch previous day's data for {symbol}...")
    today = date.today()
    for i in range(1, 6):
        prev_day = today - timedelta(days=i)
        prev_day_str = prev_day.strftime('%Y-%m-%d')

        data = client.get_historical_data(symbol=symbol, range_from=prev_day_str, range_to=prev_day_str, resolution="D")

        if data is not None and not data.empty:
            last_candle = data.iloc[0]
            logging.info(f"Found previous trading day on {prev_day_str} for {symbol}. H={last_candle['high']}, L={last_candle['low']}, C={last_candle['close']}")
            return {'high': last_candle['high'], 'low': last_candle['low'], 'close': last_candle['close']}

    logging.error(f"CRITICAL: Could not fetch previous day's data for {symbol} in the last 5 days.")
    return None

def get_weekly_symbols(client: FyersClient):
    """
    Determines and caches the weekly option symbols.
    """
    today = datetime.now()
    if today.weekday() == 0 and os.path.exists(STRIKE_CACHE_FILE):
        logging.info("It's Monday. Clearing weekly strike cache for the new week.")
        os.remove(STRIKE_CACHE_FILE)

    if os.path.exists(STRIKE_CACHE_FILE):
        with open(STRIKE_CACHE_FILE, 'r') as f:
            data = json.load(f)
            logging.info(f"Loaded weekly symbols from cache: {data}")
            return data['ce_symbol'], data['pe_symbol']

    if today.weekday() >= 2: # Wednesday or later
        logging.info("No strike cache found. Attempting to select new weekly strike...")

        nifty_quote_res = client.fyers.quotes({"symbols":"NSE:NIFTY50-INDEX"})
        if nifty_quote_res.get('s') != 'ok':
            logging.error("Could not fetch Nifty 50 LTP to select strike. Cannot proceed.")
            return None, None

        ltp = nifty_quote_res['d'][0]['v']['lp']
        strike = int(round(ltp / 100) * 100)

        ce_symbol = f"NSE:NIFTY{config.OPTION_EXPIRY_FORMAT}{strike}CE"
        pe_symbol = f"NSE:NIFTY{config.OPTION_EXPIRY_FORMAT}{strike}PE"

        logging.warning(f"NEW WEEKLY STRIKE SELECTED: {strike}. Symbols: {ce_symbol}, {pe_symbol}")

        with open(STRIKE_CACHE_FILE, 'w') as f:
            json.dump({'strike': strike, 'ce_symbol': ce_symbol, 'pe_symbol': pe_symbol}, f)

        return ce_symbol, pe_symbol
    else:
        logging.warning("It is Monday or Tuesday. Waiting for Wednesday to select weekly strike.")
        return None, None

def run_bot():
    """The main orchestrator function for the trading bot."""
    setup_logging()
    logging.info("Initializing trading bot...")
    client = initialize_client()

    trade_attempts = {'CE': {}, 'PE': {}}
    open_trades = {'CE': None, 'PE': None}
    ce_prev_day_data, pe_prev_day_data = None, None
    last_checked_day = None
    ce_symbol, pe_symbol = None, None

    while True:
        try:
            now = datetime.now()
            today = now.date()

            if not (time(9, 15) <= now.time() <= time(15, 30)):
                logging.info(f"Outside market hours. Waiting... Current time: {now.time()}")
                time.sleep(60)
                continue

            # Daily Setup
            if today != last_checked_day:
                logging.info(f"New trading day ({today}). Running daily setup tasks.")
                ce_symbol, pe_symbol = get_weekly_symbols(client)

                if ce_symbol and pe_symbol:
                    # **CORE LOGIC FIX**: Fetch previous day data for each option symbol individually.
                    ce_prev_day_data = get_previous_trading_day_data(client, symbol=ce_symbol)
                    pe_prev_day_data = get_previous_trading_day_data(client, symbol=pe_symbol)

                last_checked_day = today
                trade_attempts = {'CE': {}, 'PE': {}}
                logging.info("Daily setup complete. Trade attempt counters reset.")

            if not ce_prev_day_data or not pe_prev_day_data:
                logging.error("Missing critical data (levels/symbols). Waiting for next daily setup. Sleeping for 5 mins.")
                time.sleep(300)
                continue

            logging.info(f"\n{'='*20} Cycle Start: {now} {'='*20}")

            today_str = now.strftime('%Y-%m-%d')
            range_from_str = (now - timedelta(days=10)).strftime('%Y-%m-%d')

            # **CORE LOGIC FIX**: Pass the correct previous day data for each symbol.
            for symbol_type, symbol, prev_day_data in [('CE', ce_symbol, ce_prev_day_data), ('PE', pe_symbol, pe_prev_day_data)]:
                logging.info(f"--- Processing {symbol_type} ({symbol}) ---")
                candles_df = client.get_historical_data(symbol, range_from_str, today_str)

                if candles_df is None or candles_df.empty:
                    logging.warning(f"Could not fetch candle data for {symbol}. Skipping.")
                    continue

                # Pass the correct previous day data for the specific option
                levels = get_all_levels(prev_day_data, candles_df)
                current_candle = candles_df.iloc[-1].to_dict()
                current_candle['timestamp'] = candles_df.index[-1]

                if not open_trades[symbol_type]:
                    signal = check_for_trade_signal(current_candle, levels, trade_attempts[symbol_type])
                    if signal:
                        logging.warning(f"!!! NEW BUY SIGNAL FOR {symbol_type}: {signal} !!!")
                        open_trades[symbol_type] = {'entry_price': signal['entry_price'], 'sl': signal['stop_loss'], 'level_name': signal['level_name']}
                else:
                    active_trade = open_trades[symbol_type]
                    if current_candle['low'] <= active_trade['sl']:
                        logging.warning(f"--- STOP-LOSS HIT FOR {symbol_type} at {active_trade['sl']} ---")
                        level_name = active_trade.get('level_name', 'unknown')
                        trade_attempts[symbol_type][level_name] = trade_attempts[symbol_type].get(level_name, 0) + 1
                        logging.info(f"Failure count for level {level_name} is now {trade_attempts[symbol_type][level_name]}")
                        open_trades[symbol_type] = None
                    else:
                        new_sl = check_for_trailing_sl_update(current_candle['close'], active_trade['sl'], levels)
                        if new_sl > active_trade['sl']:
                            logging.warning(f"--- TRAILING SL FOR {symbol_type} UPDATED TO: {new_sl} ---")
                            active_trade['sl'] = new_sl

            logging.info(f"{'='*20} Cycle End {'='*20}")
            time.sleep(60)

        except KeyboardInterrupt:
            logging.info("Bot stopped by user.")
            break
        except Exception as e:
            logging.error(f"An unexpected error in main loop: {e}", exc_info=True)
            time.sleep(60)

if __name__ == "__main__":
    run_bot()
