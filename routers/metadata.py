from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from connection.database import SessionLocal
from models.models import DocumentMetadata
from connection.schemas import MetadataCreate, MetadataOut

router = APIRouter(prefix="/meta", tags=["metadata"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.post("/", response_model=MetadataOut)
def create_metadata(payload: MetadataCreate, db: Session = Depends(get_db)):
    m = DocumentMetadata(**payload.dict())
    db.add(m); db.commit(); db.refresh(m)
    return m

@router.get("/{doc_id}", response_model=MetadataOut)
def get_metadata(doc_id: int, db: Session = Depends(get_db)):
    m = db.query(DocumentMetadata).filter_by(document_id=doc_id).first()
    if not m:
        raise HTTPException(404, "No metadata")
    return m