from datetime import datetime

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AgentStep(Base):
    __tablename__ = 'agent_steps'
    __table_args__ = (
        CheckConstraint(
            'step_index >= 1',
            name='ck_agent_steps_step_index_positive',
        ),
        CheckConstraint(
            "step_status IN ("
            "'running', "
            "'completed', "
            "'interrupted', "
            "'failed', "
            "'cancelled'"
            ")",
            name='ck_agent_steps_status_allowed',
        ),
        CheckConstraint(
            'completed_at IS NULL OR completed_at >= started_at',
            name='ck_agent_steps_completion_time_order',
        ),
        CheckConstraint(
            "(step_status = 'running' AND completed_at IS NULL) OR "
            "(step_status IN ("
            "'completed', "
            "'interrupted', "
            "'failed', "
            "'cancelled'"
            ") AND completed_at IS NOT NULL)",
            name='ck_agent_steps_status_completion_consistency',
        ),
        CheckConstraint(
            "step_status != 'failed' "
            'OR error_code IS NOT NULL '
            'OR error_message IS NOT NULL',
            name='ck_agent_steps_failed_error_present',
        ),
        UniqueConstraint(
            'agent_run_id',
            'step_index',
            name='uq_agent_steps_run_step_index',
        ),
        Index('ix_agent_steps_node_name', 'node_name'),
        Index('ix_agent_steps_step_status', 'step_status'),
        Index('ix_agent_steps_started_at', 'started_at'),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    agent_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('agent_runs.id', ondelete='CASCADE'),
        nullable=False,
    )

    step_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    node_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    step_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default='running',
        server_default='running',
    )

    input_state_json: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), 'postgresql'),
        nullable=True,
    )

    output_state_json: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), 'postgresql'),
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

    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    agent_run = relationship(
        'AgentRun',
        back_populates='steps',
    )

    tool_calls = relationship(
        'AgentToolCall',
        back_populates='agent_step',
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='AgentToolCall.tool_call_index',
    )