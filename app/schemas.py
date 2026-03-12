from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any, List, Union
from datetime import datetime


# ---- User Schemas ----

class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    email: str
    id: int
    is_admin: bool
    auth_provider: str = "local"
    created_at: datetime
    max_upload_docs: int = 0
    default_visibility: str = "private"
    about_approved_at: Optional[datetime] = None
    about_approved_version: Optional[int] = None
    needs_about_approval: bool = False
    material_count: int = 0

    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    new_password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class GoogleAuthRequest(BaseModel):
    id_token: str
    nonce: Optional[str] = None


# ---- Case Schemas ----

class CaseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = "fa-briefcase"
    color: Optional[str] = "#2c5364"


class CaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


class CaseResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = "fa-briefcase"
    color: Optional[str] = "#2c5364"
    is_active: bool = True
    material_count: int = 0
    entity_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Material Schemas ----

class MaterialResponse(BaseModel):
    id: int
    owner_id: int
    case_id: Optional[int] = None
    case_name: Optional[str] = None
    folder_id: Optional[int] = None
    filename: str
    file_path: str
    file_type: str = "other"
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    upload_date: datetime
    content_text: str = ""
    content_summary: Optional[str] = None
    metadata_json: Dict[str, Any] = {}
    is_public: bool = True
    extraction_status: str = "pending"
    page_count: Optional[int] = None
    duration_seconds: Optional[int] = None
    dimensions: Optional[str] = None
    thumbnail_path: Optional[str] = None

    class Config:
        from_attributes = True


class MaterialUpdate(BaseModel):
    content_text: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None


class MetadataNestedUpdate(BaseModel):
    path: str
    value: Any = None
    action: str = "set"


# ---- Folder Schemas ----

class FolderCreate(BaseModel):
    case_id: int
    name: str
    path: Optional[str] = None
    gdrive_id: Optional[str] = None
    source_type: str = "upload"
    parent_folder_id: Optional[int] = None


class FolderResponse(BaseModel):
    id: int
    case_id: int
    name: str
    path: Optional[str] = None
    source_type: str = "upload"
    parent_folder_id: Optional[int] = None
    is_watched: bool = False
    material_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Entity Schemas ----

class EntityCreate(BaseModel):
    entity_type: str  # event, person, corporation, topic
    case_id: int
    name: str
    description: Optional[str] = None
    metadata_json: Dict[str, Any] = {}
    # Event-specific
    event_date: Optional[datetime] = None
    event_end_date: Optional[datetime] = None
    event_location: Optional[str] = None
    # Person-specific
    person_role: Optional[str] = None
    person_id_number: Optional[str] = None
    # Corporation-specific
    corp_type: Optional[str] = None
    corp_registration: Optional[str] = None
    # Topic-specific
    topic_color: Optional[str] = None
    topic_icon: Optional[str] = None


class EntityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    event_date: Optional[datetime] = None
    event_end_date: Optional[datetime] = None
    event_location: Optional[str] = None
    person_role: Optional[str] = None
    person_id_number: Optional[str] = None
    corp_type: Optional[str] = None
    corp_registration: Optional[str] = None
    topic_color: Optional[str] = None
    topic_icon: Optional[str] = None


class EntityResponse(BaseModel):
    id: int
    entity_type: str
    case_id: int
    name: str
    description: Optional[str] = None
    metadata_json: Dict[str, Any] = {}
    event_date: Optional[datetime] = None
    event_end_date: Optional[datetime] = None
    event_location: Optional[str] = None
    person_role: Optional[str] = None
    person_id_number: Optional[str] = None
    corp_type: Optional[str] = None
    corp_registration: Optional[str] = None
    topic_color: Optional[str] = None
    topic_icon: Optional[str] = None
    created_at: datetime
    material_link_count: int = 0
    entity_link_count: int = 0

    class Config:
        from_attributes = True


# ---- Link Schemas ----

class EntityEntityLinkCreate(BaseModel):
    entity_a_id: int
    entity_b_id: int
    relationship_type: Optional[str] = None
    relationship_detail: Optional[str] = None


class EntityMaterialLinkCreate(BaseModel):
    entity_id: int
    material_id: int
    relevance: Optional[str] = None
    detail: Optional[str] = None
    page_ref: Optional[str] = None


class EntityFolderLinkCreate(BaseModel):
    entity_id: int
    folder_id: int
    detail: Optional[str] = None


# ---- Group Schemas ----

class GroupCreate(BaseModel):
    case_id: int
    name: str
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class GroupResponse(BaseModel):
    id: int
    case_id: int
    name: str
    description: Optional[str] = None
    analysis_result: Optional[str] = None
    member_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class GroupAddMembers(BaseModel):
    material_ids: List[int]


# ---- Timeline Schemas ----

class TimelineEventCreate(BaseModel):
    case_id: int
    title: str
    description: Optional[str] = None
    event_date: datetime
    event_end_date: Optional[datetime] = None
    location: Optional[str] = None
    material_id: Optional[int] = None
    entity_id: Optional[int] = None
    tags: List[str] = []


class TimelineEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_date: Optional[datetime] = None
    event_end_date: Optional[datetime] = None
    location: Optional[str] = None
    tags: Optional[List[str]] = None


class TimelineEventResponse(BaseModel):
    id: int
    case_id: int
    material_id: Optional[int] = None
    entity_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    event_date: datetime
    event_end_date: Optional[datetime] = None
    location: Optional[str] = None
    source: str = "manual"
    confidence: Optional[int] = None
    tags: List[str] = []
    created_at: datetime

    class Config:
        from_attributes = True


class TimelineGenerateRequest(BaseModel):
    case_id: int
    material_ids: Optional[List[int]] = None
    entity_ids: Optional[List[int]] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    provider: str = "gemini"


# ---- PromptRule Schemas ----

class PromptRuleCreate(BaseModel):
    name: str
    trigger_tag: Optional[str] = None
    trigger_value: Optional[str] = None
    prompt_text: str
    is_active: bool = True
    json_schema: Optional[str] = None
    max_tokens: int = 2000
    case_id: Optional[int] = None


class PromptRuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger_tag: Optional[str] = None
    trigger_value: Optional[str] = None
    prompt_text: Optional[str] = None
    is_active: Optional[bool] = None
    json_schema: Optional[str] = None
    max_tokens: Optional[int] = None
    case_id: Optional[int] = None


class PromptRuleResponse(BaseModel):
    id: int
    name: str
    trigger_tag: Optional[str] = None
    trigger_value: Optional[str] = None
    prompt_text: str
    is_active: bool = True
    json_schema: Optional[str] = None
    max_tokens: int = 2000
    case_id: Optional[int] = None
    case_name: Optional[str] = None

    class Config:
        from_attributes = True


# ---- Queue Schemas ----

class QueueAddRequest(BaseModel):
    material_ids: List[int]
    provider: str = "deepseek"
    priority: int = 0


class QueueStatusItem(BaseModel):
    queue_id: int
    material_id: int
    filename: Optional[str] = None
    status: str
    provider: str
    position: Optional[int] = None
    error_detail: Optional[str] = None
    queued_at: Optional[str] = None


class QueueStatusResponse(BaseModel):
    items: List[QueueStatusItem]
    running_count: int
    pending_count: int


# ---- Search Schemas ----

class SearchFilter(BaseModel):
    field: str
    operator: str
    value: Optional[Union[str, int, float, bool, Dict[str, Any], List[str]]] = None


class ParametricSearchRequest(BaseModel):
    filters: List[SearchFilter] = []
    logic: str = "AND"
    text_query: Optional[str] = None
    sort: str = "newest"
    page: int = 1
    size: int = 50
    case_id: Optional[int] = None


# ---- Activity Schemas ----

class ActivityLogResponse(BaseModel):
    id: int
    timestamp: datetime
    event_type: str
    user_id: Optional[int] = None
    material_id: Optional[int] = None
    detail: Optional[str] = None
    level: str = "info"
    user_email: Optional[str] = None
    material_filename: Optional[str] = None

    class Config:
        from_attributes = True


# ---- Feedback Schemas ----

class FeedbackCreate(BaseModel):
    page: str
    message: str
    action_log: Optional[List[Dict[str, Any]]] = None


# ---- Site Setting Schemas ----

class SiteSettingUpdate(BaseModel):
    value: str
