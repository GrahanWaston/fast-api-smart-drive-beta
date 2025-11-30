from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func
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

@router.get("/", response_model=None)
async def get_departments(
    org_id: Optional[int] = Query(None, description="Filter by organization ID"),
    db: Session = Depends(get_db)
):
    """Get all departments with optional organization filter"""
    try:
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
                "org": {
                    "id": dept.org.id,
                    "name": dept.org.name,
                    "code": dept.org.code
                } if dept.org else None,
                "parent": {
                    "id": dept.parent.id,
                    "name": dept.parent.name
                } if dept.parent else None,
                "users_count": users_count
            }
            result.append(dept_dict)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading departments: {str(e)}")

@router.get("/{dept_id}", response_model=DepartmentOut)
async def get_department(dept_id: int, db: Session = Depends(get_db)):
    """Get department by ID"""
    try:
        dept = db.query(Department).filter(Department.id == dept_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        return dept
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading department: {str(e)}")

@router.post("/", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def create_department(dept_data: DepartmentCreate, db: Session = Depends(get_db)):
    """Create new department"""
    try:
        # Debug logging
        print(f"Received department data: {dept_data}")
        print(f"Name: {dept_data.name}, Code: {dept_data.code}, Org ID: {dept_data.org_id}")
        
        # Validate required fields
        if not dept_data.name or not dept_data.name.strip():
            raise HTTPException(status_code=400, detail="Department name is required")
        
        if not dept_data.code or not dept_data.code.strip():
            raise HTTPException(status_code=400, detail="Department code is required")
        
        if not dept_data.org_id:
            raise HTTPException(status_code=400, detail="Organization is required")
        
        # Check if organization exists
        org = db.query(Organization).filter(Organization.id == dept_data.org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # Check if department code already exists in this organization
        existing_code = db.query(Department).filter(
            Department.code == dept_data.code.strip(),
            Department.org_id == dept_data.org_id
        ).first()
        if existing_code:
            raise HTTPException(
                status_code=400, 
                detail="Department code already exists in this organization"
            )
        
        # Check if department name already exists in the same organization
        existing_dept = db.query(Department).filter(
            Department.name == dept_data.name.strip(),
            Department.org_id == dept_data.org_id
        ).first()
        if existing_dept:
            raise HTTPException(
                status_code=400, 
                detail="Department name already exists in this organization"
            )
        
        # Create new department
        new_dept = Department(
            name=dept_data.name.strip(),
            code=dept_data.code.strip(),
            org_id=dept_data.org_id,
            parent_id=dept_data.parent_id
        )
        
        db.add(new_dept)
        db.commit()
        db.refresh(new_dept)
        
        return new_dept
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"Full error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating department: {str(e)}")

@router.put("/{dept_id}", response_model=DepartmentOut)
async def update_department(
    dept_id: int, 
    dept_data: DepartmentUpdate, 
    db: Session = Depends(get_db)
):
    """Update department"""
    try:
        dept = db.query(Department).filter(Department.id == dept_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        
        # Validate and update org_id if provided
        if dept_data.org_id and dept_data.org_id != dept.org_id:
            org = db.query(Organization).filter(Organization.id == dept_data.org_id).first()
            if not org:
                raise HTTPException(status_code=404, detail="Organization not found")
            dept.org_id = dept_data.org_id
        
        # Check if new name already exists in the same organization (excluding current dept)
        if dept_data.name and dept_data.name.strip():
            if dept_data.name != dept.name:
                target_org_id = dept_data.org_id if dept_data.org_id else dept.org_id
                existing_dept = db.query(Department).filter(
                    Department.name == dept_data.name.strip(),
                    Department.org_id == target_org_id,
                    Department.id != dept_id
                ).first()
                if existing_dept:
                    raise HTTPException(
                        status_code=400, 
                        detail="Department name already exists in this organization"
                    )
            dept.name = dept_data.name.strip()
        
        # Check if new code already exists in the same organization (excluding current dept)
        if dept_data.code and dept_data.code.strip():
            if dept_data.code != dept.code:
                target_org_id = dept_data.org_id if dept_data.org_id else dept.org_id
                existing_code = db.query(Department).filter(
                    Department.code == dept_data.code.strip(),
                    Department.org_id == target_org_id,
                    Department.id != dept_id
                ).first()
                if existing_code:
                    raise HTTPException(
                        status_code=400, 
                        detail="Department code already exists in this organization"
                    )
            dept.code = dept_data.code.strip()
        
        # Update parent_id if provided
        if dept_data.parent_id is not None:
            if dept_data.parent_id == dept_id:
                raise HTTPException(status_code=400, detail="Department cannot be its own parent")
            dept.parent_id = dept_data.parent_id
        
        db.commit()
        db.refresh(dept)
        
        return dept
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating department: {str(e)}")

@router.delete("/{dept_id}", status_code=status.HTTP_200_OK)
async def delete_department(dept_id: int, db: Session = Depends(get_db)):
    """Delete department"""
    try:
        dept = db.query(Department).filter(Department.id == dept_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        
        # Check if department has users
        user_count = db.query(User).filter(User.department_id == dept_id).count()
        if user_count > 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot delete department with {user_count} users. Reassign users first."
            )
        
        # Check if department has child departments
        child_count = db.query(Department).filter(Department.parent_id == dept_id).count()
        if child_count > 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot delete department with {child_count} child departments. Delete child departments first."
            )
        
        # PERBAIKAN: Check if department has directories
        from models.models import Directory
        directory_count = db.query(Directory).filter(Directory.department_id == dept_id).count()
        if directory_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete department with {directory_count} directories/files. Move or delete them first."
            )
        
        # PERBAIKAN: Check if department has documents
        from models.models import Document
        document_count = db.query(Document).filter(Document.department_id == dept_id).count()
        if document_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete department with {document_count} documents. Move or delete them first."
            )
        
        db.delete(dept)
        db.commit()
        
        return {"success": True, "message": "Department deleted successfully"}
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting department: {str(e)}")