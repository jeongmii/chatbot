from __future__ import annotations
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func
from typing import Optional
import uuid

Base = declarative_base()


def uuid_str() -> str:
    return str(uuid.uuid4())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    participant_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    study_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    source: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    model: Mapped[Optional[str]] = mapped_column(String(64))

    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    meta_json: Mapped[Optional[str]] = mapped_column(Text)

    messages: Mapped[list[Message]] = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), index=True)  # system | user | assistant | tool
    content: Mapped[str] = mapped_column(Text)

    sequence: Mapped[int] = mapped_column(Integer, index=True)  # monotonically increasing per session

    model: Mapped[Optional[str]] = mapped_column(String(64))
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")
