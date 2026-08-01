from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agent_graph.coordinator import AgentGraphStepCoordinator
from app.ai.issue_summarizer import IssueContext
from app.services.agent_issue_context_service import (
    AgentIssueContextService,
)
from app.services.agent_investigation_routing_service import (
    AgentInvestigationRoutingOutcome,
    AgentInvestigationRoutingService,
    NEXT_NODE_EVALUATE_EVIDENCE,
    NEXT_NODE_FAILED,
    NEXT_NODE_LIMIT_EXCEEDED,
    NEXT_NODE_SELECT_TOOL,
)
from app.services.agent_orchestration_service import (
    AgentOrchestrationService,
)
from app.services.agent_clarification_request_service import (
    AGENT_CLARIFICATION_REQUEST_VERSION,
    WAITING_FOR_CLARIFICATION_STATUS,
    AgentClarificationRequest,
    AgentClarificationRequestError,
    AgentClarificationRequestService,
)
from app.services.agent_evidence_evaluation_service import (
    AGENT_EVIDENCE_EVALUATION_VERSION,
    GENERATE_ANALYSIS_NODE,
    LIMIT_EXCEEDED_NODE,
    REQUEST_CLARIFICATION_NODE,
    AgentEvidenceEvaluationDecision,
    AgentEvidenceEvaluationError,
    AgentEvidenceEvaluationService,
)
from app.services.agent_analysis_generation_service import (
    AGENT_ANALYSIS_GENERATION_VERSION,
    AgentAnalysisGenerationError,
    AgentAnalysisGenerationOutcome,
    AgentAnalysisGenerationService,
)
from app.services.agent_guarded_tool_execution_service import (
    AgentGuardedToolExecutionOutcome,
    AgentGuardedToolExecutionService,
)
from app.services.agent_tool_result_state_service import (
    AGENT_TOOL_RESULT_STATE_VERSION,
    AgentToolResultStateError,
    AgentToolResultStateOutcome,
    AgentToolResultStateService,
)
from app.services.agent_tool_selection_service import (
    AGENT_TOOL_SELECTION_VERSION,
    AgentToolSelectionDecision,
    AgentToolSelectionError,
    AgentToolSelectionService,
)
from app.services.agent_triage_service import (
    AgentTriageExhaustedError,
    AgentTriageOutcome,
    AgentTriageService,
)


DEFAULT_AGENT_GRAPH_VERSION = "agent_mvp_v0.1"

LOAD_ISSUE_NODE = "load_issue"
TRIAGE_ISSUE_NODE = "triage_issue"
AWAIT_TRIAGE_CONFIRMATION_NODE = (
    "await_triage_confirmation"
)
WAITING_FOR_TRIAGE_CONFIRMATION_STATUS = (
    "waiting_for_triage_confirmation"
)

AGENT_RUNNER_INVESTIGATION_ROUTE_VERSION = (
    "agent_runner_investigation_route_v0.1"
)
ROUTE_INVESTIGATION_NODE = "route_investigation"
SELECT_TOOL_NODE = NEXT_NODE_SELECT_TOOL
EVALUATE_EVIDENCE_NODE = NEXT_NODE_EVALUATE_EVIDENCE

AGENT_RUNNER_SELECT_TOOL_VERSION = (
    "agent_runner_select_tool_v0.1"
)
EXECUTE_TOOL_NODE = "execute_tool"

AGENT_RUNNER_EXECUTE_TOOL_VERSION = (
    "agent_runner_execute_tool_v0.1"
)

AGENT_RUNNER_EVALUATE_EVIDENCE_VERSION = (
    "agent_runner_evaluate_evidence_v0.1"
)

AGENT_RUNNER_GENERATE_ANALYSIS_VERSION = (
    "agent_runner_generate_analysis_v0.1"
)
PERSIST_ANALYSIS_NODE = "persist_analysis"

AGENT_RUNNER_PERSIST_ANALYSIS_VERSION = (
    "agent_runner_persist_analysis_v0.1"
)
FINAL_REVIEW_NODE = "final_review"
GENERATING_ANALYSIS_STATUS = "generating_analysis"

AGENT_RUNNER_FINAL_REVIEW_VERSION = (
    "agent_runner_final_review_v0.1"
)
AWAIT_FINAL_REVIEW_NODE = "await_final_review"
WAITING_FOR_FINAL_REVIEW_STATUS = (
    "waiting_for_final_review"
)
FINALIZE_RUN_NODE = "finalize_run"

AGENT_RUNNER_REQUEST_CLARIFICATION_VERSION = (
    "agent_runner_request_clarification_v0.1"
)

AGENT_RUNNER_BOUNDED_LOOP_VERSION = (
    "agent_runner_bounded_loop_v0.1"
)
DEFAULT_MAX_TRANSITIONS_PER_CALL = 16

RUNNING_RUN_STATUS = "running"
WAITING_RUN_STATUSES = frozenset(
    {
        WAITING_FOR_TRIAGE_CONFIRMATION_STATUS,
        WAITING_FOR_CLARIFICATION_STATUS,
        WAITING_FOR_FINAL_REVIEW_STATUS,
    }
)
BOUNDED_LOOP_ACTIVE_RUN_STATUSES = frozenset(
    {
        RUNNING_RUN_STATUS,
        GENERATING_ANALYSIS_STATUS,
    }
)
UNIMPLEMENTED_RUN_STATUSES = frozenset()
TERMINAL_RUN_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "cancelled",
        LIMIT_EXCEEDED_NODE,
    }
)
BOUNDED_LOOP_SUPPORTED_NODES = frozenset(
    {
        ROUTE_INVESTIGATION_NODE,
        SELECT_TOOL_NODE,
        EXECUTE_TOOL_NODE,
        EVALUATE_EVIDENCE_NODE,
        GENERATE_ANALYSIS_NODE,
        PERSIST_ANALYSIS_NODE,
        FINAL_REVIEW_NODE,
        REQUEST_CLARIFICATION_NODE,
    }
)
BOUNDED_LOOP_TOOL_BUDGET_NODES = frozenset(
    {
        SELECT_TOOL_NODE,
        EXECUTE_TOOL_NODE,
    }
)
BOUNDED_LOOP_UNIMPLEMENTED_NODES = frozenset(
    {
        FINALIZE_RUN_NODE,
    }
)

BOUNDED_LOOP_STOP_WAITING = "waiting"
BOUNDED_LOOP_STOP_TERMINAL = "terminal"
BOUNDED_LOOP_STOP_UNIMPLEMENTED = (
    "unimplemented_boundary"
)
BOUNDED_LOOP_STOP_TRANSITION_CAP = (
    "transition_cap"
)


@dataclass(frozen=True)
class AgentRunnerFirstSliceResult:
    """Result of running through the first human wait."""

    agent_run: object
    load_issue_step: object
    triage_issue_step: object
    await_triage_confirmation_step: object
    issue_context: IssueContext
    triage_outcome: AgentTriageOutcome
    state_json: dict[str, object]


@dataclass(frozen=True)
class AgentRunnerInvestigationRouteResult:
    """Result of advancing the route_investigation node."""

    agent_run: object
    route_investigation_step: object
    next_step: object | None
    routing_outcome: AgentInvestigationRoutingOutcome
    state_json: dict[str, object]


@dataclass(frozen=True)
class AgentRunnerSelectToolResult:
    """Result of advancing the select_tool node."""

    agent_run: object
    select_tool_step: object
    execute_tool_step: object
    selection_decision: AgentToolSelectionDecision
    state_json: dict[str, object]


@dataclass(frozen=True)
class AgentRunnerExecuteToolResult:
    """Result of advancing the execute_tool node."""

    agent_run: object
    execute_tool_step: object
    evaluate_evidence_step: object
    guarded_execution_outcome: (
        AgentGuardedToolExecutionOutcome
    )
    result_state_outcome: (
        AgentToolResultStateOutcome
    )
    state_json: dict[str, object]


@dataclass(frozen=True)
class AgentRunnerEvaluateEvidenceResult:
    """Result of advancing the evaluate_evidence node."""

    agent_run: object
    evaluate_evidence_step: object
    next_step: object | None
    evaluation_decision: AgentEvidenceEvaluationDecision
    state_json: dict[str, object]


@dataclass(frozen=True)
class AgentRunnerGenerateAnalysisResult:
    """Result of advancing the generate_analysis node."""

    agent_run: object
    generate_analysis_step: object
    persist_analysis_step: object
    generation_outcome: AgentAnalysisGenerationOutcome
    state_json: dict[str, object]


@dataclass(frozen=True)
class AgentRunnerPersistAnalysisResult:
    """Result of advancing the persist_analysis node."""

    agent_run: object
    persist_analysis_step: object
    analysis_log: object
    final_review_step: object
    state_json: dict[str, object]


@dataclass(frozen=True)
class AgentRunnerFinalReviewResult:
    """Result of entering the final human review wait."""

    agent_run: object
    final_review_step: object
    await_final_review_step: object
    state_json: dict[str, object]


@dataclass(frozen=True)
class AgentRunnerRequestClarificationResult:
    """Result of interrupting for clarification."""

    agent_run: object
    request_clarification_step: object
    clarification_request: AgentClarificationRequest
    state_json: dict[str, object]


@dataclass(frozen=True)
class AgentRunnerBoundedLoopResult:
    """Result of bounded automatic investigation progress."""

    agent_run: object
    current_step: object | None
    transition_count: int
    stop_reason: str
    visited_nodes: tuple[str, ...]
    loop_version: str = AGENT_RUNNER_BOUNDED_LOOP_VERSION

class AgentRunnerBoundedLoopError(RuntimeError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        normalized_error_code = error_code.strip()
        normalized_message = message.strip()

        if not normalized_error_code:
            raise ValueError(
                "Bounded loop error_code must be nonblank"
            )
        if not normalized_message:
            raise ValueError(
                "Bounded loop message must be nonblank"
            )

        super().__init__(normalized_message)
        self.error_code = normalized_error_code


class AgentRunnerInvestigationRouteBlockedError(
    RuntimeError
):
    def __init__(
        self,
        *,
        routing_outcome: AgentInvestigationRoutingOutcome,
    ) -> None:
        if routing_outcome.next_node != NEXT_NODE_FAILED:
            raise ValueError(
                "Blocked Runner route requires a failed outcome"
            )
        super().__init__(routing_outcome.reason)
        self.error_code = routing_outcome.error_code
        self.routing_outcome = routing_outcome


class AgentRunnerService:
    """Runs the first Agent MVP execution slice."""

    def __init__(
        self,
        *,
        graph_step_coordinator: (
            AgentGraphStepCoordinator | None
        ) = None,
        orchestration_service: (
            AgentOrchestrationService | None
        ) = None,
        issue_context_service: (
            AgentIssueContextService | None
        ) = None,
        triage_service: (
            AgentTriageService | None
        ) = None,
        investigation_routing_service: (
            AgentInvestigationRoutingService | None
        ) = None,
        tool_selection_service: (
            AgentToolSelectionService | None
        ) = None,
        guarded_tool_execution_service: (
            AgentGuardedToolExecutionService | None
        ) = None,
        tool_result_state_service: (
            AgentToolResultStateService | None
        ) = None,
        evidence_evaluation_service: (
            AgentEvidenceEvaluationService | None
        ) = None,
        analysis_generation_service: (
            AgentAnalysisGenerationService | None
        ) = None,
        clarification_request_service: (
            AgentClarificationRequestService | None
        ) = None,
    ) -> None:
        if (
            graph_step_coordinator is not None
            and not isinstance(
                graph_step_coordinator,
                AgentGraphStepCoordinator,
            )
        ):
            raise TypeError(
                "graph_step_coordinator must be an "
                "AgentGraphStepCoordinator or None"
            )
        self._graph_step_coordinator = (
            graph_step_coordinator
        )

        self._orchestration_service = (
            orchestration_service
            or AgentOrchestrationService()
        )
        self._issue_context_service = (
            issue_context_service
            or AgentIssueContextService()
        )
        self._triage_service = (
            triage_service
            or AgentTriageService()
        )
        self._investigation_routing_service = (
            investigation_routing_service
            or AgentInvestigationRoutingService()
        )
        self._tool_selection_service = (
            tool_selection_service
            or AgentToolSelectionService()
        )
        self._guarded_tool_execution_service = (
            guarded_tool_execution_service
            or AgentGuardedToolExecutionService()
        )
        self._tool_result_state_service = (
            tool_result_state_service
            or AgentToolResultStateService()
        )
        self._evidence_evaluation_service = (
            evidence_evaluation_service
            or AgentEvidenceEvaluationService()
        )
        self._analysis_generation_service = (
            analysis_generation_service
            or AgentAnalysisGenerationService()
        )
        self._clarification_request_service = (
            clarification_request_service
            or AgentClarificationRequestService()
        )

    def start_and_run_to_triage_wait(
        self,
        db: Session,
        *,
        run_id: str,
        issue_id: int,
        graph_version: str = (
            DEFAULT_AGENT_GRAPH_VERSION
        ),
        initial_state: (
            dict[str, object] | None
        ) = None,
    ) -> AgentRunnerFirstSliceResult:
        state_json = dict(initial_state or {})
        state_json["issue_id"] = issue_id
        state_json["graph_version"] = graph_version

        agent_run = (
            self._orchestration_service.start_run(
                db,
                run_id=run_id,
                issue_id=issue_id,
                graph_version=graph_version,
                initial_node=LOAD_ISSUE_NODE,
                initial_state=dict(state_json),
            )
        )

        load_issue_step = (
            self._orchestration_service.start_step(
                db,
                run_id=run_id,
                node_name=LOAD_ISSUE_NODE,
                input_state_json=dict(state_json),
            )
        )

        load_step_index = self._step_index(
            load_issue_step
        )

        try:
            issue_context = (
                self._issue_context_service
                .load_issue_context(
                    db,
                    issue_id=issue_id,
                )
            )
            serialized_context = (
                self._issue_context_service
                .serialize_issue_context(
                    issue_context
                )
            )

            load_output = {
                "issue_context": serialized_context,
            }
            state_after_load = {
                **state_json,
                **load_output,
            }

            (
                agent_run,
                load_issue_step,
                triage_issue_step,
            ) = (
                self._orchestration_service
                .complete_step_and_advance_run(
                    db,
                    run_id=run_id,
                    step_index=load_step_index,
                    next_node=TRIAGE_ISSUE_NODE,
                    state_json=dict(
                        state_after_load
                    ),
                    output_state_json=dict(
                        load_output
                    ),
                )
            )
        except Exception as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=load_step_index,
                node_name=LOAD_ISSUE_NODE,
                error_code=(
                    "issue_not_found"
                    if isinstance(exc, LookupError)
                    else "load_issue_failed"
                ),
                error_message=(
                    str(exc)
                    if isinstance(exc, LookupError)
                    else (
                        f"{type(exc).__name__} occurred "
                        "while loading Issue context"
                    )
                ),
            )
            raise

        triage_step_index = self._step_index(
            triage_issue_step
        )

        try:
            triage_outcome = (
                self._triage_service.triage(
                    issue_context
                )
            )
            triage_state_update = (
                triage_outcome.to_state_update()
            )
            state_after_triage = {
                **state_after_load,
                **triage_state_update,
            }

            (
                agent_run,
                triage_issue_step,
                await_triage_confirmation_step,
            ) = (
                self._orchestration_service
                .complete_step_and_advance_run(
                    db,
                    run_id=run_id,
                    step_index=triage_step_index,
                    next_node=(
                        AWAIT_TRIAGE_CONFIRMATION_NODE
                    ),
                    state_json=dict(
                        state_after_triage
                    ),
                    output_state_json=dict(
                        triage_state_update
                    ),
                )
            )
        except AgentTriageExhaustedError as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=triage_step_index,
                node_name=TRIAGE_ISSUE_NODE,
                error_code=exc.code,
                error_message=exc.detail,
                output_state_json={
                    "triage_attempt": exc.attempts,
                    "max_retries": exc.max_retries,
                },
            )
            raise
        except Exception as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=triage_step_index,
                node_name=TRIAGE_ISSUE_NODE,
                error_code="triage_issue_failed",
                error_message=(
                    f"{type(exc).__name__} occurred "
                    "while generating triage"
                ),
            )
            raise

        await_step_index = self._step_index(
            await_triage_confirmation_step
        )

        wait_output = {
            "triage_suggestion": (
                triage_state_update[
                    "triage_suggestion"
                ]
            ),
            "triage_attempt": (
                triage_state_update[
                    "triage_attempt"
                ]
            ),
            "max_retries": (
                triage_state_update[
                    "max_retries"
                ]
            ),
        }

        (
            agent_run,
            await_triage_confirmation_step,
        ) = (
            self._orchestration_service
            .interrupt_step_and_wait_run(
                db,
                run_id=run_id,
                step_index=await_step_index,
                waiting_status=(
                    WAITING_FOR_TRIAGE_CONFIRMATION_STATUS
                ),
                state_json=dict(
                    state_after_triage
                ),
                output_state_json=wait_output,
            )
        )

        return AgentRunnerFirstSliceResult(
            agent_run=agent_run,
            load_issue_step=load_issue_step,
            triage_issue_step=triage_issue_step,
            await_triage_confirmation_step=(
                await_triage_confirmation_step
            ),
            issue_context=issue_context,
            triage_outcome=triage_outcome,
            state_json=dict(
                state_after_triage
            ),
        )

    def advance_investigation_route(
        self,
        db: Session,
        *,
        agent_run: object,
        route_investigation_step: object,
    ) -> AgentRunnerInvestigationRouteResult:
        run_id = getattr(agent_run, "run_id", None)
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise ValueError(
                "Agent Run must expose a normalized run_id"
            )

        run_status = getattr(
            agent_run,
            "run_status",
            None,
        )
        if run_status != "running":
            raise ValueError(
                "Agent Run cannot route investigation "
                f"from status: {run_status}"
            )

        current_node = getattr(
            agent_run,
            "current_node",
            None,
        )
        if current_node != ROUTE_INVESTIGATION_NODE:
            raise ValueError(
                "Agent Run has unexpected current node: "
                f"{current_node}"
            )

        step_count = getattr(
            agent_run,
            "step_count",
            None,
        )
        if (
            type(step_count) is not int
            or step_count < 1
        ):
            raise ValueError(
                "Agent Run must expose a positive "
                "integer step_count"
            )

        tool_call_count = getattr(
            agent_run,
            "tool_call_count",
            None,
        )
        if (
            type(tool_call_count) is not int
            or tool_call_count < 0
        ):
            raise ValueError(
                "Agent Run must expose a nonnegative "
                "integer tool_call_count"
            )

        persisted_state = getattr(
            agent_run,
            "state_json",
            None,
        )
        if not isinstance(persisted_state, Mapping):
            raise ValueError(
                "Agent Run state_json must be a mapping"
            )
        state_json = dict(persisted_state)

        route_step_index = self._step_index(
            route_investigation_step
        )
        if route_step_index != step_count:
            raise ValueError(
                "route_investigation must be the latest Step"
            )

        route_step_node = getattr(
            route_investigation_step,
            "node_name",
            None,
        )
        if route_step_node != ROUTE_INVESTIGATION_NODE:
            raise ValueError(
                "Agent Step has unexpected route node: "
                f"{route_step_node}"
            )

        route_step_status = getattr(
            route_investigation_step,
            "step_status",
            None,
        )
        if route_step_status != "running":
            raise ValueError(
                "route_investigation Step must be running"
            )

        route_input_state = getattr(
            route_investigation_step,
            "input_state_json",
            None,
        )
        if not isinstance(route_input_state, Mapping):
            raise ValueError(
                "route_investigation Step input state "
                "must be a mapping"
            )
        if dict(route_input_state) != state_json:
            raise ValueError(
                "route_investigation Step state snapshot "
                "does not match Agent Run state"
            )

        routing_outcome = (
            self._investigation_routing_service.route(
                state_json,
                step_count=step_count,
                tool_call_count=tool_call_count,
            )
        )

        if routing_outcome.next_node == NEXT_NODE_FAILED:
            raise AgentRunnerInvestigationRouteBlockedError(
                routing_outcome=routing_outcome
            )

        state_after_route = {
            **state_json,
            **routing_outcome.to_state_update(),
        }
        route_output = {
            "routing_version": (
                routing_outcome.routing_version
            ),
            "next_node": routing_outcome.next_node,
            "reason": routing_outcome.reason,
            "error_code": routing_outcome.error_code,
            "max_steps": routing_outcome.max_steps,
            "max_tool_calls": (
                routing_outcome.max_tool_calls
            ),
        }

        if (
            routing_outcome.next_node
            == NEXT_NODE_LIMIT_EXCEEDED
        ):
            (
                limited_run,
                completed_route_step,
            ) = (
                self._orchestration_service
                .complete_step_and_limit_run(
                    db,
                    run_id=run_id,
                    step_index=route_step_index,
                    error_code=(
                        routing_outcome.error_code
                    ),
                    error_message=(
                        routing_outcome.reason
                    ),
                    state_json=dict(state_after_route),
                    output_state_json=dict(route_output),
                )
            )

            return AgentRunnerInvestigationRouteResult(
                agent_run=limited_run,
                route_investigation_step=(
                    completed_route_step
                ),
                next_step=None,
                routing_outcome=routing_outcome,
                state_json=dict(state_after_route),
            )

        if routing_outcome.next_node not in {
            SELECT_TOOL_NODE,
            EVALUATE_EVIDENCE_NODE,
        }:
            raise RuntimeError(
                "Investigation routing returned an "
                "unsupported executable node"
            )

        (
            advanced_run,
            completed_route_step,
            next_step,
        ) = (
            self._orchestration_service
            .complete_step_and_advance_run(
                db,
                run_id=run_id,
                step_index=route_step_index,
                next_node=routing_outcome.next_node,
                state_json=dict(state_after_route),
                output_state_json=dict(route_output),
            )
        )

        return AgentRunnerInvestigationRouteResult(
            agent_run=advanced_run,
            route_investigation_step=(
                completed_route_step
            ),
            next_step=next_step,
            routing_outcome=routing_outcome,
            state_json=dict(state_after_route),
        )
    def advance_select_tool(
        self,
        db: Session,
        *,
        agent_run: object,
        select_tool_step: object,
    ) -> AgentRunnerSelectToolResult:
        run_id = getattr(agent_run, "run_id", None)
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise ValueError(
                "Agent Run must expose a normalized run_id"
            )

        run_status = getattr(
            agent_run,
            "run_status",
            None,
        )
        if run_status != "running":
            raise ValueError(
                "Agent Run cannot select a Tool "
                f"from status: {run_status}"
            )

        current_node = getattr(
            agent_run,
            "current_node",
            None,
        )
        if current_node != SELECT_TOOL_NODE:
            raise ValueError(
                "Agent Run has unexpected current node: "
                f"{current_node}"
            )

        step_count = getattr(
            agent_run,
            "step_count",
            None,
        )
        if (
            type(step_count) is not int
            or step_count < 1
        ):
            raise ValueError(
                "Agent Run must expose a positive "
                "integer step_count"
            )

        persisted_state = getattr(
            agent_run,
            "state_json",
            None,
        )
        if not isinstance(persisted_state, Mapping):
            raise ValueError(
                "Agent Run state_json must be a mapping"
            )
        state_json = dict(persisted_state)

        select_step_index = self._step_index(
            select_tool_step
        )
        if select_step_index != step_count:
            raise ValueError(
                "select_tool must be the latest Step"
            )

        select_step_node = getattr(
            select_tool_step,
            "node_name",
            None,
        )
        if select_step_node != SELECT_TOOL_NODE:
            raise ValueError(
                "Agent Step has unexpected select node: "
                f"{select_step_node}"
            )

        select_step_status = getattr(
            select_tool_step,
            "step_status",
            None,
        )
        if select_step_status != "running":
            raise ValueError(
                "select_tool Step must be running"
            )

        select_input_state = getattr(
            select_tool_step,
            "input_state_json",
            None,
        )
        if not isinstance(select_input_state, Mapping):
            raise ValueError(
                "select_tool Step input state "
                "must be a mapping"
            )
        if dict(select_input_state) != state_json:
            raise ValueError(
                "select_tool Step state snapshot "
                "does not match Agent Run state"
            )

        if state_json.get("selected_tool") is not None:
            raise ValueError(
                "Agent state already contains selected_tool"
            )

        try:
            selection_decision = (
                self._tool_selection_service.select(
                    state_json
                )
            )
            if not isinstance(
                selection_decision,
                AgentToolSelectionDecision,
            ):
                raise TypeError(
                    "Tool Selection Service returned "
                    "an invalid decision type"
                )

            selection_update = (
                selection_decision.to_state_update()
            )
            state_after_selection = {
                **state_json,
                **selection_update,
            }

            (
                advanced_run,
                completed_select_step,
                execute_tool_step,
            ) = (
                self._orchestration_service
                .complete_step_and_advance_run(
                    db,
                    run_id=run_id,
                    step_index=select_step_index,
                    next_node=EXECUTE_TOOL_NODE,
                    state_json=dict(
                        state_after_selection
                    ),
                    output_state_json=dict(
                        selection_update
                    ),
                )
            )
        except AgentToolSelectionError as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=select_step_index,
                node_name=SELECT_TOOL_NODE,
                error_code=exc.error_code,
                error_message=str(exc),
                output_state_json={
                    "selection_version": (
                        AGENT_TOOL_SELECTION_VERSION
                    ),
                    "error_code": exc.error_code,
                },
            )
            raise
        except Exception as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=select_step_index,
                node_name=SELECT_TOOL_NODE,
                error_code="select_tool_failed",
                error_message=(
                    f"{type(exc).__name__} occurred "
                    "while selecting an Agent Tool"
                ),
                output_state_json={
                    "selection_version": (
                        AGENT_TOOL_SELECTION_VERSION
                    ),
                    "error_code": "select_tool_failed",
                },
            )
            raise

        return AgentRunnerSelectToolResult(
            agent_run=advanced_run,
            select_tool_step=completed_select_step,
            execute_tool_step=execute_tool_step,
            selection_decision=selection_decision,
            state_json=dict(state_after_selection),
        )
    def advance_execute_tool(
        self,
        db: Session,
        *,
        agent_run: object,
        execute_tool_step: object,
    ) -> AgentRunnerExecuteToolResult:
        run_id = getattr(agent_run, "run_id", None)
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise ValueError(
                "Agent Run must expose a normalized run_id"
            )

        run_status = getattr(
            agent_run,
            "run_status",
            None,
        )
        if run_status != "running":
            raise ValueError(
                "Agent Run cannot execute a Tool "
                f"from status: {run_status}"
            )

        current_node = getattr(
            agent_run,
            "current_node",
            None,
        )
        if current_node != EXECUTE_TOOL_NODE:
            raise ValueError(
                "Agent Run has unexpected current node: "
                f"{current_node}"
            )

        step_count = getattr(
            agent_run,
            "step_count",
            None,
        )
        if (
            type(step_count) is not int
            or step_count < 1
        ):
            raise ValueError(
                "Agent Run must expose a positive "
                "integer step_count"
            )

        persisted_state = getattr(
            agent_run,
            "state_json",
            None,
        )
        if not isinstance(persisted_state, Mapping):
            raise ValueError(
                "Agent Run state_json must be a mapping"
            )
        state_json = dict(persisted_state)

        execute_step_index = self._step_index(
            execute_tool_step
        )
        if execute_step_index != step_count:
            raise ValueError(
                "execute_tool must be the latest Step"
            )

        execute_step_node = getattr(
            execute_tool_step,
            "node_name",
            None,
        )
        if execute_step_node != EXECUTE_TOOL_NODE:
            raise ValueError(
                "Agent Step has unexpected execute node: "
                f"{execute_step_node}"
            )

        execute_step_status = getattr(
            execute_tool_step,
            "step_status",
            None,
        )
        if execute_step_status != "running":
            raise ValueError(
                "execute_tool Step must be running"
            )

        execute_input_state = getattr(
            execute_tool_step,
            "input_state_json",
            None,
        )
        if not isinstance(execute_input_state, Mapping):
            raise ValueError(
                "execute_tool Step input state "
                "must be a mapping"
            )
        if dict(execute_input_state) != state_json:
            raise ValueError(
                "execute_tool Step state snapshot "
                "does not match Agent Run state"
            )

        selected_tool = state_json.get(
            "selected_tool"
        )
        if not isinstance(selected_tool, Mapping):
            raise ValueError(
                "Agent state must contain selected_tool"
            )

        required_selected_fields = {
            "selection_version",
            "tool_name",
            "tool_version",
            "arguments",
            "call_identity",
            "confidence",
            "reason",
        }
        if set(selected_tool.keys()) != (
            required_selected_fields
        ):
            raise ValueError(
                "selected_tool fields do not match "
                "the frozen contract"
            )

        selection_version = selected_tool.get(
            "selection_version"
        )
        if (
            selection_version
            != AGENT_TOOL_SELECTION_VERSION
        ):
            raise ValueError(
                "selected_tool selection_version "
                "is unsupported"
            )

        tool_name = selected_tool.get(
            "tool_name"
        )
        if (
            not isinstance(tool_name, str)
            or not tool_name.strip()
            or tool_name != tool_name.strip()
        ):
            raise ValueError(
                "selected_tool tool_name must be "
                "a normalized nonblank string"
            )

        tool_version = selected_tool.get(
            "tool_version"
        )
        if (
            not isinstance(tool_version, str)
            or not tool_version.strip()
            or tool_version != tool_version.strip()
        ):
            raise ValueError(
                "selected_tool tool_version must be "
                "a normalized nonblank string"
            )

        call_identity = selected_tool.get(
            "call_identity"
        )
        expected_identity_prefix = (
            f"{tool_name}:"
        )
        if (
            not isinstance(call_identity, str)
            or not call_identity.startswith(
                expected_identity_prefix
            )
            or len(
                call_identity[
                    len(expected_identity_prefix):
                ]
            ) != 64
        ):
            raise ValueError(
                "selected_tool call_identity is invalid"
            )

        arguments = selected_tool.get(
            "arguments"
        )
        if not isinstance(arguments, Mapping):
            raise ValueError(
                "selected_tool arguments must be "
                "a mapping"
            )

        confidence = selected_tool.get(
            "confidence"
        )
        if (
            isinstance(confidence, bool)
            or not isinstance(
                confidence,
                (int, float),
            )
            or confidence < 0
            or confidence > 1
        ):
            raise ValueError(
                "selected_tool confidence must be "
                "between 0 and 1"
            )

        reason = selected_tool.get("reason")
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or reason != reason.strip()
        ):
            raise ValueError(
                "selected_tool reason must be "
                "a normalized nonblank string"
            )

        max_tool_calls = state_json.get(
            "max_tool_calls"
        )
        if (
            type(max_tool_calls) is not int
            or max_tool_calls < 1
        ):
            raise ValueError(
                "Agent state max_tool_calls must be "
                "a positive integer"
            )

        try:
            guarded_execution_outcome = (
                self._guarded_tool_execution_service
                .execute_once(
                    db,
                    run_id=run_id,
                    step_index=execute_step_index,
                    tool_name=tool_name,
                    arguments=dict(arguments),
                    max_tool_calls=max_tool_calls,
                )
            )
            if not isinstance(
                guarded_execution_outcome,
                AgentGuardedToolExecutionOutcome,
            ):
                raise TypeError(
                    "Guarded Tool Execution returned "
                    "an invalid outcome type"
                )

            result_state_outcome = (
                self._tool_result_state_service.apply(
                    state_json,
                    guarded_execution_outcome,
                )
            )
            if not isinstance(
                result_state_outcome,
                AgentToolResultStateOutcome,
            ):
                raise TypeError(
                    "Tool Result State Service returned "
                    "an invalid outcome type"
                )
        except AgentToolResultStateError as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=execute_step_index,
                node_name=EXECUTE_TOOL_NODE,
                error_code=exc.error_code,
                error_message=str(exc),
                output_state_json={
                    "execute_version": (
                        AGENT_RUNNER_EXECUTE_TOOL_VERSION
                    ),
                    "error_code": exc.error_code,
                },
            )
            raise
        except Exception as exc:
            structured_error_code = getattr(
                exc,
                "error_code",
                None,
            )
            if (
                isinstance(
                    structured_error_code,
                    str,
                )
                and structured_error_code.strip()
                and structured_error_code
                == structured_error_code.strip()
            ):
                error_code = structured_error_code
                error_message = str(exc)
            else:
                error_code = "execute_tool_failed"
                error_message = (
                    f"{type(exc).__name__} occurred "
                    "while executing an Agent Tool"
                )

            self._fail_step(
                db,
                run_id=run_id,
                step_index=execute_step_index,
                node_name=EXECUTE_TOOL_NODE,
                error_code=error_code,
                error_message=error_message,
                output_state_json={
                    "execute_version": (
                        AGENT_RUNNER_EXECUTE_TOOL_VERSION
                    ),
                    "error_code": error_code,
                },
            )
            raise

        result_state_update = (
            result_state_outcome.to_state_update()
        )
        state_after_execution = {
            **state_json,
            **result_state_update,
        }

        (
            advanced_run,
            completed_execute_step,
            evaluate_evidence_step,
        ) = (
            self._orchestration_service
            .complete_step_and_advance_run(
                db,
                run_id=run_id,
                step_index=execute_step_index,
                next_node=EVALUATE_EVIDENCE_NODE,
                state_json=dict(
                    state_after_execution
                ),
                output_state_json=(
                    result_state_outcome.as_dict()
                ),
            )
        )

        return AgentRunnerExecuteToolResult(
            agent_run=advanced_run,
            execute_tool_step=completed_execute_step,
            evaluate_evidence_step=(
                evaluate_evidence_step
            ),
            guarded_execution_outcome=(
                guarded_execution_outcome
            ),
            result_state_outcome=(
                result_state_outcome
            ),
            state_json=dict(
                state_after_execution
            ),
        )
    def advance_evaluate_evidence(
        self,
        db: Session,
        *,
        agent_run: object,
        evaluate_evidence_step: object,
    ) -> AgentRunnerEvaluateEvidenceResult:
        run_id = getattr(agent_run, "run_id", None)
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise ValueError(
                "Agent Run must expose a normalized run_id"
            )

        run_status = getattr(
            agent_run,
            "run_status",
            None,
        )
        if run_status != "running":
            raise ValueError(
                "Agent Run cannot evaluate evidence "
                f"from status: {run_status}"
            )

        current_node = getattr(
            agent_run,
            "current_node",
            None,
        )
        if current_node != EVALUATE_EVIDENCE_NODE:
            raise ValueError(
                "Agent Run has unexpected current node: "
                f"{current_node}"
            )

        step_count = getattr(
            agent_run,
            "step_count",
            None,
        )
        if (
            type(step_count) is not int
            or step_count < 1
        ):
            raise ValueError(
                "Agent Run must expose a positive "
                "integer step_count"
            )

        persisted_state = getattr(
            agent_run,
            "state_json",
            None,
        )
        if not isinstance(persisted_state, Mapping):
            raise ValueError(
                "Agent Run state_json must be a mapping"
            )
        state_json = dict(persisted_state)

        evaluate_step_index = self._step_index(
            evaluate_evidence_step
        )
        if evaluate_step_index != step_count:
            raise ValueError(
                "evaluate_evidence must be the latest Step"
            )

        evaluate_step_node = getattr(
            evaluate_evidence_step,
            "node_name",
            None,
        )
        if evaluate_step_node != EVALUATE_EVIDENCE_NODE:
            raise ValueError(
                "Agent Step has unexpected evaluation node: "
                f"{evaluate_step_node}"
            )

        evaluate_step_status = getattr(
            evaluate_evidence_step,
            "step_status",
            None,
        )
        if evaluate_step_status != "running":
            raise ValueError(
                "evaluate_evidence Step must be running"
            )

        evaluate_input_state = getattr(
            evaluate_evidence_step,
            "input_state_json",
            None,
        )
        if not isinstance(evaluate_input_state, Mapping):
            raise ValueError(
                "evaluate_evidence Step input state "
                "must be a mapping"
            )
        if dict(evaluate_input_state) != state_json:
            raise ValueError(
                "evaluate_evidence Step state snapshot "
                "does not match Agent Run state"
            )

        try:
            evaluation_decision = (
                self._evidence_evaluation_service.evaluate(
                    state_json
                )
            )
            if not isinstance(
                evaluation_decision,
                AgentEvidenceEvaluationDecision,
            ):
                raise TypeError(
                    "Evidence Evaluation Service returned "
                    "an invalid decision type"
                )
        except AgentEvidenceEvaluationError as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=evaluate_step_index,
                node_name=EVALUATE_EVIDENCE_NODE,
                error_code=exc.error_code,
                error_message=str(exc),
                output_state_json={
                    "evaluation_version": (
                        AGENT_EVIDENCE_EVALUATION_VERSION
                    ),
                    "error_code": exc.error_code,
                },
            )
            raise
        except Exception as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=evaluate_step_index,
                node_name=EVALUATE_EVIDENCE_NODE,
                error_code="evaluate_evidence_failed",
                error_message=(
                    f"{type(exc).__name__} occurred "
                    "while evaluating Agent evidence"
                ),
                output_state_json={
                    "evaluation_version": (
                        AGENT_EVIDENCE_EVALUATION_VERSION
                    ),
                    "error_code": (
                        "evaluate_evidence_failed"
                    ),
                },
            )
            raise

        supported_next_nodes = {
            GENERATE_ANALYSIS_NODE,
            SELECT_TOOL_NODE,
            REQUEST_CLARIFICATION_NODE,
            LIMIT_EXCEEDED_NODE,
        }
        if (
            evaluation_decision.next_node
            not in supported_next_nodes
        ):
            raise ValueError(
                "Evidence Evaluation returned an "
                "unsupported next node: "
                f"{evaluation_decision.next_node}"
            )

        evaluation_update = (
            evaluation_decision.to_state_update()
        )
        state_after_evaluation = {
            **state_json,
            **evaluation_update,
        }

        if (
            evaluation_decision.next_node
            == LIMIT_EXCEEDED_NODE
        ):
            (
                limited_run,
                completed_evaluate_step,
            ) = (
                self._orchestration_service
                .complete_step_and_limit_run(
                    db,
                    run_id=run_id,
                    step_index=evaluate_step_index,
                    error_code="max_tool_calls_reached",
                    error_message=(
                        evaluation_decision
                        .evidence_reason
                    ),
                    state_json=dict(
                        state_after_evaluation
                    ),
                    output_state_json=(
                        evaluation_decision.as_dict()
                    ),
                )
            )

            return AgentRunnerEvaluateEvidenceResult(
                agent_run=limited_run,
                evaluate_evidence_step=(
                    completed_evaluate_step
                ),
                next_step=None,
                evaluation_decision=(
                    evaluation_decision
                ),
                state_json=dict(
                    state_after_evaluation
                ),
            )

        (
            advanced_run,
            completed_evaluate_step,
            next_step,
        ) = (
            self._orchestration_service
            .complete_step_and_advance_run(
                db,
                run_id=run_id,
                step_index=evaluate_step_index,
                next_node=(
                    evaluation_decision.next_node
                ),
                state_json=dict(
                    state_after_evaluation
                ),
                output_state_json=(
                    evaluation_decision.as_dict()
                ),
            )
        )

        return AgentRunnerEvaluateEvidenceResult(
            agent_run=advanced_run,
            evaluate_evidence_step=(
                completed_evaluate_step
            ),
            next_step=next_step,
            evaluation_decision=(
                evaluation_decision
            ),
            state_json=dict(
                state_after_evaluation
            ),
        )
    def advance_generate_analysis(
        self,
        db: Session,
        *,
        agent_run: object,
        generate_analysis_step: object,
    ) -> AgentRunnerGenerateAnalysisResult:
        run_id = getattr(agent_run, "run_id", None)
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise ValueError(
                "Agent Run must expose a normalized run_id"
            )

        run_status = getattr(
            agent_run,
            "run_status",
            None,
        )
        if run_status != RUNNING_RUN_STATUS:
            raise ValueError(
                "Agent Run cannot generate analysis "
                f"from status: {run_status}"
            )

        current_node = getattr(
            agent_run,
            "current_node",
            None,
        )
        if current_node != GENERATE_ANALYSIS_NODE:
            raise ValueError(
                "Agent Run has unexpected current node: "
                f"{current_node}"
            )

        step_count = getattr(
            agent_run,
            "step_count",
            None,
        )
        if (
            type(step_count) is not int
            or step_count < 1
        ):
            raise ValueError(
                "Agent Run must expose a positive "
                "integer step_count"
            )

        persisted_state = getattr(
            agent_run,
            "state_json",
            None,
        )
        if not isinstance(persisted_state, Mapping):
            raise ValueError(
                "Agent Run state_json must be a mapping"
            )
        state_json = dict(persisted_state)

        generate_step_index = self._step_index(
            generate_analysis_step
        )
        if generate_step_index != step_count:
            raise ValueError(
                "generate_analysis must be the latest Step"
            )

        generate_step_node = getattr(
            generate_analysis_step,
            "node_name",
            None,
        )
        if generate_step_node != GENERATE_ANALYSIS_NODE:
            raise ValueError(
                "Agent Step has unexpected generation node: "
                f"{generate_step_node}"
            )

        generate_step_status = getattr(
            generate_analysis_step,
            "step_status",
            None,
        )
        if generate_step_status != "running":
            raise ValueError(
                "generate_analysis Step must be running"
            )

        generate_input_state = getattr(
            generate_analysis_step,
            "input_state_json",
            None,
        )
        if not isinstance(generate_input_state, Mapping):
            raise ValueError(
                "generate_analysis Step input state "
                "must be a mapping"
            )
        if dict(generate_input_state) != state_json:
            raise ValueError(
                "generate_analysis Step state snapshot "
                "does not match Agent Run state"
            )

        if state_json.get("generated_analysis") is not None:
            raise ValueError(
                "Agent state already contains generated_analysis"
            )

        try:
            generation_outcome = (
                self._analysis_generation_service.generate(
                    state_json
                )
            )
            if not isinstance(
                generation_outcome,
                AgentAnalysisGenerationOutcome,
            ):
                raise TypeError(
                    "Analysis Generation Service returned "
                    "an invalid outcome type"
                )
        except AgentAnalysisGenerationError as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=generate_step_index,
                node_name=GENERATE_ANALYSIS_NODE,
                error_code=exc.error_code,
                error_message=str(exc),
                output_state_json={
                    "generation_version": (
                        AGENT_ANALYSIS_GENERATION_VERSION
                    ),
                    "runner_generation_version": (
                        AGENT_RUNNER_GENERATE_ANALYSIS_VERSION
                    ),
                    "error_code": exc.error_code,
                },
            )
            raise
        except Exception as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=generate_step_index,
                node_name=GENERATE_ANALYSIS_NODE,
                error_code="generate_analysis_failed",
                error_message=(
                    f"{type(exc).__name__} occurred "
                    "while generating Agent analysis"
                ),
                output_state_json={
                    "generation_version": (
                        AGENT_ANALYSIS_GENERATION_VERSION
                    ),
                    "runner_generation_version": (
                        AGENT_RUNNER_GENERATE_ANALYSIS_VERSION
                    ),
                    "error_code": (
                        "generate_analysis_failed"
                    ),
                },
            )
            raise

        generation_update = (
            generation_outcome.to_state_update()
        )
        state_after_generation = {
            **state_json,
            **generation_update,
        }

        (
            advanced_run,
            completed_generate_step,
            persist_analysis_step,
        ) = (
            self._orchestration_service
            .complete_step_and_advance_run(
                db,
                run_id=run_id,
                step_index=generate_step_index,
                next_node=PERSIST_ANALYSIS_NODE,
                state_json=dict(
                    state_after_generation
                ),
                output_state_json=(
                    generation_outcome.as_dict()
                ),
            )
        )

        return AgentRunnerGenerateAnalysisResult(
            agent_run=advanced_run,
            generate_analysis_step=(
                completed_generate_step
            ),
            persist_analysis_step=persist_analysis_step,
            generation_outcome=generation_outcome,
            state_json=dict(state_after_generation),
        )

    def advance_persist_analysis(
        self,
        db: Session,
        *,
        agent_run: object,
        persist_analysis_step: object,
    ) -> AgentRunnerPersistAnalysisResult:
        run_id = getattr(agent_run, "run_id", None)
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise ValueError(
                "Agent Run must expose a normalized run_id"
            )

        run_status = getattr(
            agent_run,
            "run_status",
            None,
        )
        if run_status != RUNNING_RUN_STATUS:
            raise ValueError(
                "Agent Run cannot persist analysis "
                f"from status: {run_status}"
            )

        current_node = getattr(
            agent_run,
            "current_node",
            None,
        )
        if current_node != PERSIST_ANALYSIS_NODE:
            raise ValueError(
                "Agent Run has unexpected persistence node: "
                f"{current_node}"
            )

        step_count = getattr(
            agent_run,
            "step_count",
            None,
        )
        if (
            type(step_count) is not int
            or step_count < 1
        ):
            raise ValueError(
                "Agent Run must expose a positive "
                "integer step_count"
            )

        persisted_state = getattr(
            agent_run,
            "state_json",
            None,
        )
        if not isinstance(persisted_state, Mapping):
            raise ValueError(
                "Agent Run state_json must be a mapping"
            )
        state_json = dict(persisted_state)

        persist_step_index = self._step_index(
            persist_analysis_step
        )
        if persist_step_index != step_count:
            raise ValueError(
                "persist_analysis must be the latest Step"
            )

        persist_step_node = getattr(
            persist_analysis_step,
            "node_name",
            None,
        )
        if persist_step_node != PERSIST_ANALYSIS_NODE:
            raise ValueError(
                "Agent Step has unexpected persistence node: "
                f"{persist_step_node}"
            )

        persist_step_status = getattr(
            persist_analysis_step,
            "step_status",
            None,
        )
        if persist_step_status != "running":
            raise ValueError(
                "persist_analysis Step must be running"
            )

        persist_input_state = getattr(
            persist_analysis_step,
            "input_state_json",
            None,
        )
        if not isinstance(persist_input_state, Mapping):
            raise ValueError(
                "persist_analysis Step input state "
                "must be a mapping"
            )
        if dict(persist_input_state) != state_json:
            raise ValueError(
                "persist_analysis Step state snapshot "
                "does not match Agent Run state"
            )

        if not isinstance(
            state_json.get("generated_analysis"),
            Mapping,
        ):
            raise ValueError(
                "Agent state must contain generated_analysis"
            )

        if getattr(
            agent_run,
            "analysis_log_id",
            None,
        ) is not None:
            raise ValueError(
                "Agent Run already has an analysis_log_id"
            )

        if state_json.get("analysis_log_id") is not None:
            raise ValueError(
                "Agent state already has an analysis_log_id"
            )

        try:
            persistence_result = (
                self._orchestration_service
                .persist_generated_analysis_and_advance_to_final_review(
                    db,
                    run_id=run_id,
                    step_index=persist_step_index,
                )
            )
        except Exception as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=persist_step_index,
                node_name=PERSIST_ANALYSIS_NODE,
                error_code="persist_analysis_failed",
                error_message=(
                    f"{type(exc).__name__} occurred "
                    "while persisting Agent analysis"
                ),
                output_state_json={
                    "runner_persistence_version": (
                        AGENT_RUNNER_PERSIST_ANALYSIS_VERSION
                    ),
                    "error_code": (
                        "persist_analysis_failed"
                    ),
                },
            )
            raise

        if (
            not isinstance(persistence_result, tuple)
            or len(persistence_result) != 4
        ):
            raise TypeError(
                "Analysis persistence orchestration returned "
                "an invalid result"
            )

        (
            advanced_run,
            completed_persist_step,
            analysis_log,
            final_review_step,
        ) = persistence_result

        analysis_log_id = getattr(
            analysis_log,
            "id",
            None,
        )
        if (
            type(analysis_log_id) is not int
            or analysis_log_id < 1
        ):
            raise TypeError(
                "Persisted analysis must expose a positive "
                "integer id"
            )

        if getattr(
            advanced_run,
            "analysis_log_id",
            None,
        ) != analysis_log_id:
            raise RuntimeError(
                "Agent Run analysis link does not match "
                "the persisted analysis"
            )

        advanced_state = getattr(
            advanced_run,
            "state_json",
            None,
        )
        if not isinstance(advanced_state, Mapping):
            raise TypeError(
                "Persisted Agent Run state_json must be a mapping"
            )
        state_after_persistence = dict(advanced_state)

        if (
            state_after_persistence.get("analysis_log_id")
            != analysis_log_id
        ):
            raise RuntimeError(
                "Persisted Agent state analysis_log_id does "
                "not match the analysis"
            )
        if (
            state_after_persistence.get("pending_approval")
            is not True
        ):
            raise RuntimeError(
                "Persisted Agent state must require approval"
            )
        if not isinstance(
            state_after_persistence.get(
                "generated_analysis"
            ),
            Mapping,
        ):
            raise RuntimeError(
                "Persisted Agent state must retain "
                "generated_analysis"
            )

        if getattr(
            advanced_run,
            "run_status",
            None,
        ) != GENERATING_ANALYSIS_STATUS:
            raise RuntimeError(
                "Persisted Agent Run must enter "
                "generating_analysis"
            )
        if getattr(
            advanced_run,
            "current_node",
            None,
        ) != FINAL_REVIEW_NODE:
            raise RuntimeError(
                "Persisted Agent Run must advance to "
                "final_review"
            )

        if self._step_index(
            completed_persist_step
        ) != persist_step_index:
            raise RuntimeError(
                "Completed persist_analysis Step index changed"
            )
        if getattr(
            completed_persist_step,
            "node_name",
            None,
        ) != PERSIST_ANALYSIS_NODE:
            raise RuntimeError(
                "Completed Step must be persist_analysis"
            )
        if getattr(
            completed_persist_step,
            "step_status",
            None,
        ) != "completed":
            raise RuntimeError(
                "persist_analysis Step must be completed"
            )

        final_review_index = self._step_index(
            final_review_step
        )
        if final_review_index != persist_step_index + 1:
            raise RuntimeError(
                "final_review Step must immediately follow "
                "persist_analysis"
            )
        if getattr(
            final_review_step,
            "node_name",
            None,
        ) != FINAL_REVIEW_NODE:
            raise RuntimeError(
                "Next Step must be final_review"
            )
        if getattr(
            final_review_step,
            "step_status",
            None,
        ) != "running":
            raise RuntimeError(
                "final_review Step must be running"
            )

        return AgentRunnerPersistAnalysisResult(
            agent_run=advanced_run,
            persist_analysis_step=(
                completed_persist_step
            ),
            analysis_log=analysis_log,
            final_review_step=final_review_step,
            state_json=dict(
                state_after_persistence
            ),
        )

    def advance_final_review(
        self,
        db: Session,
        *,
        agent_run: object,
        final_review_step: object,
    ) -> AgentRunnerFinalReviewResult:
        run_id = getattr(agent_run, "run_id", None)
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise ValueError(
                "Agent Run must expose a normalized run_id"
            )

        run_status = getattr(
            agent_run,
            "run_status",
            None,
        )
        if run_status != GENERATING_ANALYSIS_STATUS:
            raise ValueError(
                "Agent Run cannot enter final review wait "
                f"from status: {run_status}"
            )

        current_node = getattr(
            agent_run,
            "current_node",
            None,
        )
        if current_node != FINAL_REVIEW_NODE:
            raise ValueError(
                "Agent Run has unexpected final review node: "
                f"{current_node}"
            )

        step_count = getattr(
            agent_run,
            "step_count",
            None,
        )
        if (
            type(step_count) is not int
            or step_count < 1
        ):
            raise ValueError(
                "Agent Run must expose a positive "
                "integer step_count"
            )

        persisted_state = getattr(
            agent_run,
            "state_json",
            None,
        )
        if not isinstance(persisted_state, Mapping):
            raise ValueError(
                "Agent Run state_json must be a mapping"
            )
        state_json = dict(persisted_state)

        final_review_step_index = self._step_index(
            final_review_step
        )
        if final_review_step_index != step_count:
            raise ValueError(
                "final_review must be the latest Step"
            )

        step_node = getattr(
            final_review_step,
            "node_name",
            None,
        )
        if step_node != FINAL_REVIEW_NODE:
            raise ValueError(
                "Agent Step has unexpected final review node: "
                f"{step_node}"
            )

        step_status = getattr(
            final_review_step,
            "step_status",
            None,
        )
        if step_status != "running":
            raise ValueError(
                "final_review Step must be running"
            )

        step_input_state = getattr(
            final_review_step,
            "input_state_json",
            None,
        )
        if not isinstance(step_input_state, Mapping):
            raise ValueError(
                "final_review Step input state "
                "must be a mapping"
            )
        if dict(step_input_state) != state_json:
            raise ValueError(
                "final_review Step state snapshot "
                "does not match Agent Run state"
            )

        analysis_log_id = getattr(
            agent_run,
            "analysis_log_id",
            None,
        )
        if (
            type(analysis_log_id) is not int
            or analysis_log_id < 1
        ):
            raise ValueError(
                "Agent Run must expose a positive "
                "analysis_log_id"
            )

        if (
            state_json.get("analysis_log_id")
            != analysis_log_id
        ):
            raise ValueError(
                "Agent state analysis_log_id does not "
                "match Agent Run"
            )

        if state_json.get("pending_approval") is not True:
            raise ValueError(
                "Agent state must require pending approval"
            )

        if not isinstance(
            state_json.get("generated_analysis"),
            Mapping,
        ):
            raise ValueError(
                "Agent state must retain generated_analysis"
            )

        if getattr(
            agent_run,
            "waiting_since",
            None,
        ) is not None:
            raise ValueError(
                "Generating Agent Run cannot already be waiting"
            )

        if getattr(
            agent_run,
            "resume_node",
            None,
        ) is not None:
            raise ValueError(
                "Generating Agent Run cannot have a resume_node"
            )

        try:
            wait_result = (
                self._orchestration_service
                .complete_final_review_and_wait_run(
                    db,
                    run_id=run_id,
                    step_index=final_review_step_index,
                )
            )
        except Exception as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=final_review_step_index,
                node_name=FINAL_REVIEW_NODE,
                error_code="final_review_wait_failed",
                error_message=(
                    f"{type(exc).__name__} occurred "
                    "while entering final review wait"
                ),
                output_state_json={
                    "runner_final_review_version": (
                        AGENT_RUNNER_FINAL_REVIEW_VERSION
                    ),
                    "error_code": (
                        "final_review_wait_failed"
                    ),
                },
            )
            raise

        if (
            not isinstance(wait_result, tuple)
            or len(wait_result) != 3
        ):
            raise TypeError(
                "Final review wait orchestration returned "
                "an invalid result"
            )

        (
            waiting_run,
            completed_final_review_step,
            await_final_review_step,
        ) = wait_result

        if getattr(
            waiting_run,
            "run_status",
            None,
        ) != WAITING_FOR_FINAL_REVIEW_STATUS:
            raise RuntimeError(
                "Agent Run must enter waiting_for_final_review"
            )

        if getattr(
            waiting_run,
            "current_node",
            None,
        ) != AWAIT_FINAL_REVIEW_NODE:
            raise RuntimeError(
                "Waiting Agent Run must use await_final_review"
            )

        if getattr(
            waiting_run,
            "resume_node",
            None,
        ) != FINALIZE_RUN_NODE:
            raise RuntimeError(
                "Waiting Agent Run must resume at finalize_run"
            )

        waiting_since = getattr(
            waiting_run,
            "waiting_since",
            None,
        )
        if waiting_since is None:
            raise RuntimeError(
                "Waiting Agent Run must have waiting_since"
            )

        if getattr(
            waiting_run,
            "analysis_log_id",
            None,
        ) != analysis_log_id:
            raise RuntimeError(
                "Waiting Agent Run analysis link changed"
            )

        waiting_state = getattr(
            waiting_run,
            "state_json",
            None,
        )
        if not isinstance(waiting_state, Mapping):
            raise TypeError(
                "Waiting Agent Run state_json must be a mapping"
            )
        state_after_wait = dict(waiting_state)

        if state_after_wait != state_json:
            raise RuntimeError(
                "Final review wait must preserve Agent state"
            )

        if (
            state_after_wait.get("analysis_log_id")
            != analysis_log_id
        ):
            raise RuntimeError(
                "Waiting Agent state analysis_log_id changed"
            )

        if (
            state_after_wait.get("pending_approval")
            is not True
        ):
            raise RuntimeError(
                "Waiting Agent state must require approval"
            )

        if not isinstance(
            state_after_wait.get("generated_analysis"),
            Mapping,
        ):
            raise RuntimeError(
                "Waiting Agent state must retain "
                "generated_analysis"
            )

        if self._step_index(
            completed_final_review_step
        ) != final_review_step_index:
            raise RuntimeError(
                "Completed final_review Step index changed"
            )

        if getattr(
            completed_final_review_step,
            "node_name",
            None,
        ) != FINAL_REVIEW_NODE:
            raise RuntimeError(
                "Completed Step must be final_review"
            )

        if getattr(
            completed_final_review_step,
            "step_status",
            None,
        ) != "completed":
            raise RuntimeError(
                "final_review Step must be completed"
            )

        await_step_index = self._step_index(
            await_final_review_step
        )
        if (
            await_step_index
            != final_review_step_index + 1
        ):
            raise RuntimeError(
                "await_final_review Step must immediately "
                "follow final_review"
            )

        if getattr(
            await_final_review_step,
            "node_name",
            None,
        ) != AWAIT_FINAL_REVIEW_NODE:
            raise RuntimeError(
                "Waiting Step must be await_final_review"
            )

        if getattr(
            await_final_review_step,
            "step_status",
            None,
        ) != "interrupted":
            raise RuntimeError(
                "await_final_review Step must be interrupted"
            )

        if getattr(
            waiting_run,
            "step_count",
            None,
        ) != await_step_index:
            raise RuntimeError(
                "Waiting Agent Run step_count changed"
            )

        await_input_state = getattr(
            await_final_review_step,
            "input_state_json",
            None,
        )
        if (
            not isinstance(await_input_state, Mapping)
            or dict(await_input_state) != state_after_wait
        ):
            raise RuntimeError(
                "await_final_review input state must match "
                "the waiting Agent state"
            )

        completed_receipt = getattr(
            completed_final_review_step,
            "output_state_json",
            None,
        )
        await_receipt = getattr(
            await_final_review_step,
            "output_state_json",
            None,
        )
        if (
            not isinstance(completed_receipt, Mapping)
            or not isinstance(await_receipt, Mapping)
            or dict(completed_receipt)
            != dict(await_receipt)
        ):
            raise RuntimeError(
                "Final review Steps must share a wait receipt"
            )

        receipt = dict(await_receipt)
        receipt_version = receipt.get(
            "final_review_wait_version"
        )
        if (
            not isinstance(receipt_version, str)
            or not receipt_version.strip()
        ):
            raise RuntimeError(
                "Final review wait receipt must expose "
                "a version"
            )

        expected_receipt_values = {
            "analysis_log_id": analysis_log_id,
            "pending_approval": True,
            "completed_node": FINAL_REVIEW_NODE,
            "waiting_node": AWAIT_FINAL_REVIEW_NODE,
            "resume_node": FINALIZE_RUN_NODE,
        }
        for key, expected_value in (
            expected_receipt_values.items()
        ):
            if receipt.get(key) != expected_value:
                raise RuntimeError(
                    "Final review wait receipt has "
                    f"unexpected {key}"
                )

        return AgentRunnerFinalReviewResult(
            agent_run=waiting_run,
            final_review_step=(
                completed_final_review_step
            ),
            await_final_review_step=(
                await_final_review_step
            ),
            state_json=dict(state_after_wait),
        )

    def advance_request_clarification(
        self,
        db: Session,
        *,
        agent_run: object,
        request_clarification_step: object,
    ) -> AgentRunnerRequestClarificationResult:
        run_id = getattr(agent_run, "run_id", None)
        if (
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
        ):
            raise ValueError(
                "Agent Run must expose a normalized run_id"
            )

        run_status = getattr(
            agent_run,
            "run_status",
            None,
        )
        if run_status != "running":
            raise ValueError(
                "Agent Run cannot request clarification "
                f"from status: {run_status}"
            )

        current_node = getattr(
            agent_run,
            "current_node",
            None,
        )
        if current_node != REQUEST_CLARIFICATION_NODE:
            raise ValueError(
                "Agent Run has unexpected current node: "
                f"{current_node}"
            )

        step_count = getattr(
            agent_run,
            "step_count",
            None,
        )
        if (
            type(step_count) is not int
            or step_count < 1
        ):
            raise ValueError(
                "Agent Run must expose a positive "
                "integer step_count"
            )

        persisted_state = getattr(
            agent_run,
            "state_json",
            None,
        )
        if not isinstance(persisted_state, Mapping):
            raise ValueError(
                "Agent Run state_json must be a mapping"
            )
        state_json = dict(persisted_state)

        request_step_index = self._step_index(
            request_clarification_step
        )
        if request_step_index != step_count:
            raise ValueError(
                "request_clarification must be the "
                "latest Step"
            )

        request_step_node = getattr(
            request_clarification_step,
            "node_name",
            None,
        )
        if request_step_node != REQUEST_CLARIFICATION_NODE:
            raise ValueError(
                "Agent Step has unexpected "
                "clarification node: "
                f"{request_step_node}"
            )

        request_step_status = getattr(
            request_clarification_step,
            "step_status",
            None,
        )
        if request_step_status != "running":
            raise ValueError(
                "request_clarification Step must be "
                "running"
            )

        request_input_state = getattr(
            request_clarification_step,
            "input_state_json",
            None,
        )
        if not isinstance(request_input_state, Mapping):
            raise ValueError(
                "request_clarification Step input state "
                "must be a mapping"
            )
        if dict(request_input_state) != state_json:
            raise ValueError(
                "request_clarification Step state "
                "snapshot does not match Agent Run state"
            )

        try:
            clarification_request = (
                self._clarification_request_service
                .create_request(state_json)
            )
            if not isinstance(
                clarification_request,
                AgentClarificationRequest,
            ):
                raise TypeError(
                    "Clarification Request Service "
                    "returned an invalid request type"
                )
        except AgentClarificationRequestError as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=request_step_index,
                node_name=REQUEST_CLARIFICATION_NODE,
                error_code=exc.error_code,
                error_message=str(exc),
                output_state_json={
                    "request_version": (
                        AGENT_CLARIFICATION_REQUEST_VERSION
                    ),
                    "error_code": exc.error_code,
                },
            )
            raise
        except Exception as exc:
            self._fail_step(
                db,
                run_id=run_id,
                step_index=request_step_index,
                node_name=REQUEST_CLARIFICATION_NODE,
                error_code=(
                    "request_clarification_failed"
                ),
                error_message=(
                    f"{type(exc).__name__} occurred "
                    "while preparing Agent clarification"
                ),
                output_state_json={
                    "request_version": (
                        AGENT_CLARIFICATION_REQUEST_VERSION
                    ),
                    "error_code": (
                        "request_clarification_failed"
                    ),
                },
            )
            raise

        state_after_request = {
            **state_json,
            **clarification_request.to_state_update(),
        }

        (
            waiting_run,
            interrupted_request_step,
        ) = (
            self._orchestration_service
            .interrupt_step_and_wait_run(
                db,
                run_id=run_id,
                step_index=request_step_index,
                waiting_status=(
                    WAITING_FOR_CLARIFICATION_STATUS
                ),
                state_json=dict(
                    state_after_request
                ),
                output_state_json=(
                    clarification_request.as_dict()
                ),
            )
        )

        return AgentRunnerRequestClarificationResult(
            agent_run=waiting_run,
            request_clarification_step=(
                interrupted_request_step
            ),
            clarification_request=(
                clarification_request
            ),
            state_json=dict(
                state_after_request
            ),
        )
    def advance_investigation_until_boundary(
        self,
        db: Session,
        *,
        agent_run: object,
        current_step: object | None,
        max_transitions: int = (
            DEFAULT_MAX_TRANSITIONS_PER_CALL
        ),
    ) -> AgentRunnerBoundedLoopResult:
        if (
            type(max_transitions) is not int
            or max_transitions < 1
        ):
            raise ValueError(
                "max_transitions must be a positive integer"
            )

        active_run = agent_run
        active_step = current_step
        transition_count = 0
        visited_nodes: list[str] = []
        seen_signatures: set[
            tuple[object, ...]
        ] = set()

        while True:
            run_status = getattr(
                active_run,
                "run_status",
                None,
            )
            current_node = getattr(
                active_run,
                "current_node",
                None,
            )

            if run_status in WAITING_RUN_STATUSES:
                return AgentRunnerBoundedLoopResult(
                    agent_run=active_run,
                    current_step=active_step,
                    transition_count=transition_count,
                    stop_reason=BOUNDED_LOOP_STOP_WAITING,
                    visited_nodes=tuple(visited_nodes),
                )

            if run_status in TERMINAL_RUN_STATUSES:
                return AgentRunnerBoundedLoopResult(
                    agent_run=active_run,
                    current_step=active_step,
                    transition_count=transition_count,
                    stop_reason=BOUNDED_LOOP_STOP_TERMINAL,
                    visited_nodes=tuple(visited_nodes),
                )

            if run_status in UNIMPLEMENTED_RUN_STATUSES:
                return AgentRunnerBoundedLoopResult(
                    agent_run=active_run,
                    current_step=active_step,
                    transition_count=transition_count,
                    stop_reason=(
                        BOUNDED_LOOP_STOP_UNIMPLEMENTED
                    ),
                    visited_nodes=tuple(visited_nodes),
                )

            if (
                not isinstance(current_node, str)
                or not current_node.strip()
                or current_node != current_node.strip()
            ):
                raise AgentRunnerBoundedLoopError(
                    error_code="invalid_current_node",
                    message=(
                        "Agent Run must expose a normalized "
                        "current_node"
                    ),
                )

            if (
                run_status
                not in BOUNDED_LOOP_ACTIVE_RUN_STATUSES
            ):
                raise AgentRunnerBoundedLoopError(
                    error_code="unsupported_run_status",
                    message=(
                        "Bounded Runner loop cannot continue "
                        f"from status: {run_status}"
                    ),
                )

            expected_run_status = (
                GENERATING_ANALYSIS_STATUS
                if current_node == FINAL_REVIEW_NODE
                else RUNNING_RUN_STATUS
            )
            if run_status != expected_run_status:
                raise AgentRunnerBoundedLoopError(
                    error_code="run_status_node_mismatch",
                    message=(
                        "Bounded Runner loop status does not "
                        "match the current node: "
                        f"status={run_status}, "
                        f"node={current_node}"
                    ),
                )

            if active_step is None:
                raise AgentRunnerBoundedLoopError(
                    error_code="missing_current_step",
                    message=(
                        "Running Agent loop requires a "
                        "current Step"
                    ),
                )

            signature = self._bounded_loop_signature(
                active_run,
                active_step,
            )
            if signature in seen_signatures:
                raise AgentRunnerBoundedLoopError(
                    error_code="runner_loop_stalled",
                    message=(
                        "Bounded Runner loop repeated a "
                        "previous state signature"
                    ),
                )
            seen_signatures.add(signature)

            if current_node in (
                BOUNDED_LOOP_UNIMPLEMENTED_NODES
            ):
                return AgentRunnerBoundedLoopResult(
                    agent_run=active_run,
                    current_step=active_step,
                    transition_count=transition_count,
                    stop_reason=(
                        BOUNDED_LOOP_STOP_UNIMPLEMENTED
                    ),
                    visited_nodes=tuple(visited_nodes),
                )

            if current_node not in (
                BOUNDED_LOOP_SUPPORTED_NODES
            ):
                raise AgentRunnerBoundedLoopError(
                    error_code="unsupported_current_node",
                    message=(
                        "Bounded Runner loop cannot dispatch "
                        f"node: {current_node}"
                    ),
                )

            if transition_count >= max_transitions:
                return AgentRunnerBoundedLoopResult(
                    agent_run=active_run,
                    current_step=active_step,
                    transition_count=transition_count,
                    stop_reason=(
                        BOUNDED_LOOP_STOP_TRANSITION_CAP
                    ),
                    visited_nodes=tuple(visited_nodes),
                )

            run_id = getattr(
                active_run,
                "run_id",
                None,
            )
            if (
                not isinstance(run_id, str)
                or not run_id.strip()
                or run_id != run_id.strip()
            ):
                raise AgentRunnerBoundedLoopError(
                    error_code="invalid_run_id",
                    message=(
                        "Agent Run must expose a "
                        "normalized run_id"
                    ),
                )

            persisted_state = getattr(
                active_run,
                "state_json",
                None,
            )
            if not isinstance(persisted_state, Mapping):
                raise AgentRunnerBoundedLoopError(
                    error_code="invalid_agent_state",
                    message=(
                        "Agent Run state_json must be "
                        "a mapping"
                    ),
                )
            state_json = dict(persisted_state)
            step_count = self._bounded_loop_counter(
                active_run,
                "step_count",
            )
            tool_call_count = self._bounded_loop_counter(
                active_run,
                "tool_call_count",
            )
            max_steps = self._bounded_loop_limit(
                state_json.get("max_steps"),
                field_name="max_steps",
                default_value=16,
            )
            max_tool_calls = self._bounded_loop_limit(
                state_json.get("max_tool_calls"),
                field_name="max_tool_calls",
                default_value=3,
            )
            state_json.setdefault(
                "max_steps",
                max_steps,
            )
            state_json.setdefault(
                "max_tool_calls",
                max_tool_calls,
            )
            step_index = self._step_index(active_step)

            if step_count >= max_steps:
                (
                    limited_run,
                    completed_step,
                ) = (
                    self._orchestration_service
                    .complete_step_and_limit_run(
                        db,
                        run_id=run_id,
                        step_index=step_index,
                        error_code="max_steps_reached",
                        error_message=(
                            "The configured max_steps "
                            "boundary has been reached."
                        ),
                        state_json=dict(state_json),
                        output_state_json={
                            "loop_version": (
                                AGENT_RUNNER_BOUNDED_LOOP_VERSION
                            ),
                            "stop_reason": (
                                "max_steps_reached"
                            ),
                        },
                    )
                )
                visited_nodes.append(current_node)
                transition_count += 1
                active_run = limited_run
                active_step = completed_step
                continue

            if (
                current_node in (
                    BOUNDED_LOOP_TOOL_BUDGET_NODES
                )
                and tool_call_count >= max_tool_calls
            ):
                (
                    limited_run,
                    completed_step,
                ) = (
                    self._orchestration_service
                    .complete_step_and_limit_run(
                        db,
                        run_id=run_id,
                        step_index=step_index,
                        error_code=(
                            "max_tool_calls_reached"
                        ),
                        error_message=(
                            "The configured max_tool_calls "
                            "boundary has been reached."
                        ),
                        state_json=dict(state_json),
                        output_state_json={
                            "loop_version": (
                                AGENT_RUNNER_BOUNDED_LOOP_VERSION
                            ),
                            "stop_reason": (
                                "max_tool_calls_reached"
                            ),
                        },
                    )
                )
                visited_nodes.append(current_node)
                transition_count += 1
                active_run = limited_run
                active_step = completed_step
                continue

            before_signature = signature
            visited_nodes.append(current_node)

            if current_node == ROUTE_INVESTIGATION_NODE:
                dispatch_result = (
                    self.advance_investigation_route(
                        db,
                        agent_run=active_run,
                        route_investigation_step=active_step,
                    )
                )
                next_run = dispatch_result.agent_run
                next_step = (
                    dispatch_result.next_step
                    if dispatch_result.next_step is not None
                    else dispatch_result.route_investigation_step
                )
            elif current_node == SELECT_TOOL_NODE:
                dispatch_result = self.advance_select_tool(
                    db,
                    agent_run=active_run,
                    select_tool_step=active_step,
                )
                next_run = dispatch_result.agent_run
                next_step = (
                    dispatch_result.execute_tool_step
                )
            elif current_node == EXECUTE_TOOL_NODE:
                dispatch_result = self.advance_execute_tool(
                    db,
                    agent_run=active_run,
                    execute_tool_step=active_step,
                )
                next_run = dispatch_result.agent_run
                next_step = (
                    dispatch_result.evaluate_evidence_step
                )
            elif current_node == EVALUATE_EVIDENCE_NODE:
                dispatch_result = (
                    self.advance_evaluate_evidence(
                        db,
                        agent_run=active_run,
                        evaluate_evidence_step=active_step,
                    )
                )
                next_run = dispatch_result.agent_run
                next_step = (
                    dispatch_result.next_step
                    if dispatch_result.next_step is not None
                    else dispatch_result.evaluate_evidence_step
                )
            elif current_node == GENERATE_ANALYSIS_NODE:
                dispatch_result = (
                    self.advance_generate_analysis(
                        db,
                        agent_run=active_run,
                        generate_analysis_step=active_step,
                    )
                )
                next_run = dispatch_result.agent_run
                next_step = (
                    dispatch_result.persist_analysis_step
                )
            elif current_node == PERSIST_ANALYSIS_NODE:
                dispatch_result = (
                    self.advance_persist_analysis(
                        db,
                        agent_run=active_run,
                        persist_analysis_step=active_step,
                    )
                )
                next_run = dispatch_result.agent_run
                next_step = (
                    dispatch_result.final_review_step
                )
            elif current_node == FINAL_REVIEW_NODE:
                dispatch_result = self.advance_final_review(
                    db,
                    agent_run=active_run,
                    final_review_step=active_step,
                )
                next_run = dispatch_result.agent_run
                next_step = (
                    dispatch_result.await_final_review_step
                )
            else:
                dispatch_result = (
                    self.advance_request_clarification(
                        db,
                        agent_run=active_run,
                        request_clarification_step=active_step,
                    )
                )
                next_run = dispatch_result.agent_run
                next_step = (
                    dispatch_result
                    .request_clarification_step
                )

            transition_count += 1
            after_signature = (
                self._bounded_loop_signature(
                    next_run,
                    next_step,
                )
            )

            if (
                after_signature == before_signature
                or after_signature in seen_signatures
            ):
                raise AgentRunnerBoundedLoopError(
                    error_code="runner_loop_stalled",
                    message=(
                        "Bounded Runner loop did not make "
                        "observable progress"
                    ),
                )

            active_run = next_run
            active_step = next_step

    @staticmethod
    def _bounded_loop_counter(
        agent_run: object,
        field_name: str,
    ) -> int:
        value = getattr(
            agent_run,
            field_name,
            None,
        )
        if (
            type(value) is not int
            or value < 0
        ):
            raise AgentRunnerBoundedLoopError(
                error_code=f"invalid_{field_name}",
                message=(
                    f"Agent Run {field_name} must be a "
                    "nonnegative integer"
                ),
            )
        return value

    @staticmethod
    def _bounded_loop_limit(
        value: object,
        *,
        field_name: str,
        default_value: int,
    ) -> int:
        resolved = (
            default_value
            if value is None
            else value
        )
        if (
            type(resolved) is not int
            or resolved < 1
        ):
            raise AgentRunnerBoundedLoopError(
                error_code=f"invalid_{field_name}",
                message=(
                    f"Agent state {field_name} must be "
                    "a positive integer"
                ),
            )
        return resolved

    @classmethod
    def _bounded_loop_signature(
        cls,
        agent_run: object,
        current_step: object,
    ) -> tuple[object, ...]:
        run_status = getattr(
            agent_run,
            "run_status",
            None,
        )
        current_node = getattr(
            agent_run,
            "current_node",
            None,
        )
        step_count = cls._bounded_loop_counter(
            agent_run,
            "step_count",
        )
        tool_call_count = cls._bounded_loop_counter(
            agent_run,
            "tool_call_count",
        )
        step_index = cls._step_index(current_step)
        step_status = getattr(
            current_step,
            "step_status",
            None,
        )
        step_node = getattr(
            current_step,
            "node_name",
            None,
        )

        if step_index != step_count:
            raise AgentRunnerBoundedLoopError(
                error_code="stale_current_step",
                message=(
                    "Bounded Runner loop requires the "
                    "latest Agent Step"
                ),
            )
        if step_status not in {
            "running",
            "completed",
            "interrupted",
            "failed",
            "cancelled",
        }:
            raise AgentRunnerBoundedLoopError(
                error_code="invalid_step_status",
                message=(
                    "Agent Step exposes an unsupported "
                    f"status: {step_status}"
                ),
            )
        if (
            run_status in BOUNDED_LOOP_ACTIVE_RUN_STATUSES
            and step_status != "running"
        ):
            raise AgentRunnerBoundedLoopError(
                error_code="current_step_not_running",
                message=(
                    "Active Agent loop requires a "
                    "running current Step"
                ),
            )
        if (
            run_status in BOUNDED_LOOP_ACTIVE_RUN_STATUSES
            and step_node != current_node
        ):
            raise AgentRunnerBoundedLoopError(
                error_code="current_step_node_mismatch",
                message=(
                    "Agent Run and current Step nodes "
                    "must match"
                ),
            )

        return (
            run_status,
            current_node,
            step_count,
            tool_call_count,
            step_index,
            step_status,
        )

    def _fail_step(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        node_name: str,
        error_code: str,
        error_message: str,
        output_state_json: (
            dict[str, object] | None
        ) = None,
    ) -> None:
        try:
            self._orchestration_service.fail_step(
                db,
                run_id=run_id,
                step_index=step_index,
                error_code=error_code,
                error_message=error_message[:1000],
                output_state_json=output_state_json,
            )
        except Exception as persistence_error:
            raise RuntimeError(
                "Failed to persist Runner failure for "
                f"{node_name!r}"
            ) from persistence_error

    @staticmethod
    def _step_index(step: object) -> int:
        value: Any = getattr(
            step,
            "step_index",
            None,
        )

        if (
            not isinstance(value, int)
            or value < 1
        ):
            raise ValueError(
                "Agent Step must expose a positive "
                "integer step_index"
            )

        return value
