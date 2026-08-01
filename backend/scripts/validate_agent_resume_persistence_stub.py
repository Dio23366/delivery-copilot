from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from datetime import datetime
from typing import Callable
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AgentRun,
    AgentStep,
    AgentToolCall,
    Base,
    Issue,
)
from app.services.agent_persistence_service import (
    AgentPersistenceService,
)
from app.services.agent_orchestration_service import (
    AgentOrchestrationService,
)


STARTED_AT = datetime(2026, 7, 25, 10, 0, 0)
INTERRUPTED_AT = datetime(2026, 7, 25, 10, 5, 0)
RESUMED_AT = datetime(2026, 7, 25, 10, 10, 0)



class TrackingSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.refreshed: list[object] = []

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def refresh(self, instance: object) -> None:
        self.refreshed.append(instance)


class SuccessfulResumePersistenceStub:
    def __init__(
        self,
        agent_run: AgentRun,
        agent_step: AgentStep,
    ) -> None:
        self.agent_run = agent_run
        self.agent_step = agent_step
        self.calls: list[dict[str, object]] = []

    def resume_waiting_investigation_run_and_append_step(
        self,
        db: object,
        *,
        run_id: str,
        triage_result: dict[str, object] | None = None,
        clarification_response: str | None = None,
        resumed_at: datetime | None = None,
    ) -> tuple[AgentRun, AgentStep]:
        self.calls.append(
            {
                'db': db,
                'run_id': run_id,
                'triage_result': triage_result,
                'clarification_response': clarification_response,
                'resumed_at': resumed_at,
            }
        )
        return self.agent_run, self.agent_step


class FailingResumePersistenceStub:
    def __init__(self) -> None:
        self.call_count = 0

    def resume_waiting_investigation_run_and_append_step(
        self,
        db: object,
        *,
        run_id: str,
        triage_result: dict[str, object] | None = None,
        clarification_response: str | None = None,
        resumed_at: datetime | None = None,
    ) -> tuple[AgentRun, AgentStep]:
        self.call_count += 1
        raise RuntimeError('simulated resume persistence failure')


def create_session() -> tuple[Engine, Session]:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    return engine, session_factory()


def close_session(engine: Engine, db: Session) -> None:
    db.rollback()
    db.close()
    engine.dispose()


def add_waiting_run(
    db: Session,
    *,
    waiting_status: str,
    state_json: dict[str, object],
) -> tuple[AgentRun, AgentStep]:
    transitions = {
        'waiting_for_triage_confirmation': {
            'current_node': 'await_triage_confirmation',
            'resume_node': 'route_investigation',
        },
        'waiting_for_clarification': {
            'current_node': 'request_clarification',
            'resume_node': 'route_investigation',
        },
    }

    transition = transitions[waiting_status]

    issue = Issue(
        title='Agent resume persistence validation',
        description='In-memory validation issue',
        issue_type='API',
        status='open',
        severity='high',
    )
    db.add(issue)
    db.flush()

    agent_run = AgentRun(
        run_id=str(uuid4()),
        issue_id=issue.id,
        graph_version='agent_mvp_v0.1',
        current_node=transition['current_node'],
        run_status=waiting_status,
        step_count=1,
        tool_call_count=0,
        retry_count=0,
        state_json=dict(state_json),
        waiting_since=INTERRUPTED_AT,
        resume_node=transition['resume_node'],
        started_at=STARTED_AT,
    )
    db.add(agent_run)
    db.flush()

    interrupted_step = AgentStep(
        agent_run_id=agent_run.id,
        step_index=1,
        node_name=transition['current_node'],
        step_status='interrupted',
        input_state_json=dict(state_json),
        output_state_json=dict(state_json),
        started_at=STARTED_AT,
        completed_at=INTERRUPTED_AT,
    )
    db.add(interrupted_step)
    db.commit()

    db.refresh(agent_run)
    db.refresh(interrupted_step)

    return agent_run, interrupted_step


def load_steps(
    db: Session,
    agent_run_id: int,
) -> list[AgentStep]:
    return list(
        db.scalars(
            select(AgentStep)
            .where(AgentStep.agent_run_id == agent_run_id)
            .order_by(AgentStep.step_index)
        ).all()
    )


def assert_value_error(
    operation: Callable[[], object],
    expected_message: str,
) -> None:
    try:
        operation()
    except ValueError as exc:
        assert expected_message in str(exc), str(exc)
    else:
        raise AssertionError(
            f'Expected ValueError containing: {expected_message}'
        )


def assert_resumed_run(
    agent_run: AgentRun,
    resumed_step: AgentStep,
) -> None:
    assert agent_run.run_status == 'running'
    assert agent_run.current_node == 'route_investigation'
    assert agent_run.waiting_since is None
    assert agent_run.resume_node is None
    assert agent_run.completed_at is None
    assert agent_run.error_code is None
    assert agent_run.error_message is None
    assert agent_run.step_count == 2

    assert resumed_step.step_index == 2
    assert resumed_step.node_name == 'route_investigation'
    assert resumed_step.step_status == 'running'
    assert resumed_step.started_at == RESUMED_AT
    assert resumed_step.completed_at is None
    assert resumed_step.input_state_json == agent_run.state_json


def test_triage_accepts_existing_result() -> None:
    engine, db = create_session()
    try:
        original_triage = {
            'issue_type': 'API',
            'subtype': 'authentication',
            'severity': 'high',
            'confidence': 0.91,
            'reason': 'Authentication evidence is present.',
        }
        initial_state = {
            'triage_result': original_triage,
            'triage_confirmed': False,
            'preserved_value': 'keep-me',
        }

        agent_run, old_step = add_waiting_run(
            db,
            waiting_status='waiting_for_triage_confirmation',
            state_json=initial_state,
        )
        old_step_id = old_step.id
        old_completed_at = old_step.completed_at

        resumed_run, resumed_step = (
            AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=agent_run.run_id,
                resumed_at=RESUMED_AT,
            )
        )
        db.commit()

        assert_resumed_run(resumed_run, resumed_step)
        assert resumed_run.state_json['triage_result'] == original_triage
        assert resumed_run.state_json['triage_confirmed'] is True
        assert resumed_run.state_json['preserved_value'] == 'keep-me'

        steps = load_steps(db, resumed_run.id)
        assert len(steps) == 2
        assert steps[0].id == old_step_id
        assert steps[0].step_status == 'interrupted'
        assert steps[0].completed_at == old_completed_at
        assert steps[1].id == resumed_step.id
    finally:
        close_session(engine, db)


def test_triage_accepts_corrected_result() -> None:
    engine, db = create_session()
    try:
        original_triage = {
            'issue_type': 'API',
            'subtype': 'authentication',
            'severity': 'medium',
            'confidence': 0.72,
            'reason': 'Initial suggestion.',
        }
        corrected_triage = {
            'issue_type': 'Integration',
            'subtype': 'credential-rotation',
            'severity': 'high',
            'confidence': 1.0,
            'reason': 'Confirmed by the delivery engineer.',
        }

        agent_run, _ = add_waiting_run(
            db,
            waiting_status='waiting_for_triage_confirmation',
            state_json={
                'triage_result': original_triage,
                'triage_confirmed': False,
            },
        )

        resumed_run, resumed_step = (
            AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=agent_run.run_id,
                triage_result=corrected_triage,
                resumed_at=RESUMED_AT,
            )
        )
        db.commit()

        assert_resumed_run(resumed_run, resumed_step)
        assert resumed_run.state_json['triage_result'] == corrected_triage
        assert resumed_run.state_json['triage_confirmed'] is True
    finally:
        close_session(engine, db)


def test_clarification_response_is_trimmed() -> None:
    engine, db = create_session()
    try:
        question = 'Which credential was rotated?'
        agent_run, old_step = add_waiting_run(
            db,
            waiting_status='waiting_for_clarification',
            state_json={
                'clarification_question': question,
                'triage_confirmed': True,
            },
        )

        resumed_run, resumed_step = (
            AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=agent_run.run_id,
                clarification_response='  The client secret was rotated.  ',
                resumed_at=RESUMED_AT,
            )
        )
        db.commit()

        assert_resumed_run(resumed_run, resumed_step)
        assert (
            resumed_run.state_json['clarification_response']
            == 'The client secret was rotated.'
        )
        assert resumed_run.state_json['clarification_question'] == question
        assert old_step.step_status == 'interrupted'
    finally:
        close_session(engine, db)


def test_blank_clarification_is_rejected() -> None:
    engine, db = create_session()
    try:
        agent_run, _ = add_waiting_run(
            db,
            waiting_status='waiting_for_clarification',
            state_json={
                'clarification_question': 'Provide the missing detail.',
            },
        )
        run_id = agent_run.run_id
        run_pk = agent_run.id

        assert_value_error(
            lambda: AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=run_id,
                clarification_response='   ',
                resumed_at=RESUMED_AT,
            ),
            'Clarification response must be nonblank',
        )
        db.rollback()
        db.expire_all()

        persisted_run = db.get(AgentRun, run_pk)
        assert persisted_run is not None
        assert persisted_run.run_status == 'waiting_for_clarification'
        assert persisted_run.step_count == 1
        assert persisted_run.waiting_since == INTERRUPTED_AT
        assert persisted_run.resume_node == 'route_investigation'
        assert len(load_steps(db, run_pk)) == 1
    finally:
        close_session(engine, db)


def test_missing_triage_result_is_rejected() -> None:
    engine, db = create_session()
    try:
        agent_run, _ = add_waiting_run(
            db,
            waiting_status='waiting_for_triage_confirmation',
            state_json={
                'triage_confirmed': False,
            },
        )

        assert_value_error(
            lambda: AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=agent_run.run_id,
                resumed_at=RESUMED_AT,
            ),
            'Triage confirmation requires a nonempty triage result',
        )
        db.rollback()

        persisted_run = db.get(AgentRun, agent_run.id)
        assert persisted_run is not None
        assert (
            persisted_run.run_status
            == 'waiting_for_triage_confirmation'
        )
        assert persisted_run.step_count == 1
    finally:
        close_session(engine, db)


def test_wrong_payload_types_are_rejected() -> None:
    engine, db = create_session()
    try:
        triage_run, _ = add_waiting_run(
            db,
            waiting_status='waiting_for_triage_confirmation',
            state_json={
                'triage_result': {'issue_type': 'API'},
            },
        )

        assert_value_error(
            lambda: AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=triage_run.run_id,
                clarification_response='not allowed',
                resumed_at=RESUMED_AT,
            ),
            'Clarification response is not valid',
        )
        db.rollback()
    finally:
        close_session(engine, db)

    engine, db = create_session()
    try:
        clarification_run, _ = add_waiting_run(
            db,
            waiting_status='waiting_for_clarification',
            state_json={
                'clarification_question': 'What changed?',
            },
        )

        assert_value_error(
            lambda: AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=clarification_run.run_id,
                triage_result={'issue_type': 'API'},
                clarification_response='A valid response',
                resumed_at=RESUMED_AT,
            ),
            'Triage result is not valid',
        )
        db.rollback()
    finally:
        close_session(engine, db)


def test_nonwaiting_run_is_rejected() -> None:
    engine, db = create_session()
    try:
        agent_run, _ = add_waiting_run(
            db,
            waiting_status='waiting_for_triage_confirmation',
            state_json={
                'triage_result': {'issue_type': 'API'},
            },
        )

        agent_run.run_status = 'running'
        agent_run.current_node = 'route_investigation'
        agent_run.waiting_since = None
        agent_run.resume_node = None
        db.commit()

        assert_value_error(
            lambda: AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=agent_run.run_id,
                resumed_at=RESUMED_AT,
            ),
            'Agent run cannot resume investigation from status',
        )
        db.rollback()

        assert len(load_steps(db, agent_run.id)) == 1
    finally:
        close_session(engine, db)


def test_latest_step_must_be_interrupted() -> None:
    engine, db = create_session()
    try:
        agent_run, latest_step = add_waiting_run(
            db,
            waiting_status='waiting_for_clarification',
            state_json={
                'clarification_question': 'What changed?',
            },
        )

        latest_step.step_status = 'completed'
        db.commit()

        assert_value_error(
            lambda: AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=agent_run.run_id,
                clarification_response='The secret changed.',
                resumed_at=RESUMED_AT,
            ),
            'latest step must be interrupted',
        )
        db.rollback()

        assert len(load_steps(db, agent_run.id)) == 1
    finally:
        close_session(engine, db)


def test_duplicate_resume_is_rejected() -> None:
    engine, db = create_session()
    try:
        agent_run, _ = add_waiting_run(
            db,
            waiting_status='waiting_for_triage_confirmation',
            state_json={
                'triage_result': {'issue_type': 'API'},
            },
        )

        service = AgentPersistenceService()
        service.resume_waiting_investigation_run_and_append_step(
            db,
            run_id=agent_run.run_id,
            resumed_at=RESUMED_AT,
        )
        db.commit()

        assert_value_error(
            lambda: service
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=agent_run.run_id,
                resumed_at=RESUMED_AT,
            ),
            'Agent run cannot resume investigation from status',
        )
        db.rollback()

        persisted_run = db.get(AgentRun, agent_run.id)
        assert persisted_run is not None
        assert persisted_run.run_status == 'running'
        assert persisted_run.step_count == 2
        assert len(load_steps(db, agent_run.id)) == 2
    finally:
        close_session(engine, db)


def test_successful_resume_can_be_rolled_back() -> None:
    engine, db = create_session()
    try:
        agent_run, _ = add_waiting_run(
            db,
            waiting_status='waiting_for_clarification',
            state_json={
                'clarification_question': 'What changed?',
            },
        )
        run_pk = agent_run.id

        resumed_run, resumed_step = (
            AgentPersistenceService()
            .resume_waiting_investigation_run_and_append_step(
                db,
                run_id=agent_run.run_id,
                clarification_response='The client secret changed.',
                resumed_at=RESUMED_AT,
            )
        )

        assert resumed_run.run_status == 'running'
        assert resumed_step.id is not None
        assert len(load_steps(db, run_pk)) == 2

        db.rollback()
        db.expire_all()

        persisted_run = db.get(AgentRun, run_pk)
        assert persisted_run is not None
        assert persisted_run.run_status == 'waiting_for_clarification'
        assert persisted_run.current_node == 'request_clarification'
        assert persisted_run.step_count == 1
        assert persisted_run.waiting_since == INTERRUPTED_AT
        assert persisted_run.resume_node == 'route_investigation'
        assert 'clarification_response' not in persisted_run.state_json
        assert len(load_steps(db, run_pk)) == 1
    finally:
        close_session(engine, db)




def test_missing_run_is_rejected() -> None:
    engine, db = create_session()
    try:
        run_id = 'missing-agent-run'

        try:
            AgentPersistenceService().resume_waiting_investigation_run_and_append_step(
                db,
                run_id=run_id,
                resumed_at=RESUMED_AT,
            )
        except LookupError as exc:
            assert str(exc) == (
                f'Agent run not found: {run_id}'
            )
        else:
            raise AssertionError(
                'Expected missing Agent run LookupError'
            )

        db.rollback()

        assert list(
            db.scalars(
                select(AgentRun)
            ).all()
        ) == []

        assert list(
            db.scalars(
                select(AgentStep)
            ).all()
        ) == []
    finally:
        close_session(engine, db)


def test_active_tool_calls_block_resume() -> None:
    for call_status in (
        'created',
        'running',
    ):
        engine, db = create_session()
        try:
            agent_run, interrupted_step = add_waiting_run(
                db,
                waiting_status='waiting_for_clarification',
                state_json={
                    'clarification_question': (
                        'Which credential changed?'
                    ),
                },
            )

            run_id = agent_run.run_id
            run_pk = agent_run.id
            step_pk = interrupted_step.id

            tool_call = AgentToolCall(
                agent_step_id=interrupted_step.id,
                tool_call_index=1,
                tool_name='search_knowledge',
                tool_version='v1',
                call_status=call_status,
                arguments_json={
                    'query': 'credential rotation',
                },
                read_only=True,
                requires_approval=False,
                timeout_seconds=30,
                started_at=(
                    STARTED_AT
                    if call_status == 'running'
                    else None
                ),
            )

            agent_run.tool_call_count = 1
            db.add(tool_call)
            db.commit()
            db.refresh(tool_call)

            tool_call_pk = tool_call.id

            assert_value_error(
                lambda: AgentPersistenceService()
                .resume_waiting_investigation_run_and_append_step(
                    db,
                    run_id=run_id,
                    clarification_response=(
                        'The client secret changed.'
                    ),
                    resumed_at=RESUMED_AT,
                ),
                (
                    'Interrupted Agent step contains '
                    'active tool calls'
                ),
            )

            db.rollback()
            db.expire_all()

            persisted_run = db.get(
                AgentRun,
                run_pk,
            )
            persisted_step = db.get(
                AgentStep,
                step_pk,
            )
            persisted_tool_call = db.get(
                AgentToolCall,
                tool_call_pk,
            )

            assert persisted_run is not None
            assert persisted_step is not None
            assert persisted_tool_call is not None

            assert (
                persisted_run.run_status
                == 'waiting_for_clarification'
            )
            assert (
                persisted_run.current_node
                == 'request_clarification'
            )
            assert persisted_run.step_count == 1
            assert persisted_run.tool_call_count == 1
            assert (
                persisted_run.waiting_since
                == INTERRUPTED_AT
            )
            assert (
                persisted_run.resume_node
                == 'route_investigation'
            )
            assert (
                'clarification_response'
                not in persisted_run.state_json
            )

            assert (
                persisted_step.step_status
                == 'interrupted'
            )
            assert (
                persisted_step.completed_at
                == INTERRUPTED_AT
            )

            assert (
                persisted_tool_call.call_status
                == call_status
            )
            assert (
                persisted_tool_call.tool_call_index
                == 1
            )

            assert len(
                load_steps(
                    db,
                    run_pk,
                )
            ) == 1
        finally:
            close_session(engine, db)


def test_orchestration_success_commits_and_refreshes() -> None:
    agent_run = AgentRun(
        run_id='orchestration-success',
        issue_id=1,
        graph_version='agent_mvp_v0.1',
        current_node='route_investigation',
        run_status='running',
        step_count=2,
        tool_call_count=0,
        retry_count=0,
        state_json={
            'triage_confirmed': True,
        },
        started_at=STARTED_AT,
    )
    agent_step = AgentStep(
        agent_run_id=1,
        step_index=2,
        node_name='route_investigation',
        step_status='running',
        input_state_json={
            'triage_confirmed': True,
        },
        started_at=RESUMED_AT,
    )

    persistence = SuccessfulResumePersistenceStub(
        agent_run,
        agent_step,
    )
    db = TrackingSession()

    result_run, result_step = AgentOrchestrationService(
        persistence_service=persistence,
    ).resume_waiting_investigation_run(
        db,
        run_id='orchestration-success',
        triage_result={
            'issue_type': 'API',
        },
        resumed_at=RESUMED_AT,
    )

    assert result_run is agent_run
    assert result_step is agent_step
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert db.refreshed == [
        agent_run,
        agent_step,
    ]

    assert len(persistence.calls) == 1
    call = persistence.calls[0]
    assert call['db'] is db
    assert call['run_id'] == 'orchestration-success'
    assert call['triage_result'] == {
        'issue_type': 'API',
    }
    assert call['clarification_response'] is None
    assert call['resumed_at'] == RESUMED_AT


def test_orchestration_failure_rolls_back() -> None:
    persistence = FailingResumePersistenceStub()
    db = TrackingSession()

    try:
        AgentOrchestrationService(
            persistence_service=persistence,
        ).resume_waiting_investigation_run(
            db,
            run_id='orchestration-failure',
            clarification_response='Human response',
            resumed_at=RESUMED_AT,
        )
    except RuntimeError as exc:
        assert str(exc) == (
            'simulated resume persistence failure'
        )
    else:
        raise AssertionError(
            'Expected simulated persistence failure'
        )

    assert persistence.call_count == 1
    assert db.commit_count == 0
    assert db.rollback_count == 1
    assert db.refreshed == []


def main() -> None:
    test_triage_accepts_existing_result()
    test_triage_accepts_corrected_result()
    test_clarification_response_is_trimmed()
    test_blank_clarification_is_rejected()
    test_missing_triage_result_is_rejected()
    test_wrong_payload_types_are_rejected()
    test_nonwaiting_run_is_rejected()
    test_latest_step_must_be_interrupted()
    test_duplicate_resume_is_rejected()
    test_successful_resume_can_be_rolled_back()
    test_missing_run_is_rejected()
    test_active_tool_calls_block_resume()
    test_orchestration_success_commits_and_refreshes()
    test_orchestration_failure_rolls_back()

    print('Agent resume persistence SQLite assertions passed')


if __name__ == '__main__':
    main()