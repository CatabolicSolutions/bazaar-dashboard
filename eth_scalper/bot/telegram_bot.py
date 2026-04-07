"""Telegram bot for user interaction and paper trading feedback"""
import asyncio
import logging
from typing import Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PAPER_TRADING_MODE
from risk.limits import risk_manager
from signals.momentum import momentum_detector
from execution.trade_manager import trade_manager

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
        self.bot_paused = False
        self.user_feedback = {}  # signal_id -> feedback
    
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
        self.application.add_handler(CommandHandler("stop", self.cmd_stop))
        self.application.add_handler(CommandHandler("resume", self.cmd_resume))
        self.application.add_handler(CommandHandler("positions", self.cmd_positions))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
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
        status = "🛑 PAUSED" if self.bot_paused else "✅ RUNNING"
        
        await update.message.reply_text(
            f"🤖 ETH Scalper Bot\n"
            f"Mode: {mode}\n"
            f"Status: {status}\n\n"
            f"Commands:\n"
            f"/status - Show bot status\n"
            f"/mode - Check trading mode\n"
            f"/positions - Open positions\n"
            f"/stop - Pause trading\n"
            f"/resume - Resume trading\n\n"
            f"I'll alert you when I detect signals."
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        risk = risk_manager.get_status()
        momentum = momentum_detector.get_stats()
        trades = trade_manager.get_stats()
        
        status = "🛑 PAUSED" if self.bot_paused else "✅ RUNNING"
        
        await update.message.reply_text(
            f"📊 Bot Status: {status}\n\n"
            f"Risk:\n"
            f"  Daily P&L: ${risk['daily_pnl']:.2f}\n"
            f"  Daily Trades: {risk['daily_trades']}\n"
            f"  Open Positions: {risk['open_positions']}\n"
            f"  Available Capital: ${risk['available_capital']:.2f}\n\n"
            f"Signals:\n"
            f"  Total Signals: {momentum['total_signals']}\n"
            f"  Recent Win Rate: {momentum['recent_win_rate']:.1%}\n"
            f"  Avg Score: {momentum['avg_score']:.1f}/10\n\n"
            f"Trades:\n"
            f"  Total: {trades['total_trades']}\n"
            f"  Win Rate: {trades['win_rate']:.1%}\n"
            f"  Total P&L: ${trades['total_pnl']:.2f}"
        )
    
    async def cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mode command"""
        mode = "📝 PAPER TRADING" if PAPER_TRADING_MODE else "💰 LIVE TRADING"
        await update.message.reply_text(f"Current mode: {mode}")
    
    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command"""
        self.bot_paused = True
        await update.message.reply_text("🛑 Bot paused. No new trades will be executed.")
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command"""
        self.bot_paused = False
        await update.message.reply_text("✅ Bot resumed. Trading active.")
    
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command"""
        positions = trade_manager.get_open_positions()
        
        if not positions:
            await update.message.reply_text("No open positions.")
            return
        
        message = "📊 Open Positions:\n\n"
        for pos in positions:
            message += (
                f"ID: {pos.id}\n"
                f"Direction: {pos.direction.upper()}\n"
                f"Entry: ${pos.entry_price:.2f}\n"
                f"Target: ${pos.target_price:.2f}\n"
                f"Stop: ${pos.stop_price:.2f}\n"
                f"Size: ${pos.size_usd:.2f}\n"
                f"Paper: {'Yes' if pos.paper else 'No'}\n\n"
            )
        
        await update.message.reply_text(message)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("execute_"):
            signal_id = int(data.split("_")[1])
            await query.edit_message_text(f"✅ Signal #{signal_id} approved for execution.")
            # Signal approval logic here
            
        elif data.startswith("skip_"):
            signal_id = int(data.split("_")[1])
            await query.edit_message_text(f"❌ Signal #{signal_id} skipped.")
            self.user_feedback[signal_id] = "skipped"
            
        elif data.startswith("adjust_"):
            signal_id = int(data.split("_")[1])
            await query.edit_message_text(f"⚙️ Signal #{signal_id} - reply with new target %")
    
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
        """Send signal alert to user with buttons"""
        if not self.application:
            return
        
        self.signal_counter += 1
        signal_id = self.signal_counter
        self.pending_signals[signal_id] = signal
        
        mode = "📝 PAPER" if paper else "💰 LIVE"
        direction = "📈 UP" if signal['direction'] == 'up' else "📉 DOWN"
        
        message = (
            f"🎯 SCALP OPPORTUNITY ({mode})\n\n"
            f"Token: ETH → USDC\n"
            f"Direction: {direction}\n"
            f"Entry: ${signal['price']:.2f}\n"
            f"Target: ${signal['price'] * 1.005:.2f} (+0.5%)\n"
            f"Gas: {signal['gas_gwei']:.1f} gwei\n"
            f"Confidence: {signal['score']}/10\n"
            f"Signal: Momentum"
        )
        
        if paper:
            keyboard = [
                [
                    InlineKeyboardButton("✅ EXECUTE", callback_data=f"execute_{signal_id}"),
                    InlineKeyboardButton("❌ SKIP", callback_data=f"skip_{signal_id}"),
                ],
                [InlineKeyboardButton("⚙️ ADJUST", callback_data=f"adjust_{signal_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
        else:
            reply_markup = None
        
        try:
            await self.application.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    async def send_trade_result(self, result: Dict):
        """Send trade result"""
        if not self.application:
            return
        
        emoji = "✅" if result['pnl_usd'] > 0 else "❌"
        
        message = (
            f"{emoji} TRADE COMPLETE ({'PAPER' if result['paper'] else 'LIVE'})\n\n"
            f"Entry: ${result['position']['entry_price']:.2f}\n"
            f"Exit: ${result['exit_price']:.2f}\n"
            f"Profit: ${result['pnl_usd']:+.2f} ({result['pnl_pct']:+.2f}%)\n"
            f"Gas: ${result.get('gas_cost_usd', 0):.2f}\n"
            f"Net: ${result['pnl_usd'] - result.get('gas_cost_usd', 0):+.2f}\n\n"
            f"Why did this work? Reply with:\n"
            f"• Good momentum timing\n"
            f"• Gas was low\n"
            f"• Volume confirmed"
        )
        
        try:
            await self.application.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message
            )
        except Exception as e:
            logger.error(f"Failed to send result: {e}")
    
    async def send_alert(self, message: str):
        """Send generic alert"""
        if not self.application:
            return
        
        try:
            await self.application.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message
            )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

# Global instance
trading_bot = TradingBot()
