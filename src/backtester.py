import logging
import pandas as pd
from datetime import datetime, timedelta

# Import shared and core logic modules
from src.utils import setup_logging, initialize_client, get_last_trading_day_data
from src.indicators import get_all_levels
from src.strategy import check_for_trade_signal, check_for_trailing_sl_update

def get_backtest_inputs():
    """
    Prompts the user for backtest parameters, including a start and end date.
    """
    logging.info("="*50)
    logging.info("Custom Period Backtester Setup")
    logging.info("="*50)

    while True:
        try:
            start_date_str = input("Enter the Start Date for the backtest (YYYY-MM-DD): ")
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            break
        except ValueError:
            logging.error("Invalid date format. Please use YYYY-MM-DD.")

    while True:
        try:
            end_date_str = input("Enter the End Date for the backtest (YYYY-MM-DD): ")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date < start_date:
                logging.error("End Date cannot be before the Start Date.")
                continue
            break
        except ValueError:
            logging.error("Invalid date format. Please use YYYY-MM-DD.")

    logging.info("Please provide the exact option symbols for the chosen period.")
    ce_symbol = input(f"Enter the Call (CE) symbol: ")
    pe_symbol = input(f"Enter the Put (PE) symbol: ")

    if not ce_symbol or not pe_symbol:
        raise ValueError("Execution stopped: Both CE and PE symbols must be provided.")

    return start_date, end_date, ce_symbol, pe_symbol

def fetch_backtest_data(client, ce_symbol, pe_symbol, start_date, end_date):
    """Fetches all historical data required for the backtest period."""
    logging.info("-" * 20 + " Fetching Historical Data " + "-" * 20)
    start_date_str, end_date_str = start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
    logging.info(f"Data range for 1-min candles: {start_date_str} to {end_date_str}")

    ce_prev_day_data = get_last_trading_day_data(client, symbol=ce_symbol, base_date=start_date)
    ce_candles = client.get_historical_data(ce_symbol, range_from=start_date_str, range_to=end_date_str)

    pe_prev_day_data = get_last_trading_day_data(client, symbol=pe_symbol, base_date=start_date)
    pe_candles = client.get_historical_data(pe_symbol, range_from=start_date_str, range_to=end_date_str)

    if ce_prev_day_data is None or pe_prev_day_data is None or ce_candles is None or pe_candles is None or ce_candles.empty or pe_candles.empty:
        raise Exception("Failed to fetch all required historical data for the given symbols and date range. Please check if the symbols are correct and data exists for the period.")
    logging.info("Successfully fetched all required historical data.")

    return {'ce': {'prev_day': ce_prev_day_data, 'candles': ce_candles}, 'pe': {'prev_day': pe_prev_day_data, 'candles': pe_candles}}

def run_simulation(backtest_data):
    """The core backtesting engine. Iterates through data and applies the strategy."""
    logging.info("-" * 20 + " Running Simulation " + "-" * 20)
    portfolio = {'CE': {'trades': [], 'pnl': 0.0}, 'PE': {'trades': [], 'pnl': 0.0}}
    open_trades = {'CE': None, 'PE': None}

    all_ce_candles, all_pe_candles = backtest_data['ce']['candles'], backtest_data['pe']['candles']
    unique_dates = sorted(all_ce_candles.index.normalize().unique())

    for i, day_date in enumerate(unique_dates):
        logging.info(f"--- Simulating Day: {day_date.date()} ---")
        trade_attempts = {'CE': {}, 'PE': {}}

        if i == 0:
            ce_prev_day_data, pe_prev_day_data = backtest_data['ce']['prev_day'], backtest_data['pe']['prev_day']
        else:
            prev_day_date = unique_dates[i-1]
            prev_ce_day_candles = all_ce_candles[all_ce_candles.index.date == prev_day_date.date()]
            prev_pe_day_candles = all_pe_candles[all_pe_candles.index.date == prev_day_date.date()]
            ce_prev_day_data = {'high': prev_ce_day_candles['high'].max(), 'low': prev_ce_day_candles['low'].min(), 'close': prev_ce_day_candles['close'].iloc[-1]}
            pe_prev_day_data = {'high': prev_pe_day_candles['high'].max(), 'low': prev_pe_day_candles['low'].min(), 'close': prev_pe_day_candles['close'].iloc[-1]}

        prev_day_map = {'CE': ce_prev_day_data, 'PE': pe_prev_day_data}
        day_ce_candles = all_ce_candles[all_ce_candles.index.date == day_date.date()]
        day_pe_candles = all_pe_candles[all_pe_candles.index.date == day_date.date()]

        day_candles = pd.concat([day_ce_candles.assign(symbol_type='CE'), day_pe_candles.assign(symbol_type='PE')]).sort_index()

        for timestamp, candle in day_candles.iterrows():
            symbol_type = candle['symbol_type']
            current_candle = candle.to_dict()

            hist_candles = all_ce_candles.loc[:timestamp] if symbol_type == 'CE' else all_pe_candles.loc[:timestamp]
            levels = get_all_levels(prev_day_map[symbol_type], hist_candles)

            if open_trades[symbol_type] is None:
                signal = check_for_trade_signal(current_candle, levels, trade_attempts.get(symbol_type, {}))
                if signal:
                    trade = {'entry_time': timestamp, 'entry_price': signal['entry_price'], 'stop_loss': signal['stop_loss'], 'type': signal['entry_type'], 'level_name': signal['level_name'], 'status': 'OPEN'}
                    open_trades[symbol_type] = trade
                    portfolio[symbol_type]['trades'].append(trade)
                    logging.warning(f"NEW TRADE ({symbol_type}) at {timestamp}: Entered at {trade['entry_price']:.2f}, SL at {trade['stop_loss']:.2f}")
            else:
                active_trade = open_trades[symbol_type]
                if current_candle['low'] <= active_trade['stop_loss']:
                    active_trade.update({'exit_time': timestamp, 'exit_price': active_trade['stop_loss'], 'pnl': active_trade['stop_loss'] - active_trade['entry_price'], 'status': 'STOPPED_OUT'})
                    portfolio[symbol_type]['pnl'] += active_trade['pnl']
                    logging.warning(f"TRADE STOPPED OUT ({symbol_type}) at {timestamp}: Exited at {active_trade['exit_price']:.2f} for P&L of {active_trade['pnl']:.2f}")
                    trade_attempts.setdefault(symbol_type, {})[active_trade['level_name']] = trade_attempts.get(symbol_type, {}).get(active_trade['level_name'], 0) + 1
                    open_trades[symbol_type] = None
                else:
                    new_sl = check_for_trailing_sl_update(current_candle['close'], active_trade['stop_loss'], levels)
                    if new_sl > active_trade['stop_loss']:
                        active_trade['stop_loss'] = new_sl
                        logging.info(f"SL TRAILED ({symbol_type}) to {new_sl:.2f} at {timestamp}")
    return portfolio

def generate_report(portfolio_results):
    """Generates and prints a summary report of the backtest performance."""
    logging.info("\n" + "="*25 + " Backtest Performance Report " + "="*25)

    ce_trades = portfolio_results['CE']['trades']
    pe_trades = portfolio_results['PE']['trades']
    all_trades = ce_trades + pe_trades

    for trade in all_trades:
        if trade['status'] == 'OPEN':
            trade['pnl'] = 0
            trade['exit_time'], trade['exit_price'] = 'N/A', 'N/A'
            trade['status'] = 'OPEN_AT_END'

    total_pnl = portfolio_results['CE']['pnl'] + portfolio_results['PE']['pnl']
    total_trades = len(all_trades)
    winning_trades = sum(1 for trade in all_trades if trade.get('pnl', 0) > 0)
    losing_trades = sum(1 for trade in all_trades if trade.get('pnl', 0) < 0)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    logging.info(f"""
    --- Overall Performance ---
    Total P&L:      {total_pnl:.2f}
    Total Trades:   {total_trades}
    Winning Trades: {winning_trades}
    Losing Trades:  {losing_trades}
    Win Rate:       {win_rate:.2f}%
    """)

    if all_trades:
        logging.info("\n" + "-"*28 + " Trade Log " + "-"*28)
        for trade in ce_trades: trade['symbol'] = 'CE'
        for trade in pe_trades: trade['symbol'] = 'PE'
        sorted_trades = sorted(all_trades, key=lambda x: x['entry_time'])

        for i, trade in enumerate(sorted_trades):
            logging.info(
                f"\n  Trade #{i+1} ({trade['symbol']}):\n"
                f"    - Entry: {trade['entry_time']} at {trade['entry_price']:.2f} (Type: {trade['type']}, Level: {trade['level_name']})\n"
                f"    - Exit:  {trade['exit_time']} at {trade['exit_price']}\n"
                f"    - P&L:   {trade.get('pnl', 0):.2f}\n"
                f"    - Status: {trade['status']}"
            )
    else:
        logging.info("No trades were taken during this period.")
    logging.info("="*78)

def run_backtest():
    """Main function to orchestrate the single-week backtest."""
    setup_logging()
    try:
        start_date, end_date, ce_symbol, pe_symbol = get_backtest_inputs()
        client = initialize_client()
        if not client: return

        backtest_data = fetch_backtest_data(client, ce_symbol, pe_symbol, start_date, end_date)
        portfolio_results = run_simulation(backtest_data)
        generate_report(portfolio_results)

    except (ValueError, KeyboardInterrupt) as e:
        logging.error(f"Execution stopped: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    run_backtest()
