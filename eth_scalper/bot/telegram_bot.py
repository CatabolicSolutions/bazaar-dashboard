"""Telegram bot for user interaction and paper trading feedback"""
import asyncio
import logging
from typing import Dict
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PAPER_TRADING_MODE
from risk.limits import risk_manager
from signals.momentum import momentum_detector

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        self.application = None
        self.pending_signals = {}  # signal_id -> signal_data
        self.signal_counter = 0
    
    async def start(self):
        """Start the bot"""
        if not TELEGRAM_BOT_TOKEN:
            logger.error("No TELEGRAM_BOT_TOKEN configured")
            return
        
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("mode", self.cmd_mode))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_feedback))
        
        logger.info("Starting Telegram bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
    
    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        mode = "PAPER TRADING" if PAPER_TRADING_MODE else "LIVE TRADING"
        await update.message.reply_text(
            f"🤖 ETH Scalper Bot\n"
            f"Mode: {mode}\n\n"
            f"Commands:\n"
            f"/status - Show bot status\n"
            f"/mode - Check trading mode\n\n"
            f"I'll alert you when I detect signals."
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        risk = risk_manager.get_status()
        momentum = momentum_detector.get_stats()
        
        await update.message.reply_text(
            f"📊 Bot Status\n\n"
            f"Risk:\n"
            f"  Daily P&L: ${risk['daily_pnl']:.2f}\n"
            f"  Daily Trades: {risk['daily_trades']}\n"
            f"  Open Positions: {risk['open_positions']}\n"
            f"  Available Capital: ${risk['available_capital']:.2f}\n\n"
            f"Signals:\n"
            f"  Total Signals: {momentum['total_signals']}\n"
            f"  Recent Win Rate: {momentum['recent_win_rate']:.1%}\n"
            f"  Avg Score: {momentum['avg_score']:.1f}/10"
        )
    
    async def cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mode command"""
        mode = "📝 PAPER TRADING" if PAPER_TRADING_MODE else "💰 LIVE TRADING"
        await update.message.reply_text(f"Current mode: {mode}")
    
    async def handle_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user feedback on paper trades"""
        text = update.message.text.upper()
        
        if any(x in text for x in ['GOOD', 'YES', 'APPROVE']):
            await update.message.reply_text("✅ Feedback recorded: Good signal")
        elif any(x in text for x in ['BAD', 'NO', 'REJECT']):
            await update.message.reply_text("❌ Feedback recorded: Bad signal")
        elif any(x in text for x in ['RISKY', 'RISK']):
            await update.message.reply_text("⚠️ Feedback recorded: Too risky")
        else:
            await update.message.reply_text("Received. Use: GOOD / BAD / RISKY")
    
    async def send_signal_alert(self, signal: Dict, paper: bool = True):
        """Send signal alert to user"""
        if not self.application:
            return
        
        self.signal_counter += 1
        signal_id = self.signal_counter
        self.pending_signals[signal_id] = signal
        
        mode = "📝 PAPER" if paper else "💰 LIVE"
        direction = "📈 UP" if signal['direction'] == 'up' else "📉 DOWN"
        
        message = (
            f"{mode} SIGNAL #{signal_id}\n\n"
            f"{direction} MOMENTUM\n"
            f"Price: ${signal['price']:.2f}\n"
            f"60s Change: {signal['change_60s_pct']:+.2f}%\n"
            f"Gas: {signal['gas_gwei']:.1f} gwei\n"
            f"Score: {signal['score']}/10\n\n"
        )
        
        if paper:
            message += (
                f"Reply with:\n"
                f"✅ GOOD - Valid signal\n"
                f"❌ BAD - False positive\n"
                f"⚠️ RISKY - Too risky"
            )
        else:
            message += "Executing trade..."
        
        try:
            await self.application.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message
            )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    async def send_trade_result(self, result: Dict):
        """Send trade result"""
        if not self.application:
            return
        
        emoji = "✅" if result['pnl_usd'] > 0 else "❌"
        
        message = (
            f"{emoji} TRADE CLOSED\n\n"
            f"P&L: ${result['pnl_usd']:+.2f} ({result['pnl_pct']:+.2f}%)\n"
            f"Size: ${result['position']['size_usd']:.2f}\n"
            f"Type: {'PAPER' if result['paper'] else 'LIVE'}"
        )
        
        try:
            await self.application.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message
            )
        except Exception as e:
            logger.error(f"Failed to send result: {e}")

# Global instance
trading_bot = TradingBot()
