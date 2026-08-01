from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AgentRun(Base):
    __tablename__ = 'agent_runs'
    __table_args__ = (
        CheckConstraint(
            "run_status IN ("
            "'created', "
            "'running', "
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'generating_analysis', "
            "'waiting_for_final_review', "
            "'completed', "
            "'failed', "
            "'cancelled', "
            "'limit_exceeded'"
            ")",
            name='ck_agent_runs_status_allowed',
        ),
        CheckConstraint(
            'step_count >= 0',
            name='ck_agent_runs_step_count_nonnegative',
        ),
        CheckConstraint(
            'tool_call_count >= 0',
            name='ck_agent_runs_tool_call_count_nonnegative',
        ),
        CheckConstraint(
            'retry_count >= 0',
            name='ck_agent_runs_retry_count_nonnegative',
        ),
        CheckConstraint(
            'completed_at IS NULL '
            'OR started_at IS NULL '
            'OR completed_at >= started_at',
            name='ck_agent_runs_completion_time_order',
        ),
        CheckConstraint(
            "(run_status = 'created' "
            'AND completed_at IS NULL) OR '
            "(run_status IN ("
            "'running', "
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'generating_analysis', "
            "'waiting_for_final_review'"
            ') '
            'AND started_at IS NOT NULL '
            'AND completed_at IS NULL) OR '
            "(run_status IN ("
            "'completed', "
            "'failed', "
            "'limit_exceeded'"
            ') '
            'AND started_at IS NOT NULL '
            'AND completed_at IS NOT NULL) OR '
            "(run_status = 'cancelled' "
            'AND completed_at IS NOT NULL)',
            name='ck_agent_runs_status_time_consistency',
        ),
        CheckConstraint(
            "(run_status IN ("
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'waiting_for_final_review'"
            ') '
            'AND waiting_since IS NOT NULL '
            'AND resume_node IS NOT NULL) OR '
            "(run_status NOT IN ("
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'waiting_for_final_review'"
            ') '
            'AND waiting_since IS NULL '
            'AND resume_node IS NULL)',
            name='ck_agent_runs_waiting_resume_fields',
        ),
        CheckConstraint(
            "run_status NOT IN ('failed', 'limit_exceeded') "
            'OR error_code IS NOT NULL '
            'OR error_message IS NOT NULL',
            name='ck_agent_runs_failure_error_present',
        ),
        CheckConstraint(
            "run_status NOT IN ('completed', 'cancelled') "
            'OR ('
            'error_code IS NULL '
            'AND error_message IS NULL'
            ')',
            name='ck_agent_runs_terminal_error_absent',
        ),
        UniqueConstraint('run_id', name='uq_agent_runs_run_id'),
        UniqueConstraint(
            'analysis_log_id',
            name='uq_agent_runs_analysis_log_id',
        ),
        Index('ix_agent_runs_issue_id', 'issue_id'),
        Index('ix_agent_runs_run_status', 'run_status'),
        Index('ix_agent_runs_current_node', 'current_node'),
        Index('ix_agent_runs_created_at', 'created_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    run_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        default=lambda: str(uuid4()),
    )

    issue_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('issues.id'),
        nullable=False,
    )

    analysis_log_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('ai_analysis_logs.id'),
        nullable=True,
    )

    graph_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    current_node: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    run_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default='created',
        server_default='created',
    )

    step_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default='0',
    )

    tool_call_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default='0',
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default='0',
    )

    state_json: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB(), 'postgresql'),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )

    waiting_since: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    resume_node: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    issue = relationship('Issue')
    analysis_log = relationship('AIAnalysisLog')

    steps = relationship(
        'AgentStep',
        back_populates='agent_run',
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='AgentStep.step_index',
    )