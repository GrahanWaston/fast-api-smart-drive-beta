from connection.database import SessionLocal
from models.models import User, Department, Organization, OrganizationLicense
from passlib.context import CryptContext
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_user(email, name, password="password123"):
    db = SessionLocal()
    try:
        # Check if exists
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"User {email} already exists!")
            return

        # Create dummy org and dept if needed
        org = db.query(Organization).first()
        if not org:
            org = Organization(name="Default Org", code="DEF", status="active")
            db.add(org)
            db.commit()
            db.refresh(org)
            
            # Create license
            lic = OrganizationLicense(
                organization_id=org.id,
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=365),
                subscription_status="active"
            )
            db.add(lic)
            db.commit()

        dept = db.query(Department).first()
        if not dept:
            dept = Department(name="IT", code="IT", org_id=org.id)
            db.add(dept)
            db.commit()
            db.refresh(dept)

        new_user = User(
            email=email,
            name=name,
            hashed_password=pwd_context.hash(password),
            role="super_admin",
            organization_id=org.id,
            department_id=dept.id
        )
        db.add(new_user)
        db.commit()
        print(f"✅ Successfully created user: {email} (Password: {password})")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    email = input("Enter email to register: ")
    name = input("Enter name: ")
    create_user(email, name)
