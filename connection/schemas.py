from enum import Enum
from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List
from datetime import datetime

class StatusEnum(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    TRASHED = "trashed"

# ============ Simple Base Schemas (No Relations) ============

class OrganizationSimple(BaseModel):
    """Organization without relations"""
    id: int
    name: str
    code: str
    status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class DepartmentSimple(BaseModel):
    """Department without relations"""
    id: int
    name: str
    code: str
    org_id: int
    
    model_config = ConfigDict(from_attributes=True)

class UserSimple(BaseModel):
    """User without relations"""
    id: int
    name: str
    email: EmailStr
    department_id: Optional[int] = None
    organization_id: Optional[int] = None
    role: str
    
    model_config = ConfigDict(from_attributes=True)

# ============ Create Schemas ============

class DirectoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    is_directory: bool = True
    department_id: Optional[int] = None
    organization_id: Optional[int] = None

class DocumentCreate(BaseModel):
    title_document: Optional[str] = None
    directory_id: Optional[int] = None

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    department_id: Optional[int] = None
    organization_id: Optional[int] = None
    role: Optional[str] = "user"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class OrganizationCreate(BaseModel):
    name: str
    code: str
    

class DepartmentCreate(BaseModel):
    name: str
    code: str
    org_id: int
    parent_id: Optional[int] = None

# ============ Output Schemas (WITH Simple Relations) ============

class DirectoryOut(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    is_directory: bool = True
    level: int
    path: str
    status: StatusEnum = StatusEnum.ACTIVE
    archived_at: Optional[datetime] = None
    trashed_at: Optional[datetime] = None
    department_id: int
    organization_id: int
    
    # Use simple versions to avoid recursion
    department: Optional[DepartmentSimple] = None
    organization: Optional[OrganizationSimple] = None
    
    model_config = ConfigDict(from_attributes=True)

class DocumentOut(BaseModel):
    id: int
    name: str
    title_document: Optional[str]
    mimetype: str
    size: int
    total_pages: int
    created_at: datetime
    directory_id: Optional[int]
    status: StatusEnum = StatusEnum.ACTIVE
    archived_at: Optional[datetime] = None
    trashed_at: Optional[datetime] = None
    department_id: int
    organization_id: int
    created_by: Optional[int] = None
    
    # Use simple versions to avoid recursion
    department: Optional[DepartmentSimple] = None
    organization: Optional[OrganizationSimple] = None
    creator: Optional[UserSimple] = None
    
    model_config = ConfigDict(from_attributes=True)

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    department_id: Optional[int]
    organization_id: Optional[int]
    role: str
    
    # Use simple versions to avoid recursion
    department: Optional[DepartmentSimple] = None
    organization: Optional[OrganizationSimple] = None
    
    model_config = ConfigDict(from_attributes=True)

class OrganizationOut(BaseModel):
    id: int
    name: str
    code: str
    status: str
    created_at: datetime
    
    # NO nested lists to avoid recursion
    model_config = ConfigDict(from_attributes=True)

class DepartmentOut(BaseModel):
    id: int
    name: str
    code: str
    org_id: int
    
    # Only include org (simple), no users/subdepts lists
    org: Optional[OrganizationSimple] = None
    parent: Optional[DepartmentSimple] = None
    
    model_config = ConfigDict(from_attributes=True)

# ============ Other Schemas ============

class ContentOut(BaseModel):
    id: int
    content: Optional[str]
    ocr_result: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)

class MetadataOut(BaseModel):
    id: int
    status: Optional[str]
    author: Optional[str]
    description: Optional[str]
    tags: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class BulkActionRequest(BaseModel):
    item_ids: List[int]
    item_type: str

class StatusUpdateResponse(BaseModel):
    success: bool
    message: str
    affected_items: int

class ActivityLogOut(BaseModel):
    id: int
    timestamp: datetime
    method: str
    path: str
    status_code: int
    duration_ms: float
    client_ip: Optional[str] = None
    user_id: Optional[int] = None
    response_status: str
    
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    department_id: Optional[int] = None
    organization_id: Optional[int] = None
    role: Optional[str] = None
    
    class Config:
        from_attributes = True

class DocumentShareCreate(BaseModel):
    target_user_id: Optional[int] = None
    target_department_id: Optional[int] = None
    target_organization_id: Optional[int] = None
    expires_in: Optional[int] = 7  # days

    class Config:
        from_attributes = True

class DocumentShareOut(BaseModel):
    id: int
    document_id: int
    shared_by: int
    target_user_id: Optional[int] = None
    target_department_id: Optional[int] = None
    target_organization_id: Optional[int] = None
    share_token: str
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
    
class MetadataBase(BaseModel):
    status: Optional[str]
    author: Optional[str]
    description: Optional[str]
    tags: Optional[str]


class MetadataCreate(MetadataBase):
    document_id: int


class MetadataOut(MetadataBase):
    id: int

    class Config:
        orm_mode = True
        
class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    status: Optional[str] = None
    
    class Config:
        from_attributes = True

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    org_id: Optional[int] = None
    parent_id: Optional[int] = None
    
    class Config:
        from_attributes = True