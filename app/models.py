from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, backref
from app.database import Base, IS_POSTGRES

if IS_POSTGRES:
    from sqlalchemy.dialects.postgresql import JSONB as _JsonColumn
else:
    _JsonColumn = JSON


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    auth_provider = Column(String, default="local", nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    max_upload_docs = Column(Integer, default=0, nullable=False)
    default_visibility = Column(String, default="private", nullable=False)
    about_approved_at = Column(DateTime(timezone=True), nullable=True)
    about_approved_version = Column(Integer, nullable=True)

    materials = relationship("Material", back_populates="owner", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, is_admin={self.is_admin})>"


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    icon = Column(String, nullable=True, default="fa-briefcase")
    color = Column(String, nullable=True, default="#2c5364")
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(_JsonColumn, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<Case(id={self.id}, name={self.name})>"


class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=True)
    gdrive_id = Column(String, nullable=True)
    source_type = Column(String, nullable=False, default="upload")  # "local" | "gdrive" | "upload"
    parent_folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    is_watched = Column(Boolean, default=False)
    last_scanned_at = Column(DateTime(timezone=True), nullable=True)
    scan_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", backref=backref("folders", cascade="all, delete-orphan"))
    parent = relationship("Folder", remote_side=[id], backref="children")

    def __repr__(self):
        return f"<Folder(id={self.id}, name={self.name}, case_id={self.case_id})>"


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True)

    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    original_path = Column(String, nullable=True)
    file_type = Column(String, nullable=False, index=True, default="other")  # pdf, image, audio, video, table, other
    mime_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_hash = Column(String, nullable=True, index=True)

    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    content_text = Column(Text, default="")
    content_summary = Column(Text, nullable=True)
    metadata_json = Column(_JsonColumn, default=dict)
    is_public = Column(Boolean, default=True, nullable=False)

    extraction_status = Column(String, default="pending")  # pending | processing | done | failed
    extraction_error = Column(Text, nullable=True)

    duration_seconds = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)
    dimensions = Column(String, nullable=True)
    thumbnail_path = Column(String, nullable=True)

    owner = relationship("User", back_populates="materials")
    case = relationship("Case", backref="materials")
    folder = relationship("Folder", backref="materials")

    @property
    def case_name(self) -> str | None:
        return self.case.name if self.case else None

    def __repr__(self):
        return f"<Material(id={self.id}, filename={self.filename}, type={self.file_type})>"


class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False, index=True)  # event, person, corporation, topic
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    metadata_json = Column(_JsonColumn, default=dict)

    # Event-specific
    event_date = Column(DateTime(timezone=True), nullable=True)
    event_end_date = Column(DateTime(timezone=True), nullable=True)
    event_location = Column(String, nullable=True)

    # Person-specific
    person_role = Column(String, nullable=True)
    person_id_number = Column(String, nullable=True)

    # Corporation-specific
    corp_type = Column(String, nullable=True)
    corp_registration = Column(String, nullable=True)

    # Topic-specific
    topic_color = Column(String, nullable=True)
    topic_icon = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    case = relationship("Case", backref=backref("entities", cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<Entity(id={self.id}, type={self.entity_type}, name={self.name})>"


class EntityEntityLink(Base):
    __tablename__ = "entity_entity_links"
    __table_args__ = (
        Index("ix_ee_link_pair", "entity_a_id", "entity_b_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_a_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_b_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type = Column(String, nullable=True)
    relationship_detail = Column(Text, nullable=True)
    metadata_json = Column(_JsonColumn, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entity_a = relationship("Entity", foreign_keys=[entity_a_id], backref="links_as_a")
    entity_b = relationship("Entity", foreign_keys=[entity_b_id], backref="links_as_b")


class EntityMaterialLink(Base):
    __tablename__ = "entity_material_links"
    __table_args__ = (
        Index("ix_em_link_pair", "entity_id", "material_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    relevance = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    page_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entity = relationship("Entity", backref=backref("material_links", cascade="all, delete-orphan"))
    material = relationship("Material", backref=backref("entity_links", cascade="all, delete-orphan"))


class EntityFolderLink(Base):
    __tablename__ = "entity_folder_links"
    __table_args__ = (
        Index("ix_ef_link_pair", "entity_id", "folder_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entity = relationship("Entity", backref=backref("folder_links", cascade="all, delete-orphan"))
    folder = relationship("Folder", backref=backref("entity_links", cascade="all, delete-orphan"))


class MaterialGroup(Base):
    __tablename__ = "material_groups"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    analysis_result = Column(Text, nullable=True)
    analysis_metadata = Column(_JsonColumn, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    case = relationship("Case", backref=backref("material_groups", cascade="all, delete-orphan"))


class MaterialGroupMember(Base):
    __tablename__ = "material_group_members"
    __table_args__ = (
        Index("ix_mgm_pair", "group_id", "material_id", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("material_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("MaterialGroup", backref=backref("members", cascade="all, delete-orphan"))
    material = relationship("Material", backref=backref("group_memberships", cascade="all, delete-orphan"))


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="SET NULL"), nullable=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    event_date = Column(DateTime(timezone=True), nullable=False, index=True)
    event_end_date = Column(DateTime(timezone=True), nullable=True)
    location = Column(String, nullable=True)
    source = Column(String, default="manual")  # ai | manual | entity
    confidence = Column(Integer, nullable=True)
    tags = Column(JSON, default=list)
    metadata_json = Column(_JsonColumn, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    case = relationship("Case", backref=backref("timeline_events", cascade="all, delete-orphan"))
    material = relationship("Material", backref="timeline_events")


class PromptRule(Base):
    __tablename__ = "prompt_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    trigger_tag = Column(String, nullable=True)
    trigger_value = Column(String, nullable=True)
    prompt_text = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    json_schema = Column(Text, nullable=True)
    max_tokens = Column(Integer, default=2000, nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    case = relationship("Case", foreign_keys=[case_id])

    @property
    def case_name(self) -> str | None:
        return self.case.name if self.case else None

    def __repr__(self):
        return f"<PromptRule(id={self.id}, name={self.name})>"


class DetectedField(Base):
    __tablename__ = "detected_fields"

    id = Column(Integer, primary_key=True, index=True)
    field_key = Column(String, unique=True, nullable=False, index=True)
    friendly_name = Column(String, nullable=True)
    field_type = Column(String, nullable=True)
    is_array = Column(Boolean, default=False, nullable=False)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<DetectedField(id={self.id}, field_key={self.field_key})>"


class ProcessingQueue(Base):
    __tablename__ = "processing_queue"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)
    priority = Column(Integer, nullable=False, default=0, index=True)
    error_detail = Column(Text, nullable=True)
    queued_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    material = relationship("Material", backref=backref("queue_entries", cascade="all, delete-orphan"))
    user = relationship("User", backref=backref("queue_entries", passive_deletes=True))

    def __repr__(self):
        return f"<ProcessingQueue(id={self.id}, material={self.material_id}, status={self.status})>"


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    event_type = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="SET NULL"), nullable=True, index=True)
    detail = Column(Text, nullable=True)
    level = Column(String, default="info", nullable=False)
    user_agent = Column(String(200), nullable=True)

    user = relationship("User", backref=backref("activity_logs", passive_deletes=True))
    material = relationship("Material", backref=backref("activity_logs", passive_deletes=True))

    def __repr__(self):
        return f"<ActivityLog(id={self.id}, event={self.event_type})>"


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    page = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    action_log = Column(JSON, nullable=True)
    status = Column(String, default="new", nullable=False)
    admin_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", backref=backref("feedbacks", passive_deletes=True))


class SiteSetting(Base):
    __tablename__ = "site_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<SiteSetting(id={self.id}, key={self.key})>"
