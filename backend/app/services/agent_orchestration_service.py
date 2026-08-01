from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AIAnalysisLog, AgentRun, AgentStep, AgentToolCall
from app.services.agent_persistence_service import (
    AgentPersistenceService,
    AgentToolCallReplayReservation,
    agent_persistence_service,
)


class AgentOrchestrationService:
    """Owns transaction boundaries for Agent workflow operations."""

    def __init__(
        self,
        persistence_service: AgentPersistenceService | None = None,
    ) -> None:
        self._persistence_service = (
            persistence_service
            if persistence_service is not None
            else agent_persistence_service
        )

    def start_run(
        self,
        db: Session,
        *,
        run_id: str,
        issue_id: int,
        graph_version: str,
        initial_node: str,
        initial_state: dict[str, object] | None = None,
        started_at: datetime | None = None,
    ) -> AgentRun:
        run_started_at = started_at or datetime.utcnow()

        try:
            agent_run = self._persistence_service.create_run(
                db,
                run_id=run_id,
                issue_id=issue_id,
                graph_version=graph_version,
                current_node=initial_node,
                state_json=initial_state,
                run_status='running',
                started_at=run_started_at,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)
        return agent_run

    def start_step(
        self,
        db: Session,
        *,
        run_id: str,
        node_name: str,
        input_state_json: dict[str, object] | None = None,
        started_at: datetime | None = None,
    ) -> AgentStep:
        try:
            agent_step = self._persistence_service.append_step(
                db,
                run_id=run_id,
                node_name=node_name,
                input_state_json=input_state_json,
                started_at=started_at,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_step)
        return agent_step

    def reserve_or_reuse_tool_call(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_name: str,
        arguments_json: dict[str, object],
        max_tool_calls: int,
    ) -> AgentToolCallReplayReservation:
        try:
            reservation = (
                self._persistence_service
                .reserve_or_reuse_tool_call(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    tool_name=tool_name,
                    arguments_json=arguments_json,
                    max_tool_calls=max_tool_calls,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(reservation.tool_call)
        return reservation

    def reserve_or_reuse_current_tool_call(
        self,
        db: Session,
        *,
        run_id: str,
        tool_name: str,
        arguments_json: dict[str, object],
        max_tool_calls: int,
    ) -> AgentToolCallReplayReservation:
        try:
            reservation = (
                self._persistence_service
                .reserve_or_reuse_current_tool_call(
                    db,
                    run_id=run_id,
                    tool_name=tool_name,
                    arguments_json=arguments_json,
                    max_tool_calls=max_tool_calls,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(reservation.tool_call)
        return reservation

    def create_tool_call(
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
        try:
            tool_call = self._persistence_service.append_tool_call(
                db,
                run_id=run_id,
                step_index=step_index,
                tool_name=tool_name,
                timeout_seconds=timeout_seconds,
                arguments_json=arguments_json,
                tool_version=tool_version,
                read_only=read_only,
                requires_approval=requires_approval,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(tool_call)
        return tool_call

    def start_tool_call(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_call_index: int,
        started_at: datetime | None = None,
    ) -> AgentToolCall:
        try:
            tool_call = (
                self._persistence_service.mark_tool_call_running(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    tool_call_index=tool_call_index,
                    started_at=started_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(tool_call)
        return tool_call

    def complete_tool_call(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_call_index: int,
        result_json: dict[str, object],
        completed_at: datetime | None = None,
    ) -> AgentToolCall:
        try:
            tool_call = (
                self._persistence_service.mark_tool_call_completed(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    tool_call_index=tool_call_index,
                    result_json=result_json,
                    completed_at=completed_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(tool_call)
        return tool_call

    def fail_tool_call(
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
        try:
            tool_call = (
                self._persistence_service.mark_tool_call_failed(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    tool_call_index=tool_call_index,
                    error_code=error_code,
                    error_message=error_message,
                    completed_at=completed_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(tool_call)
        return tool_call

    def timeout_tool_call(
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
        try:
            tool_call = (
                self._persistence_service.mark_tool_call_timed_out(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    tool_call_index=tool_call_index,
                    error_code=error_code,
                    error_message=error_message,
                    completed_at=completed_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(tool_call)
        return tool_call

    def cancel_tool_call(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_call_index: int,
        completed_at: datetime | None = None,
    ) -> AgentToolCall:
        try:
            tool_call = (
                self._persistence_service.mark_tool_call_cancelled(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    tool_call_index=tool_call_index,
                    completed_at=completed_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(tool_call)
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
        try:
            (
                agent_run,
                completed_step,
                next_step,
            ) = (
                self._persistence_service
                .complete_step_and_advance_run(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    next_node=next_node,
                    state_json=state_json,
                    output_state_json=(
                        output_state_json
                    ),
                    completed_at=completed_at,
                    next_started_at=next_started_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)
        db.refresh(completed_step)
        db.refresh(next_step)

        return (
            agent_run,
            completed_step,
            next_step,
        )

    def complete_step(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        output_state_json: dict[str, object] | None = None,
        completed_at: datetime | None = None,
    ) -> AgentStep:
        try:
            agent_step = (
                self._persistence_service.mark_step_completed(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    output_state_json=output_state_json,
                    completed_at=completed_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_step)
        return agent_step

    def fail_step(
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
        try:
            agent_step = (
                self._persistence_service.mark_step_failed(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    error_code=error_code,
                    error_message=error_message,
                    output_state_json=output_state_json,
                    completed_at=completed_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_step)
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
        try:
            agent_run, agent_step = (
                self._persistence_service
                .complete_step_and_limit_run(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    error_code=error_code,
                    error_message=error_message,
                    state_json=state_json,
                    output_state_json=output_state_json,
                    completed_at=completed_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)
        db.refresh(agent_step)

        return agent_run, agent_step

    def interrupt_step_and_wait_run(
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
        try:
            agent_run, agent_step = (
                self._persistence_service
                .mark_step_interrupted_and_run_waiting(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    waiting_status=waiting_status,
                    state_json=state_json,
                    output_state_json=output_state_json,
                    interrupted_at=interrupted_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)
        db.refresh(agent_step)

        return agent_run, agent_step

    def resume_waiting_investigation_run(
        self,
        db: Session,
        *,
        run_id: str,
        triage_result: dict[str, object] | None = None,
        clarification_response: str | None = None,
        resumed_at: datetime | None = None,
    ) -> tuple[AgentRun, AgentStep]:
        try:
            agent_run, agent_step = (
                self._persistence_service
                .resume_waiting_investigation_run_and_append_step(
                    db,
                    run_id=run_id,
                    triage_result=triage_result,
                    clarification_response=clarification_response,
                    resumed_at=resumed_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)
        db.refresh(agent_step)

        return agent_run, agent_step

    def cancel_active_run(
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
        try:
            agent_run, agent_step, tool_call = (
                self._persistence_service
                .mark_active_run_cancelled(
                    db,
                    run_id=run_id,
                    cancelled_at=cancelled_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)

        if agent_step is not None:
            db.refresh(agent_step)

        if tool_call is not None:
            db.refresh(tool_call)

        return agent_run, agent_step, tool_call
    def cancel_waiting_run(
        self,
        db: Session,
        *,
        run_id: str,
        cancelled_at: datetime | None = None,
    ) -> AgentRun:
        try:
            agent_run = (
                self._persistence_service
                .mark_waiting_run_cancelled(
                    db,
                    run_id=run_id,
                    cancelled_at=cancelled_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)
        return agent_run

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
        try:
            (
                agent_run,
                completed_persist_step,
                analysis,
                final_review_step,
            ) = (
                self._persistence_service
                .persist_generated_analysis_and_advance_to_final_review(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    completed_at=completed_at,
                    final_review_started_at=(
                        final_review_started_at
                    ),
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)
        db.refresh(completed_persist_step)
        db.refresh(analysis)
        db.refresh(final_review_step)

        return (
            agent_run,
            completed_persist_step,
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
        try:
            (
                agent_run,
                completed_final_review_step,
                await_final_review_step,
            ) = (
                self._persistence_service
                .complete_final_review_and_wait_run(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    interrupted_at=interrupted_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)
        db.refresh(completed_final_review_step)
        db.refresh(await_final_review_step)

        return (
            agent_run,
            completed_final_review_step,
            await_final_review_step,
        )

    def finalize_waiting_review_run(
        self,
        db: Session,
        *,
        analysis_id: int,
        feedback_status: str,
        feedback_note: str | None = None,
        edited_output: str | None = None,
        completed_at: datetime | None = None,
    ) -> tuple[AgentRun, AIAnalysisLog, AgentStep]:
        try:
            agent_run, analysis, finalized_step = (
                self._persistence_service
                .finalize_waiting_review_run_and_append_step(
                    db,
                    analysis_id=analysis_id,
                    feedback_status=feedback_status,
                    feedback_note=feedback_note,
                    edited_output=edited_output,
                    completed_at=completed_at,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(agent_run)
        db.refresh(analysis)
        db.refresh(finalized_step)

        return agent_run, analysis, finalized_step


agent_orchestration_service = AgentOrchestrationService()