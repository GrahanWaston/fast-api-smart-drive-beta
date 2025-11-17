from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .base import Base 

# DATABASE_URL = "postgres://avnadmin:AVNS_noBu8_GLpF_BhYClUzw@pg-32c1c2a5-grahanwaston-f621.c.aivencloud.com:25460/defaultdb?sslmode=require"
# DATABASE_URL = "postgresql://postgres:123@localhost/db_smart_drive_beta"

DATABASE_URL = "postgresql://avnadmin:AVNS_noBu8_GLpF_BhYClUzw@pg-32c1c2a5-grahanwaston-f621.c.aivencloud.com:25460/defaultdb?sslmode=require"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db():
    from models import models  
    Base.metadata.create_all(bind=engine)

def get_db():
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def save_activity_log(log_data: dict):
    """Simpan activity log ke database"""
    from models.models import ActivityLog
    db = SessionLocal()
    try:
        log = ActivityLog(**log_data)
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    except Exception as e:
        db.rollback()
        print(f"❌ Error saving log: {e}")
        return None
    finally:
        db.close()