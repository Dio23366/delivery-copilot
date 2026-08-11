from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AIAnalysisLog, AgentRun, AgentStep, AgentToolCall
from app.services.agent_tool_contract_service import (
    AgentToolContractError,
    AgentToolContractService,
    ValidatedAgentToolArguments,
    agent_tool_contract_service,
)
from app.services.agent_tool_registry import AgentToolDefinition


AGENT_TOOL_CALL_REPLAY_RESERVATION_VERSION = (
    'agent_tool_call_replay_reservation_v0.1'
)


class AgentToolCallReplayPersistenceError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class AgentToolCallReplayReservation:
    tool_call: AgentToolCall
    call_identity: str
    reservation_action: str
    step_index: int | None = None
    reservation_version: str = (
        AGENT_TOOL_CALL_REPLAY_RESERVATION_VERSION
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.call_identity, str)
            or not self.call_identity.strip()
            or self.call_identity != self.call_identity.strip()
        ):
            raise ValueError(
                'call_identity must be a normalized '
                'nonblank string',
            )
        if self.reservation_action not in {
            'created',
            'reused',
        }:
            raise ValueError(
                'reservation_action must be created or reused',
            )
        if (
            self.step_index is not None
            and (
                type(self.step_index) is not int
                or self.step_index <= 0
            )
        ):
            raise ValueError(
                'step_index must be a positive integer when provided',
            )

    def as_dict(self) -> dict[str, object]:
        return {
            'reservation_version': self.reservation_version,
            'reservation_action': self.reservation_action,
            'call_identity': self.call_identity,
            'step_index': self.step_index,
            'tool_call_index': self.tool_call.tool_call_index,
            'call_status': self.tool_call.call_status,
        }


AGENT_ANALYSIS_PERSISTENCE_VERSION = (
    'agent_analysis_persistence_v0.1'
)
GENERATED_ANALYSIS_STATE_KEY = 'generated_analysis'
PERSIST_ANALYSIS_NODE = 'persist_analysis'
FINAL_REVIEW_NODE = 'final_review'
GENERATING_ANALYSIS_STATUS = 'generating_analysis'
PENDING_FEEDBACK_STATUS = 'pending'
AGENT_FINAL_REVIEW_WAIT_VERSION = (
    'agent_final_review_wait_v0.1'
)
AWAIT_FINAL_REVIEW_NODE = 'await_final_review'
WAITING_FOR_FINAL_REVIEW_STATUS = (
    'waiting_for_final_review'
)
FINALIZE_RUN_NODE = 'finalize_run'

GENERATED_ANALYSIS_FIELDS = frozenset(
    {
        'generation_version',
        'analysis_type',
        'provider',
        'model_name',
        'prompt_version',
        'provider_fallback_reason',
        'issue_summary',
        'possible_root_cause',
        'recommended_actions',
        'customer_update_draft',
        'risk_level',
        'project_impact',
        'retrieval_status',
        'retrieval_query',
        'knowledge_citations',
        'retrieval_error_code',
        'supplemental_evidence_count',
    }
)
KNOWLEDGE_CITATION_FIELDS = frozenset(
    {
        'citation_id',
        'rank',
        'chunk_id',
        'document_id',
        'document_title',
        'scope_type',
        'doc_type',
        'source_kind',
        'source_name',
        'source_uri',
        'chunk_index',
        'chunk_text',
        'similarity_score',
    }
)
CONTROLLED_ANALYSIS_PROVIDERS = frozenset(
    {'llm', 'rule_based_fallback'}
)
CONTROLLED_RISK_LEVELS = frozenset(
    {'low', 'medium', 'high', 'critical'}
)
CONTROLLED_RETRIEVAL_STATUSES = frozenset(
    {'not_attempted', 'succeeded', 'no_results', 'failed'}
)


class AgentPersistenceService:
    """Transaction-neutral persistence helpers for Agent execution."""

    def __init__(
        self,
        *,
        tool_contract_service: AgentToolContractService = (
            agent_tool_contract_service
        ),
    ) -> None:
        if not isinstance(
            tool_contract_service,
            AgentToolContractService,
        ):
            raise TypeError(
                'tool_contract_service must be an '
                'AgentToolContractService',
            )
        self._tool_contract_service = tool_contract_service

    def create_run(
        self,
        db: Session,
        *,
        run_id: str,
        issue_id: int,
        graph_version: str,
        current_node: str,
        state_json: dict[str, object] | None = None,
        run_status: str = 'created',
        started_at: datetime | None = None,
    ) -> AgentRun:
        agent_run = AgentRun(
            run_id=run_id,
            issue_id=issue_id,
            graph_version=graph_version,
            current_node=current_node,
            run_status=run_status,
            state_json=dict(state_json or {}),
            started_at=started_at,
        )
        db.add(agent_run)
        db.flush()
        return agent_run

    def get_run_by_run_id(
        self,
        db: Session,
        run_id: str,
    ) -> AgentRun | None:
        statement = select(AgentRun).where(
            AgentRun.run_id == run_id,
        )
        return db.scalar(statement)

    def lock_run_by_run_id(
        self,
        db: Session,
        run_id: str,
    ) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(AgentRun.run_id == run_id)
            .with_for_update()
        )
        return db.scalar(statement)

    def lock_run_by_analysis_id(
        self,
        db: Session,
        analysis_id: int,
    ) -> AgentRun | None:
        statement = (
            select(AgentRun)
            .where(
                AgentRun.analysis_log_id == analysis_id,
            )
            .with_for_update()
        )
        return db.scalar(statement)

    def lock_analysis_by_id(
        self,
        db: Session,
        analysis_id: int,
    ) -> AIAnalysisLog | None:
        statement = (
            select(AIAnalysisLog)
            .where(
                AIAnalysisLog.id == analysis_id,
            )
            .with_for_update()
        )
        return db.scalar(statement)

    def lock_step_by_run_and_index(
        self,
        db: Session,
        *,
        agent_run_id: int,
        step_index: int,
    ) -> AgentStep | None:
        statement = (
            select(AgentStep)
            .where(
                AgentStep.agent_run_id == agent_run_id,
                AgentStep.step_index == step_index,
            )
            .with_for_update()
        )
        return db.scalar(statement)

    def lock_tool_call_by_step_and_index(
        self,
        db: Session,
        *,
        agent_step_id: int,
        tool_call_index: int,
    ) -> AgentToolCall | None:
        statement = (
            select(AgentToolCall)
            .where(
                AgentToolCall.agent_step_id == agent_step_id,
                AgentToolCall.tool_call_index == tool_call_index,
            )
            .with_for_update()
        )
        return db.scalar(statement)

    def append_step(
        self,
        db: Session,
        *,
        run_id: str,
        node_name: str,
        input_state_json: dict[str, object] | None = None,
        started_at: datetime | None = None,
    ) -> AgentStep:
        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        next_step_index = agent_run.step_count + 1

        agent_step = AgentStep(
            agent_run_id=agent_run.id,
            step_index=next_step_index,
            node_name=node_name,
            step_status='running',
            input_state_json=(
                dict(input_state_json)
                if input_state_json is not None
                else None
            ),
            started_at=started_at or datetime.utcnow(),
        )

        agent_run.step_count = next_step_index
        db.add(agent_step)
        db.flush()
        return agent_step

    def reserve_or_reuse_tool_call(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_name: str,
        arguments_json: Mapping[str, object],
        max_tool_calls: int,
    ) -> AgentToolCallReplayReservation:
        self._validate_replay_identity_inputs(
            run_id=run_id,
            max_tool_calls=max_tool_calls,
        )
        if type(step_index) is not int or step_index <= 0:
            raise ValueError(
                'step_index must be a positive integer',
            )

        requested, definition = (
            self._validate_replay_tool_request(
                tool_name=tool_name,
                arguments_json=arguments_json,
            )
        )
        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        return self._reserve_or_reuse_locked_tool_call(
            db,
            agent_run=agent_run,
            agent_step=agent_step,
            step_index=step_index,
            requested=requested,
            definition=definition,
            max_tool_calls=max_tool_calls,
        )

    def reserve_or_reuse_current_tool_call(
        self,
        db: Session,
        *,
        run_id: str,
        tool_name: str,
        arguments_json: Mapping[str, object],
        max_tool_calls: int,
    ) -> AgentToolCallReplayReservation:
        self._validate_replay_identity_inputs(
            run_id=run_id,
            max_tool_calls=max_tool_calls,
        )
        requested, definition = (
            self._validate_replay_tool_request(
                tool_name=tool_name,
                arguments_json=arguments_json,
            )
        )

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )
        if agent_run.run_status != 'running':
            raise AgentToolCallReplayPersistenceError(
                error_code='invalid_replay_run_status',
                message=(
                    'Replay-aware Tool execution requires '
                    'a running AgentRun.'
                ),
            )
        if agent_run.current_node != 'execute_tool':
            raise AgentToolCallReplayPersistenceError(
                error_code='invalid_replay_current_node',
                message=(
                    'Replay-aware Tool execution requires '
                    'AgentRun.current_node=execute_tool.'
                ),
            )

        step_index = agent_run.step_count
        if type(step_index) is not int or step_index <= 0:
            raise AgentToolCallReplayPersistenceError(
                error_code='invalid_replay_step_count',
                message=(
                    'AgentRun.step_count must resolve a '
                    'positive current Step index.'
                ),
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise AgentToolCallReplayPersistenceError(
                error_code='current_replay_step_not_found',
                message=(
                    'The current execute_tool AgentStep '
                    'could not be resolved.'
                ),
            )
        if agent_step.step_status != 'running':
            raise AgentToolCallReplayPersistenceError(
                error_code='invalid_replay_step_status',
                message=(
                    'The current execute_tool AgentStep '
                    'must be running.'
                ),
            )
        if agent_step.node_name != 'execute_tool':
            raise AgentToolCallReplayPersistenceError(
                error_code='invalid_replay_step_node',
                message=(
                    'The current AgentStep must be the '
                    'execute_tool node.'
                ),
            )

        return self._reserve_or_reuse_locked_tool_call(
            db,
            agent_run=agent_run,
            agent_step=agent_step,
            step_index=step_index,
            requested=requested,
            definition=definition,
            max_tool_calls=max_tool_calls,
        )

    @staticmethod
    def _validate_replay_identity_inputs(
        *,
        run_id: str,
        max_tool_calls: int,
    ) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError(
                'run_id must be a nonblank string',
            )
        if run_id != run_id.strip():
            raise ValueError(
                'run_id must be normalized',
            )
        if type(max_tool_calls) is not int or max_tool_calls < 1:
            raise ValueError(
                'max_tool_calls must be a positive integer',
            )

    def _validate_replay_tool_request(
        self,
        *,
        tool_name: str,
        arguments_json: Mapping[str, object],
    ) -> tuple[
        ValidatedAgentToolArguments,
        AgentToolDefinition,
    ]:
        try:
            requested = (
                self._tool_contract_service
                .validate_arguments(
                    tool_name,
                    arguments_json,
                )
            )
            definition = (
                self._tool_contract_service
                .registry.get(
                    requested.tool_name
                )
            )
        except (
            AgentToolContractError,
            LookupError,
            ValueError,
        ) as exc:
            error_code = getattr(
                exc,
                'error_code',
                'invalid_requested_tool_call',
            )
            raise AgentToolCallReplayPersistenceError(
                error_code=error_code,
                message=str(exc),
            ) from exc

        if (
            definition.read_only is not True
            or definition.requires_approval is not False
        ):
            raise AgentToolCallReplayPersistenceError(
                error_code='unsafe_replay_tool',
                message=(
                    'Replay-aware execution only supports '
                    'approved read-only tools.'
                ),
            )

        return requested, definition

    def _reserve_or_reuse_locked_tool_call(
        self,
        db: Session,
        *,
        agent_run: AgentRun,
        agent_step: AgentStep,
        step_index: int,
        requested: ValidatedAgentToolArguments,
        definition: AgentToolDefinition,
        max_tool_calls: int,
    ) -> AgentToolCallReplayReservation:
        rows = tuple(
            db.execute(
                select(
                    AgentToolCall,
                    AgentStep.step_index,
                )
                .join(
                    AgentStep,
                    AgentToolCall.agent_step_id
                    == AgentStep.id,
                )
                .where(
                    AgentStep.agent_run_id
                    == agent_run.id,
                )
                .order_by(
                    AgentStep.step_index,
                    AgentToolCall.tool_call_index,
                )
                .with_for_update(
                    of=AgentToolCall,
                )
            ).all()
        )

        persisted_count = agent_run.tool_call_count
        if (
            type(persisted_count) is not int
            or persisted_count < 0
        ):
            raise AgentToolCallReplayPersistenceError(
                error_code='invalid_persisted_tool_call_count',
                message=(
                    'AgentRun.tool_call_count must be a '
                    'nonnegative integer.'
                ),
            )
        if persisted_count != len(rows):
            raise AgentToolCallReplayPersistenceError(
                error_code='tool_call_count_mismatch',
                message=(
                    'AgentRun.tool_call_count does not '
                    'match persisted AgentToolCall rows.'
                ),
            )

        matches: list[tuple[AgentToolCall, int]] = []
        current_step_indexes: list[int] = []

        for tool_call, persisted_step_index in rows:
            if persisted_step_index == step_index:
                current_step_indexes.append(
                    int(tool_call.tool_call_index)
                )

            arguments = tool_call.arguments_json
            if not isinstance(arguments, Mapping):
                raise AgentToolCallReplayPersistenceError(
                    error_code='invalid_persisted_tool_arguments',
                    message=(
                        'Persisted Tool arguments must be '
                        'a JSON object.'
                    ),
                )

            try:
                validated = (
                    self._tool_contract_service
                    .validate_arguments(
                        tool_call.tool_name,
                        arguments,
                    )
                )
            except AgentToolContractError as exc:
                raise AgentToolCallReplayPersistenceError(
                    error_code='invalid_persisted_tool_call',
                    message=(
                        'Persisted ToolCall no longer '
                        'matches the approved contract.'
                    ),
                ) from exc

            if tool_call.tool_version != validated.tool_version:
                raise AgentToolCallReplayPersistenceError(
                    error_code='persisted_tool_version_mismatch',
                    message=(
                        'Persisted Tool version does not '
                        'match the approved Registry.'
                    ),
                )

            if validated.call_identity == requested.call_identity:
                matches.append(
                    (
                        tool_call,
                        int(persisted_step_index),
                    )
                )

        if len(matches) > 1:
            raise AgentToolCallReplayPersistenceError(
                error_code='duplicate_persisted_tool_call_identity',
                message=(
                    'Multiple persisted ToolCalls resolve '
                    'to the same call identity.'
                ),
            )

        if matches:
            tool_call, persisted_step_index = matches[0]

            if persisted_step_index != step_index:
                raise AgentToolCallReplayPersistenceError(
                    error_code='replay_tool_call_step_mismatch',
                    message=(
                        'A matching persisted ToolCall belongs '
                        'to a different Agent step.'
                    ),
                )
            if (
                tool_call.read_only is not True
                or tool_call.requires_approval is not False
                or tool_call.timeout_seconds
                != definition.timeout_seconds
            ):
                raise AgentToolCallReplayPersistenceError(
                    error_code='persisted_tool_policy_mismatch',
                    message=(
                        'Persisted ToolCall policy does not '
                        'match the approved Registry.'
                    ),
                )

            return AgentToolCallReplayReservation(
                tool_call=tool_call,
                call_identity=requested.call_identity,
                reservation_action='reused',
                step_index=step_index,
            )

        if persisted_count >= max_tool_calls:
            raise AgentToolCallReplayPersistenceError(
                error_code='max_tool_calls_reached',
                message=(
                    'The Agent run has reached its maximum '
                    'ToolCall count.'
                ),
            )

        next_tool_call_index = (
            max(current_step_indexes, default=0) + 1
        )
        tool_call = AgentToolCall(
            agent_step_id=agent_step.id,
            tool_call_index=next_tool_call_index,
            tool_name=definition.tool_name,
            tool_version=definition.tool_version,
            call_status='created',
            arguments_json=requested.as_dict(),
            read_only=definition.read_only,
            requires_approval=(
                definition.requires_approval
            ),
            timeout_seconds=definition.timeout_seconds,
        )

        agent_run.tool_call_count += 1
        db.add(tool_call)
        db.flush()

        return AgentToolCallReplayReservation(
            tool_call=tool_call,
            call_identity=requested.call_identity,
            reservation_action='created',
            step_index=step_index,
        )

    def append_tool_call(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_name: str,
        timeout_seconds: int,
        arguments_json: dict[str, object] | None = None,
        tool_version: str | None = None,
        read_only: bool = True,
        requires_approval: bool = False,
    ) -> AgentToolCall:
        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        current_tool_call_index = db.scalar(
            select(
                func.coalesce(
                    func.max(AgentToolCall.tool_call_index),
                    0,
                )
            ).where(
                AgentToolCall.agent_step_id == agent_step.id,
            )
        )
        next_tool_call_index = int(
            current_tool_call_index or 0,
        ) + 1

        tool_call = AgentToolCall(
            agent_step_id=agent_step.id,
            tool_call_index=next_tool_call_index,
            tool_name=tool_name,
            tool_version=tool_version,
            call_status='created',
            arguments_json=dict(arguments_json or {}),
            read_only=read_only,
            requires_approval=requires_approval,
            timeout_seconds=timeout_seconds,
        )

        agent_run.tool_call_count += 1
        db.add(tool_call)
        db.flush()
        return tool_call

    def mark_tool_call_running(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_call_index: int,
        started_at: datetime | None = None,
    ) -> AgentToolCall:
        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        tool_call = self.lock_tool_call_by_step_and_index(
            db,
            agent_step_id=agent_step.id,
            tool_call_index=tool_call_index,
        )
        if tool_call is None:
            raise LookupError(
                'Agent tool call not found: '
                f'run_id={run_id}, '
                f'step_index={step_index}, '
                f'tool_call_index={tool_call_index}',
            )

        if tool_call.call_status != 'created':
            raise ValueError(
                'Agent tool call cannot start from status: '
                f'{tool_call.call_status}',
            )

        tool_call.call_status = 'running'
        tool_call.started_at = started_at or datetime.utcnow()

        db.flush()
        return tool_call

    def mark_tool_call_completed(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_call_index: int,
        result_json: dict[str, object],
        completed_at: datetime | None = None,
    ) -> AgentToolCall:
        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        tool_call = self.lock_tool_call_by_step_and_index(
            db,
            agent_step_id=agent_step.id,
            tool_call_index=tool_call_index,
        )
        if tool_call is None:
            raise LookupError(
                'Agent tool call not found: '
                f'run_id={run_id}, '
                f'step_index={step_index}, '
                f'tool_call_index={tool_call_index}',
            )

        if tool_call.call_status != 'running':
            raise ValueError(
                'Agent tool call cannot complete from status: '
                f'{tool_call.call_status}',
            )

        tool_call.result_json = dict(result_json)
        tool_call.completed_at = (
            completed_at or datetime.utcnow()
        )
        tool_call.call_status = 'completed'

        db.flush()
        return tool_call

    def mark_tool_call_failed(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_call_index: int,
        error_code: str | None = None,
        error_message: str | None = None,
        completed_at: datetime | None = None,
    ) -> AgentToolCall:
        normalized_error_code = (
            error_code.strip()
            if error_code is not None
            else None
        )
        normalized_error_message = (
            error_message.strip()
            if error_message is not None
            else None
        )

        normalized_error_code = normalized_error_code or None
        normalized_error_message = normalized_error_message or None

        if (
            normalized_error_code is None
            and normalized_error_message is None
        ):
            raise ValueError(
                'Agent tool call failure requires '
                'error_code or error_message',
            )

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        tool_call = self.lock_tool_call_by_step_and_index(
            db,
            agent_step_id=agent_step.id,
            tool_call_index=tool_call_index,
        )
        if tool_call is None:
            raise LookupError(
                'Agent tool call not found: '
                f'run_id={run_id}, '
                f'step_index={step_index}, '
                f'tool_call_index={tool_call_index}',
            )

        if tool_call.call_status != 'running':
            raise ValueError(
                'Agent tool call cannot fail from status: '
                f'{tool_call.call_status}',
            )

        tool_call.error_code = normalized_error_code
        tool_call.error_message = normalized_error_message
        tool_call.completed_at = (
            completed_at or datetime.utcnow()
        )
        tool_call.call_status = 'failed'

        db.flush()
        return tool_call

    def mark_tool_call_timed_out(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_call_index: int,
        error_code: str | None = 'TOOL_TIMEOUT',
        error_message: str | None = None,
        completed_at: datetime | None = None,
    ) -> AgentToolCall:
        normalized_error_code = (
            error_code.strip()
            if error_code is not None
            else None
        )
        normalized_error_message = (
            error_message.strip()
            if error_message is not None
            else None
        )

        normalized_error_code = normalized_error_code or None
        normalized_error_message = normalized_error_message or None

        if (
            normalized_error_code is None
            and normalized_error_message is None
        ):
            raise ValueError(
                'Agent tool call timeout requires '
                'error_code or error_message',
            )

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        tool_call = self.lock_tool_call_by_step_and_index(
            db,
            agent_step_id=agent_step.id,
            tool_call_index=tool_call_index,
        )
        if tool_call is None:
            raise LookupError(
                'Agent tool call not found: '
                f'run_id={run_id}, '
                f'step_index={step_index}, '
                f'tool_call_index={tool_call_index}',
            )

        if tool_call.call_status != 'running':
            raise ValueError(
                'Agent tool call cannot time out from status: '
                f'{tool_call.call_status}',
            )

        tool_call.error_code = normalized_error_code
        tool_call.error_message = normalized_error_message
        tool_call.completed_at = (
            completed_at or datetime.utcnow()
        )
        tool_call.call_status = 'timed_out'

        db.flush()
        return tool_call

    def mark_tool_call_cancelled(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_call_index: int,
        completed_at: datetime | None = None,
    ) -> AgentToolCall:
        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        tool_call = self.lock_tool_call_by_step_and_index(
            db,
            agent_step_id=agent_step.id,
            tool_call_index=tool_call_index,
        )
        if tool_call is None:
            raise LookupError(
                'Agent tool call not found: '
                f'run_id={run_id}, '
                f'step_index={step_index}, '
                f'tool_call_index={tool_call_index}',
            )

        if tool_call.call_status != 'running':
            raise ValueError(
                'Agent tool call cannot be cancelled from status: '
                f'{tool_call.call_status}',
            )

        tool_call.completed_at = (
            completed_at or datetime.utcnow()
        )
        tool_call.call_status = 'cancelled'

        db.flush()
        return tool_call

    def complete_step_and_advance_run(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        next_node: str,
        state_json: dict[str, object],
        output_state_json: dict[str, object] | None = None,
        completed_at: datetime | None = None,
        next_started_at: datetime | None = None,
    ) -> tuple[AgentRun, AgentStep, AgentStep]:
        normalized_next_node = next_node.strip()
        if not normalized_next_node:
            raise ValueError(
                'Next Agent node must be nonblank',
            )

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        if agent_run.run_status != 'running':
            raise ValueError(
                'Agent run cannot advance from status: '
                f'{agent_run.run_status}',
            )

        if step_index != agent_run.step_count:
            raise ValueError(
                'Only the latest Agent step may advance '
                'the run: '
                f'expected={agent_run.step_count}, '
                f'actual={step_index}',
            )

        current_step = (
            self.lock_step_by_run_and_index(
                db,
                agent_run_id=agent_run.id,
                step_index=step_index,
            )
        )
        if current_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, '
                f'step_index={step_index}',
            )

        if current_step.step_status != 'running':
            raise ValueError(
                'Agent step cannot advance from status: '
                f'{current_step.step_status}',
            )

        if current_step.node_name != agent_run.current_node:
            raise ValueError(
                'Agent run and current step node mismatch: '
                f'run={agent_run.current_node}, '
                f'step={current_step.node_name}',
            )

        effective_completed_at = (
            completed_at or datetime.utcnow()
        )
        effective_state = dict(state_json)
        effective_output_state = (
            dict(output_state_json)
            if output_state_json is not None
            else dict(effective_state)
        )

        current_step.output_state_json = (
            effective_output_state
        )
        current_step.error_code = None
        current_step.error_message = None
        current_step.completed_at = (
            effective_completed_at
        )
        current_step.step_status = 'completed'

        next_step_index = agent_run.step_count + 1
        next_step = AgentStep(
            agent_run_id=agent_run.id,
            step_index=next_step_index,
            node_name=normalized_next_node,
            step_status='running',
            input_state_json=dict(effective_state),
            started_at=(
                next_started_at
                or effective_completed_at
            ),
        )

        agent_run.current_node = normalized_next_node
        agent_run.state_json = effective_state
        agent_run.step_count = next_step_index
        agent_run.waiting_since = None
        agent_run.resume_node = None
        agent_run.error_code = None
        agent_run.error_message = None
        agent_run.completed_at = None

        db.add(next_step)
        db.flush()

        return agent_run, current_step, next_step

    def mark_step_completed(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        output_state_json: dict[str, object] | None = None,
        completed_at: datetime | None = None,
    ) -> AgentStep:
        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        if agent_step.step_status != 'running':
            raise ValueError(
                'Agent step cannot complete from status: '
                f'{agent_step.step_status}',
            )

        agent_step.output_state_json = (
            dict(output_state_json)
            if output_state_json is not None
            else None
        )
        agent_step.error_code = None
        agent_step.error_message = None
        agent_step.completed_at = (
            completed_at or datetime.utcnow()
        )
        agent_step.step_status = 'completed'

        db.flush()
        return agent_step

    def mark_step_failed(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        error_code: str | None = None,
        error_message: str | None = None,
        output_state_json: dict[str, object] | None = None,
        completed_at: datetime | None = None,
    ) -> AgentStep:
        normalized_error_code = (
            error_code.strip()
            if error_code is not None
            else None
        )
        normalized_error_message = (
            error_message.strip()
            if error_message is not None
            else None
        )

        normalized_error_code = normalized_error_code or None
        normalized_error_message = normalized_error_message or None

        if (
            normalized_error_code is None
            and normalized_error_message is None
        ):
            raise ValueError(
                'Agent step failure requires '
                'error_code or error_message',
            )

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        if agent_step.step_status != 'running':
            raise ValueError(
                'Agent step cannot fail from status: '
                f'{agent_step.step_status}',
            )

        agent_step.output_state_json = (
            dict(output_state_json)
            if output_state_json is not None
            else None
        )
        agent_step.error_code = normalized_error_code
        agent_step.error_message = normalized_error_message
        agent_step.completed_at = (
            completed_at or datetime.utcnow()
        )
        agent_step.step_status = 'failed'

        db.flush()
        return agent_step

    def complete_step_and_limit_run(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        error_code: str | None,
        error_message: str | None,
        state_json: dict[str, object],
        output_state_json: dict[str, object] | None = None,
        completed_at: datetime | None = None,
    ) -> tuple[AgentRun, AgentStep]:
        normalized_error_code = (
            error_code.strip()
            if error_code is not None
            else None
        )
        normalized_error_message = (
            error_message.strip()
            if error_message is not None
            else None
        )

        normalized_error_code = normalized_error_code or None
        normalized_error_message = normalized_error_message or None

        if (
            normalized_error_code is None
            and normalized_error_message is None
        ):
            raise ValueError(
                'limit_exceeded requires '
                'error_code or error_message',
            )

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        if agent_run.run_status != 'running':
            raise ValueError(
                'Agent run cannot reach limit_exceeded '
                f'from status: {agent_run.run_status}',
            )

        if step_index != agent_run.step_count:
            raise ValueError(
                'Only the latest Agent step may '
                'terminate the run: '
                f'expected={agent_run.step_count}, '
                f'actual={step_index}',
            )

        source_node = agent_run.current_node
        if (
            not isinstance(source_node, str)
            or not source_node.strip()
            or source_node != source_node.strip()
        ):
            raise ValueError(
                'Agent run must expose a normalized '
                'current_node',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, '
                f'step_index={step_index}',
            )

        if agent_step.step_status != 'running':
            raise ValueError(
                'Agent step cannot reach limit_exceeded '
                f'from status: {agent_step.step_status}',
            )

        if agent_step.node_name != source_node:
            raise ValueError(
                'Agent run and current step node mismatch: '
                f'run={source_node}, '
                f'step={agent_step.node_name}',
            )

        active_tool_call_indices = list(
            db.scalars(
                select(
                    AgentToolCall.tool_call_index,
                )
                .where(
                    AgentToolCall.agent_step_id
                    == agent_step.id,
                    AgentToolCall.call_status.in_(
                        {
                            'created',
                            'running',
                        }
                    ),
                )
                .order_by(
                    AgentToolCall.tool_call_index,
                )
            ).all()
        )
        if active_tool_call_indices:
            raise ValueError(
                'Agent step contains active tool calls: '
                f'{active_tool_call_indices}',
            )

        if agent_run.started_at is None:
            raise ValueError(
                'Running Agent run must have started_at',
            )

        if agent_step.started_at is None:
            raise ValueError(
                'Running Agent step must have started_at',
            )

        effective_completed_at = (
            completed_at or datetime.utcnow()
        )

        if effective_completed_at < agent_run.started_at:
            raise ValueError(
                'Agent run completion cannot precede '
                'start time',
            )

        if effective_completed_at < agent_step.started_at:
            raise ValueError(
                'Agent step completion cannot precede '
                'start time',
            )

        limit_snapshot = {
            'source_node': source_node,
            'error_code': normalized_error_code,
            'error_message': normalized_error_message,
            'step_count': agent_run.step_count,
            'tool_call_count': agent_run.tool_call_count,
        }

        effective_state = dict(state_json)
        effective_state['limit_exceeded'] = dict(
            limit_snapshot,
        )

        effective_output = (
            dict(output_state_json)
            if output_state_json is not None
            else {}
        )
        effective_output.update(
            {
                'next_node': 'limit_exceeded',
                **limit_snapshot,
            }
        )

        agent_step.output_state_json = effective_output
        agent_step.error_code = None
        agent_step.error_message = None
        agent_step.completed_at = effective_completed_at
        agent_step.step_status = 'completed'

        agent_run.run_status = 'limit_exceeded'
        agent_run.current_node = 'limit_exceeded'
        agent_run.state_json = effective_state
        agent_run.waiting_since = None
        agent_run.resume_node = None
        agent_run.error_code = normalized_error_code
        agent_run.error_message = normalized_error_message
        agent_run.completed_at = effective_completed_at

        db.flush()
        return agent_run, agent_step

    def mark_step_interrupted_and_run_waiting(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        waiting_status: str,
        state_json: dict[str, object],
        output_state_json: dict[str, object] | None = None,
        interrupted_at: datetime | None = None,
    ) -> tuple[AgentRun, AgentStep]:
        waiting_transitions = {
            'waiting_for_triage_confirmation': {
                'source_status': 'running',
                'current_node': 'await_triage_confirmation',
                'resume_node': 'route_investigation',
            },
            'waiting_for_clarification': {
                'source_status': 'running',
                'current_node': 'request_clarification',
                'resume_node': 'route_investigation',
            },
            'waiting_for_final_review': {
                'source_status': 'generating_analysis',
                'current_node': 'await_final_review',
                'resume_node': 'finalize_run',
            },
        }

        transition = waiting_transitions.get(waiting_status)
        if transition is None:
            raise ValueError(
                f'Unsupported Agent run waiting status: {waiting_status}',
            )

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        expected_source_status = transition['source_status']
        if agent_run.run_status != expected_source_status:
            raise ValueError(
                'Agent run cannot enter '
                f'{waiting_status} from status: '
                f'{agent_run.run_status}',
            )

        agent_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if agent_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, step_index={step_index}',
            )

        if agent_step.step_status != 'running':
            raise ValueError(
                'Agent step cannot interrupt from status: '
                f'{agent_step.step_status}',
            )

        effective_interrupted_at = (
            interrupted_at or datetime.utcnow()
        )

        agent_step.output_state_json = (
            dict(output_state_json)
            if output_state_json is not None
            else None
        )
        agent_step.error_code = None
        agent_step.error_message = None
        agent_step.completed_at = effective_interrupted_at
        agent_step.step_status = 'interrupted'

        agent_run.run_status = waiting_status
        agent_run.current_node = transition['current_node']
        agent_run.state_json = dict(state_json)
        agent_run.waiting_since = effective_interrupted_at
        agent_run.resume_node = transition['resume_node']
        agent_run.error_code = None
        agent_run.error_message = None
        agent_run.completed_at = None

        db.flush()
        return agent_run, agent_step

    def resume_waiting_investigation_run_and_append_step(
        self,
        db: Session,
        *,
        run_id: str,
        triage_result: dict[str, object] | None = None,
        clarification_response: str | None = None,
        resumed_at: datetime | None = None,
    ) -> tuple[AgentRun, AgentStep]:
        waiting_transitions = {
            'waiting_for_triage_confirmation': {
                'current_node': 'await_triage_confirmation',
                'resume_node': 'route_investigation',
            },
            'waiting_for_clarification': {
                'current_node': 'request_clarification',
                'resume_node': 'route_investigation',
            },
        }

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        transition = waiting_transitions.get(
            agent_run.run_status,
        )
        if transition is None:
            raise ValueError(
                'Agent run cannot resume investigation from status: '
                f'{agent_run.run_status}',
            )

        if agent_run.current_node != transition['current_node']:
            raise ValueError(
                'Waiting Agent run has inconsistent current node: '
                f'{agent_run.current_node}',
            )

        if agent_run.waiting_since is None:
            raise ValueError(
                'Waiting Agent run is missing waiting_since',
            )

        resume_node = agent_run.resume_node
        if resume_node != transition['resume_node']:
            raise ValueError(
                'Waiting Agent run has inconsistent resume node: '
                f'{resume_node}',
            )

        if agent_run.step_count < 1:
            raise ValueError(
                'Waiting Agent run has no interrupted step',
            )

        latest_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=agent_run.step_count,
        )
        if latest_step is None:
            raise LookupError(
                'Latest Agent step not found: '
                f'run_id={run_id}, '
                f'step_index={agent_run.step_count}',
            )

        if latest_step.step_status != 'interrupted':
            raise ValueError(
                'Waiting Agent run latest step must be interrupted: '
                f'{latest_step.step_status}',
            )

        active_tool_call_indices = list(
            db.scalars(
                select(
                    AgentToolCall.tool_call_index,
                )
                .where(
                    AgentToolCall.agent_step_id
                    == latest_step.id,
                    AgentToolCall.call_status.in_(
                        {
                            'created',
                            'running',
                        }
                    ),
                )
                .order_by(
                    AgentToolCall.tool_call_index,
                )
            ).all()
        )
        if active_tool_call_indices:
            raise ValueError(
                'Interrupted Agent step contains active tool calls: '
                f'{active_tool_call_indices}',
            )

        resumed_state = dict(agent_run.state_json or {})

        if (
            agent_run.run_status
            == 'waiting_for_triage_confirmation'
        ):
            if clarification_response is not None:
                raise ValueError(
                    'Clarification response is not valid for '
                    'triage confirmation resume',
                )

            effective_triage_result = (
                triage_result
                if triage_result is not None
                else resumed_state.get('triage_result')
            )
            if (
                not isinstance(effective_triage_result, dict)
                or not effective_triage_result
            ):
                raise ValueError(
                    'Triage confirmation requires a nonempty '
                    'triage result',
                )

            resumed_state['triage_result'] = dict(
                effective_triage_result,
            )
            resumed_state['triage_confirmed'] = True
        else:
            if triage_result is not None:
                raise ValueError(
                    'Triage result is not valid for '
                    'clarification resume',
                )

            if (
                not isinstance(clarification_response, str)
                or not clarification_response.strip()
            ):
                raise ValueError(
                    'Clarification response must be nonblank',
                )

            resumed_state['clarification_response'] = (
                clarification_response.strip()
            )

        effective_resumed_at = resumed_at or datetime.utcnow()
        next_step_index = agent_run.step_count + 1

        resumed_step = AgentStep(
            agent_run_id=agent_run.id,
            step_index=next_step_index,
            node_name=resume_node,
            step_status='running',
            input_state_json=dict(resumed_state),
            started_at=effective_resumed_at,
        )

        agent_run.run_status = 'running'
        agent_run.current_node = resume_node
        agent_run.state_json = resumed_state
        agent_run.waiting_since = None
        agent_run.resume_node = None
        agent_run.error_code = None
        agent_run.error_message = None
        agent_run.completed_at = None
        agent_run.step_count = next_step_index

        db.add(resumed_step)
        db.flush()

        return agent_run, resumed_step


    def persist_generated_analysis_and_advance_to_final_review(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        completed_at: datetime | None = None,
        final_review_started_at: datetime | None = None,
    ) -> tuple[
        AgentRun,
        AgentStep,
        AIAnalysisLog,
        AgentStep,
    ]:
        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        if agent_run.run_status != 'running':
            raise ValueError(
                'Agent run cannot persist analysis from status: '
                f'{agent_run.run_status}',
            )

        if agent_run.current_node != PERSIST_ANALYSIS_NODE:
            raise ValueError(
                'Agent run has unexpected persistence node: '
                f'{agent_run.current_node}',
            )

        if step_index != agent_run.step_count:
            raise ValueError(
                'Only the latest Agent step may persist '
                'analysis: '
                f'expected={agent_run.step_count}, '
                f'actual={step_index}',
            )

        if agent_run.analysis_log_id is not None:
            raise ValueError(
                'Agent run already has an analysis_log_id',
            )

        persist_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if persist_step is None:
            raise LookupError(
                'Agent step not found: '
                f'run_id={run_id}, '
                f'step_index={step_index}',
            )

        if persist_step.step_status != 'running':
            raise ValueError(
                'persist_analysis Step must be running: '
                f'{persist_step.step_status}',
            )

        if persist_step.node_name != PERSIST_ANALYSIS_NODE:
            raise ValueError(
                'Agent Step has unexpected persistence node: '
                f'{persist_step.node_name}',
            )

        previous_state = dict(
            agent_run.state_json or {}
        )
        step_input_state = getattr(
            persist_step,
            'input_state_json',
            None,
        )
        if not isinstance(step_input_state, Mapping):
            raise ValueError(
                'persist_analysis Step input state '
                'must be a mapping',
            )

        if dict(step_input_state) != previous_state:
            raise ValueError(
                'persist_analysis Step state snapshot '
                'does not match Agent Run state',
            )

        if previous_state.get('analysis_log_id') is not None:
            raise ValueError(
                'Agent state already contains analysis_log_id',
            )

        generated_analysis = (
            self._validated_generated_analysis(
                previous_state.get(
                    GENERATED_ANALYSIS_STATE_KEY
                )
            )
        )

        effective_completed_at = (
            completed_at or datetime.utcnow()
        )
        effective_final_review_started_at = (
            final_review_started_at
            or effective_completed_at
        )
        if (
            effective_final_review_started_at
            < effective_completed_at
        ):
            raise ValueError(
                'final_review cannot start before '
                'persist_analysis completes',
            )

        recommended_actions_json = (
            self._json_text(
                generated_analysis[
                    'recommended_actions'
                ],
                field_name='recommended_actions',
            )
        )
        knowledge_citations_json = (
            self._json_text(
                generated_analysis[
                    'knowledge_citations'
                ],
                field_name='knowledge_citations',
            )
        )

        analysis = AIAnalysisLog(
            issue_id=agent_run.issue_id,
            analysis_type=generated_analysis[
                'analysis_type'
            ],
            provider=generated_analysis['provider'],
            model_name=generated_analysis[
                'model_name'
            ],
            prompt_version=generated_analysis[
                'prompt_version'
            ],
            issue_summary=generated_analysis[
                'issue_summary'
            ],
            possible_root_cause=generated_analysis[
                'possible_root_cause'
            ],
            recommended_actions_json=(
                recommended_actions_json
            ),
            customer_update_draft=generated_analysis[
                'customer_update_draft'
            ],
            risk_level=generated_analysis[
                'risk_level'
            ],
            project_impact=generated_analysis[
                'project_impact'
            ],
            feedback_status=PENDING_FEEDBACK_STATUS,
            feedback_note=None,
            edited_output=None,
            retrieval_status=generated_analysis[
                'retrieval_status'
            ],
            retrieval_query=generated_analysis[
                'retrieval_query'
            ],
            knowledge_citations_json=(
                knowledge_citations_json
            ),
            retrieval_error_code=generated_analysis[
                'retrieval_error_code'
            ],
        )

        db.add(analysis)
        db.flush()

        analysis_id = getattr(analysis, 'id', None)
        if type(analysis_id) is not int or analysis_id < 1:
            raise RuntimeError(
                'Persisted AI analysis did not receive '
                'a positive integer id',
            )

        state_after_persistence = dict(
            previous_state
        )
        state_after_persistence['analysis_log_id'] = (
            analysis_id
        )
        state_after_persistence['pending_approval'] = True

        persistence_receipt = {
            'persistence_version': (
                AGENT_ANALYSIS_PERSISTENCE_VERSION
            ),
            'analysis_log_id': analysis_id,
            'feedback_status': (
                PENDING_FEEDBACK_STATUS
            ),
            'next_node': FINAL_REVIEW_NODE,
        }

        persist_step.output_state_json = dict(
            persistence_receipt
        )
        persist_step.error_code = None
        persist_step.error_message = None
        persist_step.completed_at = (
            effective_completed_at
        )
        persist_step.step_status = 'completed'

        next_step_index = agent_run.step_count + 1
        final_review_step = AgentStep(
            agent_run_id=agent_run.id,
            step_index=next_step_index,
            node_name=FINAL_REVIEW_NODE,
            step_status='running',
            input_state_json=dict(
                state_after_persistence
            ),
            started_at=(
                effective_final_review_started_at
            ),
        )

        agent_run.analysis_log_id = analysis_id
        agent_run.run_status = (
            GENERATING_ANALYSIS_STATUS
        )
        agent_run.current_node = FINAL_REVIEW_NODE
        agent_run.state_json = dict(
            state_after_persistence
        )
        agent_run.step_count = next_step_index
        agent_run.waiting_since = None
        agent_run.resume_node = None
        agent_run.error_code = None
        agent_run.error_message = None
        agent_run.completed_at = None

        db.add(final_review_step)
        db.flush()

        return (
            agent_run,
            persist_step,
            analysis,
            final_review_step,
        )

    def complete_final_review_and_wait_run(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        interrupted_at: datetime | None = None,
    ) -> tuple[AgentRun, AgentStep, AgentStep]:
        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        if agent_run.run_status != GENERATING_ANALYSIS_STATUS:
            raise ValueError(
                'Agent run cannot enter final review wait '
                f'from status: {agent_run.run_status}',
            )

        if agent_run.current_node != FINAL_REVIEW_NODE:
            raise ValueError(
                'Agent run has unexpected final review node: '
                f'{agent_run.current_node}',
            )

        if step_index != agent_run.step_count:
            raise ValueError(
                'Only the latest Agent step may enter '
                'final review wait: '
                f'expected={agent_run.step_count}, '
                f'actual={step_index}',
            )

        analysis_id = agent_run.analysis_log_id
        if type(analysis_id) is not int or analysis_id < 1:
            raise ValueError(
                'Agent run must have a positive analysis_log_id',
            )

        final_review_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=step_index,
        )
        if final_review_step is None:
            raise LookupError(
                'Final review Agent step not found: '
                f'run_id={run_id}, '
                f'step_index={step_index}',
            )

        if final_review_step.node_name != FINAL_REVIEW_NODE:
            raise ValueError(
                'Latest Agent step is not final_review: '
                f'{final_review_step.node_name}',
            )

        if final_review_step.step_status != 'running':
            raise ValueError(
                'final_review Step must be running: '
                f'{final_review_step.step_status}',
            )

        previous_state = dict(
            agent_run.state_json or {}
        )
        step_input_state = getattr(
            final_review_step,
            'input_state_json',
            None,
        )
        if not isinstance(step_input_state, Mapping):
            raise ValueError(
                'final_review Step input state '
                'must be a mapping',
            )

        if dict(step_input_state) != previous_state:
            raise ValueError(
                'final_review Step state snapshot '
                'does not match Agent Run state',
            )

        if previous_state.get('analysis_log_id') != analysis_id:
            raise ValueError(
                'Agent state analysis_log_id does not match '
                'Agent Run analysis link',
            )

        if previous_state.get('pending_approval') is not True:
            raise ValueError(
                'Agent state must require pending approval',
            )

        if not isinstance(
            previous_state.get(
                GENERATED_ANALYSIS_STATE_KEY
            ),
            Mapping,
        ):
            raise ValueError(
                'Agent state must retain generated_analysis',
            )

        if agent_run.waiting_since is not None:
            raise ValueError(
                'Generating Agent run cannot already be waiting',
            )

        if agent_run.resume_node is not None:
            raise ValueError(
                'Generating Agent run cannot have a resume_node',
            )

        effective_interrupted_at = (
            interrupted_at or datetime.utcnow()
        )
        final_review_started_at = getattr(
            final_review_step,
            'started_at',
            None,
        )
        if (
            final_review_started_at is not None
            and effective_interrupted_at
            < final_review_started_at
        ):
            raise ValueError(
                'Final review wait cannot precede '
                'final_review start time',
            )

        review_receipt = {
            'final_review_wait_version': (
                AGENT_FINAL_REVIEW_WAIT_VERSION
            ),
            'analysis_log_id': analysis_id,
            'pending_approval': True,
            'completed_node': FINAL_REVIEW_NODE,
            'waiting_node': AWAIT_FINAL_REVIEW_NODE,
            'resume_node': FINALIZE_RUN_NODE,
        }

        final_review_step.output_state_json = dict(
            review_receipt
        )
        final_review_step.error_code = None
        final_review_step.error_message = None
        final_review_step.completed_at = (
            effective_interrupted_at
        )
        final_review_step.step_status = 'completed'

        await_step_index = agent_run.step_count + 1
        await_final_review_step = AgentStep(
            agent_run_id=agent_run.id,
            step_index=await_step_index,
            node_name=AWAIT_FINAL_REVIEW_NODE,
            step_status='interrupted',
            input_state_json=dict(previous_state),
            output_state_json=dict(review_receipt),
            started_at=effective_interrupted_at,
            completed_at=effective_interrupted_at,
        )

        agent_run.run_status = (
            WAITING_FOR_FINAL_REVIEW_STATUS
        )
        agent_run.current_node = AWAIT_FINAL_REVIEW_NODE
        agent_run.state_json = dict(previous_state)
        agent_run.step_count = await_step_index
        agent_run.waiting_since = (
            effective_interrupted_at
        )
        agent_run.resume_node = FINALIZE_RUN_NODE
        agent_run.error_code = None
        agent_run.error_message = None
        agent_run.completed_at = None

        db.add(await_final_review_step)
        db.flush()

        return (
            agent_run,
            final_review_step,
            await_final_review_step,
        )

    @staticmethod
    def _required_analysis_text(
        value: object,
        *,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f'generated_analysis.{field_name} '
                'must be a string',
            )

        normalized = value.strip()
        if not normalized:
            raise ValueError(
                f'generated_analysis.{field_name} '
                'must be nonblank',
            )
        return normalized

    @staticmethod
    def _optional_analysis_text(
        value: object,
        *,
        field_name: str,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(
                f'generated_analysis.{field_name} '
                'must be a string or null',
            )

        normalized = value.strip()
        return normalized or None

    @classmethod
    def _validated_generated_analysis(
        cls,
        value: object,
    ) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError(
                'Agent state must contain generated_analysis '
                'as a mapping',
            )

        payload = dict(value)
        if frozenset(payload) != GENERATED_ANALYSIS_FIELDS:
            raise ValueError(
                'generated_analysis fields do not match '
                'the frozen persistence contract',
            )

        generation_version = cls._required_analysis_text(
            payload['generation_version'],
            field_name='generation_version',
        )
        if (
            generation_version
            != 'agent_analysis_generation_v0.1'
        ):
            raise ValueError(
                'generated_analysis has an unsupported '
                'generation_version',
            )

        analysis_type = cls._required_analysis_text(
            payload['analysis_type'],
            field_name='analysis_type',
        )
        if analysis_type != 'issue_summarizer':
            raise ValueError(
                'generated_analysis has an unsupported '
                'analysis_type',
            )

        provider = cls._required_analysis_text(
            payload['provider'],
            field_name='provider',
        )
        if provider not in CONTROLLED_ANALYSIS_PROVIDERS:
            raise ValueError(
                'generated_analysis has an unsupported '
                'provider',
            )

        risk_level = cls._required_analysis_text(
            payload['risk_level'],
            field_name='risk_level',
        )
        if risk_level not in CONTROLLED_RISK_LEVELS:
            raise ValueError(
                'generated_analysis has an unsupported '
                'risk_level',
            )

        retrieval_status = cls._required_analysis_text(
            payload['retrieval_status'],
            field_name='retrieval_status',
        )
        if (
            retrieval_status
            not in CONTROLLED_RETRIEVAL_STATUSES
        ):
            raise ValueError(
                'generated_analysis has an unsupported '
                'retrieval_status',
            )

        recommended_actions = payload[
            'recommended_actions'
        ]
        if not isinstance(
            recommended_actions,
            list,
        ):
            raise ValueError(
                'generated_analysis.recommended_actions '
                'must be a list',
            )
        normalized_actions = [
            cls._required_analysis_text(
                item,
                field_name=(
                    'recommended_actions item'
                ),
            )
            for item in recommended_actions
        ]
        if not normalized_actions:
            raise ValueError(
                'generated_analysis.recommended_actions '
                'must not be empty',
            )

        raw_citations = payload[
            'knowledge_citations'
        ]
        if not isinstance(raw_citations, list):
            raise ValueError(
                'generated_analysis.knowledge_citations '
                'must be a list',
            )
        citations: list[dict[str, object]] = []

        for index, item in enumerate(raw_citations):
            if not isinstance(item, Mapping):
                raise ValueError(
                    'generated_analysis.knowledge_citations '
                    f'item {index} must be a mapping',
                )
            citation = dict(item)
            if (
                frozenset(citation)
                != KNOWLEDGE_CITATION_FIELDS
            ):
                raise ValueError(
                    'knowledge citation fields do not match '
                    'the frozen persistence contract',
                )
            citations.append(citation)

        supplemental_count = payload[
            'supplemental_evidence_count'
        ]
        if (
            type(supplemental_count) is not int
            or supplemental_count < 0
        ):
            raise ValueError(
                'generated_analysis.'
                'supplemental_evidence_count must be '
                'a nonnegative integer',
            )

        normalized = {
            'generation_version': generation_version,
            'analysis_type': analysis_type,
            'provider': provider,
            'model_name': cls._optional_analysis_text(
                payload['model_name'],
                field_name='model_name',
            ),
            'prompt_version': (
                cls._optional_analysis_text(
                    payload['prompt_version'],
                    field_name='prompt_version',
                )
            ),
            'provider_fallback_reason': (
                cls._optional_analysis_text(
                    payload[
                        'provider_fallback_reason'
                    ],
                    field_name=(
                        'provider_fallback_reason'
                    ),
                )
            ),
            'issue_summary': (
                cls._required_analysis_text(
                    payload['issue_summary'],
                    field_name='issue_summary',
                )
            ),
            'possible_root_cause': (
                cls._required_analysis_text(
                    payload[
                        'possible_root_cause'
                    ],
                    field_name='possible_root_cause',
                )
            ),
            'recommended_actions': (
                normalized_actions
            ),
            'customer_update_draft': (
                cls._required_analysis_text(
                    payload[
                        'customer_update_draft'
                    ],
                    field_name=(
                        'customer_update_draft'
                    ),
                )
            ),
            'risk_level': risk_level,
            'project_impact': (
                cls._required_analysis_text(
                    payload['project_impact'],
                    field_name='project_impact',
                )
            ),
            'retrieval_status': retrieval_status,
            'retrieval_query': (
                cls._optional_analysis_text(
                    payload['retrieval_query'],
                    field_name='retrieval_query',
                )
            ),
            'knowledge_citations': citations,
            'retrieval_error_code': (
                cls._optional_analysis_text(
                    payload[
                        'retrieval_error_code'
                    ],
                    field_name='retrieval_error_code',
                )
            ),
            'supplemental_evidence_count': (
                supplemental_count
            ),
        }
        return normalized

    @staticmethod
    def _json_text(
        value: object,
        *,
        field_name: str,
    ) -> str:
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f'generated_analysis.{field_name} '
                'must be JSON serializable',
            ) from exc

    def finalize_waiting_review_run_and_append_step(
        self,
        db: Session,
        *,
        analysis_id: int,
        feedback_status: str,
        feedback_note: str | None = None,
        edited_output: str | None = None,
        completed_at: datetime | None = None,
    ) -> tuple[AgentRun, AIAnalysisLog, AgentStep]:
        final_feedback_statuses = {
            'accepted',
            'rejected',
            'edited_and_accepted',
        }

        if feedback_status not in final_feedback_statuses:
            raise ValueError(
                'Unsupported final feedback status: '
                f'{feedback_status}',
            )

        normalized_feedback_note = (
            feedback_note.strip()
            if isinstance(feedback_note, str)
            else None
        )
        if normalized_feedback_note == '':
            normalized_feedback_note = None

        normalized_edited_output = (
            edited_output.strip()
            if isinstance(edited_output, str)
            else None
        )

        if (
            feedback_status == 'edited_and_accepted'
            and not normalized_edited_output
        ):
            raise ValueError(
                'edited_output is required for '
                'edited_and_accepted',
            )

        agent_run = self.lock_run_by_analysis_id(
            db,
            analysis_id,
        )
        if agent_run is None:
            raise LookupError(
                'Agent run not found for analysis: '
                f'{analysis_id}',
            )

        if agent_run.run_status != 'waiting_for_final_review':
            raise ValueError(
                'Agent run cannot finalize review from status: '
                f'{agent_run.run_status}',
            )

        if agent_run.current_node != 'await_final_review':
            raise ValueError(
                'Agent run has unexpected final review node: '
                f'{agent_run.current_node}',
            )

        if agent_run.waiting_since is None:
            raise ValueError(
                'Waiting Agent run must have waiting_since',
            )

        if agent_run.resume_node != 'finalize_run':
            raise ValueError(
                'Agent run has unexpected final review '
                f'resume_node: {agent_run.resume_node}',
            )

        if agent_run.step_count <= 0:
            raise ValueError(
                'Waiting Agent run must have an interrupted step',
            )

        analysis = self.lock_analysis_by_id(
            db,
            analysis_id,
        )
        if analysis is None:
            raise LookupError(
                f'AI analysis log not found: {analysis_id}',
            )

        if analysis.id != agent_run.analysis_log_id:
            raise ValueError(
                'Agent run analysis link changed while locked',
            )

        if analysis.issue_id != agent_run.issue_id:
            raise ValueError(
                'Agent run and AI analysis issue mismatch',
            )

        if analysis.feedback_status != 'pending':
            raise ValueError(
                'AI analysis feedback has already been '
                f'finalized: {analysis.feedback_status}',
            )

        interrupted_step = self.lock_step_by_run_and_index(
            db,
            agent_run_id=agent_run.id,
            step_index=agent_run.step_count,
        )
        if interrupted_step is None:
            raise LookupError(
                'Final review Agent step not found: '
                f'run_id={agent_run.run_id}, '
                f'step_index={agent_run.step_count}',
            )

        if interrupted_step.node_name != 'await_final_review':
            raise ValueError(
                'Latest Agent step is not await_final_review: '
                f'{interrupted_step.node_name}',
            )

        if interrupted_step.step_status != 'interrupted':
            raise ValueError(
                'Final review Agent step must be interrupted: '
                f'{interrupted_step.step_status}',
            )

        effective_completed_at = (
            completed_at or datetime.utcnow()
        )

        if (
            agent_run.started_at is not None
            and effective_completed_at < agent_run.started_at
        ):
            raise ValueError(
                'Agent run completion cannot precede start time',
            )

        if effective_completed_at < agent_run.waiting_since:
            raise ValueError(
                'Agent run completion cannot precede '
                'final review waiting time',
            )

        previous_state = dict(agent_run.state_json or {})
        final_state = dict(previous_state)
        final_state['analysis_log_id'] = analysis.id
        final_state['pending_approval'] = False
        final_state['final_status'] = feedback_status

        analysis.feedback_status = feedback_status
        analysis.feedback_note = normalized_feedback_note
        analysis.edited_output = normalized_edited_output

        next_step_index = agent_run.step_count + 1
        finalized_step = AgentStep(
            agent_run_id=agent_run.id,
            step_index=next_step_index,
            node_name='finalize_run',
            step_status='completed',
            input_state_json=dict(previous_state),
            output_state_json=dict(final_state),
            error_code=None,
            error_message=None,
            started_at=effective_completed_at,
            completed_at=effective_completed_at,
        )

        agent_run.run_status = 'completed'
        agent_run.current_node = 'finalize_run'
        agent_run.state_json = dict(final_state)
        agent_run.waiting_since = None
        agent_run.resume_node = None
        agent_run.error_code = None
        agent_run.error_message = None
        agent_run.completed_at = effective_completed_at
        agent_run.step_count = next_step_index

        db.add(finalized_step)
        db.flush()

        return agent_run, analysis, finalized_step

    def mark_active_run_cancelled(
        self,
        db: Session,
        *,
        run_id: str,
        cancelled_at: datetime | None = None,
    ) -> tuple[
        AgentRun,
        AgentStep | None,
        AgentToolCall | None,
    ]:
        cancellable_statuses = {
            'created',
            'running',
            'generating_analysis',
        }
        inconsistent_step_statuses = {
            'interrupted',
            'cancelled',
        }

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        if agent_run.run_status not in cancellable_statuses:
            raise ValueError(
                'Active Agent run cannot cancel from status: '
                f'{agent_run.run_status}',
            )

        effective_cancelled_at = (
            cancelled_at or datetime.utcnow()
        )

        agent_step: AgentStep | None = None
        tool_call: AgentToolCall | None = None

        if agent_run.step_count > 0:
            agent_step = self.lock_step_by_run_and_index(
                db,
                agent_run_id=agent_run.id,
                step_index=agent_run.step_count,
            )
            if agent_step is None:
                raise LookupError(
                    'Latest Agent step not found: '
                    f'run_id={run_id}, '
                    f'step_index={agent_run.step_count}',
                )

            if (
                agent_step.step_status
                in inconsistent_step_statuses
            ):
                raise ValueError(
                    'Active Agent run has inconsistent '
                    'latest step status: '
                    f'{agent_step.step_status}',
                )

            active_tool_call_indices = list(
                db.scalars(
                    select(
                        AgentToolCall.tool_call_index,
                    )
                    .where(
                        AgentToolCall.agent_step_id
                        == agent_step.id,
                        AgentToolCall.call_status.in_(
                            {
                                'created',
                                'running',
                            }
                        ),
                    )
                    .order_by(
                        AgentToolCall.tool_call_index,
                    )
                ).all()
            )

            if len(active_tool_call_indices) > 1:
                raise ValueError(
                    'Agent step contains multiple active '
                    'tool calls: '
                    f'run_id={run_id}, '
                    f'step_index={agent_step.step_index}',
                )

            if agent_step.step_status == 'completed':
                if active_tool_call_indices:
                    raise ValueError(
                        'Completed Agent step contains an '
                        'active tool call: '
                        f'run_id={run_id}, '
                        f'step_index={agent_step.step_index}',
                    )
            elif agent_step.step_status == 'failed':
                # Recovery cancellation deliberately preserves the failed
                # Step and its error payload as immutable audit evidence. A
                # failed Step must not, however, leave a Tool call active.
                if active_tool_call_indices:
                    raise ValueError(
                        'Failed Agent step contains an '
                        'active tool call: '
                        f'run_id={run_id}, '
                        f'step_index={agent_step.step_index}',
                    )
            elif agent_step.step_status == 'running':
                if active_tool_call_indices:
                    active_tool_call_index = (
                        active_tool_call_indices[0]
                    )
                    tool_call = (
                        self.lock_tool_call_by_step_and_index(
                            db,
                            agent_step_id=agent_step.id,
                            tool_call_index=(
                                active_tool_call_index
                            ),
                        )
                    )
                    if tool_call is None:
                        raise LookupError(
                            'Active Agent tool call not found: '
                            f'run_id={run_id}, '
                            f'step_index='
                            f'{agent_step.step_index}, '
                            f'tool_call_index='
                            f'{active_tool_call_index}',
                        )

                    if tool_call.call_status not in {
                        'created',
                        'running',
                    }:
                        raise ValueError(
                            'Agent tool call cannot be '
                            'cancelled from status: '
                            f'{tool_call.call_status}',
                        )

                    tool_call.call_status = 'cancelled'
                    tool_call.result_json = None
                    tool_call.error_code = None
                    tool_call.error_message = None
                    tool_call.completed_at = (
                        effective_cancelled_at
                    )

                agent_step.step_status = 'cancelled'
                agent_step.error_code = None
                agent_step.error_message = None
                agent_step.completed_at = (
                    effective_cancelled_at
                )

        agent_run.run_status = 'cancelled'
        agent_run.waiting_since = None
        agent_run.resume_node = None
        agent_run.error_code = None
        agent_run.error_message = None
        agent_run.completed_at = effective_cancelled_at

        db.flush()
        return agent_run, agent_step, tool_call
    def mark_waiting_run_cancelled(
        self,
        db: Session,
        *,
        run_id: str,
        cancelled_at: datetime | None = None,
    ) -> AgentRun:
        cancellable_statuses = {
            'waiting_for_triage_confirmation',
            'waiting_for_clarification',
        }

        agent_run = self.lock_run_by_run_id(
            db,
            run_id,
        )
        if agent_run is None:
            raise LookupError(
                f'Agent run not found: {run_id}',
            )

        if agent_run.run_status not in cancellable_statuses:
            raise ValueError(
                'Agent run cannot cancel from status: '
                f'{agent_run.run_status}',
            )

        agent_run.run_status = 'cancelled'
        agent_run.waiting_since = None
        agent_run.resume_node = None
        agent_run.error_code = None
        agent_run.error_message = None
        agent_run.completed_at = (
            cancelled_at or datetime.utcnow()
        )

        db.flush()
        return agent_run
agent_persistence_service = AgentPersistenceService()
