from datetime import datetime
from sqlalchemy import Integer, Text, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class Clarification(Base):
    __tablename__ = "clarifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("tickets.id"), nullable=False)
    requested_fields: Mapped[str] = mapped_column(Text, nullable=False)
    teacher_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    student_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
