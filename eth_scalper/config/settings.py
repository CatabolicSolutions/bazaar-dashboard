"""Configuration loader - handles env vars safely"""
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# RPC / API
INCH_API_KEY = os.getenv('1INCH_API_KEY')
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
ALCHEMY_URL = os.getenv('ALCHEMY_URL')
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
CHAIN_ID = int(os.getenv('CHAIN_ID', '8453'))
CHAIN_NAME = os.getenv('CHAIN_NAME', 'base')

# Wallet
WALLET_ADDRESS = os.getenv('WALLET_ADDRESS')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Trading Config
INITIAL_CAPITAL_USD = float(os.getenv('INITIAL_CAPITAL_USD', '150'))
MAX_POSITION_USD = float(os.getenv('MAX_POSITION_USD', '75'))
MAX_DAILY_LOSS_USD = float(os.getenv('MAX_DAILY_LOSS_USD', '15'))
PAPER_TRADING_MODE = os.getenv('PAPER_TRADING_MODE', 'true').lower() == 'true'

# Bloc compounding directive
BLOC_PRIMARY_SYMBOLS = [s.strip().upper() for s in os.getenv('BLOC_PRIMARY_SYMBOLS', 'ETH,BTC').split(',') if s.strip()]
BLOC_COMP_MODE = os.getenv('BLOC_COMP_MODE', 'volatility_capture')
BLOC_MIN_PRICE_MOVEMENT_PCT = float(os.getenv('BLOC_MIN_PRICE_MOVEMENT_PCT', '0.10'))
BLOC_MIN_NET_PROFIT_PCT = float(os.getenv('BLOC_MIN_NET_PROFIT_PCT', '0.20'))
BLOC_MIN_SIGNAL_SCORE = int(os.getenv('BLOC_MIN_SIGNAL_SCORE', '4'))
BLOC_HARD_STOP_LOSS_PCT = float(os.getenv('BLOC_HARD_STOP_LOSS_PCT', '0.10'))
BLOC_MAX_HOLD_SECONDS = int(os.getenv('BLOC_MAX_HOLD_SECONDS', '180'))
BLOC_MAX_DAILY_TRADES = int(os.getenv('BLOC_MAX_DAILY_TRADES', '30'))
BLOC_MAX_CONCURRENT_POSITIONS = int(os.getenv('BLOC_MAX_CONCURRENT_POSITIONS', '1'))
BLOC_MAX_SLIPPAGE_PERCENT = float(os.getenv('BLOC_MAX_SLIPPAGE_PERCENT', '0.35'))
BLOC_MIN_LIQUIDITY_USD = float(os.getenv('BLOC_MIN_LIQUIDITY_USD', '25'))
BLOC_SIGNAL_LOOKBACK_SECONDS = int(os.getenv('BLOC_SIGNAL_LOOKBACK_SECONDS', '60'))

# Rate Limits
MAX_INCH_REQUESTS_PER_DAY = 900  # Buffer below 1000 limit

# Signal Thresholds - aligned to compounding directive
MIN_PRICE_MOVEMENT_PCT = BLOC_MIN_PRICE_MOVEMENT_PCT
MAX_GAS_GWEI = 50
MIN_PROFIT_PCT = BLOC_MIN_NET_PROFIT_PCT
MIN_PROFIT_AFTER_GAS_PERCENT = BLOC_MIN_NET_PROFIT_PCT
MIN_SIGNAL_SCORE = BLOC_MIN_SIGNAL_SCORE

# Status Reporting
STATUS_HEARTBEAT_MINUTES = 5  # Send status update every N minutes
PRICE_ALERT_THRESHOLD = 0.5  # Alert on 0.5% moves even if not trading

# Execution Parameters
MAX_SLIPPAGE_PERCENT = BLOC_MAX_SLIPPAGE_PERCENT
COOLDOWN_AFTER_LOSS_SECONDS = 60
MAX_DAILY_TRADES = BLOC_MAX_DAILY_TRADES
MAX_OPEN_POSITIONS = BLOC_MAX_CONCURRENT_POSITIONS
AUTO_MANUAL_BUY_FALLBACK_SECONDS = int(os.getenv('AUTO_MANUAL_BUY_FALLBACK_SECONDS', '120'))
HOLD_TIME_MIN_SECONDS = 15
HOLD_TIME_MAX_SECONDS = BLOC_MAX_HOLD_SECONDS

# Tokens and Base trading universe
ETH_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
WETH_ADDRESS = os.getenv('WETH_ADDRESS', '0x4200000000000000000000000000000000000006')
USDC_ADDRESS = os.getenv('USDC_ADDRESS', '0x833589fCD6EDB6E08f4c7C32D4f71b54bdA02913')
CBETH_ADDRESS = os.getenv('CBETH_ADDRESS', '0x2Ae3F1Ec7F1F5012CFEab0185bfcbB5dA0b3C0b8')
CBBTC_ADDRESS = os.getenv('CBBTC_ADDRESS', '0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf')

BASE_ASSET_UNIVERSE = [
    {
        'symbol': 'ETH',
        'coingecko_id': 'ethereum',
        'base_token': WETH_ADDRESS,
        'quote_token': USDC_ADDRESS,
        'priority': 1,
        'enabled': 'ETH' in BLOC_PRIMARY_SYMBOLS,
    },
    {
        'symbol': 'BTC',
        'coingecko_id': 'bitcoin',
        'base_token': CBBTC_ADDRESS,
        'quote_token': USDC_ADDRESS,
        'priority': 2,
        'enabled': 'BTC' in BLOC_PRIMARY_SYMBOLS,
    },
    {
        'symbol': 'cbETH',
        'coingecko_id': 'coinbase-wrapped-staked-eth',
        'base_token': CBETH_ADDRESS,
        'quote_token': USDC_ADDRESS,
        'priority': 99,
        'enabled': False,
    },
]

# Validate required config
def validate_config():
    """Check all required config is present"""
    required = {
        '1INCH_API_KEY': INCH_API_KEY,
        'ALCHEMY_API_KEY': ALCHEMY_API_KEY,
        'ALCHEMY_URL': ALCHEMY_URL,
        'BASE_RPC_URL': BASE_RPC_URL,
        'WALLET_ADDRESS': WALLET_ADDRESS,
        'PRIVATE_KEY': PRIVATE_KEY,
    }
    
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(f"Missing required config: {', '.join(missing)}")
    
    return True

# Request tracking (in-memory, resets on restart)
class RateLimiter:
    def __init__(self):
        self.inch_requests_today = 0
        self.last_reset = None
    
    def can_make_inch_request(self):
        """Check if we can make another 1inch request"""
        return self.inch_requests_today < MAX_INCH_REQUESTS_PER_DAY
    
    def record_inch_request(self):
        """Record a 1inch request"""
        self.inch_requests_today += 1
        return self.inch_requests_today
    
    def get_status(self):
        """Get current rate limit status"""
        return {
            'inch_requests_today': self.inch_requests_today,
            'inch_limit': MAX_INCH_REQUESTS_PER_DAY,
            'remaining': MAX_INCH_REQUESTS_PER_DAY - self.inch_requests_today
        }

rate_limiter = RateLimiter()
