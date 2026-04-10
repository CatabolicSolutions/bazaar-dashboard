"""Telegram bot for user interaction and trading feedback"""
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
from signals.price_feed import price_feed

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
        self.application.add_handler(CommandHandler("price", self.cmd_price))
        self.application.add_handler(CommandHandler("history", self.cmd_history))
        self.application.add_handler(CommandHandler("buy", self.cmd_buy))
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
        mode = "📝 PAPER TRADING" if PAPER_TRADING_MODE else "💰 LIVE TRADING"
        status = "🛑 PAUSED" if self.bot_paused else "✅ RUNNING"
        
        await update.message.reply_text(
            f"🤖 <b>ETH Scalper Bot</b>\n\n"
            f"Mode: {mode}\n"
            f"Status: {status}\n\n"
            f"<b>Commands:</b>\n"
            f"📊 /status - Full bot status\n"
            f"💵 /price - Current ETH price\n"
            f"📈 /positions - Open positions\n"
            f"📜 /history - Trade history\n"
            f"🛒 /buy - Manual buy trigger\n"
            f"⏸️ /stop - Pause trading\n"
            f"▶️ /resume - Resume trading\n\n"
            f"<i>I'll alert you when I detect signals.</i>",
            parse_mode='HTML'
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - ENHANCED"""
        risk = risk_manager.get_status()
        momentum = momentum_detector.get_stats()
        trades = trade_manager.get_stats()
        stats = price_feed.get_price_stats()
        
        status = "🛑 PAUSED" if self.bot_paused else "✅ RUNNING"
        mode = "📝 PAPER" if PAPER_TRADING_MODE else "💰 LIVE"
        
        eth_price = stats['current_price'] or 0
        change_60s = stats['change_60s_pct'] or 0
        gas = stats['gas_gwei'] or 0
        
        price_emoji = "🟢" if change_60s >= 0 else "🔴"
        pnl_emoji = "🟢" if risk['daily_pnl'] >= 0 else "🔴"
        
        await update.message.reply_text(
            f"📊 <b>Bot Status:</b> {status} ({mode})\n\n"
            f"{price_emoji} <b>ETH Price:</b> ${eth_price:.2f}\n"
            f"   60s Change: {change_60s:+.2f}%\n"
            f"⛽ <b>Gas:</b> {gas:.1f} gwei\n\n"
            f"{pnl_emoji} <b>Daily P&L:</b> ${risk['daily_pnl']:+.2f}\n"
            f"📊 <b>Trades Today:</b> {risk['daily_trades']}\n"
            f"🎯 <b>Open Positions:</b> {risk['open_positions']}\n"
            f"💵 <b>Available:</b> ${risk['available_capital']:.2f}\n\n"
            f"📈 <b>Total Trades:</b> {trades['total_trades']}\n"
            f"🏆 <b>Win Rate:</b> {trades['win_rate']:.1%}\n"
            f"📊 <b>Signals Detected:</b> {momentum['total_signals']}\n"
            f"⭐ <b>Avg Signal Score:</b> {momentum['avg_score']:.1f}/10",
            parse_mode='HTML'
        )
    
    async def cmd_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /price command"""
        stats = price_feed.get_price_stats()
        
        eth_price = stats['current_price'] or 0
        change_60s = stats['change_60s_pct'] or 0
        gas = stats['gas_gwei'] or 0
        
        emoji = "🟢" if change_60s >= 0 else "🔴"
        
        await update.message.reply_text(
            f"{emoji} <b>ETH Price: ${eth_price:.2f}</b>\n\n"
            f"60s Change: {change_60s:+.2f}%\n"
            f"Gas: {gas:.1f} gwei\n"
            f"Data Points: {stats['history_length']}",
            parse_mode='HTML'
        )
    
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command - ENHANCED"""
        positions = trade_manager.get_open_positions()
        
        if not positions:
            await update.message.reply_text(
                "📭 <b>No Open Positions</b>\n\n"
                "Bot is scanning for entry signals...",
                parse_mode='HTML'
            )
            return
        
        for pos in positions:
            direction_emoji = "📈" if pos.direction == 'long' else "📉"
            
            await update.message.reply_text(
                f"{direction_emoji} <b>Position {pos.id}</b>\n\n"
                f"Direction: {pos.direction.upper()}\n"
                f"Entry: ${pos.entry_price:.2f}\n"
                f"Target: ${pos.target_price:.2f} (+{(pos.target_price/pos.entry_price-1)*100:.2f}%)\n"
                f"Stop: ${pos.stop_price:.2f} (-{(1-pos.stop_price/pos.entry_price)*100:.2f}%)\n"
                f"Size: ${pos.size_usd:.2f}\n"
                f"Mode: {'📝 Paper' if pos.paper else '💰 LIVE'}\n"
                f"Opened: {pos.entry_time:.0f}",
                parse_mode='HTML'
            )
    
    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command"""
        trades = trade_manager.get_stats()
        history = trade_manager.trade_history[-5:]  # Last 5 trades
        
        if not history:
            await update.message.reply_text("📭 No trade history yet.")
            return
        
        message = "📜 <b>Recent Trades:</b>\n\n"
        
        for pos in reversed(history):
            emoji = "✅" if pos.pnl_usd > 0 else "❌"
            mode = "📝" if pos.paper else "💰"
            message += (
                f"{emoji} {mode} {pos.direction.upper()} ${pos.pnl_usd:+.2f}\n"
            )
        
        message += f"\n<b>Total P&L:</b> ${trades['total_pnl']:.2f}"
        
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def cmd_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /buy command - Manual trigger"""
        from execution.live_executor import live_executor
        from execution.oneinch import inch_client
        
        if not PAPER_TRADING_MODE and not live_executor.enabled:
            await update.message.reply_text(
                "❌ <b>Live trading not enabled!</b>\n"
                "Bot needs to be restarted in live mode.",
                parse_mode='HTML'
            )
            return
        
        # Get current price
        current_price = price_feed.get_eth_price()
        if not current_price:
            await update.message.reply_text("❌ Could not fetch current price.")
            return
        
        # Show buy preview
        eth_amount = 0.03  # ~$75 at $2500 ETH
        usd_value = eth_amount * current_price
        
        keyboard = [
            [
                InlineKeyboardButton("✅ CONFIRM BUY", callback_data="manual_buy_0.03"),
                InlineKeyboardButton("❌ CANCEL", callback_data="cancel_buy"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🛒 <b>Manual Buy Preview</b>\n\n"
            f"ETH Price: ${current_price:.2f}\n"
            f"Amount: {eth_amount} ETH\n"
            f"USD Value: ~${usd_value:.2f}\n"
            f"Gas: ~$2-5 (estimated)\n\n"
            f"<i>Confirm to execute swap via 1inch</i>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mode command"""
        mode = "📝 PAPER TRADING" if PAPER_TRADING_MODE else "💰 LIVE TRADING"
        await update.message.reply_text(f"<b>Current mode:</b> {mode}", parse_mode='HTML')
    
    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command"""
        self.bot_paused = True
        await update.message.reply_text(
            "⏸️ <b>Bot PAUSED</b>\n\n"
            "No new trades will be executed.\n"
            "Existing positions will continue to be monitored.",
            parse_mode='HTML'
        )
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command"""
        self.bot_paused = False
        await update.message.reply_text(
            "▶️ <b>Bot RESUMED</b>\n\n"
            "Trading is now ACTIVE.\n"
            "Scanning for signals...",
            parse_mode='HTML'
        )
    
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
            
        elif data == "manual_buy_0.03":
            await query.edit_message_text("🔄 Executing buy... Check /positions for status.")
            # Trigger manual buy logic
            
        elif data == "cancel_buy":
            await query.edit_message_text("❌ Buy cancelled.")
    
    async def handle_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user feedback on trades"""
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
            f"🎯 <b>SCALP OPPORTUNITY ({mode})</b>\n\n"
            f"{direction} ETH → USDC\n"
            f"Entry: <b>${signal['price']:.2f}</b>\n"
            f"Target: ${signal['price'] * 1.005:.2f} (+0.5%)\n"
            f"Gas: {signal['gas_gwei']:.1f} gwei\n"
            f"Confidence: {'⭐' * (signal['score'] // 2)} ({signal['score']}/10)\n"
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
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    async def send_trade_result(self, result: Dict):
        """Send trade result"""
        if not self.application:
            return
        
        emoji = "✅" if result['pnl_usd'] > 0 else "❌"
        mode = "📝 PAPER" if result['paper'] else "💰 LIVE"
        net_pnl = result['pnl_usd'] - result.get('gas_cost_usd', 0)
        
        message = (
            f"{emoji} <b>TRADE COMPLETE ({mode})</b>\n\n"
            f"Entry: ${result['position']['entry_price']:.2f}\n"
            f"Exit: ${result['exit_price']:.2f}\n"
            f"Gross: ${result['pnl_usd']:+.2f} ({result['pnl_pct']:+.2f}%)\n"
            f"Gas: -${result.get('gas_cost_usd', 0):.2f}\n"
            f"<b>Net P&L: ${net_pnl:+.2f}</b>"
        )
        
        try:
            await self.application.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=message,
                parse_mode='HTML'
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
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

# Global instance
trading_bot = TradingBot()
