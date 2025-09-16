import logging
from datetime import datetime
import os

from src.utils import setup_logging, initialize_client

def get_download_inputs():
    """Prompts the user for the parameters needed for data download."""
    logging.info("="*50)
    logging.info("Fyers Historical Data Downloader")
    logging.info("="*50)

    symbol = input("Enter the exact symbol to download (e.g., NSE:NIFTY2491224000CE): ").strip()
    if not symbol:
        raise ValueError("Execution stopped: Symbol cannot be empty.")

    while True:
        try:
            start_date_str = input("Enter the Start Date for the data (YYYY-MM-DD): ")
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            break
        except ValueError:
            logging.error("Invalid date format. Please use YYYY-MM-DD.")

    while True:
        try:
            end_date_str = input("Enter the End Date for the data (YYYY-MM-DD): ")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date < start_date:
                logging.error("End Date cannot be before the Start Date.")
                continue
            break
        except ValueError:
            logging.error("Invalid date format. Please use YYYY-MM-DD.")

    return symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def download_data():
    """Main function to orchestrate the data download process."""
    setup_logging()
    try:
        symbol, range_from, range_to = get_download_inputs()

        client = initialize_client()
        if not client:
            return

        logging.info(f"Attempting to download data for symbol '{symbol}' from {range_from} to {range_to}...")

        # Fetch the historical data from the Fyers API
        historical_data = client.get_historical_data(symbol, range_from, range_to)

        if historical_data is None or historical_data.empty:
            logging.error(f"Failed to download data for '{symbol}'. The API returned no data. Please double-check the symbol and ensure data exists for the requested period.")
            return

        # Sanitize the symbol to create a valid filename (e.g., replace ':' with '_')
        safe_filename = symbol.replace(":", "_") + ".csv"

        # Define the path to the data directory
        data_dir = "data"
        file_path = os.path.join(data_dir, safe_filename)

        # Save the DataFrame to a CSV file, including the timestamp index
        historical_data.to_csv(file_path, index=True)

        logging.info(f"Success! Data for '{symbol}' was downloaded and saved to: {file_path}")
        logging.info(f"Total candles downloaded: {len(historical_data)}")

    except (ValueError, KeyboardInterrupt) as e:
        logging.error(f"Execution stopped: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during the download process: {e}", exc_info=True)

if __name__ == "__main__":
    download_data()
