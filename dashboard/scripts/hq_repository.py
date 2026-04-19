import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/eth_scalper_db")

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class HQSnapshot(Base):
    __tablename__ = "hq_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)
    source = Column(String, nullable=False, default="dashboard")
    mode = Column(String, nullable=True)
    status = Column(String, nullable=True)
    compounding_state = Column(String, nullable=True)
    holding_asset = Column(String, nullable=True)
    holding_units = Column(String, nullable=True)
    deployable_capital_usd = Column(String, nullable=True)
    invested_capital_usd = Column(String, nullable=True)
    payload = Column(JSONB, nullable=False)


class HQEvent(Base):
    __tablename__ = "hq_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)
    event_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, default="info")
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=True)
    acknowledged = Column(Boolean, nullable=False, default=False)


class HQRepository:
    def __init__(self):
        self.enabled = DATABASE_URL.startswith("postgresql")

    def create_tables(self) -> None:
        if not self.enabled:
            return
        Base.metadata.create_all(bind=engine)

    def append_snapshot(self, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        session = SessionLocal()
        try:
            live = payload.get("live") or {}
            snapshot = HQSnapshot(
                source=payload.get("source", "dashboard"),
                mode=live.get("mode"),
                status=live.get("status"),
                compounding_state=live.get("compounding_state"),
                holding_asset=live.get("holding_asset"),
                holding_units=str(live.get("holding_units")) if live.get("holding_units") is not None else None,
                deployable_capital_usd=str(live.get("deployable_capital_usd")) if live.get("deployable_capital_usd") is not None else None,
                invested_capital_usd=str(live.get("invested_capital_usd")) if live.get("invested_capital_usd") is not None else None,
                payload=payload,
            )
            session.add(snapshot)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def append_event(self, event_type: str, title: str, message: str = "", severity: str = "info", payload: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled:
            return
        session = SessionLocal()
        try:
            event = HQEvent(
                event_type=event_type,
                title=title,
                message=message,
                severity=severity,
                payload=payload or {},
            )
            session.add(event)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        session = SessionLocal()
        try:
            row = session.query(HQSnapshot).order_by(HQSnapshot.created_at.desc()).first()
            return row.payload if row else None
        except Exception:
            return None
        finally:
            session.close()

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        session = SessionLocal()
        try:
            rows = session.query(HQEvent).order_by(HQEvent.created_at.desc()).limit(limit).all()
            out = []
            for row in rows:
                out.append({
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "event_type": row.event_type,
                    "severity": row.severity,
                    "title": row.title,
                    "message": row.message,
                    "payload": row.payload or {},
                })
            return out
        except Exception:
            return []
        finally:
            session.close()


hq_repository = HQRepository()
