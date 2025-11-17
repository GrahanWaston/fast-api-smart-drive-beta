from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List
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

@router.get("/", response_model=None)   # remove/adjust response_model if it doesn't include departments_count
async def get_organizations(db: Session = Depends(get_db)):
    """Get all organizations with departments_count"""
    rows = (
        db.query(
            Organization.id,
            Organization.name,
            func.count(Department.id).label("departments_count")
        )
        .outerjoin(Department, Department.org_id == Organization.id)
        .group_by(Organization.id)
        .all()
    )

    result = []
    for r in rows:
        result.append({
            "id": r.id,
            "name": r.name,
            "departments_count": int(r.departments_count),
        })

    return result

@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(org_id: int, db: Session = Depends(get_db)):
    """Get organization by ID"""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

@router.post("/", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(org_data: OrganizationCreate, db: Session = Depends(get_db)):
    """Create new organization"""
    # Check if organization name already exists
    existing_org = db.query(Organization).filter(Organization.name == org_data.name).first()
    if existing_org:
        raise HTTPException(status_code=400, detail="Organization name already exists")
    
    new_org = Organization(**org_data.dict())
    db.add(new_org)
    db.commit()
    db.refresh(new_org)
    return new_org

@router.put("/{org_id}", response_model=OrganizationOut)
async def update_organization(org_id: int, org_data: OrganizationCreate, db: Session = Depends(get_db)):
    """Update organization"""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check if new name already exists (excluding current org)
    existing_org = db.query(Organization).filter(
        Organization.name == org_data.name,
        Organization.id != org_id
    ).first()
    if existing_org:
        raise HTTPException(status_code=400, detail="Organization name already exists")
    
    for field, value in org_data.dict().items():
        setattr(org, field, value)
    
    db.commit()
    db.refresh(org)
    return org

@router.put("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: int, 
    org_data: OrganizationUpdate, 
    db: Session = Depends(get_db)
):
    """Update organization"""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Check if new name already exists (excluding current org)
    if org_data.name and org_data.name != org.name:
        existing_org = db.query(Organization).filter(
            Organization.name == org_data.name,
            Organization.id != org_id
        ).first()
        if existing_org:
            raise HTTPException(status_code=400, detail="Organization name already exists")
    
    # Check if new code already exists (excluding current org)
    if org_data.code and org_data.code != org.code:
        existing_org = db.query(Organization).filter(
            Organization.code == org_data.code,
            Organization.id != org_id
        ).first()
        if existing_org:
            raise HTTPException(status_code=400, detail="Organization code already exists")
    
    # Update fields
    update_data = org_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(org, field, value)
    
    db.commit()
    db.refresh(org)
    return org