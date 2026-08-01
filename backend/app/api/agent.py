from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AgentRun,
    AgentStep,
    AgentToolCall,
    Issue,
)
from app.services.agent_orchestration_service import (
    agent_orchestration_service,
)
from app.services.agent_runner_service import (
    AgentRunnerBoundedLoopError,
    AgentRunnerService,
)


router = APIRouter()
agent_runner_service = AgentRunnerService()

AGENT_GRAPH_VERSION = "agent_mvp_v0.1"
AGENT_INITIAL_NODE = "load_issue"

ACTIVE_RUN_STATUSES = (
    "created",
    "running",
    "generating_analysis",
    "waiting_for_triage_confirmation",
    "waiting_for_clarification",
    "waiting_for_final_review",
)

ACTIVE_CANCEL_STATUSES = (
    "running",
    "generating_analysis",
)

WAITING_RUN_STATUSES = (
    "waiting_for_triage_confirmation",
    "waiting_for_clarification",
    "waiting_for_final_review",
)


class AgentRunCreatePayload(BaseModel):
    issue_id: int = Field(gt=0)


class AgentRunResumePayload(BaseModel):
    triage_result: dict[str, object] | None = None
    clarification_response: str | None = Field(
        default=None,
        max_length=4000,
    )


def _serialize_datetime(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _serialize_tool_call(
    tool_call: AgentToolCall,
) -> dict[str, object]:
    return {
        "id": tool_call.id,
        "tool_call_index": (
            tool_call.tool_call_index
        ),
        "tool_name": tool_call.tool_name,
        "tool_version": tool_call.tool_version,
        "call_status": tool_call.call_status,
        "arguments": tool_call.arguments_json,
        "result": tool_call.result_json,
        "read_only": tool_call.read_only,
        "requires_approval": (
            tool_call.requires_approval
        ),
        "timeout_seconds": (
            tool_call.timeout_seconds
        ),
        "error_code": tool_call.error_code,
        "error_message": tool_call.error_message,
        "started_at": _serialize_datetime(
            tool_call.started_at
        ),
        "completed_at": _serialize_datetime(
            tool_call.completed_at
        ),
        "created_at": _serialize_datetime(
            tool_call.created_at
        ),
        "updated_at": _serialize_datetime(
            tool_call.updated_at
        ),
    }


def _serialize_step(
    step: AgentStep,
    tool_calls: list[AgentToolCall],
) -> dict[str, object]:
    return {
        "id": step.id,
        "step_index": step.step_index,
        "node_name": step.node_name,
        "step_status": step.step_status,
        "input_state": step.input_state_json,
        "output_state": step.output_state_json,
        "error_code": step.error_code,
        "error_message": step.error_message,
        "started_at": _serialize_datetime(
            step.started_at
        ),
        "completed_at": _serialize_datetime(
            step.completed_at
        ),
        "tool_calls": [
            _serialize_tool_call(tool_call)
            for tool_call in tool_calls
        ],
    }


def _serialize_agent_run(
    db: Session,
    run: AgentRun,
) -> dict[str, object]:
    steps = (
        db.query(AgentStep)
        .filter(
            AgentStep.agent_run_id == run.id
        )
        .order_by(AgentStep.step_index)
        .all()
    )

    step_ids = [
        step.id
        for step in steps
    ]

    tool_calls: list[AgentToolCall] = []

    if step_ids:
        tool_calls = (
            db.query(AgentToolCall)
            .filter(
                AgentToolCall.agent_step_id.in_(
                    step_ids
                )
            )
            .order_by(
                AgentToolCall.agent_step_id,
                AgentToolCall.tool_call_index,
            )
            .all()
        )

    calls_by_step: dict[
        int,
        list[AgentToolCall],
    ] = {
        step_id: []
        for step_id in step_ids
    }

    for tool_call in tool_calls:
        calls_by_step.setdefault(
            tool_call.agent_step_id,
            [],
        ).append(tool_call)

    return {
        "id": run.id,
        "run_id": run.run_id,
        "issue_id": run.issue_id,
        "analysis_log_id": run.analysis_log_id,
        "graph_version": run.graph_version,
        "current_node": run.current_node,
        "run_status": run.run_status,
        "step_count": run.step_count,
        "tool_call_count": (
            run.tool_call_count
        ),
        "retry_count": run.retry_count,
        "state": run.state_json,
        "waiting_since": _serialize_datetime(
            run.waiting_since
        ),
        "resume_node": run.resume_node,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "started_at": _serialize_datetime(
            run.started_at
        ),
        "completed_at": _serialize_datetime(
            run.completed_at
        ),
        "created_at": _serialize_datetime(
            run.created_at
        ),
        "updated_at": _serialize_datetime(
            run.updated_at
        ),
        "steps": [
            _serialize_step(
                step,
                calls_by_step.get(
                    step.id,
                    [],
                ),
            )
            for step in steps
        ],
    }


def _get_run_or_404(
    db: Session,
    run_id: str,
) -> AgentRun:
    try:
        run = (
            db.query(AgentRun)
            .filter(AgentRun.run_id == run_id)
            .first()
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "查询 Agent Run 失败："
                f"{exc!s}"
            ),
        ) from exc

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Agent Run 不存在",
        )

    return run


@router.post("/runs")
def create_agent_run(
    payload: AgentRunCreatePayload,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        issue = (
            db.query(Issue)
            .filter(Issue.id == payload.issue_id)
            .with_for_update()
            .first()
        )

        if issue is None:
            db.rollback()
            raise HTTPException(
                status_code=404,
                detail="Issue 不存在",
            )

        existing_run = (
            db.query(AgentRun)
            .filter(
                AgentRun.issue_id
                == payload.issue_id,
                AgentRun.run_status.in_(
                    ACTIVE_RUN_STATUSES
                ),
            )
            .order_by(AgentRun.id.desc())
            .first()
        )

        if existing_run is not None:
            result = _serialize_agent_run(
                db,
                existing_run,
            )
            db.rollback()
            return result

        runner_result = (
            agent_runner_service
            .start_and_run_to_triage_wait(
                db,
                run_id=str(uuid4()),
                issue_id=payload.issue_id,
                graph_version=AGENT_GRAPH_VERSION,
                initial_state={
                    "issue_id": payload.issue_id,
                },
            )
        )
        run = runner_result.agent_run
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "创建 Agent Run 失败："
                f"{exc!s}"
            ),
        ) from exc

    return _serialize_agent_run(db, run)


@router.get("/runs/{run_id}")
def get_agent_run(
    run_id: str,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    run = _get_run_or_404(db, run_id)

    try:
        return _serialize_agent_run(db, run)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "读取 Agent Run 详情失败："
                f"{exc!s}"
            ),
        ) from exc


@router.post("/runs/{run_id}/resume")
def resume_agent_run(
    run_id: str,
    payload: AgentRunResumePayload,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    triage_result = payload.triage_result
    clarification_response = (
        payload.clarification_response
    )

    if isinstance(
        clarification_response,
        str,
    ):
        clarification_response = (
            clarification_response.strip()
        )

        if not clarification_response:
            clarification_response = None

    provided_count = sum(
        value is not None
        for value in (
            triage_result,
            clarification_response,
        )
    )

    if provided_count != 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "Resume 必须且只能提供 "
                "triage_result 或 "
                "clarification_response"
            ),
        )

    try:
        run, route_investigation_step = (
            agent_orchestration_service
            .resume_waiting_investigation_run(
                db,
                run_id=run_id,
                triage_result=triage_result,
                clarification_response=(
                    clarification_response
                ),
            )
        )
        loop_result = (
            agent_runner_service
            .advance_investigation_until_boundary(
                db,
                agent_run=run,
                current_step=route_investigation_step,
            )
        )
        run = loop_result.agent_run
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except AgentRunnerBoundedLoopError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "恢复 Agent Run 失败："
                f"{exc!s}"
            ),
        ) from exc

    return _serialize_agent_run(db, run)


@router.post("/runs/{run_id}/cancel")
def cancel_agent_run(
    run_id: str,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    run = _get_run_or_404(db, run_id)

    try:
        if run.run_status in WAITING_RUN_STATUSES:
            cancelled_run = (
                agent_orchestration_service
                .cancel_waiting_run(
                    db,
                    run_id=run_id,
                )
            )
        elif (
            run.run_status
            in ACTIVE_CANCEL_STATUSES
        ):
            cancelled_run, _, _ = (
                agent_orchestration_service
                .cancel_active_run(
                    db,
                    run_id=run_id,
                )
            )
        else:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Agent Run 当前状态不可取消："
                    f"{run.run_status}"
                ),
            )
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "取消 Agent Run 失败："
                f"{exc!s}"
            ),
        ) from exc

    return _serialize_agent_run(
        db,
        cancelled_run,
    )