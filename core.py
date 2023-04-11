import configparser
from broker_root import broker_root
from broker_ibkr import broker_ibkr
from broker_alpaca import broker_alpaca

# exported globals: config, aconfig, account, datafolder, driver

bot = 'live'

config = configparser.ConfigParser()
config.read('config.ini')

account = config['DEFAULT']['main-account']
datafolder = config['DEFAULT']['data-folder']

aconfig = config[account]
if aconfig['driver'] == 'ibkr':
    driver = broker_ibkr(bot, account)
elif aconfig['driver'] == 'alpaca':
    driver = broker_alpaca(bot, account)
else:
    raise Exception("Unknown driver: " + aconfig['driver'])
