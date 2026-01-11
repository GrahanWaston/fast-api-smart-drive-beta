import enum
from sqlalchemy import (
    Column, Enum, Float, Integer, LargeBinary, String, Boolean, ForeignKey,
    DateTime, Text
)
from sqlalchemy.orm import relationship
from datetime import datetime
from connection.base import Base

class StatusEnum(enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    TRASHED = "trashed"

class Directory(Base):
    __tablename__ = "directories"
    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String, nullable=False)
    mimetype     = Column(String, nullable=True)
    is_directory = Column(Boolean, default=True)
    parent_id    = Column(Integer, ForeignKey("directories.id", ondelete="CASCADE"), nullable=True)
    level        = Column(Integer, default=0)
    path         = Column(String, default="/")
    status       = Column(Enum(StatusEnum), default=StatusEnum.ACTIVE, index=True) 
    archived_at  = Column(DateTime, nullable=True) 
    trashed_at   = Column(DateTime, nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    
    children     = relationship("Directory", backref="parent", remote_side=[id])
    documents    = relationship("Document", backref="directory")
    organization = relationship("Organization", backref="directories")
    department   = relationship("Department", backref="directories")
    
class DocumentCategory(Base):
    __tablename__ = "document_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    organization = relationship("Organization", backref="document_categories")
    creator = relationship("User", foreign_keys=[created_by], backref="created_categories")



class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    title_document = Column(String, nullable=True, index=True)
    
    file_type = Column(String(50), default="Document", index=True)  
    document_category_id = Column(Integer, ForeignKey("document_categories.id", ondelete="SET NULL"), nullable=True)
    file_category = Column(String(50), nullable=True, index=True)  
    file_owner = Column(String(255), nullable=True)  
    expire_date = Column(DateTime, nullable=True, index=True)  
    
    # Existing attributes
    mimetype = Column(String, nullable=False, index=True)
    size = Column(Integer, nullable=False)
    data = Column(LargeBinary, nullable=False)
    total_pages = Column(Integer, default=0)
    directory_id = Column(Integer, ForeignKey("directories.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum(StatusEnum), default=StatusEnum.ACTIVE, index=True)
    archived_at = Column(DateTime, nullable=True)
    trashed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    contents = relationship("DocumentContent", backref="document", cascade="all, delete")
    metadatas = relationship("DocumentMetadata", backref="document", uselist=False, cascade="all, delete")
    organization = relationship("Organization", backref="documents")
    department = relationship("Department", backref="documents")
    creator = relationship("User", foreign_keys=[created_by], backref="documents")
    document_category = relationship("DocumentCategory", backref="documents")  

class DocumentContent(Base):
    __tablename__ = "document_contents"
    id          = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"))
    content     = Column(Text, nullable=True)
    ocr_result  = Column(Text, nullable=True)

class DocumentMetadata(Base):
    __tablename__ = "document_metadatas"
    id          = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"))
    status      = Column(String, default="draft")
    exp_date    = Column(DateTime, nullable=True)
    author      = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    tags        = Column(String, nullable=True)
    
class Organization(Base):
    __tablename__ = "organizations"
    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String, nullable=False)
    code     = Column(String, unique=True, nullable=False) 
    status   = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    license_info = relationship("OrganizationLicense", backref="org", uselist=False, cascade="all, delete")
    
class Department(Base):
    __tablename__ = "departments"
    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String, nullable=False)
    org_id   = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"))
    parent_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)  
    code     = Column(String, nullable=False) 
    org      = relationship("Organization", backref="departments")
    parent   = relationship("Department", remote_side=[id], backref="sub_departments")  

class User(Base):
    __tablename__ = "users"
    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String, nullable=False)
    email           = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    department_id   = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    role            = Column(String, default="user") 
    
    department = relationship("Department", backref="users")
    organization = relationship("Organization", backref="users")
    
class ActivityLog(Base):
    __tablename__ = "activity_logs"
    
    id              = Column(Integer, primary_key=True, index=True)
    timestamp       = Column(DateTime, default=datetime.utcnow, index=True)
    method          = Column(String, index=True)  
    path            = Column(String, index=True)  
    status_code     = Column(Integer)
    duration_ms     = Column(Float)
    client_ip       = Column(String, nullable=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    query_params    = Column(Text, nullable=True) 
    response_status = Column(String)  
    
    user = relationship("User", backref="activity_logs")
    
class DocumentShare(Base):
    __tablename__ = "document_shares"
    id = Column(Integer, primary_key=True, index=True)
    document_id             = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    shared_by               = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_organization_id  = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    target_department_id    = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True)
    target_user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    permission              = Column(String, default="view")  # view, download, edit
    expires_at              = Column(DateTime, nullable=True)
    created_at              = Column(DateTime, default=datetime.utcnow)
    
    document            = relationship("Document", backref="shares")
    sharer              = relationship("User", foreign_keys=[shared_by], backref="shared_documents")
    target_organization = relationship("Organization", foreign_keys=[target_organization_id])
    target_department   = relationship("Department", foreign_keys=[target_department_id])
    target_user         = relationship("User", foreign_keys=[target_user_id])
    
    
class SubscriptionStatus(enum.Enum):
    ACTIVE      = "active"
    EXPIRED     = "expired"
    SUSPENDED   = "suspended"
    TRIAL       = "trial"
    
class OrganizationLicense(Base):
    __tablename__ = "organization_licenses"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    subscription_status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.TRIAL, index=True)
    start_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_date = Column(DateTime, nullable=False, index=True)
    trial_days = Column(Integer, default=30)
    max_users = Column(Integer, default=10)
    max_storage_gb = Column(Integer, default=5)
    last_checked = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    organization = relationship("Organization", backref="license", uselist=False)