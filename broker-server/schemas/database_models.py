import uuid

from sqlalchemy import JSON, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier = Column(String, nullable=False, unique=True)
    metadata_ = Column("metadata", JSONB, nullable=False)
    createdAt = Column(String)


class Thread(Base):
    __tablename__ = "threads"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    createdAt = Column(String)
    name = Column(String)
    userId = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    userIdentifier = Column(String)
    tags = Column(ARRAY(String))
    metadata_ = Column("metadata", JSONB)

    user = relationship("User", backref="threads")


class LangGraphState(Base):
    __tablename__ = "langgraphs"

    thread_id = Column(String, primary_key=True)
    state = Column(JSON, nullable=False)
    workflow = Column(String, nullable=False)
