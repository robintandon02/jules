import os
import logging
from datetime import date, timedelta

from src import config
from src.auth import generate_access_token
from src.fyers_client import FyersClient

TOKEN_FILE = "access_token.txt"

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
    """
    Handles getting a valid Fyers client, using a cached token or generating a new one.
    This function is shared between the live bot and the backtester.
    """
    access_token = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            access_token = f.read().strip()

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
        with open(TOKEN_FILE, 'w') as f:
            f.write(access_token)
        logging.info("New access token cached.")
        return FyersClient(client_id=config.API_ID, token=access_token)
    else:
        raise Exception("Fatal: Could not generate a valid access token.")

def get_last_trading_day_data(client: FyersClient, symbol: str, base_date: date):
    """
    Fetches the OHLC data for the last valid trading day before a given base_date.
    """
    logging.info(f"Attempting to find last trading day's data for {symbol} before {base_date}...")
    for i in range(1, 6):
        # Look back up to 5 days to find the last trading day
        prev_day = base_date - timedelta(days=i)
        prev_day_str = prev_day.strftime('%Y-%m-%d')

        data = client.get_historical_data(
            symbol=symbol, range_from=prev_day_str, range_to=prev_day_str, resolution="D"
        )

        if data is not None and not data.empty:
            last_candle = data.iloc[0]
            logging.info(f"Found previous trading day on {prev_day_str} for {symbol}. H={last_candle['high']}, L={last_candle['low']}, C={last_candle['close']}")
            return {'high': last_candle['high'], 'low': last_candle['low'], 'close': last_candle['close']}

    logging.error(f"CRITICAL: Could not fetch previous day's data for {symbol} in the last 5 days before {base_date}.")
    return None
