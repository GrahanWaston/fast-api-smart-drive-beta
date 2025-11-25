# routers/directories.py 

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
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
    """Recursively update status - OPTIMIZED with bulk operations"""
    timestamp = datetime.utcnow()
    
    # Get all child directory IDs recursively
    child_dir_ids = []
    
    def collect_child_ids(pid):
        children = db.query(Directory.id).filter(Directory.parent_id == pid).all()
        for (child_id,) in children:
            child_dir_ids.append(child_id)
            collect_child_ids(child_id)
    
    collect_child_ids(parent_id)
    
    # ✅ OPTIMIZATION: Bulk update directories
    if child_dir_ids:
        update_dict = {Directory.status: status}
        if timestamp_field:
            update_dict[getattr(Directory, timestamp_field)] = timestamp
        
        db.query(Directory).filter(
            Directory.id.in_(child_dir_ids)
        ).update(update_dict, synchronize_session=False)
    
    # ✅ OPTIMIZATION: Bulk update documents
    all_dir_ids = [parent_id] + child_dir_ids
    update_dict = {Document.status: status}
    if timestamp_field:
        update_dict[getattr(Document, timestamp_field)] = timestamp
    
    db.query(Document).filter(
        Document.directory_id.in_(all_dir_ids)
    ).update(update_dict, synchronize_session=False)


@router.post("/", response_model=DirectoryOut)
def create_directory(
    payload: DirectoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"📁 CREATE DIRECTORY - User: {current_user.name}", flush=True)
    
    # Use org/dept from user if not in payload
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
    
    # Eager load relationships
    d = db.query(Directory).options(
        joinedload(Directory.department),
        joinedload(Directory.organization)
    ).filter(Directory.id == d.id).first()
    
    return d


@router.get("/", response_model=List[DirectoryOut])
def list_directories(
    parent_id: Optional[str] = Query(None),
    is_directory: bool = Query(True),
    status: Optional[StatusEnum] = Query(StatusEnum.ACTIVE),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    OPTIMIZED VERSION - Uses eager loading to prevent N+1 queries
    """
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

    # ✅ OPTIMIZATION 1: Use joinedload for eager loading
    q = db.query(Directory).options(
        joinedload(Directory.department),
        joinedload(Directory.organization)
    ).filter(
        Directory.parent_id == parent_id,
        Directory.is_directory == is_directory,
        Directory.status == status
    )
    
    # Apply filters only if not [0]
    if accessible_orgs != [0]:
        q = q.filter(Directory.organization_id.in_(accessible_orgs))
    
    if accessible_depts != [0]:
        q = q.filter(Directory.department_id.in_(accessible_depts))
    
    # ✅ OPTIMIZATION 2: Execute query once
    directories = q.all()
    print(f"📂 Found {len(directories)} directories", flush=True)
    
    return directories


@router.get("/archived", response_model=List[DirectoryOut])
def list_archived_directories(
    db: Session = Depends(get_db)
):
    """Get all archived directories - OPTIMIZED"""
    return db.query(Directory).options(
        joinedload(Directory.department),
        joinedload(Directory.organization)
    ).filter(Directory.status == StatusEnum.ARCHIVED).all()


@router.get("/trash", response_model=List[DirectoryOut])
def list_trashed_directories(
    db: Session = Depends(get_db)
):
    """Get all trashed directories - OPTIMIZED"""
    return db.query(Directory).options(
        joinedload(Directory.department),
        joinedload(Directory.organization)
    ).filter(Directory.status == StatusEnum.TRASHED).all()


@router.put("/{directory_id}/archive", response_model=StatusUpdateResponse)
def archive_directory(
    directory_id: int,
    db: Session = Depends(get_db)
):
    """Archive a directory and all its contents - OPTIMIZED"""
    directory = db.query(Directory).filter(Directory.id == directory_id).first()
    if not directory:
        raise HTTPException(404, "Directory not found")
    
    if directory.status != StatusEnum.ACTIVE:
        raise HTTPException(400, f"Cannot archive directory with status: {directory.status.value}")
    
    # Archive the directory
    directory.status = StatusEnum.ARCHIVED
    directory.archived_at = datetime.utcnow()
    db.add(directory)
    
    # Archive all children recursively (now optimized)
    update_children_status_recursive(db, directory_id, StatusEnum.ARCHIVED, "archived_at")
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Directory '{directory.name}' and all its contents have been archived",
        affected_items=1
    )


@router.put("/{directory_id}/restore", response_model=StatusUpdateResponse)
def restore_directory(
    directory_id: int,
    db: Session = Depends(get_db)
):
    """Restore a directory - OPTIMIZED"""
    directory = db.query(Directory).filter(Directory.id == directory_id).first()
    if not directory:
        raise HTTPException(404, "Directory not found")
    
    if directory.status == StatusEnum.ACTIVE:
        raise HTTPException(400, "Directory is already active")
    
    # Check parent status
    if directory.parent_id:
        parent = db.query(Directory).filter(Directory.id == directory.parent_id).first()
        if not parent or parent.status != StatusEnum.ACTIVE:
            raise HTTPException(400, "Cannot restore: parent directory is not active")
    
    # Restore the directory
    directory.status = StatusEnum.ACTIVE
    directory.archived_at = None
    directory.trashed_at = None
    db.add(directory)
    
    # Restore all children recursively (optimized)
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
    """Move to trash - OPTIMIZED"""
    directory = db.query(Directory).filter(Directory.id == directory_id).first()
    if not directory:
        raise HTTPException(404, "Directory not found")
    
    if directory.status == StatusEnum.TRASHED:
        raise HTTPException(400, "Directory is already in trash")
    
    directory.status = StatusEnum.TRASHED
    directory.trashed_at = datetime.utcnow()
    db.add(directory)
    
    # Move all children to trash (optimized)
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
    """Permanently delete - OPTIMIZED counting"""
    directory = db.query(Directory).filter(Directory.id == directory_id).first()
    if not directory:
        raise HTTPException(404, "Directory not found")
    
    # ✅ OPTIMIZATION: Use CTE or recursive query for counting
    def count_all_children(parent_id: int):
        child_ids = []
        def collect_ids(pid):
            children = db.query(Directory.id).filter(Directory.parent_id == pid).all()
            for (cid,) in children:
                child_ids.append(cid)
                collect_ids(cid)
        collect_ids(parent_id)
        return child_ids
    
    child_dir_ids = count_all_children(directory_id)
    all_dir_ids = [directory_id] + child_dir_ids
    
    # Count documents
    documents_count = db.query(Document).filter(
        Document.directory_id.in_(all_dir_ids)
    ).count()
    
    directory_name = directory.name
    db.delete(directory)
    db.commit()
    
    total_affected = len(child_dir_ids) + 1 + documents_count
    
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
    """Bulk archive - OPTIMIZED"""
    if request.item_type != "directory":
        raise HTTPException(400, "This endpoint only supports directories")
    
    # ✅ OPTIMIZATION: Process all at once
    directories = db.query(Directory).filter(
        Directory.id.in_(request.item_ids),
        Directory.status == StatusEnum.ACTIVE
    ).all()
    
    affected_count = 0
    for directory in directories:
        directory.status = StatusEnum.ARCHIVED
        directory.archived_at = datetime.utcnow()
        db.add(directory)
        update_children_status_recursive(db, directory.id, StatusEnum.ARCHIVED, "archived_at")
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
    """Bulk trash - OPTIMIZED"""
    if request.item_type != "directory":
        raise HTTPException(400, "This endpoint only supports directories")
    
    directories = db.query(Directory).filter(
        Directory.id.in_(request.item_ids),
        Directory.status != StatusEnum.TRASHED
    ).all()
    
    affected_count = 0
    for directory in directories:
        directory.status = StatusEnum.TRASHED
        directory.trashed_at = datetime.utcnow()
        db.add(directory)
        update_children_status_recursive(db, directory.id, StatusEnum.TRASHED, "trashed_at")
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
    """Bulk restore - OPTIMIZED"""
    if request.item_type != "directory":
        raise HTTPException(400, "This endpoint only supports directories")
    
    directories = db.query(Directory).filter(
        Directory.id.in_(request.item_ids),
        Directory.status != StatusEnum.ACTIVE
    ).all()
    
    affected_count = 0
    for directory in directories:
        # Check parent
        if directory.parent_id:
            parent = db.query(Directory).filter(Directory.id == directory.parent_id).first()
            if not parent or parent.status != StatusEnum.ACTIVE:
                continue
        
        directory.status = StatusEnum.ACTIVE
        directory.archived_at = None
        directory.trashed_at = None
        db.add(directory)
        update_children_status_recursive(db, directory.id, StatusEnum.ACTIVE, None)
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
    """Bulk permanent delete - OPTIMIZED"""
    if request.item_type != "directory":
        raise HTTPException(400, "This endpoint only supports directories")
    
    # ✅ OPTIMIZATION: Let CASCADE handle children
    affected_count = db.query(Directory).filter(
        Directory.id.in_(request.item_ids)
    ).delete(synchronize_session=False)
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Successfully deleted {affected_count} directories permanently",
        affected_items=affected_count
    )