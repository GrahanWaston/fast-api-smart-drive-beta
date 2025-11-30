# routers/users.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from connection.database import SessionLocal
from connection.schemas import UserCreate, UserOut, UserUpdate
from models.models import User, Department, Organization
from utils.authorization import get_current_user
from utils.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[UserOut])
def get_users(
    org_id: Optional[int] = Query(None),
    dept_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get users with filters - permission based"""
    query = db.query(User).options(
        joinedload(User.department),
        joinedload(User.organization)
    )
    
    # Apply filters based on user role
    if current_user.role == 'org_admin':
        query = query.filter(User.organization_id == current_user.organization_id)
    elif current_user.role == 'dept_head':
        query = query.filter(User.department_id == current_user.department_id)
    
    # Apply additional filters
    if org_id:
        query = query.filter(User.organization_id == org_id)
    if dept_id:
        query = query.filter(User.department_id == dept_id)
    if role:
        query = query.filter(User.role == role)
    
    users = query.offset(skip).limit(limit).all()
    return users

@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific user by ID - permission based"""
    user = db.query(User).options(
        joinedload(User.department),
        joinedload(User.organization)
    ).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(404, "User not found")
    
    # Permission checks
    if current_user.role == 'org_admin':
        if user.organization_id != current_user.organization_id:
            raise HTTPException(403, "Cannot access users in other organizations")
    elif current_user.role == 'dept_head':
        if user.department_id != current_user.department_id:
            raise HTTPException(403, "Cannot access users in other departments")
    
    return user

@router.post("/", response_model=UserOut)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create new user - permission based"""
    # Check if email exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(400, "Email already exists")
    
    # Validate organization and department
    if user_data.organization_id:
        org = db.query(Organization).filter(Organization.id == user_data.organization_id).first()
        if not org:
            raise HTTPException(400, "Organization not found")
    
    if user_data.department_id:
        dept = db.query(Department).filter(Department.id == user_data.department_id).first()
        if not dept:
            raise HTTPException(400, "Department not found")
        # Ensure department belongs to organization
        if user_data.organization_id and dept.org_id != user_data.organization_id:
            raise HTTPException(400, "Department does not belong to the specified organization")
    
    # Permission checks
    if current_user.role == 'org_admin':
        # Org admin can only create users in their organization
        if user_data.organization_id != current_user.organization_id:
            raise HTTPException(403, "Cannot create users in other organizations")
        # Org admin cannot create super_admins
        if user_data.role == 'super_admin':
            raise HTTPException(403, "Cannot create super admin users")
    elif current_user.role == 'dept_head':
        # Dept head can only create users in their department
        if user_data.department_id != current_user.department_id:
            raise HTTPException(403, "Cannot create users in other departments")
        # Dept head can only create regular users
        if user_data.role not in ['user', 'dept_head']:
            raise HTTPException(403, "Can only create regular users or department heads")
    
    user = User(
        name=user_data.name,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        department_id=user_data.department_id,
        organization_id=user_data.organization_id,
        role=user_data.role
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Return user with relationships
    user = db.query(User).options(
        joinedload(User.department),
        joinedload(User.organization)
    ).filter(User.id == user.id).first()
    
    return user

@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update user - permission based"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    
    # Check if email already exists (excluding current user)
    if user_data.email and user_data.email != user.email:
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(400, "Email already exists")
    
    # Permission checks
    if current_user.role == 'org_admin':
        if user.organization_id != current_user.organization_id:
            raise HTTPException(403, "Cannot update users in other organizations")
        # Org admin cannot edit super_admin
        if user.role == 'super_admin':
            raise HTTPException(403, "Cannot edit super admin users")
        # Org admin cannot change users to super_admin
        if user_data.role == 'super_admin':
            raise HTTPException(403, "Cannot assign super admin role")
    elif current_user.role == 'dept_head':
        if user.department_id != current_user.department_id:
            raise HTTPException(403, "Cannot update users in other departments")
        # Dept head cannot edit super_admin or org_admin
        if user.role in ['super_admin', 'org_admin']:
            raise HTTPException(403, "Cannot edit admin users")
        # Dept head cannot change role to org_admin or super_admin
        if user_data.role in ['org_admin', 'super_admin']:
            raise HTTPException(403, "Cannot assign admin roles")
    
    # Update fields
    update_data = user_data.dict(exclude_unset=True)
    if 'password' in update_data and update_data['password']:
        user.hashed_password = hash_password(update_data['password'])
        del update_data['password']
    
    for field, value in update_data.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    
    # Return user with relationships
    user = db.query(User).options(
        joinedload(User.department),
        joinedload(User.organization)
    ).filter(User.id == user.id).first()
    
    return user

@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete user - permission based"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    
    # Cannot delete yourself
    if user.id == current_user.id:
        raise HTTPException(400, "Cannot delete your own account")
    
    # Permission checks
    if current_user.role == 'org_admin':
        if user.organization_id != current_user.organization_id:
            raise HTTPException(403, "Cannot delete users in other organizations")
        # Org admin cannot delete super_admin
        if user.role == 'super_admin':
            raise HTTPException(403, "Cannot delete super admin users")
    elif current_user.role == 'dept_head':
        if user.department_id != current_user.department_id:
            raise HTTPException(403, "Cannot delete users in other departments")
        # Dept head cannot delete super_admin or org_admin
        if user.role in ['super_admin', 'org_admin']:
            raise HTTPException(403, "Cannot delete admin users")
    
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}


@router.get("/organization/{org_id}", response_model=List[UserOut])
def get_users_by_organization(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get users by organization - permission based"""
    # Permission check for org_admin and dept_head
    if current_user.role == 'org_admin':
        if org_id != current_user.organization_id:
            raise HTTPException(403, "Cannot access users in other organizations")
    elif current_user.role == 'dept_head':
        # Dept head can only see users in their own department, not entire org
        raise HTTPException(403, "Cannot access organization-wide users")
    
    users = db.query(User).options(
        joinedload(User.department),
        joinedload(User.organization)
    ).filter(User.organization_id == org_id).all()
    
    return users

@router.get("/department/{dept_id}", response_model=List[UserOut])
def get_users_by_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get users by department - permission based"""
    # Permission check
    if current_user.role == 'org_admin':
        # Check if department belongs to admin's organization
        dept = db.query(Department).filter(Department.id == dept_id).first()
        if not dept or dept.org_id != current_user.organization_id:
            raise HTTPException(403, "Cannot access departments in other organizations")
    elif current_user.role == 'dept_head':
        if dept_id != current_user.department_id:
            raise HTTPException(403, "Cannot access other departments")
    
    users = db.query(User).options(
        joinedload(User.department),
        joinedload(User.organization)
    ).filter(User.department_id == dept_id).all()
    
    return users