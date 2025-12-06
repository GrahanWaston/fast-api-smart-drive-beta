# routers/document_categories.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from connection.database import SessionLocal
from models.models import DocumentCategory, User
from connection.schemas import (
    DocumentCategoryCreate, 
    DocumentCategoryOut, 
    DocumentCategoryUpdate
)
from routers.auth import get_current_user

router = APIRouter(prefix="/document-categories", tags=["document-categories"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=DocumentCategoryOut)
def create_document_category(
    category: DocumentCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create new document category
    Access: super_admin, org_admin
    """
    print(f"📁 CREATE CATEGORY - User: {current_user.name}, Role: {current_user.role}", flush=True)
    
    # Authorization check
    if current_user.role not in ['super_admin', 'org_admin']:
        raise HTTPException(403, "Only super admin and org admin can create categories")
    
    # Org admin can only create for their organization
    if current_user.role == 'org_admin':
        if category.organization_id != current_user.organization_id:
            raise HTTPException(403, "You can only create categories for your organization")
    
    # Check if code already exists in this organization
    existing = db.query(DocumentCategory).filter(
        DocumentCategory.code == category.code,
        DocumentCategory.organization_id == category.organization_id
    ).first()
    
    if existing:
        raise HTTPException(400, "Category code already exists in this organization")
    
    new_category = DocumentCategory(
        name=category.name,
        code=category.code,
        description=category.description,
        organization_id=category.organization_id,
        created_by=current_user.id
    )
    
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    
    print(f"✅ Category created: {new_category.name} (ID: {new_category.id})", flush=True)
    return new_category

@router.get("/", response_model=List[DocumentCategoryOut])
def list_document_categories(
    org_id: Optional[int] = Query(None, description="Filter by organization ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List document categories
    Access: All users (filtered by organization)
    """
    print(f"📁 LIST CATEGORIES - User: {current_user.name}", flush=True)
    
    query = db.query(DocumentCategory).options(
        joinedload(DocumentCategory.organization),
        joinedload(DocumentCategory.creator)
    )
    
    # Filter based on user role
    if current_user.role == 'super_admin':
        # Super admin can see all
        if org_id:
            query = query.filter(DocumentCategory.organization_id == org_id)
    else:
        # Other users only see their organization's categories
        query = query.filter(DocumentCategory.organization_id == current_user.organization_id)
    
    categories = query.order_by(DocumentCategory.name).all()
    print(f"✅ Found {len(categories)} categories", flush=True)
    
    return categories

@router.get("/{category_id}", response_model=DocumentCategoryOut)
def get_document_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get document category by ID
    Access: All users (must be in same organization)
    """
    category = db.query(DocumentCategory).options(
        joinedload(DocumentCategory.organization),
        joinedload(DocumentCategory.creator)
    ).filter(DocumentCategory.id == category_id).first()
    
    if not category:
        raise HTTPException(404, "Category not found")
    
    # Authorization check
    if current_user.role != 'super_admin':
        if category.organization_id != current_user.organization_id:
            raise HTTPException(403, "Access denied")
    
    return category

@router.put("/{category_id}", response_model=DocumentCategoryOut)
def update_document_category(
    category_id: int,
    category_update: DocumentCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update document category
    Access: super_admin, org_admin
    """
    category = db.query(DocumentCategory).filter(
        DocumentCategory.id == category_id
    ).first()
    
    if not category:
        raise HTTPException(404, "Category not found")
    
    # Authorization check
    if current_user.role not in ['super_admin', 'org_admin']:
        raise HTTPException(403, "Only super admin and org admin can update categories")
    
    if current_user.role == 'org_admin':
        if category.organization_id != current_user.organization_id:
            raise HTTPException(403, "You can only update categories in your organization")
    
    # Update fields
    if category_update.name is not None:
        category.name = category_update.name
        
    if category_update.code is not None:
        # Check if new code already exists
        existing = db.query(DocumentCategory).filter(
            DocumentCategory.code == category_update.code,
            DocumentCategory.organization_id == category.organization_id,
            DocumentCategory.id != category_id
        ).first()
        if existing:
            raise HTTPException(400, "Category code already exists")
        category.code = category_update.code
        
    if category_update.description is not None:
        category.description = category_update.description
    
    db.add(category)
    db.commit()
    db.refresh(category)
    
    print(f"✅ Category updated: {category.name}", flush=True)
    return category

@router.delete("/{category_id}")
def delete_document_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete document category
    Access: super_admin, org_admin
    Note: Documents using this category will have their category_id set to NULL
    """
    category = db.query(DocumentCategory).filter(
        DocumentCategory.id == category_id
    ).first()
    
    if not category:
        raise HTTPException(404, "Category not found")
    
    # Authorization check
    if current_user.role not in ['super_admin', 'org_admin']:
        raise HTTPException(403, "Only super admin and org admin can delete categories")
    
    if current_user.role == 'org_admin':
        if category.organization_id != current_user.organization_id:
            raise HTTPException(403, "You can only delete categories in your organization")
    
    # Check if category is in use
    from models.models import Document
    docs_count = db.query(Document).filter(
        Document.document_category_id == category_id
    ).count()
    
    category_name = category.name
    db.delete(category)
    db.commit()
    
    print(f"✅ Category deleted: {category_name} ({docs_count} documents affected)", flush=True)
    
    return {
        "success": True,
        "message": f"Category '{category_name}' deleted successfully",
        "affected_documents": docs_count
    }

@router.get("/statistics/by-organization")
def get_category_statistics(
    org_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get category usage statistics
    Access: super_admin, org_admin
    """
    if current_user.role not in ['super_admin', 'org_admin']:
        raise HTTPException(403, "Access denied")
    
    from models.models import Document
    from sqlalchemy import func
    
    # Determine which organization to query
    target_org_id = org_id
    if current_user.role == 'org_admin':
        target_org_id = current_user.organization_id
    
    query = db.query(
        DocumentCategory.id,
        DocumentCategory.name,
        DocumentCategory.code,
        func.count(Document.id).label('document_count')
    ).outerjoin(Document).group_by(
        DocumentCategory.id,
        DocumentCategory.name,
        DocumentCategory.code
    )
    
    if target_org_id:
        query = query.filter(DocumentCategory.organization_id == target_org_id)
    
    results = query.all()
    
    return [
        {
            "category_id": r.id,
            "category_name": r.name,
            "category_code": r.code,
            "document_count": r.document_count
        }
        for r in results
    ]