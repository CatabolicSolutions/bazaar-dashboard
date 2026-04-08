"""Configuration loader - handles env vars safely"""
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# API Keys
INCH_API_KEY = os.getenv('1INCH_API_KEY')
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
ALCHEMY_URL = os.getenv('ALCHEMY_URL')

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

# Rate Limits
MAX_INCH_REQUESTS_PER_DAY = 900  # Buffer below 1000 limit

# Signal Thresholds - ADJUSTED FOR MORE FREQUENT TRADES
MIN_PRICE_MOVEMENT_PCT = 0.15  # 0.15% in 60 seconds (was 0.4%)
MAX_GAS_GWEI = 50  # Increased from 30
MIN_PROFIT_PCT = 0.3  # After gas costs (was 0.5%)
MIN_PROFIT_AFTER_GAS_PERCENT = 0.15  # Minimum viable trade (was 0.3%)
MIN_SIGNAL_SCORE = 5  # Out of 10 (was 7)

# Status Reporting
STATUS_HEARTBEAT_MINUTES = 5  # Send status update every N minutes
PRICE_ALERT_THRESHOLD = 0.5  # Alert on 0.5% moves even if not trading

# Execution Parameters
MAX_SLIPPAGE_PERCENT = 0.5
COOLDOWN_AFTER_LOSS_SECONDS = 300  # 5 min pause after losses
MAX_DAILY_TRADES = 20
MAX_OPEN_POSITIONS = 2
HOLD_TIME_MIN_SECONDS = 30
HOLD_TIME_MAX_SECONDS = 300  # 5 minutes

# Tokens
ETH_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
WETH_ADDRESS = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'
USDC_ADDRESS = '0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'

# Validate required config
def validate_config():
    """Check all required config is present"""
    required = {
        '1INCH_API_KEY': INCH_API_KEY,
        'ALCHEMY_API_KEY': ALCHEMY_API_KEY,
        'ALCHEMY_URL': ALCHEMY_URL,
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
