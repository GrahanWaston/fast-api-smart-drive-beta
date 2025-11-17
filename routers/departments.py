from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from connection.database import SessionLocal
from connection.schemas import DepartmentCreate, DepartmentOut, DepartmentUpdate
from models.models import Department, Organization, User

router = APIRouter(prefix="/departments", tags=["departments"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[DepartmentOut])
async def get_departments(
    org_id: Optional[int] = Query(None, description="Filter by organization ID"),
    db: Session = Depends(get_db)
):
    """Get all departments with optional organization filter"""
    from sqlalchemy import func
    
    query = db.query(Department)
    
    if org_id:
        query = query.filter(Department.org_id == org_id)
    
    departments = query.all()
    
    # Add users count to each department
    result = []
    for dept in departments:
        users_count = db.query(func.count(User.id)).filter(User.department_id == dept.id).scalar()
        dept_dict = {
            "id": dept.id,
            "name": dept.name,
            "code": dept.code,
            "org_id": dept.org_id,
            "parent_id": dept.parent_id,
            "org": dept.org,
            "users_count": users_count
        }
        result.append(dept_dict)
    
    return result

@router.get("/{dept_id}", response_model=DepartmentOut)
async def get_department(dept_id: int, db: Session = Depends(get_db)):
    """Get department by ID"""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept

@router.post("/", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def create_department(dept_data: DepartmentCreate, db: Session = Depends(get_db)):
    """Create new department"""
    # Check if organization exists
    org = db.query(Organization).filter(Organization.id == dept_data.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check if department name already exists in the same organization
    existing_dept = db.query(Department).filter(
        Department.name == dept_data.name,
        Department.org_id == dept_data.org_id
    ).first()
    if existing_dept:
        raise HTTPException(
            status_code=400, 
            detail="Department name already exists in this organization"
        )
    
    new_dept = Department(**dept_data.dict())
    db.add(new_dept)
    db.commit()
    db.refresh(new_dept)
    return new_dept

@router.put("/{dept_id}", response_model=DepartmentOut)
async def update_department(dept_id: int, dept_data: DepartmentCreate, db: Session = Depends(get_db)):
    """Update department"""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    
    # Check if organization exists
    org = db.query(Organization).filter(Organization.id == dept_data.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check if new name already exists in the same organization (excluding current dept)
    existing_dept = db.query(Department).filter(
        Department.name == dept_data.name,
        Department.org_id == dept_data.org_id,
        Department.id != dept_id
    ).first()
    if existing_dept:
        raise HTTPException(
            status_code=400, 
            detail="Department name already exists in this organization"
        )
    
    for field, value in dept_data.dict().items():
        setattr(dept, field, value)
    
    db.commit()
    db.refresh(dept)
    return dept

@router.put("/{dept_id}", response_model=DepartmentOut)
async def update_department(
    dept_id: int, 
    dept_data: DepartmentUpdate, 
    db: Session = Depends(get_db)
):
    """Update department"""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    
    # Check if organization exists
    if dept_data.org_id:
        org = db.query(Organization).filter(Organization.id == dept_data.org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check if new name already exists in the same organization (excluding current dept)
    if dept_data.name and dept_data.name != dept.name:
        existing_dept = db.query(Department).filter(
            Department.name == dept_data.name,
            Department.org_id == dept_data.org_id,
            Department.id != dept_id
        ).first()
        if existing_dept:
            raise HTTPException(
                status_code=400, 
                detail="Department name already exists in this organization"
            )
    
    # Update fields
    update_data = dept_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(dept, field, value)
    
    db.commit()
    db.refresh(dept)
    return dept
