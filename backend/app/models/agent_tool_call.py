from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AgentToolCall(Base):
    __tablename__ = 'agent_tool_calls'
    __table_args__ = (
        CheckConstraint(
            'tool_call_index >= 1',
            name='ck_agent_tool_calls_call_index_positive',
        ),
        CheckConstraint(
            "call_status IN ("
            "'created', "
            "'running', "
            "'completed', "
            "'failed', "
            "'timed_out', "
            "'cancelled'"
            ")",
            name='ck_agent_tool_calls_status_allowed',
        ),
        CheckConstraint(
            'completed_at IS NULL '
            'OR started_at IS NULL '
            'OR completed_at >= started_at',
            name='ck_agent_tool_calls_completion_time_order',
        ),
        CheckConstraint(
            "(call_status = 'created' "
            'AND started_at IS NULL '
            'AND completed_at IS NULL) OR '
            "(call_status = 'running' "
            'AND started_at IS NOT NULL '
            'AND completed_at IS NULL) OR '
            "(call_status IN ("
            "'completed', "
            "'failed', "
            "'timed_out'"
            ') '
            'AND started_at IS NOT NULL '
            'AND completed_at IS NOT NULL) OR '
            "(call_status = 'cancelled' "
            'AND completed_at IS NOT NULL)',
            name='ck_agent_tool_calls_status_time_consistency',
        ),
        CheckConstraint(
            "call_status != 'completed' OR result_json IS NOT NULL",
            name='ck_agent_tool_calls_completed_result_present',
        ),
        CheckConstraint(
            "call_status NOT IN ('failed', 'timed_out') "
            'OR error_code IS NOT NULL '
            'OR error_message IS NOT NULL',
            name='ck_agent_tool_calls_failure_error_present',
        ),
        CheckConstraint(
            'timeout_seconds > 0',
            name='ck_agent_tool_calls_timeout_positive',
        ),
        UniqueConstraint(
            'agent_step_id',
            'tool_call_index',
            name='uq_agent_tool_calls_step_call_index',
        ),
        Index('ix_agent_tool_calls_tool_name', 'tool_name'),
        Index('ix_agent_tool_calls_call_status', 'call_status'),
        Index('ix_agent_tool_calls_created_at', 'created_at'),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    agent_step_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('agent_steps.id', ondelete='CASCADE'),
        nullable=False,
    )

    tool_call_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    tool_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    tool_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    call_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default='created',
        server_default='created',
    )

    arguments_json: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB(), 'postgresql'),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )

    result_json: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), 'postgresql'),
        nullable=True,
    )

    read_only: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
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

    agent_step = relationship(
        'AgentStep',
        back_populates='tool_calls',
    )