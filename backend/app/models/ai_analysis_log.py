from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AIAnalysisLog(Base):
    __tablename__ = 'ai_analysis_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    issue_id: Mapped[int] = mapped_column(Integer, ForeignKey('issues.id'), nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(String(100), nullable=False, default='issue_summarizer')
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default='rule_based_fallback')
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue_summary: Mapped[str] = mapped_column(Text, nullable=False)
    possible_root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_actions_json: Mapped[str] = mapped_column(Text, nullable=False)
    customer_update_draft: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)
    project_impact: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_status: Mapped[str] = mapped_column(String(50), nullable=False, default='pending')
    feedback_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_status: Mapped[str] = mapped_column(String(50), nullable=False, default='not_attempted')
    retrieval_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_citations_json: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    retrieval_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    issue = relationship('Issue', back_populates='analyses')
