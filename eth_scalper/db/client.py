import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, BigInteger, Text, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from typing import Optional, Dict

# --- Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/eth_scalper_db")

# --- SQLAlchemy Setup ---
Base = declarative_base()
Engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=Engine)

# --- Models ---
class Trade(Base):
    __tablename__ = "trades"
    trade_id = Column(String, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    bot_id = Column(String, default="eth_scalper")
    symbol = Column(String)
    direction = Column(String)
    quantity = Column(Float)
    price = Column(Float)
    pnl_usd = Column(Float)
    pnl_pct = Column(Float)
    gas_cost_usd = Column(Float)
    tx_hash = Column(String)
    exit_tx_hash = Column(String)
    reason = Column(String)
    notes = Column(Text)
    data = Column(JSONB) # Original signal data, etc.

class Position(Base):
    __tablename__ = "positions"
    position_id = Column(String, primary_key=True, index=True)
    bot_id = Column(String, default="eth_scalper")
    # For entry trade, can link to a trade record if an explicit entry trade is logged as such
    entry_trade_id = Column(String) 
    status = Column(String) # 'pending', 'open', 'closing', 'closed', 'failed'
    entry_time = Column(DateTime)
    entry_price = Column(Float)
    size_usd = Column(Float)
    direction = Column(String)
    target_price = Column(Float)
    stop_price = Column(Float)
    exit_time = Column(DateTime)
    exit_price = Column(Float)
    final_pnl_usd = Column(Float)
    final_pnl_pct = Column(Float)
    executed_units = Column(Float)
    bound_token = Column(String)
    bound_symbol = Column(String)
    is_resumable = Column(Boolean)
    metadata_json = Column(JSONB) # Signal data, etc.

class Signal(Base):
    __tablename__ = "signals"
    signal_id = Column(String, primary_key=True, index=True)
    timestamp = Column(DateTime) # Use datetime from signal data
    bot_id = Column(String, default="eth_scalper")
    type = Column(String)
    symbol = Column(String)
    direction = Column(String)
    price = Column(Float)
    change_60s_pct = Column(Float)
    score = Column(Integer)
    gas_gwei = Column(Float)
    executed = Column(Boolean)
    reason = Column(String)
    # Link to a position if a signal leads to an executed trade
    position_id = Column(String) 
    metadata_json = Column(JSONB) # Raw signal data

class WalletBalance(Base):
    __tablename__ = "wallet_balances"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    bot_id = Column(String, default="eth_scalper")
    currency = Column(String)
    balance = Column(Float)
    usd_value = Column(Float)

# --- DB Operations ---
def create_tables():
    Base.metadata.create_all(bind=Engine)

def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# --- Public API for main.py ---

def add_signal_entry(signal_data: Dict, executed: bool, reason: Optional[str] = None, position_id: Optional[str] = None):
    db = get_db()
    try:
        new_signal = Signal(
            signal_id=f"sig_{int(signal_data['timestamp']*1000)}", # Use signal timestamp for ID consistency
            timestamp=datetime.fromtimestamp(signal_data['timestamp']),
            type=signal_data.get('type'),
            symbol=signal_data.get('symbol'),
            direction=signal_data.get('direction'),
            price=signal_data.get('price'),
            change_60s_pct=signal_data.get('change_60s_pct'),
            score=signal_data.get('score'),
            gas_gwei=signal_data.get('gas_gwei'),
            executed=executed,
            reason=reason,
            position_id=position_id,
            metadata_json=signal_data
        )
        db.add(new_signal)
        db.commit()
        db.refresh(new_signal)
    except Exception as e:
        print(f"Error logging signal to DB: {e}")
        db.rollback()
    finally:
        db.close()

def add_position_entry(position_obj):
    db = get_db()
    try:
        new_position = Position(
            position_id=position_obj.id,
            entry_trade_id=position_obj.trade_id, # Link to potential trade_id for entry
            status=position_obj.status.value,
            entry_time=datetime.fromtimestamp(position_obj.entry_time),
            entry_price=position_obj.entry_price,
            size_usd=position_obj.size_usd,
            direction=position_obj.direction,
            target_price=position_obj.target_price,
            stop_price=position_obj.stop_price,
            paper=position_obj.paper,
            executed_units=getattr(position_obj, 'executed_to_amount_units', None),
            bound_token=getattr(position_obj, 'bound_token', None),
            bound_symbol=getattr(position_obj, 'bound_symbol', None),
            is_resumable=getattr(position_obj, 'resumable_after_restart', False),
            metadata_json=position_obj.signal # Store the raw signal data here
        )
        db.add(new_position)
        db.commit()
        db.refresh(new_position)
        return new_position
    except Exception as e:
        print(f"Error adding position to DB: {e}")
        db.rollback()
    finally:
        db.close()

def update_position_entry(position_obj):
    db = get_db()
    try:
        db_position = db.query(Position).filter(Position.position_id == position_obj.id).first()
        if db_position:
            db_position.status = position_obj.status.value
            db_position.exit_time = datetime.fromtimestamp(position_obj.exit_time) if position_obj.exit_time else None
            db_position.exit_price = position_obj.exit_price
            db_position.final_pnl_usd = position_obj.pnl_usd
            db_position.final_pnl_pct = position_obj.pnl_pct
            db.commit()
            db.refresh(db_position)
        return db_position
    except Exception as e:
        print(f"Error updating position in DB: {e}")
        db.rollback()
    finally:
        db.close()

def add_trade_entry(position_obj, exit_price: float, reason: str, pnl_usd: float, pnl_pct: float, gas_cost_usd: float = 2.0):
    db = get_db()
    try:
        new_trade = Trade(
            trade_id=position_obj.id, # Using position_id as trade_id for simplicity
            timestamp=datetime.fromtimestamp(position_obj.entry_time), # Entry time as trade start
            symbol=position_obj.signal.get('symbol'),
            direction=position_obj.direction,
            quantity=position_obj.executed_units,
            price=position_obj.entry_price,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            gas_cost_usd=gas_cost_usd,
            tx_hash=position_obj.tx_hash,
            exit_tx_hash=position_obj.exit_tx_hash,
            reason=reason,
            data=position_obj.signal # Full signal data
        )
        db.add(new_trade)
        db.commit()
        db.refresh(new_trade)
    except Exception as e:
        print(f"Error logging trade to DB: {e}")
        db.rollback()
    finally:
        db.close()

def add_wallet_balance_entry(wallet_data: Dict):
    db = get_db()
    try:
        current_time = datetime.utcnow()
        for currency, balance in wallet_data.items():
            if currency in ['eth', 'usdc', 'weth']: # Filter for relevant currencies
                usd_value = balance # Assuming usd_value is directly available or can be calculated later
                if currency == 'eth': # Need to calculate usd value for ETH/WETH
                    # This would ideally come from a price feed, for now set to balance
                    usd_value = balance * wallet_data.get('estimated_eth_price', 0) # Placeholder
                elif currency == 'weth':
                    usd_value = balance * wallet_data.get('estimated_eth_price', 0) # Placeholder
                
                new_balance = WalletBalance(
                    timestamp=current_time,
                    currency=currency.upper(),
                    balance=balance,
                    usd_value=usd_value
                )
                db.add(new_balance)
        db.commit()
    except Exception as e:
        print(f"Error logging wallet balances to DB: {e}")
        db.rollback()
    finally:
        db.close()

def get_open_positions_from_db():
    db = get_db()
    try:
        return db.query(Position).filter(Position.status == 'open').all()
    except Exception as e:
        print(f"Error fetching open positions from DB: {e}")
        return []
    finally:
        db.close()

