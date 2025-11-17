# routers/logs.py
from typing import Optional
from fastapi import APIRouter, Depends, Query
from connection.database import SessionLocal
from models.models import ActivityLog
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

router = APIRouter(prefix="/logs", tags=["logs"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/activity-logs")
async def get_activity_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    status_response: Optional[str] = Query(None),
    sort_by: str = Query("timestamp", regex="^(timestamp|status_code|duration_ms)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    """
    Server-side pagination & filtering untuk activity logs
    
    Query params:
    - skip: offset (default 0)
    - limit: items per page (default 50, max 100)
    - search: cari by path atau method
    - method: filter by GET, POST, PUT, DELETE, PATCH
    - status_response: filter by success, failed, error
    - sort_by: timestamp, status_code, atau duration_ms
    - sort_order: asc atau desc
    """
    
    # Base query
    query = db.query(ActivityLog)
    
    # Filter by search term (path atau method)
    if search:
        query = query.filter(
            or_(
                ActivityLog.path.ilike(f"%{search}%"),
                ActivityLog.method.ilike(f"%{search}%")
            )
        )
    
    # Filter by method
    if method:
        query = query.filter(ActivityLog.method == method.upper())
    
    # Filter by response status
    if status_response:
        query = query.filter(ActivityLog.response_status == status_response)
    
    # Get total count sebelum pagination
    total = query.count()
    
    # Sort
    sort_column = getattr(ActivityLog, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Pagination
    logs = query.offset(skip).limit(limit).all()
    
    # Format response
    return {
        "data": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "method": log.method,
                "path": log.path,
                "status_code": log.status_code,
                "duration_ms": log.duration_ms,
                "client_ip": log.client_ip,
                "user_id": log.user_id,
                "query_params": log.query_params,
                "response_status": log.response_status
            }
            for log in logs
        ],
        "pagination": {
            "skip": skip,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit,
            "current_page": (skip // limit) + 1 if total > 0 else 1
        }
    }

@router.get("/activity-logs/summary")
async def get_activity_summary(db: Session = Depends(get_db)):
    """Summary activity logs"""
    
    total = db.query(func.count(ActivityLog.id)).scalar() or 0
    
    method_count = db.query(
        ActivityLog.method,
        func.count(ActivityLog.id).label("count")
    ).group_by(ActivityLog.method).all()
    
    status_code_count = db.query(
        ActivityLog.status_code,
        func.count(ActivityLog.id).label("count")
    ).group_by(ActivityLog.status_code).all()
    
    response_status_count = db.query(
        ActivityLog.response_status,
        func.count(ActivityLog.id).label("count")
    ).group_by(ActivityLog.response_status).all()
    
    avg_duration = db.query(func.avg(ActivityLog.duration_ms)).scalar()
    
    return {
        "total_logs": total,
        "by_method": {m: c for m, c in method_count},
        "by_status_code": {int(s): c for s, c in status_code_count},
        "by_response_status": {s: c for s, c in response_status_count},
        "avg_duration_ms": float(avg_duration) if avg_duration else 0
    }