import logging
from fyers_apiv3 import fyersModel
import pandas as pd

# Get a logger instance for this module
logger = logging.getLogger(__name__)

class FyersClient:
    """
    A client to handle interactions with the Fyers API v3.
    """
    def __init__(self, client_id: str, token: str, log_path=""):
        """
        Initializes the FyersClient.

        :param client_id: The API ID (or App ID) from your Fyers developer dashboard.
        :param token: A valid access token generated for the client_id.
        :param log_path: Optional path to store logs. Disabled by default.
        """
        if not token or not client_id:
            raise ValueError("Client ID and access token must be provided.")

        self.fyers = fyersModel.FyersModel(
            client_id=client_id,
            is_async=False,
            token=token,
            log_path=log_path
        )

    def get_historical_data(self, symbol: str, range_from: str, range_to: str, resolution: str = "1"):
        """
        Fetches historical candle data from Fyers.
        """
        data = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1",
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1"
        }

        response = self.fyers.history(data=data)

        if response.get("s") == "ok":
            candles = response.get('candles', [])
            if not candles:
                return pd.DataFrame()

            df = pd.DataFrame(candles)
            df.columns = ['epoch', 'open', 'high', 'low', 'close', 'volume']
            df['timestamp'] = pd.to_datetime(df['epoch'], unit='s')
            df.set_index('timestamp', inplace=True)
            return df[['open', 'high', 'low', 'close', 'volume']]
        else:
            logger.error(f"Error fetching historical data for {symbol}: {response.get('message')}")
            return None

    def get_profile(self):
        """
        Fetches the user's profile to test the API connection and token.
        """
        response = self.fyers.get_profile()
        if response.get("s") == "ok":
            return response.get('data')
        else:
            logger.error(f"Error fetching profile: {response.get('message')}")
            return None
