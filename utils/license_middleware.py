# license_middleware.py
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from models.models import OrganizationLicense, User
from datetime import datetime

async def check_organization_license(request: Request, current_user: User, db: Session):
    """Middleware to check if organization license is active"""
    
    # Skip check untuk super_admin
    if current_user.role == "super_admin":
        return True
    
    # Skip untuk endpoint tertentu (login, logout, etc)
    exempt_paths = ["/auth/login", "/auth/logout", "/auth/me"]
    if request.url.path in exempt_paths:
        return True
    
    license = db.query(OrganizationLicense).filter(
        OrganizationLicense.organization_id == current_user.organization_id
    ).first()
    
    if not license:
        raise HTTPException(
            status_code=403, 
            detail="No valid license found for your organization"
        )
    
    # Check if expired
    if license.end_date < datetime.utcnow():
        license.subscription_status = "expired"
        db.commit()
        
        raise HTTPException(
            status_code=403,
            detail=f"Organization license has expired. Please contact administrator."
        )
    
    # Check user limit (optional)
    if request.method == "POST" and "/users" in request.url.path:
        user_count = db.query(User).filter(
            User.organization_id == current_user.organization_id
        ).count()
        
        if user_count >= license.max_users:
            raise HTTPException(
                status_code=403,
                detail=f"User limit reached ({license.max_users}). Please upgrade your license."
            )
    
    return True