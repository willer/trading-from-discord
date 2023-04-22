#!/usr/bin/python3

import datetime
import re
import sys
import configparser
from dateutil.parser import parse as parse_date

from broker_root import broker_root
from broker_ibkr import broker_ibkr
from broker_alpaca import broker_alpaca

config = configparser.ConfigParser()
config.read('config.ini')

# figure out what account list to use, if any is specified
accountlist = config[f"DEFAULT"]['accounts']
accounts = accountlist.split(",")

if len(sys.argv) >= 2 and sys.argv[1] == "-h":
    print("Usage: " + sys.argv[0] + " [parameters]")
    print("  parameters with their defaults:")
    print("    light=2 ")
    print("    regular=3 ")
    print("    lotto=2")
    print("    allow_fill_above_message=0.5")
    exit()


for i in range(2, len(sys.argv)):
    param = sys.argv[i]
    print("Parameter: " + param)
    if param.startswith("light="):
        light = int(param[6:])
    elif param.startswith("regular="):
        regular = int(param[8:])
    elif param.startswith("lotto="):
        lotto = int(param[6:])
    elif param.startswith("allow_fill_above_message="):
        allow_fill_above_message = float(param[25:])

def parse_flexible_date(date_str):
    try:
        # Set dayfirst=True to interpret the day as the first component of the date
        parsed_date = parse_date(date_str, dayfirst=True)
        return parsed_date
    except ValueError:
        # Handle invalid date format
        return None

# Example messages:
# Light ES 4130C fill 5.75 @here
# Took Lotto SPX 4090 Calls @here
# Light SPX 4105P fill 4.20 @here
# QQQ 13/April 315P fill 2.50 light as well @here
# SPY 14/April 408P fill 3.30 light will add more if go higher to 410 @here
# MSFT May/5 280 puts $6.10 light 2 contract for now @here
# AAPL 14/APRIL 165P fill 2.15 @here light
# SPX 3800P May 18 fill $28.20 @here
# Eyeing SPX 4115 Calls not the best setup so going with a couple contracts at 7.60 with SL 4104 (RISKY) @here 
# Risky but AAPL 165C 14/April fill .48 @here last trade for the day pretty much, will come back later if i see any good scalp
# Taking a STAB SPX 4090C fill  4.80 pleas go light @here


while True:
    message = input("Enter message: ")
    if message == "":
        break
    expiry = datetime.date.today() + datetime.timedelta(days=1)

    # interpreted buy parameters
    symbol = None
    strike = None
    expected_fill = None
    put_call = None

    for account in accounts:

        aconfig = config[account]
        # preference parameters
        light = 2
        if 'light' in aconfig:
            light = int(aconfig['light'])

        regular = 3
        if 'regular' in aconfig:
            regular = int(aconfig['regular'])

        lotto = 2
        if 'lotto' in aconfig:
            lotto = int(aconfig['lotto'])

        allow_fill_pct_above_message = 0.15
        if 'allow_fill_pct_above_message' in aconfig:
            allow_fill_pct_above_message = float(aconfig['allow_fill_pct_above_message'])

        use_options = 'yes'
        if 'use_options' in aconfig:
            use_options = aconfig['use_options']
        if use_options != 'yes':
            continue

        contracts = regular

        words = message.split()
        for i in range(0, len(words)):
            word = words[i].lower()
            if word.lower() == "light":
                contracts = light
            elif word.lower() == "regular":
                contracts = regular
            elif word.lower() in ["calls","call"]:
                put_call = "C"
            elif word.lower() in ["puts","put"]:
                put_call = "P"
            elif word.lower() == "lotto":
                contracts = lotto
            elif word in ["es","nq","spx","spxw","spy","qqq","msft","aapl","amd","tsla","amzn","goog","googl","fb","nvda","nflx","intc","csco","adbe","baba","bidu","pypl","ma"]:
                symbol = word.upper()
            elif re.match("^[0-9]+c$", word):
                put_call = "C"
                strike = float(word[:-1])
            elif re.match("^[0-9]+p$",word):
                put_call = "P"
                strike = float(word[:-1])
            elif re.match("^[0-9]+$",word) and strike is None:
                strike = float(word)
            elif re.match("^[0-9.]+$",word):
                expected_fill = float(word)
            elif re.match("^\\$[0-9.]+$",word):
                expected_fill = float(word[1:])
            elif re.match("^[0-9]+/[a-z][a-z]+$",word):
                expiry = parse_flexible_date(word)
            elif re.match("^[a-z][a-z]+/[0-9]+$",word):
                expiry = parse_flexible_date(word)
            #else:
            #    print("Unknown word: " + word)

        if symbol is None:
            print("No symbol found")
            break
        if strike is None:
            print("No strike found")
            break
        if put_call is None:
            print("No put_call found")
            break
        print(f"ACCOUNT: {account}")

        if contracts == 0:
            print("No order")
            continue

        driver: broker_root = None
        if aconfig['driver'] == 'ibkr':
            driver = broker_ibkr('live', account)
        elif aconfig['driver'] == 'alpaca':
            driver = broker_alpaca('live', account)
        else:
            raise Exception("Unknown driver: " + aconfig['driver'])

        if expected_fill is None:
            # example: get_price_opt('SPY', datetime.date.today, 280, 'P')
            expected_fill = driver.get_price_opt(symbol, expiry, strike, put_call)

        max_fill = driver.x_round(expected_fill * (1 + allow_fill_pct_above_message), 10)

        print(f"symbol={symbol} strike={strike} put_call={put_call} expiry={expiry} expected_fill={expected_fill} contracts={contracts}")

        # example: buy_opt('SPY', datetime.date.today, 280, 'P', 1, 1.35)
        driver.buy_opt(symbol, expiry, strike, put_call, contracts, max_fill)


    max_fill = None
    if expected_fill is not None:
        max_fill = round(expected_fill * (1 + allow_fill_pct_above_message), 1)


    
