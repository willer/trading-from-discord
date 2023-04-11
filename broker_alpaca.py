import asyncio
import datetime
import time
import configparser
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from broker_root import broker_root
import yfinance as yf

alpacaconn_cache = {}
ticker_cache = {}

class StockStub:
    def __init__(self, symbol):
        self.symbol = symbol
        self.is_futures = 0

# declare a class to represent the IB driver
class broker_alpaca(broker_root):
    def __init__(self, bot, account):
        self.config = configparser.ConfigParser()
        self.config.read('config.ini')
        self.bot = bot
        self.account = account
        self.aconfig = self.config[account]
        self.conn = None
        self.dataconn = None

        # pick up a cached IB connection if it exists; cache lifetime is 5 mins
        alcachekey = f"{self.aconfig['key']}"
        if alcachekey in alpacaconn_cache and alpacaconn_cache[alcachekey]['time'] > time.time() - 300:
            self.conn = alpacaconn_cache[alcachekey]['conn']
            self.dataconn = alpacaconn_cache[alcachekey]['dataconn']

        if self.conn is None:
            try:
                print(f"Alpaca: Trying to connect...")
                paper = True if self.aconfig['paper'] == 'yes' else False
                self.conn = TradingClient(api_key=self.aconfig['key'], secret_key=self.aconfig['secret'], paper=paper)
                self.dataconn = StockHistoricalDataClient(api_key=self.aconfig['key'], secret_key=self.aconfig['secret'])

            except Exception as e:
                self.handle_ex(e)
                raise

            # cache the connection
            alpacaconn_cache[alcachekey] = {'conn': self.conn, 'dataconn': self.dataconn, 'time': time.time()}
            print("Alpaca: Connected")

    def get_stock(self, symbol):
        # normalization of the symbol, from TV to Alpaca form
        stock = StockStub(symbol)
        symbol = symbol.replace('1!', '')
        if symbol in ['NQ', 'ES', 'RTY']:
            stock.is_futures = 1
        elif symbol in ['YM']:
            stock.is_futures = 1
        elif symbol in ['ZN']:
            stock.is_futures = 1
        # forex futures listed at https://www.interactivebrokers.com/en/trading/cme-wti-futures.php
        elif symbol in ['M6E', 'M6A', 'M6B', 'MJY', 'MSF', 'MIR', 'MNH']:
            stock.is_futures = 1
        elif symbol in ['MCD']:
            stock.is_futures = 1
        elif symbol in ['HE']:
            stock.is_futures = 1
        elif symbol == 'DX':
            stock.is_futures = 1
        elif symbol in ['CL', 'NG']:
            stock.is_futures = 1
        elif symbol in ['GC', 'SI', 'HG']:
            stock.is_futures = 1
        else:
            stock.is_futures = 0

        return stock

    def get_price(self, symbol):
        stock = self.get_stock(symbol)

        # keep a cache of tickers to avoid repeated calls to IB, but only for 5s
        if symbol in ticker_cache and time.time() - ticker_cache[symbol]['time'] < 5:
            ticker = ticker_cache[symbol]['ticker']
        else:
            multisymbol_request_params = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
            latest_multisymbol_quotes = self.dataconn.get_stock_latest_quote(multisymbol_request_params)
            ticker = latest_multisymbol_quotes[symbol]
            ticker_cache[symbol] = {'ticker': ticker, 'time': time.time()}

        price = ticker.ask_price
        print(f"  get_price({symbol}) -> {price}")
        return price

    def get_net_liquidity(self):
        # get the current Alpaca net liquidity in USD
        net_liquidity = self.conn.get_account().last_equity
        print(f"  get_net_liquidity() -> {net_liquidity}")
        return float(net_liquidity)

    def get_position_size(self, symbol):
        # get the current Alpaca position size for this stock and this account
        position_size = 0
        for position in self.conn.get_all_positions():
            if position.symbol == symbol:
                position_size = int(position.qty)
                break
        print(f"  get_position_size({symbol}) -> {position_size}")
        return position_size


    async def set_position_size(self, symbol, amount):
        print(f"set_position_size({symbol},{amount}) acct {self.account}")

        # get the current position size
        position_size = self.get_position_size(symbol)

        # figure out how much to buy or sell
        position_variation = round(amount - position_size, 0)

        # if we need to buy or sell, do it with a limit order
        if position_variation != 0:
            price = self.get_price(symbol)
            high_limit_price = round(price * 1.005, 2)
            low_limit_price  = round(price * 0.995, 2)

            # convert position_variation to a string with no decimal places
            position_variation = int(position_variation)

            if position_variation > 0:
                limit_order_data = LimitOrderRequest(
                    symbol=symbol,
                    limit_price=high_limit_price,
                    qty=abs(position_variation),
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                    extended_hours = True
                   )
            else:
                limit_order_data = LimitOrderRequest(
                    symbol=symbol,
                    limit_price=low_limit_price,
                    qty=abs(position_variation),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    extended_hours = True
                   )

            print("  placing order: ", limit_order_data)
            trade = self.conn.submit_order(order_data=limit_order_data)
            print("    trade: ", trade)

            # wait for the order to be filled, up to 30s
            maxloops = 30
            print("    waiting for trade1: ", trade)
            trade = self.conn.get_order_by_id(trade.id)
            while trade.status in ['new','partially_filled'] and maxloops > 0:
                await asyncio.sleep(1)
                print("    waiting for trade2: ", trade)
                maxloops -= 1
                trade = self.conn.get_order_by_id(trade.id)

            # throw exception on order failure
            if trade.status not in ['filled']:
                msg = f"ORDER FAILED: set_position_size({symbol},{amount}) acct {self.account} -> {trade.status}"
                print(msg)
                self.handle_ex(msg)

            print("order filled")

    def download_data(self, symbol, end, duration, timeframe, cachedata=False):
        if end != "":
            raise Exception("Can only use blank end date")
        if timeframe != "1 day":
            raise Exception("Can only use 1 day timeframe")
        if 'Y' not in duration:
            raise Exception("Can only use years in duration, in IB format like '5 Y'")

        duration_years = int(duration.split(' ')[0])
        start = datetime.datetime.now() - datetime.timedelta(days=duration_years*365)

        request_params = StockBarsRequest(symbol_or_symbols=symbol, 
            start=start.strftime("%Y-%m-%d"), 
            timeframe = TimeFrame.Day)

        bars = self.dataconn.get_stock_bars(request_params)
        return bars.df

    def health_check(self):
        self.get_net_liquidity()
        self.get_price('SOXL')
        self.get_position_size('SOXL')
        self.get_position_size('SOXS')
