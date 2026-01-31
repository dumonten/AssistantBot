# src/infrastructure/db/models.py
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import JSON, Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier = Column(String, nullable=False, unique=True)
    metadata_ = Column("metadata", JSONB, nullable=False)
    createdAt = Column(
        String
    )  # лучше было бы использовать DateTime, но оставляем как в схеме

    # Связи
    threads = relationship(
        "Thread", back_populates="user", cascade="all, delete-orphan"
    )


class Thread(Base):
    __tablename__ = "threads"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    createdAt = Column(String)
    name = Column(String)
    userId = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    userIdentifier = Column(String)
    tags = Column(ARRAY(String), default=list)
    metadata_ = Column("metadata", JSONB)

    # Связи
    user = relationship("User", back_populates="threads")
    steps = relationship("Step", back_populates="thread", cascade="all, delete-orphan")
    elements = relationship(
        "Element", back_populates="thread", cascade="all, delete-orphan"
    )
    feedbacks = relationship(
        "Feedback", back_populates="thread", cascade="all, delete-orphan"
    )


class Step(Base):
    __tablename__ = "steps"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    threadId = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    parentId = Column(
        PG_UUID(as_uuid=True), index=True
    )  # может ссылаться на другой step в том же thread
    streaming = Column(Boolean, nullable=False, default=False)
    waitForAnswer = Column(Boolean)
    isError = Column(Boolean)
    metadata_ = Column("metadata", JSONB)
    tags = Column(ARRAY(String), default=list)
    input = Column(Text)
    output = Column(Text)
    createdAt = Column(String)
    command = Column(Text)
    start = Column(String)  # обычно ISO datetime string
    end = Column(String)
    generation = Column(JSONB)
    showInput = Column(String)
    language = Column(String)
    indent = Column(Integer)
    defaultOpen = Column(Boolean)

    # Связи
    thread = relationship("Thread", back_populates="steps")


class Element(Base):
    __tablename__ = "elements"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    threadId = Column(
        PG_UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE")
    )
    type = Column(String)
    url = Column(String)
    chainlitKey = Column(String)
    name = Column(String, nullable=False)
    display = Column(String)
    objectKey = Column(String)
    size = Column(String)
    page = Column(Integer)
    language = Column(String)
    forId = Column(PG_UUID(as_uuid=True))  # обычно → steps.id
    mime = Column(String)
    props = Column(JSONB)

    # Связи
    thread = relationship("Thread", back_populates="elements")


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    forId = Column(PG_UUID(as_uuid=True), nullable=False)  # чаще всего → steps.id
    threadId = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    value = Column(Integer, nullable=False)
    comment = Column(Text)

    # Связи
    thread = relationship("Thread", back_populates="feedbacks")


# Дополнительная таблица, которая была в твоём коде
class LangGraphState(Base):
    __tablename__ = "langgraphs"

    thread_id = Column(String, primary_key=True)
    state = Column(JSON, nullable=False)
    workflow = Column(String, nullable=False)
