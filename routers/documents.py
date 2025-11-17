# routers/documents.py - Enhanced with archive/trash features

from io import BytesIO
import json
import os
import secrets
import shutil
import tempfile
from fastapi import APIRouter, Depends, Query, Response, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session
from typing import List, Optional
from pdfminer.high_level import extract_text
from docx import Document as DocxDoc
from PIL import Image
import pytesseract
import openpyxl
from datetime import datetime, timedelta, timezone
from utils.authorization import *

from connection.database import SessionLocal
from models.models import Document, DocumentContent, StatusEnum, Directory, DocumentShare
from connection.schemas import (
    DocumentCreate, DocumentOut, ContentOut, BulkActionRequest, DocumentShareCreate, DocumentShareOut, StatusUpdateResponse
)

router = APIRouter(prefix="/docs", tags=["documents"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=DocumentOut)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title_document: str = Form(None),
    directory_id: int = Form(None),
    exp_date: str = Form(None),
    tags: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.department_id or not current_user.organization_id:
        raise HTTPException(400, "User must be assigned to a department and organization")
    
    # Check if directory exists and user has access
    if directory_id:
        directory = db.query(Directory).filter(Directory.id == directory_id).first()
        if not directory:
            raise HTTPException(404, "Directory not found")
        if not can_access_directory(current_user, directory):
            raise HTTPException(403, "Access denied to this directory")
    
    # Baca data biner
    content_bytes = await file.read()
    size = len(content_bytes)

    # Simpan metadata dokumen
    doc = Document(
        name=file.filename,
        title_document=title_document or file.filename,
        mimetype=file.content_type,
        size=size,
        data=content_bytes,
        directory_id=directory_id,
        status=StatusEnum.ACTIVE,
        organization_id=current_user.organization_id,
        department_id=current_user.department_id,
        created_by=current_user.id
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Simpan metadata tambahan jika ada
    if exp_date or tags or description:
        from models.models import DocumentMetadata
        
        metadata = DocumentMetadata(
            document_id=doc.id,
            tags=tags,
            description=description
        )
        
        # Parse exp_date jika ada
        if exp_date:
            try:
                metadata.exp_date = datetime.datetime.strptime(exp_date, "%Y-%m-%d")
            except ValueError:
                pass  # Ignore invalid date format
        
        db.add(metadata)
        db.commit()

    def extract_and_store(doc_id: int, data: bytes, ext: str, mimetype: str):
        text = ""
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmpf:
            tmpf.write(data)
            tmpf.flush()

            # PDF
            if ext.lower() == "pdf":
                try:
                    text = extract_text(tmpf.name)
                except Exception:
                    text = ""
            # Word .docx / .doc
            elif ext.lower() in ("docx", "doc"):
                try:
                    d = DocxDoc(tmpf.name)
                    text = "\n".join(p.text for p in d.paragraphs)
                except Exception:
                    text = ""
            # Excel .xlsx
            elif ext.lower() in ("xlsx", "xls"):
                try:
                    wb = openpyxl.load_workbook(tmpf.name, read_only=True)
                    parts = []
                    for sheet in wb.worksheets:
                        for row in sheet.iter_rows(values_only=True):
                            parts.append(" ".join(str(c)
                                         for c in row if c is not None))
                    text = "\n".join(parts)
                except Exception:
                    text = ""
            # Image OCR (png/jpg/jpeg)
            elif mimetype.startswith("image/"):
                try:
                    img = Image.open(tmpf.name)
                    text = pytesseract.image_to_string(img)
                except Exception:
                    text = ""
            else:
                # Fallback: coba OCR di image
                try:
                    img = Image.open(tmpf.name)
                    text = pytesseract.image_to_string(img)
                except Exception:
                    text = ""

        db2 = SessionLocal()
        try:
            cc = DocumentContent(document_id=doc_id,
                                 content=text, ocr_result=text)
            db2.add(cc)
            db2.commit()
        finally:
            db2.close()

    # Schedule background extraction
    ext = file.filename.split(".")[-1]
    background_tasks.add_task(
        extract_and_store, doc.id, content_bytes, ext, file.content_type)

    return doc


@router.get("/", response_model=List[DocumentOut])
def list_documents(
    directory_id: int = None,
    status: Optional[StatusEnum] = Query(StatusEnum.ACTIVE),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"📄 LIST DOCUMENTS - User: {current_user.name}", flush=True)
    
    accessible_depts = get_accessible_departments(current_user, db)
    accessible_orgs = get_accessible_organizations(current_user, db)
    
    print(f"📄 Accessible depts: {accessible_depts}", flush=True)
    print(f"📄 Accessible orgs: {accessible_orgs}", flush=True)
    
    # Build query
    query = db.query(Document).filter(
        Document.directory_id == directory_id,
        Document.status == status
    )
    
    # Apply filters hanya jika bukan [0] (sentinel value)
    if accessible_orgs != [0]:
        query = query.filter(Document.organization_id.in_(accessible_orgs))
    
    if accessible_depts != [0]:
        query = query.filter(Document.department_id.in_(accessible_depts))
    
    documents = query.all()
    print(f"📄 Found {len(documents)} documents", flush=True)
    
    return documents


@router.get("/archived", response_model=List[DocumentOut])
def list_archived_documents(
    db: Session = Depends(get_db)
):
    """Get all archived documents"""
    return db.query(Document).filter(Document.status == StatusEnum.ARCHIVED).all()


@router.get("/trash", response_model=List[DocumentOut])
def list_trashed_documents(
    db: Session = Depends(get_db)
):
    """Get all trashed documents"""
    return db.query(Document).filter(Document.status == StatusEnum.TRASHED).all()


@router.get("/search", response_model=List[DocumentOut])
def search_documents(
    q: Optional[str] = Query(None, description="Search title or content"),
    title: Optional[str] = Query(None, description="Title contains"),
    has_words: Optional[str] = Query(
        None, description="Content must include all these words"),
    folder_id: Optional[int] = Query(None, description="Filter by folder"),
    mimetype: Optional[str] = Query(None, description="Filter by MIME type"),
    status: Optional[StatusEnum] = Query(StatusEnum.ACTIVE, description="Filter by status"),
    db: Session = Depends(get_db)
):
    query = db.query(Document).filter(Document.status == status)

    if q:
        query = query.outerjoin(DocumentContent).filter(
            or_(
                Document.title_document.ilike(f"%{q}%"),
                DocumentContent.content.ilike(f"%{q}%")
            )
        )

    if title:
        query = query.filter(Document.title_document.ilike(f"%{title}%"))

    if has_words:
        for w in has_words.split():
            query = query.outerjoin(DocumentContent).filter(
                DocumentContent.content.ilike(f"%{w}%")
            )

    if folder_id is not None:
        query = query.filter(Document.directory_id == folder_id)

    if mimetype:
        query = query.filter(Document.mimetype == mimetype)

    return query.distinct().all()


@router.put("/{document_id}/archive", response_model=StatusUpdateResponse)
def archive_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Archive a document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    
    if document.status != StatusEnum.ACTIVE:
        raise HTTPException(400, f"Cannot archive document with status: {document.status.value}")
    
    document.status = StatusEnum.ARCHIVED
    document.archived_at = datetime.datetime.utcnow()
    db.add(document)
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Document '{document.name}' has been archived",
        affected_items=1
    )


@router.put("/{document_id}/restore", response_model=StatusUpdateResponse)
def restore_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Restore a document from archive or trash"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    
    if document.status == StatusEnum.ACTIVE:
        raise HTTPException(400, "Document is already active")
    
    # Check if parent directory exists and is active (if has parent)
    if document.directory_id:
        directory = db.query(Directory).filter(Directory.id == document.directory_id).first()
        if not directory or directory.status != StatusEnum.ACTIVE:
            raise HTTPException(400, "Cannot restore: parent directory is not active")
    
    document.status = StatusEnum.ACTIVE
    document.archived_at = None
    document.trashed_at = None
    db.add(document)
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Document '{document.name}' has been restored",
        affected_items=1
    )


@router.put("/{document_id}/trash", response_model=StatusUpdateResponse)
def move_document_to_trash(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Move a document to trash (soft delete)"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    
    if document.status == StatusEnum.TRASHED:
        raise HTTPException(400, "Document is already in trash")
    
    document.status = StatusEnum.TRASHED
    document.trashed_at = datetime.datetime.utcnow()
    db.add(document)
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Document '{document.name}' has been moved to trash",
        affected_items=1
    )


@router.delete("/{document_id}/permanent", response_model=StatusUpdateResponse)
def delete_document_permanent(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Permanently delete a document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    
    # Delete the document (CASCADE will handle children and documents)
    document_name = document.name
    db.delete(document)
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Document '{document_name}' has been permanently deleted",
        affected_items=1
    )
    
@router.post("/bulk-archive", response_model=StatusUpdateResponse)
def bulk_archive_documents(
    request: BulkActionRequest,
    db: Session = Depends(get_db)
):
    """Archive multiple documents"""
    if request.item_type != "document":
        raise HTTPException(400, "This endpoint only supports documents")
    
    affected_count = 0
    for doc_id in request.item_ids:
        document = db.query(Document).filter(Document.id == doc_id).first()
        if document and document.status == StatusEnum.ACTIVE:
            document.status = StatusEnum.ARCHIVED
            document.archived_at = datetime.datetime.utcnow()
            db.add(document)
            affected_count += 1
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Successfully archived {affected_count} documents",
        affected_items=affected_count
    )


@router.post("/bulk-trash", response_model=StatusUpdateResponse)
def bulk_trash_documents(
    request: BulkActionRequest,
    db: Session = Depends(get_db)
):
    """Move multiple documents to trash"""
    if request.item_type != "document":
        raise HTTPException(400, "This endpoint only supports documents")
    
    affected_count = 0
    for doc_id in request.item_ids:
        document = db.query(Document).filter(Document.id == doc_id).first()
        if document and document.status != StatusEnum.TRASHED:
            document.status = StatusEnum.TRASHED
            document.trashed_at = datetime.datetime.utcnow()
            db.add(document)
            affected_count += 1
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Successfully moved {affected_count} documents to trash",
        affected_items=affected_count
    )


@router.post("/bulk-restore", response_model=StatusUpdateResponse)
def bulk_restore_documents(
    request: BulkActionRequest,
    db: Session = Depends(get_db)
):
    """Restore multiple documents from archive or trash"""
    if request.item_type != "document":
        raise HTTPException(400, "This endpoint only supports documents")
    
    affected_count = 0
    for doc_id in request.item_ids:
        document = db.query(Document).filter(Document.id == doc_id).first()
        if document and document.status != StatusEnum.ACTIVE:
            # Check if parent directory is active (if has parent)
            if document.directory_id:
                directory = db.query(Directory).filter(Directory.id == document.directory_id).first()
                if not directory or directory.status != StatusEnum.ACTIVE:
                    continue  # Skip if parent directory is not active
            
            document.status = StatusEnum.ACTIVE
            document.archived_at = None
            document.trashed_at = None
            db.add(document)
            affected_count += 1
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Successfully restored {affected_count} documents",
        affected_items=affected_count
    )


@router.delete("/bulk-permanent", response_model=StatusUpdateResponse)
def bulk_delete_documents_permanent(
    request: BulkActionRequest,
    db: Session = Depends(get_db)
):
    """Permanently delete multiple documents"""
    if request.item_type != "document":
        raise HTTPException(400, "This endpoint only supports documents")
    
    affected_count = 0
    for doc_id in request.item_ids:
        document = db.query(Document).filter(Document.id == doc_id).first()
        if document:
            db.delete(document)  # This will also delete related DocumentContent via CASCADE
            affected_count += 1
    
    db.commit()
    
    return StatusUpdateResponse(
        success=True,
        message=f"Successfully deleted {affected_count} documents permanently",
        affected_items=affected_count
    )
    
@router.get("/{document_id}/preview")
async def preview_document(
    document_id: int,
    page: int = Query(1, ge=1, description="Page number for PDF"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    
    if not can_access_document(current_user, document, db):
        raise HTTPException(403, "Access denied")
    
    mimetype = document.mimetype.lower()
    
    # Handle PDF
    if mimetype == "application/pdf":
        try:
            import fitz  # PyMuPDF
            
            # IMPORTANT: Use BytesIO to keep data in memory
            pdf_stream = BytesIO(document.data)
            pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")
            
            # Validate page number
            total_pages = len(pdf_document)
            if page > total_pages:
                pdf_document.close()
                raise HTTPException(400, f"Page {page} exceeds document length {total_pages}")
            
            # Get the specified page (0-indexed)
            pdf_page = pdf_document[page - 1]
            
            # Render page to image with higher quality
            mat = fitz.Matrix(2, 2)  # 2x zoom for better quality
            pix = pdf_page.get_pixmap(matrix=mat)
            
            # Convert to PNG bytes
            img_data = pix.tobytes("png")
            
            # IMPORTANT: Close document AFTER getting image data
            pdf_document.close()
            pdf_stream.close()
            
            return Response(
                content=img_data,
                media_type="image/png",
                headers={
                    "X-Total-Pages": str(total_pages),
                    "X-Current-Page": str(page),
                    "Cache-Control": "max-age=3600"  # Cache for 1 hour
                }
            )
            
        except ImportError:
            raise HTTPException(500, "PyMuPDF (fitz) not installed. Run: pip install PyMuPDF")
        except Exception as e:
            raise HTTPException(500, f"Error processing PDF: {str(e)}")
    
    # Handle Images
    elif mimetype.startswith("image/"):
        return Response(
            content=document.data, 
            media_type=document.mimetype,
            headers={"Cache-Control": "max-age=3600"}
        )
    
    # Handle Word documents
    elif mimetype in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword"
    ]:
        try:
            from docx import Document as DocxDoc
            import tempfile
            import os
            
            # Save docx to temp file
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
                tmp_docx.write(document.data)
                tmp_docx_path = tmp_docx.name
            
            try:
                # Try to read and convert to simple HTML
                docx_doc = DocxDoc(tmp_docx_path)
                
                # Build HTML content
                html_parts = ['<!DOCTYPE html><html><head><meta charset="UTF-8">']
                html_parts.append('<style>body{font-family:Arial,sans-serif;padding:20px;max-width:800px;margin:0 auto;}</style>')
                html_parts.append('</head><body>')
                
                # Add paragraphs (limit to first 100)
                for i, para in enumerate(docx_doc.paragraphs[:100]):
                    if para.text.strip():
                        html_parts.append(f'<p>{para.text}</p>')
                    if i >= 99:
                        html_parts.append('<p><em>... (content truncated for preview)</em></p>')
                        break
                
                html_parts.append('</body></html>')
                html_content = ''.join(html_parts)
                
                return Response(
                    content=html_content, 
                    media_type="text/html",
                    headers={"Cache-Control": "max-age=3600"}
                )
                
            finally:
                # Cleanup temp file
                if os.path.exists(tmp_docx_path):
                    os.remove(tmp_docx_path)
                    
        except Exception as e:
            raise HTTPException(500, f"Error processing Word document: {str(e)}")
    
    else:
        raise HTTPException(400, f"Preview not supported for {mimetype}")

@router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Download the original document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    
    return Response(
        content=document.data,
        media_type=document.mimetype,
        headers={
            "Content-Disposition": f'attachment; filename="{document.name}"'
        }
    )


@router.get("/{document_id}/info")
async def get_document_info(
    document_id: int,
    db: Session = Depends(get_db)
):
    """Get document information including page count for PDFs"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    
    info = {
        "id": document.id,
        "name": document.name,
        "title": document.title_document,
        "mimetype": document.mimetype,
        "size": document.size,
        "total_pages": 1,
        "created_at": document.created_at
    }
    
    # Get page count for PDFs
    if document.mimetype == "application/pdf":
        try:
            import fitz
            pdf_document = fitz.open(stream=BytesIO(document.data), filetype="pdf")
            info["total_pages"] = len(pdf_document)
            pdf_document.close()
        except:
            pass
    
    return info

# Pastikan folder cache ada
SHARE_CACHE_DIR = "temp/share_tokens"
os.makedirs(SHARE_CACHE_DIR, exist_ok=True)

@router.post("/{document_id}/share")
def create_share_link(
    document_id: int,
    expires_in: int = Query(7),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a simple share link"""
    print(f"🔗 SHARE REQUEST - Document: {document_id}, User: {current_user.name} (ID: {current_user.id})")
    
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(404, "Document not found")
    
    print(f"📄 DOCUMENT INFO - Created by: {document.created_by}, Name: {document.name}")
    print(f"👤 USER INFO - Current user ID: {current_user.id}, Role: {current_user.role}")
    
    # Authorization check - relaxed for testing
    accessible_depts = get_accessible_departments(current_user, db)
    accessible_orgs = get_accessible_organizations(current_user, db)
    
    has_access = (
        document.organization_id in accessible_orgs and 
        document.department_id in accessible_depts
    )
    
    if not has_access:
        print(f"❌ ACCESS DENIED - User {current_user.id} cannot share document {document_id}")
        raise HTTPException(403, "You don't have access to this document")
    
    print(f"✅ ACCESS GRANTED - User can share document")
    
    # Generate share token
    share_token = secrets.token_urlsafe(32)
    
    # PERBAIKAN: Gunakan datetime.datetime.now(timezone.utc) untuk Python 3.13
    expires_at = datetime.datetime.now(timezone.utc) + timedelta(days=expires_in)
    created_at = datetime.datetime.now(timezone.utc)
    
    # Create file-based share cache
    share_data = {
        "document_id": document_id,
        "share_token": share_token,
        "expires_at": expires_at.isoformat(),
        "created_by": current_user.id,
        "created_at": created_at.isoformat(),
        "document_name": document.name,
        "document_title": document.title_document
    }
    
    # Ensure share cache directory exists
    os.makedirs(SHARE_CACHE_DIR, exist_ok=True)
    
    token_file = os.path.join(SHARE_CACHE_DIR, f"{share_token}.json")
    with open(token_file, "w") as f:
        json.dump(share_data, f)
    
    share_url = f"/shared/{share_token}"  #
    
    print(f"🔗 SHARE CREATED - Token: {share_token}, URL: {share_url}")
    
    return {
        "share_link": share_url,
        "share_token": share_token,
        "expires_at": expires_at.isoformat(),
        "expires_in_days": expires_in
    }

@router.get("/shared/{share_token}/preview")
def preview_shared_document(
    share_token: str,
    page: int = Query(1, ge=1, description="Page number for PDF"),
):
    """Preview shared document - public endpoint"""
    token_file = os.path.join(SHARE_CACHE_DIR, f"{share_token}.json")
    
    if not os.path.exists(token_file):
        raise HTTPException(404, "Share link not found or has been deleted")
    
    try:
        with open(token_file, "r") as f:
            share_data = json.load(f)
    except Exception as e:
        raise HTTPException(500, f"Error reading share data: {str(e)}")
    
    # PERBAIKAN: Gunakan datetime.now(timezone.utc)
    expires_at = datetime.datetime.fromisoformat(share_data["expires_at"])
    if datetime.datetime.now(timezone.utc) > expires_at:
        try:
            os.remove(token_file)
        except:
            pass
        raise HTTPException(403, "Share link has expired")
    
    # Get document
    db = SessionLocal()
    try:
        document_id = share_data["document_id"]
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(404, "Document not found")
        
        # Handle PDF preview
        mimetype = document.mimetype.lower()
        
        if mimetype == "application/pdf":
            try:
                import fitz
                
                pdf_stream = BytesIO(document.data)
                pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")
                
                total_pages = len(pdf_document)
                if page > total_pages:
                    pdf_document.close()
                    raise HTTPException(400, f"Page {page} exceeds document length {total_pages}")
                
                pdf_page = pdf_document[page - 1]
                mat = fitz.Matrix(2, 2)
                pix = pdf_page.get_pixmap(matrix=mat)
                
                img_data = pix.tobytes("png")
                
                pdf_document.close()
                pdf_stream.close()
                
                return Response(
                    content=img_data,
                    media_type="image/png",
                    headers={
                        "X-Total-Pages": str(total_pages),
                        "X-Current-Page": str(page),
                        "Cache-Control": "max-age=3600"
                    }
                )
                
            except ImportError:
                raise HTTPException(500, "PyMuPDF not installed")
            except Exception as e:
                raise HTTPException(500, f"Error processing PDF: {str(e)}")
        
        # Handle Images
        elif mimetype.startswith("image/"):
            return Response(
                content=document.data, 
                media_type=document.mimetype,
                headers={"Cache-Control": "max-age=3600"}
            )
        
        # Handle Word documents
        elif mimetype in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword"
        ]:
            try:
                from docx import Document as DocxDoc
                import tempfile
                
                with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
                    tmp_docx.write(document.data)
                    tmp_docx_path = tmp_docx.name
                
                try:
                    docx_doc = DocxDoc(tmp_docx_path)
                    
                    html_parts = ['<!DOCTYPE html><html><head><meta charset="UTF-8">']
                    html_parts.append('<style>body{font-family:Arial,sans-serif;padding:20px;max-width:800px;margin:0 auto;}</style>')
                    html_parts.append('</head><body>')
                    
                    for i, para in enumerate(docx_doc.paragraphs[:100]):
                        if para.text.strip():
                            html_parts.append(f'<p>{para.text}</p>')
                        if i >= 99:
                            html_parts.append('<p><em>... (content truncated)</em></p>')
                            break
                    
                    html_parts.append('</body></html>')
                    html_content = ''.join(html_parts)
                    
                    return Response(
                        content=html_content, 
                        media_type="text/html",
                        headers={"Cache-Control": "max-age=3600"}
                    )
                finally:
                    if os.path.exists(tmp_docx_path):
                        os.remove(tmp_docx_path)
                        
            except Exception as e:
                raise HTTPException(500, f"Error processing Word document: {str(e)}")
        
        else:
            raise HTTPException(400, f"Preview not supported for {mimetype}")
            
    finally:
        db.close()


@router.get("/shared/{share_token}/info")
def get_shared_document_info(share_token: str):
    """Get shared document info"""
    token_file = os.path.join(SHARE_CACHE_DIR, f"{share_token}.json")
    
    if not os.path.exists(token_file):
        raise HTTPException(404, "Share link not found")
    
    try:
        with open(token_file, "r") as f:
            share_data = json.load(f)
    except:
        raise HTTPException(500, "Error reading share data")
    
    # Check expiration
    expires_at = datetime.datetime.fromisoformat(share_data["expires_at"])
    # if datetime.datetime.datetime.utcnow() > expires_at:
    #     try:
    #         os.remove(token_file)
    #     except:
    #         pass
    #     raise HTTPException(403, "Share link has expired")
    
    # Get document
    db = SessionLocal()
    try:
        document_id = share_data["document_id"]
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(404, "Document not found")
        
        info = {
            "id": document.id,
            "name": document.name,
            "title": document.title_document,
            "mimetype": document.mimetype,
            "size": document.size,
            "total_pages": 1,
            "created_at": document.created_at,
            "shared_by": share_data.get("created_by", "Unknown"),
            "shared_at": share_data.get("created_at"),
            "expires_at": share_data.get("expires_at")
        }
        
        # Get page count for PDFs
        if document.mimetype == "application/pdf":
            try:
                import fitz
                pdf_document = fitz.open(stream=BytesIO(document.data), filetype="pdf")
                info["total_pages"] = len(pdf_document)
                pdf_document.close()
            except:
                pass
        
        return info
    finally:
        db.close()


@router.get("/shared/{share_token}/download")
def download_shared_document(share_token: str):
    """Download shared document"""
    token_file = os.path.join(SHARE_CACHE_DIR, f"{share_token}.json")
    
    if not os.path.exists(token_file):
        raise HTTPException(404, "Share link not found")
    
    try:
        with open(token_file, "r") as f:
            share_data = json.load(f)
    except:
        raise HTTPException(500, "Error reading share data")
    
    # Check expiration
    expires_at = datetime.fromisoformat(share_data["expires_at"])
    if datetime.datetime.utcnow() > expires_at:
        try:
            os.remove(token_file)
        except:
            pass
        raise HTTPException(403, "Share link has expired")
    
    # Get document
    db = SessionLocal()
    try:
        document_id = share_data["document_id"]
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(404, "Document not found")
        
        return Response(
            content=document.data,
            media_type=document.mimetype,
            headers={
                "Content-Disposition": f'attachment; filename="{document.name}"'
            }
        )
    finally:
        db.close()


@router.delete("/{share_token}/revoke")
def revoke_share_link(share_token: str):
    """Revoke a share link"""
    token_file = os.path.join(SHARE_CACHE_DIR, f"{share_token}.json")
    
    if not os.path.exists(token_file):
        raise HTTPException(404, "Share link not found")
    
    try:
        os.remove(token_file)
        return {
            "success": True,
            "message": "Share link revoked successfully"
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to revoke share link: {str(e)}")
    
@router.get("/shared/with-me", response_model=List[DocumentOut])
def get_shared_with_me(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    shared_docs = db.query(Document).join(DocumentShare).filter(
        DocumentShare.expires_at > datetime.datetime.utcnow(),
        (
            (DocumentShare.target_user_id == current_user.id) |
            (DocumentShare.target_department_id == current_user.department_id) |
            (DocumentShare.target_organization_id == current_user.organization_id)
        )
    ).offset(skip).limit(limit).all()
    
    return shared_docs