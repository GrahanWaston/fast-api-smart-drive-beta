# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from connection.database import SessionLocal
from models.models import OrganizationLicense, SubscriptionStatus
from datetime import datetime

def check_expired_licenses():
    """Background task to check and update expired licenses"""
    db = SessionLocal()
    try:
        # Update expired licenses
        expired_count = db.query(OrganizationLicense).filter(
            OrganizationLicense.end_date < datetime.utcnow(),
            OrganizationLicense.subscription_status.in_(['active', 'trial'])
        ).update({
            'subscription_status': SubscriptionStatus.EXPIRED,
            'updated_at': datetime.utcnow()
        })
        
        # Update last_checked for all
        db.query(OrganizationLicense).update({
            'last_checked': datetime.utcnow()
        })
        
        db.commit()
        print(f"[License Check] Updated {expired_count} expired licenses")
        
    except Exception as e:
        print(f"[License Check] Error: {str(e)}")
        db.rollback()
    finally:
        db.close()

def start_scheduler():
    """Start background scheduler"""
    scheduler = BackgroundScheduler()
    
    # Run every hour
    scheduler.add_job(
        check_expired_licenses, 
        'interval', 
        hours=1,
        id='check_licenses'
    )
    
    # Run immediately on startup
    scheduler.add_job(
        check_expired_licenses,
        'date',
        id='check_licenses_startup'
    )
    
    scheduler.start()
    print("[Scheduler] License checker started")
    
    return scheduler