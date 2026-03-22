from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config import Config

Base = declarative_base()
engine = create_engine(Config.DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in Config.DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)

class TargetAccount(Base):
    __tablename__ = 'target_accounts'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    active = Column(Boolean, default=True)
    devices_removed = Column(Integer, default=0)
    last_run = Column(DateTime, nullable=True)
    status = Column(String(100), default='Pending')
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ExecutionLog(Base):
    __tablename__ = 'execution_logs'
    
    id = Column(Integer, primary_key=True)
    account_email = Column(String(255), nullable=False)
    account_id = Column(Integer, nullable=False)
    action = Column(String(100))
    result = Column(String(50))
    details = Column(Text)
    devices_removed = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()