# routers/analytics.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
from connection.database import SessionLocal
from models.models import (
    Document, DocumentCategory, Directory, User, 
    Organization, Department, StatusEnum
)
from utils.authorization import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/super-admin/dashboard")
def get_super_admin_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Complete analytics dashboard for super admin"""
    if current_user.role != 'super_admin':
        raise HTTPException(403, "Access denied")
    
    # Basic counts
    total_orgs = db.query(func.count(Organization.id)).scalar()
    total_depts = db.query(func.count(Department.id)).scalar()
    total_users = db.query(func.count(User.id)).scalar()
    total_docs = db.query(func.count(Document.id)).filter(
        Document.status == StatusEnum.ACTIVE
    ).scalar()
    
    # Storage usage per organization (in bytes)
    storage_by_org = db.query(
        Organization.id,
        Organization.name,
        Organization.code,
        func.sum(Document.size).label('total_size'),
        func.count(Document.id).label('doc_count')
    ).join(Document, Document.organization_id == Organization.id).filter(
        Document.status == StatusEnum.ACTIVE
    ).group_by(Organization.id, Organization.name, Organization.code).all()
    
    org_storage = [{
        "org_id": org.id,
        "org_name": org.name,
        "org_code": org.code,
        "total_bytes": org.total_size or 0,
        "total_mb": round((org.total_size or 0) / (1024 * 1024), 2),
        "total_gb": round((org.total_size or 0) / (1024 * 1024 * 1024), 2),
        "doc_count": org.doc_count
    } for org in storage_by_org]
    
    # Documents by category
    docs_by_category = db.query(
        DocumentCategory.id,
        DocumentCategory.name,
        DocumentCategory.code,
        func.count(Document.id).label('count')
    ).join(Document, Document.document_category_id == DocumentCategory.id).filter(
        Document.status == StatusEnum.ACTIVE
    ).group_by(DocumentCategory.id, DocumentCategory.name, DocumentCategory.code).all()
    
    category_stats = [{
        "category_id": cat.id,
        "category_name": cat.name,
        "category_code": cat.code,
        "doc_count": cat.count
    } for cat in docs_by_category]
    
    # Documents by file type
    docs_by_type = db.query(
        Document.file_type,
        func.count(Document.id).label('count')
    ).filter(Document.status == StatusEnum.ACTIVE).group_by(
        Document.file_type
    ).all()
    
    type_stats = [{
        "file_type": doc.file_type or "Unknown",
        "count": doc.count
    } for doc in docs_by_type]
    
    # Documents by file category
    docs_by_file_category = db.query(
        Document.file_category,
        func.count(Document.id).label('count'),
        func.sum(Document.size).label('total_size')
    ).filter(Document.status == StatusEnum.ACTIVE).group_by(
        Document.file_category
    ).all()
    
    file_category_stats = [{
        "file_category": doc.file_category or "Unknown",
        "count": doc.count,
        "total_mb": round((doc.total_size or 0) / (1024 * 1024), 2)
    } for doc in docs_by_file_category]
    
    # Expiring documents (next 30 days)
    now = datetime.utcnow()
    thirty_days = now + timedelta(days=30)
    
    expiring_soon = db.query(
        Document.id,
        Document.name,
        Document.title_document,
        Document.expire_date,
        Organization.name.label('org_name'),
        Department.name.label('dept_name')
    ).join(Organization, Document.organization_id == Organization.id).join(
        Department, Document.department_id == Department.id
    ).filter(
        Document.status == StatusEnum.ACTIVE,
        Document.expire_date.isnot(None),
        Document.expire_date >= now,
        Document.expire_date <= thirty_days
    ).order_by(Document.expire_date).all()
    
    expiring_docs = [{
        "doc_id": doc.id,
        "doc_name": doc.name,
        "doc_title": doc.title_document,
        "expire_date": doc.expire_date.isoformat() if doc.expire_date else None,
        "org_name": doc.org_name,
        "dept_name": doc.dept_name,
        "days_remaining": (doc.expire_date - now).days if doc.expire_date else None
    } for doc in expiring_soon]
    
    # Expired documents
    expired_docs = db.query(func.count(Document.id)).filter(
        Document.status == StatusEnum.ACTIVE,
        Document.expire_date.isnot(None),
        Document.expire_date < now
    ).scalar()
    
    # User distribution by role
    users_by_role = db.query(
        User.role,
        func.count(User.id).label('count')
    ).group_by(User.role).all()
    
    role_stats = [{
        "role": user.role,
        "count": user.count
    } for user in users_by_role]
    
    # Recent uploads (last 7 days)
    seven_days_ago = now - timedelta(days=7)
    recent_uploads = db.query(func.count(Document.id)).filter(
        Document.created_at >= seven_days_ago
    ).scalar()
    
    return {
        "summary": {
            "total_organizations": total_orgs,
            "total_departments": total_depts,
            "total_users": total_users,
            "total_documents": total_docs,
            "expired_documents": expired_docs,
            "recent_uploads": recent_uploads
        },
        "storage_by_organization": org_storage,
        "documents_by_category": category_stats,
        "documents_by_type": type_stats,
        "documents_by_file_category": file_category_stats,
        "expiring_documents": expiring_docs,
        "users_by_role": role_stats
    }

@router.get("/org-admin/dashboard")
def get_org_admin_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Analytics dashboard for organization admin"""
    if current_user.role not in ['super_admin', 'org_admin']:
        raise HTTPException(403, "Access denied")
    
    org_id = current_user.organization_id
    
    # Basic counts
    total_depts = db.query(func.count(Department.id)).filter(
        Department.org_id == org_id
    ).scalar()
    
    total_users = db.query(func.count(User.id)).filter(
        User.organization_id == org_id
    ).scalar()
    
    total_docs = db.query(func.count(Document.id)).filter(
        Document.organization_id == org_id,
        Document.status == StatusEnum.ACTIVE
    ).scalar()
    
    # Storage usage
    total_storage = db.query(func.sum(Document.size)).filter(
        Document.organization_id == org_id,
        Document.status == StatusEnum.ACTIVE
    ).scalar() or 0
    
    # Storage by department
    storage_by_dept = db.query(
        Department.id,
        Department.name,
        Department.code,
        func.sum(Document.size).label('total_size'),
        func.count(Document.id).label('doc_count')
    ).join(Document, Document.department_id == Department.id).filter(
        Department.org_id == org_id,
        Document.status == StatusEnum.ACTIVE
    ).group_by(Department.id, Department.name, Department.code).all()
    
    dept_storage = [{
        "dept_id": dept.id,
        "dept_name": dept.name,
        "dept_code": dept.code,
        "total_bytes": dept.total_size or 0,
        "total_mb": round((dept.total_size or 0) / (1024 * 1024), 2),
        "total_gb": round((dept.total_size or 0) / (1024 * 1024 * 1024), 2),
        "doc_count": dept.doc_count
    } for dept in storage_by_dept]
    
    # Documents by category
    docs_by_category = db.query(
        DocumentCategory.name,
        func.count(Document.id).label('count')
    ).join(Document, Document.document_category_id == DocumentCategory.id).filter(
        Document.organization_id == org_id,
        Document.status == StatusEnum.ACTIVE
    ).group_by(DocumentCategory.name).all()
    
    category_stats = [{
        "category_name": cat.name,
        "doc_count": cat.count
    } for cat in docs_by_category]
    
    # Documents by file category
    docs_by_file_category = db.query(
        Document.file_category,
        func.count(Document.id).label('count'),
        func.sum(Document.size).label('total_size')
    ).filter(
        Document.organization_id == org_id,
        Document.status == StatusEnum.ACTIVE
    ).group_by(Document.file_category).all()
    
    file_category_stats = [{
        "file_category": doc.file_category or "Unknown",
        "count": doc.count,
        "total_mb": round((doc.total_size or 0) / (1024 * 1024), 2)
    } for doc in docs_by_file_category]
    
    # Expiring documents
    now = datetime.utcnow()
    thirty_days = now + timedelta(days=30)
    
    expiring_soon = db.query(
        Document.id,
        Document.name,
        Document.title_document,
        Document.expire_date,
        Department.name.label('dept_name')
    ).join(Department, Document.department_id == Department.id).filter(
        Document.organization_id == org_id,
        Document.status == StatusEnum.ACTIVE,
        Document.expire_date.isnot(None),
        Document.expire_date >= now,
        Document.expire_date <= thirty_days
    ).order_by(Document.expire_date).all()
    
    expiring_docs = [{
        "doc_id": doc.id,
        "doc_name": doc.name,
        "doc_title": doc.title_document,
        "expire_date": doc.expire_date.isoformat() if doc.expire_date else None,
        "dept_name": doc.dept_name,
        "days_remaining": (doc.expire_date - now).days if doc.expire_date else None
    } for doc in expiring_soon]
    
    # Expired documents
    expired_docs = db.query(func.count(Document.id)).filter(
        Document.organization_id == org_id,
        Document.status == StatusEnum.ACTIVE,
        Document.expire_date.isnot(None),
        Document.expire_date < now
    ).scalar()
    
    # Users by role
    users_by_role = db.query(
        User.role,
        func.count(User.id).label('count')
    ).filter(
        User.organization_id == org_id
    ).group_by(User.role).all()
    
    role_stats = [{
        "role": user.role,
        "count": user.count
    } for user in users_by_role]
    
    return {
        "summary": {
            "total_departments": total_depts,
            "total_users": total_users,
            "total_documents": total_docs,
            "total_storage_bytes": total_storage,
            "total_storage_mb": round(total_storage / (1024 * 1024), 2),
            "total_storage_gb": round(total_storage / (1024 * 1024 * 1024), 2),
            "expired_documents": expired_docs
        },
        "storage_by_department": dept_storage,
        "documents_by_category": category_stats,
        "documents_by_file_category": file_category_stats,
        "expiring_documents": expiring_docs,
        "users_by_role": role_stats
    }

@router.get("/dept-head/dashboard")
def get_dept_head_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Analytics dashboard for department head"""
    if current_user.role not in ['super_admin', 'org_admin', 'dept_head']:
        raise HTTPException(403, "Access denied")
    
    dept_id = current_user.department_id
    
    # Basic counts
    total_users = db.query(func.count(User.id)).filter(
        User.department_id == dept_id
    ).scalar()
    
    total_docs = db.query(func.count(Document.id)).filter(
        Document.department_id == dept_id,
        Document.status == StatusEnum.ACTIVE
    ).scalar()
    
    # Storage usage
    total_storage = db.query(func.sum(Document.size)).filter(
        Document.department_id == dept_id,
        Document.status == StatusEnum.ACTIVE
    ).scalar() or 0
    
    # Documents by file category
    docs_by_file_category = db.query(
        Document.file_category,
        func.count(Document.id).label('count'),
        func.sum(Document.size).label('total_size')
    ).filter(
        Document.department_id == dept_id,
        Document.status == StatusEnum.ACTIVE
    ).group_by(Document.file_category).all()
    
    file_category_stats = [{
        "file_category": doc.file_category or "Unknown",
        "count": doc.count,
        "total_mb": round((doc.total_size or 0) / (1024 * 1024), 2)
    } for doc in docs_by_file_category]
    
    # Documents by owner
    docs_by_owner = db.query(
        Document.file_owner,
        func.count(Document.id).label('count')
    ).filter(
        Document.department_id == dept_id,
        Document.status == StatusEnum.ACTIVE
    ).group_by(Document.file_owner).all()
    
    owner_stats = [{
        "owner_name": doc.file_owner or "Unknown",
        "doc_count": doc.count
    } for doc in docs_by_owner]
    
    # Expiring documents
    now = datetime.utcnow()
    thirty_days = now + timedelta(days=30)
    
    expiring_soon = db.query(
        Document.id,
        Document.name,
        Document.title_document,
        Document.expire_date,
        Document.file_owner
    ).filter(
        Document.department_id == dept_id,
        Document.status == StatusEnum.ACTIVE,
        Document.expire_date.isnot(None),
        Document.expire_date >= now,
        Document.expire_date <= thirty_days
    ).order_by(Document.expire_date).all()
    
    expiring_docs = [{
        "doc_id": doc.id,
        "doc_name": doc.name,
        "doc_title": doc.title_document,
        "expire_date": doc.expire_date.isoformat() if doc.expire_date else None,
        "owner": doc.file_owner,
        "days_remaining": (doc.expire_date - now).days if doc.expire_date else None
    } for doc in expiring_soon]
    
    # Expired documents
    expired_docs = db.query(func.count(Document.id)).filter(
        Document.department_id == dept_id,
        Document.status == StatusEnum.ACTIVE,
        Document.expire_date.isnot(None),
        Document.expire_date < now
    ).scalar()
    
    return {
        "summary": {
            "total_users": total_users,
            "total_documents": total_docs,
            "total_storage_bytes": total_storage,
            "total_storage_mb": round(total_storage / (1024 * 1024), 2),
            "total_storage_gb": round(total_storage / (1024 * 1024 * 1024), 2),
            "expired_documents": expired_docs
        },
        "documents_by_file_category": file_category_stats,
        "documents_by_owner": owner_stats,
        "expiring_documents": expiring_docs
    }
    
@router.get("/super-admin/charts")
def get_super_admin_charts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get chart data for super admin dashboard"""
    if current_user.role != 'super_admin':
        raise HTTPException(403, "Access denied")
    
    # Storage chart per organization (untuk pie/bar chart)
    storage_chart = db.query(
        Organization.name.label('label'),
        func.sum(Document.size).label('value')
    ).join(Document, Document.organization_id == Organization.id).filter(
        Document.status == StatusEnum.ACTIVE
    ).group_by(Organization.name).all()
    
    # Document category distribution
    category_chart = db.query(
        DocumentCategory.name.label('label'),
        func.count(Document.id).label('value')
    ).join(Document, Document.document_category_id == DocumentCategory.id).filter(
        Document.status == StatusEnum.ACTIVE
    ).group_by(DocumentCategory.name).all()
    
    # File type distribution
    file_type_chart = db.query(
        Document.file_category.label('label'),
        func.count(Document.id).label('value')
    ).filter(
        Document.status == StatusEnum.ACTIVE
    ).group_by(Document.file_category).all()
    
    # Upload trend (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    upload_trend = db.query(
        func.date(Document.created_at).label('date'),
        func.count(Document.id).label('count')
    ).filter(
        Document.created_at >= thirty_days_ago
    ).group_by(func.date(Document.created_at)).order_by('date').all()
    
    return {
        "storage_by_org": [
            {"label": item.label, "value": round((item.value or 0) / (1024 * 1024 * 1024), 2)}
            for item in storage_chart
        ],
        "docs_by_category": [
            {"label": item.label, "value": item.value}
            for item in category_chart
        ],
        "docs_by_file_type": [
            {"label": item.label or "Unknown", "value": item.value}
            for item in file_type_chart
        ],
        "upload_trend": [
            {"date": item.date.isoformat(), "count": item.count}
            for item in upload_trend
        ]
    }

@router.get("/org-admin/charts")
def get_org_admin_charts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get chart data for org admin dashboard"""
    if current_user.role not in ['super_admin', 'org_admin']:
        raise HTTPException(403, "Access denied")
    
    org_id = current_user.organization_id
    
    # Storage by department
    storage_chart = db.query(
        Department.name.label('label'),
        func.sum(Document.size).label('value')
    ).join(Document, Document.department_id == Department.id).filter(
        Department.org_id == org_id,
        Document.status == StatusEnum.ACTIVE
    ).group_by(Department.name).all()
    
    # Documents by category
    category_chart = db.query(
        DocumentCategory.name.label('label'),
        func.count(Document.id).label('value')
    ).join(Document, Document.document_category_id == DocumentCategory.id).filter(
        Document.organization_id == org_id,
        Document.status == StatusEnum.ACTIVE
    ).group_by(DocumentCategory.name).all()
    
    # Upload trend (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    upload_trend = db.query(
        func.date(Document.created_at).label('date'),
        func.count(Document.id).label('count')
    ).filter(
        Document.organization_id == org_id,
        Document.created_at >= thirty_days_ago
    ).group_by(func.date(Document.created_at)).order_by('date').all()
    
    return {
        "storage_by_dept": [
            {"label": item.label, "value": round((item.value or 0) / (1024 * 1024 * 1024), 2)}
            for item in storage_chart
        ],
        "docs_by_category": [
            {"label": item.label, "value": item.value}
            for item in category_chart
        ],
        "upload_trend": [
            {"date": item.date.isoformat(), "count": item.count}
            for item in upload_trend
        ]
    }