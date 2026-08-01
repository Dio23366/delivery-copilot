from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Project(Base):
    __tablename__ = 'projects'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('customers.id'), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    health: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    customer = relationship('Customer', back_populates='projects')
    requirements = relationship('Requirement', back_populates='project')
    issues = relationship('Issue', back_populates='project')
