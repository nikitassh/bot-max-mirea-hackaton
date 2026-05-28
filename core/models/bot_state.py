from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class BotState(Base):
    __tablename__ = "bot_state"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
