# routers/directories.py - Enhanced with archive/trash features

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from datetime import datetime
from connection.database import SessionLocal
from models.models import Directory, Document, StatusEnum
from connection.schemas import (
    DirectoryCreate, DirectoryOut, BulkActionRequest, StatusUpdateResponse
)
from utils.authorization import *

router = APIRouter(prefix="/dirs", tags=["directories"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def update_children_status_recursive(db: Session, parent_id: int, status: StatusEnum, timestamp_field: str):
    """Recursively update status of all children (directories and documents)"""
    timestamp = datetime.datetime.utcnow()
    
    # Update child directories
    child_dirs = db.query(Directory).filter(Directory.parent_id == parent_id).all()
    for child_dir in child_dirs:
        child_dir.status = status
        setattr(child_dir, timestamp_field, timestamp)
        db.add(child_dir)
        # Recursively update children's children
        update_children_status_recursive(db, child_dir.id, status, timestamp_field)
    
    # Update documents in this directory
    documents = db.query(Document).filter(Document.directory_id == parent_id).all()
    for doc in documents:
        doc.status = status
        setattr(doc, timestamp_field, timestamp)
        db.add(doc)


@router.post("/", response_model=DirectoryOut)
def create_directory(
    payload: DirectoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"📁 CREATE DIRECTORY - User: {current_user.name}", flush=True)
    
    # FIX: Ambil org/dept dari user jika tidak ada di payload
    org_id = payload.organization_id or current_user.organization_id
    dept_id = payload.department_id or current_user.department_id
    
    if not dept_id or not org_id:
        raise HTTPException(400, "User must be assigned to a department and organization")
    
    # Check parent access if provided
    if payload.parent_id:
        parent = db.query(Directory).get(payload.parent_id)
        if not parent:
            raise HTTPException(404, "Parent not found")
        if not can_access_directory(current_user, parent):
            raise HTTPException(403, "Access denied to parent directory")
    
    # Calculate level & path
    level = 0
    path = "/"
    if payload.parent_id:
        parent = db.query(Directory).get(payload.parent_id)
        level = parent.level + 1
        path = parent.path.rstrip("/") + "/" + payload.name
    
    # Create directory
    d = Directory(
        name=payload.name,
        parent_id=payload.parent_id,
        level=level,
        path=path,
        is_directory=True,
        status=StatusEnum.ACTIVE,
        organization_id=org_id,
        department_id=dept_id
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    
    # Manual serialize to avoid recursion
    return {
        "id": d.id,
        "name": d.name,
        "parent_id": d.parent_id,
        "is_directory": d.is_directory,
        "level": d.level,
        "path": d.path,
        "status": d.status,
        "archived_at": d.archived_at,
        "trashed_at": d.trashed_at,
        "department_id": d.department_id,
        "organization_id": d.organization_id,
        "department": {
            "id": d.department.id,
            "name": d.department.name,
            "code": d.department.code,
            "org_id": d.department.org_id
        } if d.department else None,
        "organization": {
            "id": d.organization.id,
            "name": d.organization.name,
            "code": d.organization.code,
            "status": d.organization.status,
            "created_at": d.organization.created_at
        } if d.organization else None
    }

@router.get("/", response_model=List[DirectoryOut])
def list_directories(
    parent_id: Optional[str] = Query(None),
    is_directory: bool = Query(True),
    status: Optional[StatusEnum] = Query(StatusEnum.ACTIVE),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"📂 LIST DIRECTORIES - User: {current_user.name}", flush=True)
    
    accessible_depts = get_accessible_departments(current_user, db)
    accessible_orgs = get_accessible_organizations(current_user, db)
    
    print(f"📂 Accessible depts: {accessible_depts}", flush=True)
    print(f"📂 Accessible orgs: {accessible_orgs}", flush=True)
    
    # Parse parent_id
    if parent_id == "null":
        parent_id = None
    else:
        try:
            parent_id = int(parent_id) if parent_id is not None else None
        except ValueError:
            raise HTTPException(400, detail="parent_id must be integer or null")

    # PERBAIKAN: Jangan return empty jika accessible lists kosong
    # Karena user mungkin belum punya assignment
    
    # Build query
    q = db.query(Directory).filter(
        Directory.parent_id == parent_id,
        Directory.is_directory == is_directory,
        Directory.status == status
    )
    
    # Apply filters hanya jika bukan [0] (sentinel value)
    if accessible_orgs != [0]:
        q = q.filter(Directory.organization_id.in_(accessible_orgs))
    
    if accessible_depts != [0]:
        q = q.filter(Directory.department_id.in_(accessible_depts))
    
    directories = q.all()
    print(f"📂 Found {len(directories)} directories", flush=True)
    
    return [
        {
            "id": d.id,
            "name": d.name,
            "parent_id": d.parent_id,
            "is_directory": d.is_directory,
            "level": d.level,
            "path": d.path,
            "status": d.status,
            "archived_at": d.archived_at,
            "trashed_at": d.trashed_at,
            "department_id": d.department_id,
            "organization_id": d.organization_id,
            # Simple nested
            "department": {
                "id": d.department.id,
                "name": d.department.name,
                "code": d.department.code,
                "org_id": d.department.org_id
            } if d.department else None,
            "organization": {
                "id": d.organization.id,
                "name": d.organization.name,
                "code": d.organization.code,
                "status": d.organization.status,
                "created_at": d.organization.created_at
            } if d.organization else None
        }
        for d in directories
    ]

@router.get("/archived", response_model=List[DirectoryOut])
def list_archived_directories(
    db: Session = Depends(get_db)
):
    """Get all archived directories"""
    return db.query(Directory).filter(Directory.status == StatusEnum.ARCHIVED).all()


@router.get("/trash", response_model=List[DirectoryOut])
def list_trashed_directories(
    db: Session = Depends(get_db)
):
    """Get all trashed directories"""
    return db.query(Directory).filter(Directory.status == StatusEnum.TRASHED).all()


@router.put("/{directory_id}/archive", response_model=StatusUpdateResponse)
def archive_directory(
    directory_id: int,
    db: Session = Depends(get_db)
):
    """Archive a directory and all its contents"""
    directory = db.query(Directory).filter(Directory.id == directory_id).first()
    if not directory:
        raise HTTPException(404, "Directory not found")
    
    if directory.status != StatusEnum.ACTIVE:
        raise HTTPException(400, f"Cannot archive directory with status: {directory.status.value}")
    
    # Archive the directory
    directory.status = StatusEnum.ARCHIVED
    directory.archived_at = datetime.datetime.utcnow()
    db.add(directory)
    
    # Archive all children recursively
    update_children_status_recursive(db, directory_id, StatusEnum.ARCHIVED, "archived_at")
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Directory '{directory.name}' and all its contents have been archived",
        affected_items=1  # Could be enhanced to count actual affected items
    )


@router.put("/{directory_id}/restore", response_model=StatusUpdateResponse)
def restore_directory(
    directory_id: int,
    db: Session = Depends(get_db)
):
    """Restore a directory from archive or trash"""
    directory = db.query(Directory).filter(Directory.id == directory_id).first()
    if not directory:
        raise HTTPException(404, "Directory not found")
    
    if directory.status == StatusEnum.ACTIVE:
        raise HTTPException(400, "Directory is already active")
    
    # Check if parent exists and is active (if has parent)
    if directory.parent_id:
        parent = db.query(Directory).filter(Directory.id == directory.parent_id).first()
        if not parent or parent.status != StatusEnum.ACTIVE:
            raise HTTPException(400, "Cannot restore: parent directory is not active")
    
    # Restore the directory
    directory.status = StatusEnum.ACTIVE
    directory.archived_at = None
    directory.trashed_at = None
    db.add(directory)
    
    # Restore all children recursively
    update_children_status_recursive(db, directory_id, StatusEnum.ACTIVE, None)
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Directory '{directory.name}' and all its contents have been restored",
        affected_items=1
    )


@router.put("/{directory_id}/trash", response_model=StatusUpdateResponse)
def move_directory_to_trash(
    directory_id: int,
    db: Session = Depends(get_db)
):
    """Move a directory to trash (soft delete)"""
    directory = db.query(Directory).filter(Directory.id == directory_id).first()
    if not directory:
        raise HTTPException(404, "Directory not found")
    
    if directory.status == StatusEnum.TRASHED:
        raise HTTPException(400, "Directory is already in trash")
    
    # Move to trash
    directory.status = StatusEnum.TRASHED
    directory.trashed_at = datetime.datetime.utcnow()
    db.add(directory)
    
    # Move all children to trash recursively
    update_children_status_recursive(db, directory_id, StatusEnum.TRASHED, "trashed_at")
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Directory '{directory.name}' and all its contents have been moved to trash",
        affected_items=1
    )


@router.delete("/{directory_id}/permanent", response_model=StatusUpdateResponse)
def delete_directory_permanent(
    directory_id: int,
    db: Session = Depends(get_db)
):
    """Permanently delete a directory and all its contents"""
    directory = db.query(Directory).filter(Directory.id == directory_id).first()
    if not directory:
        raise HTTPException(404, "Directory not found")
    
    # Get all child directories recursively for counting
    def get_all_children(parent_id: int):
        children = []
        child_dirs = db.query(Directory).filter(Directory.parent_id == parent_id).all()
        for child in child_dirs:
            children.append(child)
            children.extend(get_all_children(child.id))
        return children
    
    # Get all documents in this directory and subdirectories
    all_children = get_all_children(directory_id)
    all_dir_ids = [directory_id] + [child.id for child in all_children]
    
    # Count documents that will be deleted
    documents_count = db.query(Document).filter(Document.directory_id.in_(all_dir_ids)).count()
    
    # Delete the directory (CASCADE will handle children and documents)
    directory_name = directory.name
    db.delete(directory)
    db.commit()
    
    total_affected = len(all_children) + 1 + documents_count  # directories + documents
    
    return StatusUpdateResponse(
        success=True,
        message=f"Directory '{directory_name}' and all its contents have been permanently deleted",
        affected_items=total_affected
    )


@router.post("/bulk-archive", response_model=StatusUpdateResponse)
def bulk_archive_directories(
    request: BulkActionRequest,
    db: Session = Depends(get_db)
):
    """Archive multiple directories"""
    if request.item_type != "directory":
        raise HTTPException(400, "This endpoint only supports directories")
    
    affected_count = 0
    for dir_id in request.item_ids:
        directory = db.query(Directory).filter(Directory.id == dir_id).first()
        if directory and directory.status == StatusEnum.ACTIVE:
            directory.status = StatusEnum.ARCHIVED
            directory.archived_at = datetime.datetime.utcnow()
            db.add(directory)
            update_children_status_recursive(db, dir_id, StatusEnum.ARCHIVED, "archived_at")
            affected_count += 1
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Successfully archived {affected_count} directories",
        affected_items=affected_count
    )


@router.post("/bulk-trash", response_model=StatusUpdateResponse)
def bulk_trash_directories(
    request: BulkActionRequest,
    db: Session = Depends(get_db)
):
    """Move multiple directories to trash"""
    if request.item_type != "directory":
        raise HTTPException(400, "This endpoint only supports directories")
    
    affected_count = 0
    for dir_id in request.item_ids:
        directory = db.query(Directory).filter(Directory.id == dir_id).first()
        if directory and directory.status != StatusEnum.TRASHED:
            directory.status = StatusEnum.TRASHED
            directory.trashed_at = datetime.datetime.utcnow()
            db.add(directory)
            update_children_status_recursive(db, dir_id, StatusEnum.TRASHED, "trashed_at")
            affected_count += 1
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Successfully moved {affected_count} directories to trash",
        affected_items=affected_count
    )


@router.post("/bulk-restore", response_model=StatusUpdateResponse)
def bulk_restore_directories(
    request: BulkActionRequest,
    db: Session = Depends(get_db)
):
    """Restore multiple directories from archive or trash"""
    if request.item_type != "directory":
        raise HTTPException(400, "This endpoint only supports directories")
    
    affected_count = 0
    for dir_id in request.item_ids:
        directory = db.query(Directory).filter(Directory.id == dir_id).first()
        if directory and directory.status != StatusEnum.ACTIVE:
            # Check parent status if has parent
            if directory.parent_id:
                parent = db.query(Directory).filter(Directory.id == directory.parent_id).first()
                if not parent or parent.status != StatusEnum.ACTIVE:
                    continue  # Skip if parent is not active
            
            directory.status = StatusEnum.ACTIVE
            directory.archived_at = None
            directory.trashed_at = None
            db.add(directory)
            update_children_status_recursive(db, dir_id, StatusEnum.ACTIVE, None)
            affected_count += 1
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Successfully restored {affected_count} directories",
        affected_items=affected_count
    )


@router.delete("/bulk-permanent", response_model=StatusUpdateResponse)
def bulk_delete_directories_permanent(
    request: BulkActionRequest,
    db: Session = Depends(get_db)
):
    """Permanently delete multiple directories"""
    if request.item_type != "directory":
        raise HTTPException(400, "This endpoint only supports directories")
    
    affected_count = 0
    for dir_id in request.item_ids:
        directory = db.query(Directory).filter(Directory.id == dir_id).first()
        if directory:
            db.delete(directory)  # CASCADE will handle children
            affected_count += 1
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Successfully deleted {affected_count} directories permanently",
        affected_items=affected_count
    )