"""
Script untuk migration database ke multi-organization
Jalankan script ini sekali untuk update schema yang ada
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  

sys.path.insert(0, parent_dir)

from connection.database import SessionLocal, engine, Base
from models.models import User, Organization, Department, Directory, Document
from utils.security import hash_password
from datetime import datetime

def migrate_to_multi_org():
    db = SessionLocal()
    try:
        # Buat organization default
        default_org = Organization(
            name="Default Organization",
            code="DEFAULT",
            status="active"
        )
        db.add(default_org)
        db.commit()
        db.refresh(default_org)
        
        # Buat department default
        default_dept = Department(
            name="Default Department",
            code="DEFAULT",
            org_id=default_org.id
        )
        db.add(default_dept)
        db.commit()
        db.refresh(default_dept)
        
        # Update existing users
        users = db.query(User).all()
        for user in users:
            user.organization_id = default_org.id
            user.department_id = default_dept.id
        
        db.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate_to_multi_org()