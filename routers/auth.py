import logging
import sys
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload
from datetime import timedelta
from connection import schemas
from connection.database import SessionLocal  
from models.models import Department, User
from utils import security
from connection.schemas import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OAuth2 scheme
oauth2_scheme = HTTPBearer()

def print_flush(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserOut)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    # Cek email unique
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    
    # Validasi department dan organization
    if user_in.department_id:
        department = db.query(Department).filter(Department.id == user_in.department_id).first()
        if not department:
            raise HTTPException(400, "Department not found")
        user_in.organization_id = department.org_id
    
    user = User(
        name=user_in.name,
        email=user_in.email,
        hashed_password=security.hash_password(user_in.password),
        department_id=user_in.department_id,
        organization_id=user_in.organization_id,
        role=user_in.role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
    
def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        token = creds.credentials
        print_flush(f"\n🔐 AUTH CHECK")
        print_flush(f"🔐 Token: {token[:30]}...")
        
        payload = security.decode_access_token(token)
        
        if not payload:
            raise HTTPException(status_code=401, detail="Token tidak valid")
        
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Token tidak valid")
        
        # Query DENGAN eager loading untuk menghindari lazy loading issues
        user = db.query(User).options(
            joinedload(User.department),
            joinedload(User.organization)
        ).filter(User.id == int(user_id)).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User tidak ditemukan")
        
        # JANGAN expunge dari session - biarkan tetap terhubung
        print_flush(f"✅ User: {user.name} (ID: {user.id})")
        print_flush(f"✅ Role: {user.role}")
        print_flush(f"✅ Org: {user.organization_id}, Dept: {user.department_id}\n")
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        print_flush(f"❌ AUTH ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Token error: {str(e)}")

@router.get("/me")
def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user info - dengan session yang masih aktif"""
    # Pastikan relationships sudah ter-load
    if current_user.department:
        # Force load department jika belum ter-load
        db.refresh(current_user, ['department'])
    if current_user.organization:
        # Force load organization jika belum ter-load
        db.refresh(current_user, ['organization'])
    
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "department_id": current_user.department_id,
        "organization_id": current_user.organization_id,
        "role": current_user.role,
        "department": {
            "id": current_user.department.id,
            "name": current_user.department.name,
            "code": current_user.department.code
        } if current_user.department else None,
        "organization": {
            "id": current_user.organization.id,
            "name": current_user.organization.name,
            "code": current_user.organization.code
        } if current_user.organization else None
    }

@router.post("/login", response_model=Token)
def login(form: UserLogin, db: Session = Depends(get_db)):
    logger.info(f"Attempting login for email: {form.email}")

    # ✅ Query tanpa joinedload
    user = db.query(User).filter(User.email == form.email).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Email atau password salah")

    if not security.verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email atau password salah")

    logger.info(f"Login successful - User: {user.name}, Org: {user.organization_id}, Dept: {user.department_id}")
    
    access_token = security.create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(hours=24),
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/debug/whoami")
def debug_whoami(current_user: User = Depends(get_current_user)):
    """Debug endpoint to check current user"""
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "organization_id": current_user.organization_id,
        "department_id": current_user.department_id,
        "organization": current_user.organization.name if current_user.organization else None,
        "department": current_user.department.name if current_user.department else None
    }
    

def require_role(required_role: str):
    """Decorator to require specific role"""
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role != required_role:
            # For super_admin, allow everything
            if current_user.role != 'super_admin':
                raise HTTPException(403, f"Requires {required_role} role")
        return current_user
    return role_checker

def require_any_role(allowed_roles: list):
    """Decorator to require any of the specified roles"""
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles and current_user.role != 'super_admin':
            raise HTTPException(403, f"Requires one of: {', '.join(allowed_roles)}")
        return current_user
    return role_checker