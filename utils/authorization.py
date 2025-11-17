import datetime
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from connection.database import SessionLocal
from models.models import User, Document, Directory, DocumentShare, Department, Organization
from routers.auth import get_current_user

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class PermissionChecker:
    def __init__(self, required_permissions: List[str] = None):
        self.required_permissions = required_permissions or []

    def __call__(self, current_user: User = Depends(get_current_user)):
        print(f"🔐 PERMISSION CHECK - User: {current_user.name}, Role: {current_user.role}", flush=True)
        
        # Super admin memiliki akses penuh
        if current_user.role == "super_admin":
            print("✅ Super admin access granted", flush=True)
            return current_user
            
        # Cek permissions
        for permission in self.required_permissions:
            if not self._has_permission(current_user, permission):
                print(f"❌ Permission denied: {permission} for user {current_user.role}", flush=True)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission {permission} required"
                )
        
        print("✅ All permissions granted", flush=True)
        return current_user

    def _has_permission(self, user: User, permission: str) -> bool:
        # Implementasi logic permission berdasarkan role
        role_permissions = {
            "user": ["view_own_docs", "view_own_dirs", "upload_docs", "create_dirs"],
            "admin": ["view_own_docs", "view_own_dirs", "upload_docs", "create_dirs", 
                     "manage_department_docs", "view_department_docs", "manage_department_dirs"],
            "org_admin": ["view_own_docs", "view_own_dirs", "upload_docs", "create_dirs",
                         "manage_organization_docs", "view_organization_docs", 
                         "manage_organization_dirs", "share_docs"]
        }
        has_perm = permission in role_permissions.get(user.role, [])
        print(f"🔐 Checking permission '{permission}' for role '{user.role}': {has_perm}", flush=True)
        return has_perm

# Enhanced helper functions untuk authorization
def can_access_document(user, document, db):
    """
    Check if user can access a specific document
    """
    # Admin can access everything
    if user.role in ["admin", "super_admin"]:
        return True
    
    # Document owner can access
    if document.created_by == user.id:
        return True
    
    # Check if user is in the same organization
    if user.organization_id != document.organization_id:
        return False
    
    # Check department access
    accessible_depts = get_accessible_departments(user, db)
    if accessible_depts != [0] and document.department_id not in accessible_depts:
        return False
    
    return True

def can_access_directory(user: User, directory: Directory) -> bool:
    """Cek akses directory dengan logic yang lebih fleksibel"""
    print(f"🔑 DIRECTORY ACCESS CHECK - User: {user.name} (Role: {user.role})", flush=True)
    
    # 1. Super admin bisa akses semua
    if user.role == "super_admin":
        return True

    # 2. Jika user tidak punya org/dept, hanya bisa akses directory yang juga tidak punya
    if not user.organization_id or not user.department_id:
        if not directory.organization_id or not directory.department_id:
            return True
        # Super admin tanpa assignment tetap bisa akses
        return user.role == "super_admin"

    # 3. Same department = full access
    if user.department_id == directory.department_id:
        return True
    
    # 4. Same organization dengan role admin
    if user.organization_id == directory.organization_id:
        if user.role in ["org_admin", "admin"]:
            return True
    
    return False

def get_accessible_departments(user: User, db: Session) -> List[int]:
    """Dapatkan list department IDs yang dapat diakses user - ENHANCED VERSION"""
    print(f"📊 GET ACCESSIBLE DEPTS - User: {user.name}, Role: {user.role}", flush=True)
    
    if not user.organization_id:
        print("⚠️ User has no organization - returning empty list", flush=True)
        return []

    if user.role == "super_admin":
        depts = [dept.id for dept in db.query(Department).all()]
        print(f"📊 Super admin - All departments: {depts}", flush=True)
        return depts
    elif user.role in ["org_admin", "admin"]:
        depts = [dept.id for dept in db.query(Department).filter(Department.org_id == user.organization_id).all()]
        print(f"📊 Admin - Org departments: {depts}", flush=True)
        return depts
    else:
        depts = [user.department_id] if user.department_id else []
        print(f"📊 User - Own department: {depts}", flush=True)
        return depts

# def get_accessible_organizations(user: User, db: Session) -> List[int]:
#     """Dapatkan list organization IDs yang dapat diakses user - ENHANCED VERSION"""
#     print(f"📊 GET ACCESSIBLE ORGS - User: {user.name}, Role: {user.role}", flush=True)
    
#     if user.role == "super_admin":
#         orgs = [org.id for org in db.query(Organization).all()]
#         print(f"📊 Super admin - All organizations: {orgs}", flush=True)
#         return orgs
#     else:
#         orgs = [user.organization_id] if user.organization_id else []
#         print(f"📊 User - Own organization: {orgs}", flush=True)
#         return orgs

def get_user_default_organization_and_department(db: Session, user: User) -> tuple[Optional[int], Optional[int]]:
    """Dapatkan default organization dan department untuk user"""
    print(f"🔧 GET DEFAULT ORG/DEPT - User: {user.name}", flush=True)
    
    # Jika user sudah punya assignment, return yang ada
    if user.organization_id and user.department_id:
        print(f"🔧 User already has org/dept: {user.organization_id}/{user.department_id}", flush=True)
        return user.organization_id, user.department_id
    
    # Cari default organization
    default_org = db.query(Organization).filter(Organization.code == "DEFAULT").first()
    if not default_org:
        print("❌ No default organization found", flush=True)
        return None, None
    
    # Cari default department dalam organization tersebut
    default_dept = db.query(Department).filter(
        Department.org_id == default_org.id,
        Department.code == "DEFAULT"
    ).first()
    
    if default_dept:
        print(f"🔧 Found default org/dept: {default_org.id}/{default_dept.id}", flush=True)
        # Update user dengan default values
        user.organization_id = default_org.id
        user.department_id = default_dept.id
        db.commit()
        return default_org.id, default_dept.id
    else:
        print("❌ No default department found", flush=True)
        return default_org.id, None

def ensure_user_org_dept_assignment(user: User, db: Session) -> bool:
    """Pastikan user memiliki organization dan department assignment"""
    print(f"🔧 ENSURING ORG/DEPT ASSIGNMENT - User: {user.name}", flush=True)
    
    if user.organization_id and user.department_id:
        print("✅ User already has org/dept assignment", flush=True)
        return True
    
    org_id, dept_id = get_user_default_organization_and_department(db, user)
    
    if org_id and dept_id:
        print(f"✅ Assigned default org/dept to user: {org_id}/{dept_id}", flush=True)
        return True
    else:
        print("❌ Failed to assign org/dept to user", flush=True)
        return False

# Utility function untuk bypass authorization sementara (development only)
def bypass_auth_for_development() -> bool:
    """Return True untuk bypass authorization selama development"""
    import os
    bypass = os.getenv("BYPASS_AUTH", "false").lower() == "true"
    if bypass:
        print("🚨 DEVELOPMENT MODE: Authorization bypassed", flush=True)
    return bypass

# def get_accessible_departments(user: User, db: Session) -> List[int]:
#     """Return list of accessible department IDs"""
#     print(f"📊 GET ACCESSIBLE DEPTS - User: {user.name}, Role: {user.role}", flush=True)
    
#     # Super admin sees all
#     if user.role == "super_admin":
#         depts = [dept.id for dept in db.query(Department).all()]
#         return depts or [0]  # Return [0] if empty to avoid empty IN clause
    
#     # Org admin sees all departments in their organization
#     if user.role in ["org_admin", "admin"] and user.organization_id:
#         depts = [dept.id for dept in db.query(Department).filter(
#             Department.org_id == user.organization_id
#         ).all()]
#         return depts or [0]
    
#     # Regular user sees only their department
#     if user.department_id:
#         return [user.department_id]
    
#     # User without department - return special value to indicate "no assignment"
#     return [0]  # Use 0 as sentinel value

def get_accessible_organizations(user: User, db: Session) -> List[int]:
    """Return list of accessible organization IDs"""
    print(f"📊 GET ACCESSIBLE ORGS - User: {user.name}, Role: {user.role}", flush=True)
    
    # Super admin sees all
    if user.role == "super_admin":
        orgs = [org.id for org in db.query(Organization).all()]
        return orgs or [0]
    
    # User with organization
    if user.organization_id:
        return [user.organization_id]
    
    # User without organization - return special value
    return [0]