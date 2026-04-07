"""Structured logging for ETH scalper"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Create logs directory
LOG_DIR = Path(__file__).parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, 'type'):
            log_data['type'] = record.type
        if hasattr(record, 'data'):
            log_data['data'] = record.data
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

# Configure loggers
def setup_logging():
    """Setup structured logging"""
    
    # Main logger
    logger = logging.getLogger('eth_scalper')
    logger.setLevel(logging.INFO)
    
    # Console handler - human readable
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler - JSON structured
    file_handler = logging.FileHandler(LOG_DIR / 'trades.jsonl')
    file_handler.setLevel(logging.INFO)
    json_formatter = JSONFormatter()
    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)
    
    # Error log
    error_handler = logging.FileHandler(LOG_DIR / 'errors.log')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(console_formatter)
    logger.addHandler(error_handler)
    
    return logger

# Global logger instance
logger = setup_logging()

def log_signal(signal: dict, executed: bool, reason: str = None):
    """Log a signal (even rejected ones)"""
    logger.info(
        f"Signal: {signal.get('direction', 'unknown')} @ ${signal.get('price', 0):.2f}",
        extra={
            'type': 'signal',
            'data': {
                'signal': signal,
                'executed': executed,
                'reason': reason
            }
        }
    )

def log_trade(entry: dict, exit_data: dict = None):
    """Log a trade entry or exit"""
    trade_type = 'exit' if exit_data else 'entry'
    logger.info(
        f"Trade {trade_type}: {entry.get('id', 'unknown')}",
        extra={
            'type': 'trade',
            'data': {
                'entry': entry,
                'exit': exit_data
            }
        }
    )

def log_feedback(signal_id: int, feedback: str):
    """Log user feedback"""
    logger.info(
        f"Feedback on signal {signal_id}: {feedback}",
        extra={
            'type': 'feedback',
            'data': {
                'signal_id': signal_id,
                'feedback': feedback
            }
        }
    )

def log_error(error: Exception, context: dict = None):
    """Log an error with context"""
    logger.error(
        f"Error: {str(error)}",
        extra={
            'type': 'error',
            'data': context or {}
        },
        exc_info=True
    )
