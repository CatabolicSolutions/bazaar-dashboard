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

# Signal Thresholds
MIN_PRICE_MOVEMENT_PCT = 0.4  # 0.4% in 60 seconds
MAX_GAS_GWEI = 30
MIN_PROFIT_PCT = 0.5  # After gas costs
MIN_SIGNAL_SCORE = 7  # Out of 10

# Tokens
ETH_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
USDC_ADDRESS = '0xA0b86a33E6441e0A421e56E4773C3C4b0Db7E5b0'

# Validate required config
def validate_config():
    """Check all required config is present"""
    required = {
        '1INCH_API_KEY': INCH_API_KEY,
        'ALCHEMY_API_KEY': ALCHEMY_API_KEY,
        'ALCHEMY_URL': ALCHEMY_URL,
        'WALLET_ADDRESS': WALLET_ADDRESS,
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
