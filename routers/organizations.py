# Oranization.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from connection.database import SessionLocal
from connection.schemas import OrganizationCreate, OrganizationOut, OrganizationUpdate
from models.models import Department, Organization

router = APIRouter(prefix="/organizations", tags=["organizations"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=None)
async def get_organizations(db: Session = Depends(get_db)):
    """Get all organizations with departments_count"""
    try:
        rows = (
            db.query(
                Organization.id,
                Organization.name,
                Organization.code,
                Organization.status,
                Organization.created_at,
                func.count(Department.id).label("departments_count")
            )
            .outerjoin(Department, Department.org_id == Organization.id)
            .group_by(Organization.id, Organization.name, Organization.code, Organization.status, Organization.created_at)
            .all()
        )

        result = []
        for r in rows:
            result.append({
                "id": r.id,
                "name": r.name,
                "code": r.code,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "departments_count": int(r.departments_count),
            })

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading organizations: {str(e)}")

@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(org_id: int, db: Session = Depends(get_db)):
    """Get organization by ID"""
    try:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        return org
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading organization: {str(e)}")

@router.post("/", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(org_data: OrganizationCreate, db: Session = Depends(get_db)):
    """Create new organization"""
    try:
        # Debug logging
        print(f"Received data: {org_data}")
        print(f"Name: {org_data.name}, Code: {getattr(org_data, 'code', 'NOT FOUND')}")
        
        # Validate required fields
        if not hasattr(org_data, 'name') or not org_data.name or not org_data.name.strip():
            raise HTTPException(status_code=400, detail="Organization name is required")
        
        if not hasattr(org_data, 'code') or not org_data.code or not org_data.code.strip():
            raise HTTPException(status_code=400, detail="Organization code is required")
        
        # Check if organization name already exists
        existing_org = db.query(Organization).filter(Organization.name == org_data.name).first()
        if existing_org:
            raise HTTPException(status_code=400, detail="Organization name already exists")
        
        # Check if code already exists
        existing_code = db.query(Organization).filter(Organization.code == org_data.code).first()
        if existing_code:
            raise HTTPException(status_code=400, detail="Organization code already exists")
        
        # Create new organization
        new_org = Organization(
            name=org_data.name.strip(),
            code=org_data.code.strip(),
            status="active"
        )
        
        db.add(new_org)
        db.commit()
        db.refresh(new_org)
        
        return new_org
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"Full error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating organization: {str(e)}")
    finally:
        db.close()

@router.put("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: int, 
    org_data: OrganizationUpdate, 
    db: Session = Depends(get_db)
):
    """Update organization"""
    try:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # Validate and check duplicates
        if org_data.name and org_data.name.strip():
            if org_data.name != org.name:
                existing_org = db.query(Organization).filter(
                    Organization.name == org_data.name,
                    Organization.id != org_id
                ).first()
                if existing_org:
                    raise HTTPException(status_code=400, detail="Organization name already exists")
            org.name = org_data.name.strip()
        
        if org_data.code and org_data.code.strip():
            if org_data.code != org.code:
                existing_code = db.query(Organization).filter(
                    Organization.code == org_data.code,
                    Organization.id != org_id
                ).first()
                if existing_code:
                    raise HTTPException(status_code=400, detail="Organization code already exists")
            org.code = org_data.code.strip()
        
        if org_data.status:
            org.status = org_data.status
        
        db.commit()
        db.refresh(org)
        
        return org
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating organization: {str(e)}")

@router.delete("/{org_id}", status_code=status.HTTP_200_OK)
async def delete_organization(org_id: int, db: Session = Depends(get_db)):
    """Delete organization"""
    try:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # Check if organization has departments
        dept_count = db.query(Department).filter(Department.org_id == org_id).count()
        if dept_count > 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot delete organization with {dept_count} departments. Delete departments first."
            )
        
        db.delete(org)
        db.commit()
        
        return {"success": True, "message": "Organization deleted successfully"}
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting organization: {str(e)}")