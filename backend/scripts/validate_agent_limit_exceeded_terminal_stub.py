from __future__ import annotations

import ast
import inspect
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.services.agent_orchestration_service import (  # noqa: E402
    AgentOrchestrationService,
)
from app.services.agent_persistence_service import (  # noqa: E402
    AgentPersistenceService,
)


RUN_STARTED_AT = datetime(2026, 7, 28, 10, 0, 0)
STEP_STARTED_AT = datetime(2026, 7, 28, 10, 5, 0)
COMPLETED_AT = datetime(2026, 7, 28, 10, 10, 0)


def build_fixture():
    db = Mock()
    db.scalars.return_value.all.return_value = []

    agent_run = SimpleNamespace(
        id=101,
        run_id='run-limit-101',
        run_status='running',
        current_node='evaluate_evidence',
        state_json={
            'triage_confirmed': True,
            'max_steps': 8,
            'max_tool_calls': 3,
        },
        waiting_since=None,
        resume_node=None,
        error_code='STALE_RUN_ERROR',
        error_message='Stale Run error',
        started_at=RUN_STARTED_AT,
        completed_at=None,
        step_count=7,
        tool_call_count=3,
    )

    agent_step = SimpleNamespace(
        id=707,
        agent_run_id=101,
        step_index=7,
        node_name='evaluate_evidence',
        step_status='running',
        input_state_json=dict(agent_run.state_json),
        output_state_json=None,
        error_code='STALE_STEP_ERROR',
        error_message='Stale Step error',
        started_at=STEP_STARTED_AT,
        completed_at=None,
    )

    service = AgentPersistenceService()
    run_lock = Mock(return_value=agent_run)
    step_lock = Mock(return_value=agent_step)

    service.lock_run_by_run_id = run_lock
    service.lock_step_by_run_and_index = step_lock

    order = Mock()
    order.attach_mock(run_lock, 'run_lock')
    order.attach_mock(step_lock, 'step_lock')
    order.attach_mock(db.scalars, 'active_tool_query')
    order.attach_mock(db.flush, 'flush')

    return service, db, agent_run, agent_step, order


def invoke_success(service, db):
    return service.complete_step_and_limit_run(
        db,
        run_id='run-limit-101',
        step_index=7,
        error_code='  max_tool_calls_reached  ',
        error_message='  Tool budget exhausted.  ',
        state_json={
            'triage_confirmed': True,
            'max_steps': 8,
            'max_tool_calls': 3,
            'evidence_sufficient': False,
        },
        output_state_json={
            'evaluation_version': (
                'agent_evidence_evaluation_v0.1'
            ),
            'evidence_sufficient': False,
        },
        completed_at=COMPLETED_AT,
    )


def assert_transaction_neutral(db: Mock) -> None:
    db.flush.assert_called_once_with()
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.refresh.assert_not_called()
    db.add.assert_not_called()


def test_success_is_controlled_terminal() -> None:
    service, db, run, step, order = build_fixture()
    original_step_count = run.step_count
    original_tool_call_count = run.tool_call_count

    result_run, result_step = invoke_success(
        service,
        db,
    )

    assert result_run is run
    assert result_step is step

    assert run.run_status == 'limit_exceeded'
    assert run.current_node == 'limit_exceeded'
    assert run.error_code == 'max_tool_calls_reached'
    assert run.error_message == 'Tool budget exhausted.'
    assert run.completed_at == COMPLETED_AT
    assert run.waiting_since is None
    assert run.resume_node is None

    assert run.step_count == original_step_count
    assert run.tool_call_count == original_tool_call_count

    snapshot = run.state_json['limit_exceeded']
    assert snapshot == {
        'source_node': 'evaluate_evidence',
        'error_code': 'max_tool_calls_reached',
        'error_message': 'Tool budget exhausted.',
        'step_count': 7,
        'tool_call_count': 3,
    }
    assert run.state_json['evidence_sufficient'] is False

    assert step.step_status == 'completed'
    assert step.error_code is None
    assert step.error_message is None
    assert step.completed_at == COMPLETED_AT
    assert step.output_state_json['next_node'] == (
        'limit_exceeded'
    )
    assert step.output_state_json['source_node'] == (
        'evaluate_evidence'
    )
    assert step.output_state_json['evaluation_version'] == (
        'agent_evidence_evaluation_v0.1'
    )

    call_order = [
        item[0]
        for item in order.mock_calls
    ]
    assert call_order == [
        'run_lock',
        'step_lock',
        'active_tool_query',
        'active_tool_query().all',
        'flush',
    ]

    assert_transaction_neutral(db)


def test_blank_error_contract_rejected_before_lock() -> None:
    for code, message in (
        (None, None),
        ('', ''),
        ('   ', '   '),
    ):
        service, db, _, _, _ = build_fixture()

        try:
            service.complete_step_and_limit_run(
                db,
                run_id='run-limit-101',
                step_index=7,
                error_code=code,
                error_message=message,
                state_json={},
                completed_at=COMPLETED_AT,
            )
        except ValueError as exc:
            assert 'requires error_code or error_message' in str(exc)
        else:
            raise AssertionError(
                'Blank terminal error should fail'
            )

        service.lock_run_by_run_id.assert_not_called()
        db.flush.assert_not_called()


def test_missing_run_rejected() -> None:
    service, db, _, _, _ = build_fixture()
    service.lock_run_by_run_id.return_value = None

    try:
        invoke_success(service, db)
    except LookupError as exc:
        assert 'Agent run not found' in str(exc)
    else:
        raise AssertionError('Missing Run should fail')

    db.flush.assert_not_called()


def test_run_status_must_be_running() -> None:
    for status in (
        'created',
        'waiting_for_clarification',
        'completed',
        'failed',
        'cancelled',
        'limit_exceeded',
    ):
        service, db, run, _, _ = build_fixture()
        run.run_status = status

        try:
            invoke_success(service, db)
        except ValueError as exc:
            assert 'cannot reach limit_exceeded' in str(exc)
        else:
            raise AssertionError(
                f'Run status should fail: {status}'
            )

        db.flush.assert_not_called()


def test_latest_step_is_required() -> None:
    service, db, run, _, _ = build_fixture()
    run.step_count = 8

    try:
        invoke_success(service, db)
    except ValueError as exc:
        assert 'Only the latest Agent step' in str(exc)
    else:
        raise AssertionError('Stale Step should fail')

    service.lock_step_by_run_and_index.assert_not_called()
    db.flush.assert_not_called()


def test_normalized_current_node_is_required() -> None:
    for node in (None, '', ' evaluate_evidence '):
        service, db, run, _, _ = build_fixture()
        run.current_node = node

        try:
            invoke_success(service, db)
        except ValueError as exc:
            assert 'normalized current_node' in str(exc)
        else:
            raise AssertionError(
                f'Invalid node should fail: {node!r}'
            )

        db.flush.assert_not_called()


def test_missing_step_rejected() -> None:
    service, db, _, _, _ = build_fixture()
    service.lock_step_by_run_and_index.return_value = None

    try:
        invoke_success(service, db)
    except LookupError as exc:
        assert 'Agent step not found' in str(exc)
    else:
        raise AssertionError('Missing Step should fail')

    db.flush.assert_not_called()


def test_step_must_be_running() -> None:
    for status in (
        'completed',
        'interrupted',
        'failed',
        'cancelled',
    ):
        service, db, _, step, _ = build_fixture()
        step.step_status = status

        try:
            invoke_success(service, db)
        except ValueError as exc:
            assert 'Agent step cannot reach' in str(exc)
        else:
            raise AssertionError(
                f'Step status should fail: {status}'
            )

        db.flush.assert_not_called()


def test_run_and_step_node_must_match() -> None:
    service, db, _, step, _ = build_fixture()
    step.node_name = 'select_tool'

    try:
        invoke_success(service, db)
    except ValueError as exc:
        assert 'node mismatch' in str(exc)
    else:
        raise AssertionError('Node mismatch should fail')

    db.flush.assert_not_called()


def test_active_tool_calls_are_rejected() -> None:
    service, db, _, _, _ = build_fixture()
    db.scalars.return_value.all.return_value = [1]

    try:
        invoke_success(service, db)
    except ValueError as exc:
        assert 'active tool calls' in str(exc)
    else:
        raise AssertionError(
            'Active ToolCall should block terminalization'
        )

    db.flush.assert_not_called()


def test_started_at_contract_is_required() -> None:
    service, db, run, _, _ = build_fixture()
    run.started_at = None

    try:
        invoke_success(service, db)
    except ValueError as exc:
        assert 'run must have started_at' in str(exc)
    else:
        raise AssertionError(
            'Missing Run started_at should fail'
        )

    db.flush.assert_not_called()

    service, db, _, step, _ = build_fixture()
    step.started_at = None

    try:
        invoke_success(service, db)
    except ValueError as exc:
        assert 'step must have started_at' in str(exc)
    else:
        raise AssertionError(
            'Missing Step started_at should fail'
        )

    db.flush.assert_not_called()


def test_completion_time_order_is_enforced() -> None:
    service, db, _, _, _ = build_fixture()

    try:
        service.complete_step_and_limit_run(
            db,
            run_id='run-limit-101',
            step_index=7,
            error_code='max_steps_reached',
            error_message=None,
            state_json={},
            completed_at=datetime(
                2026,
                7,
                28,
                9,
                59,
                59,
            ),
        )
    except ValueError as exc:
        assert 'run completion cannot precede' in str(exc)
    else:
        raise AssertionError(
            'Completion before Run start should fail'
        )

    db.flush.assert_not_called()

    service, db, _, _, _ = build_fixture()

    try:
        service.complete_step_and_limit_run(
            db,
            run_id='run-limit-101',
            step_index=7,
            error_code='max_steps_reached',
            error_message=None,
            state_json={},
            completed_at=datetime(
                2026,
                7,
                28,
                10,
                4,
                59,
            ),
        )
    except ValueError as exc:
        assert 'step completion cannot precede' in str(exc)
    else:
        raise AssertionError(
            'Completion before Step start should fail'
        )

    db.flush.assert_not_called()


def test_default_output_contains_terminal_snapshot() -> None:
    service, db, run, step, _ = build_fixture()

    service.complete_step_and_limit_run(
        db,
        run_id='run-limit-101',
        step_index=7,
        error_code='max_steps_reached',
        error_message=None,
        state_json={'max_steps': 7},
        completed_at=COMPLETED_AT,
    )

    assert step.output_state_json == {
        'next_node': 'limit_exceeded',
        'source_node': 'evaluate_evidence',
        'error_code': 'max_steps_reached',
        'error_message': None,
        'step_count': 7,
        'tool_call_count': 3,
    }
    assert run.state_json['max_steps'] == 7
    assert_transaction_neutral(db)


def test_input_state_is_copied() -> None:
    service, db, run, _, _ = build_fixture()
    state = {
        'max_steps': 7,
        'nested': {'value': 1},
    }

    service.complete_step_and_limit_run(
        db,
        run_id='run-limit-101',
        step_index=7,
        error_code='max_steps_reached',
        error_message=None,
        state_json=state,
        completed_at=COMPLETED_AT,
    )

    assert run.state_json is not state
    state['max_steps'] = 99
    assert run.state_json['max_steps'] == 7


def build_orchestration_service(
    persistence,
) -> AgentOrchestrationService:
    service = object.__new__(
        AgentOrchestrationService
    )
    service._persistence_service = persistence
    return service


def test_orchestration_success_commits_and_refreshes() -> None:
    db = Mock()
    persistence = Mock()
    run = SimpleNamespace(
        run_status='limit_exceeded',
    )
    step = SimpleNamespace(
        step_status='completed',
    )

    persistence.complete_step_and_limit_run.return_value = (
        run,
        step,
    )

    service = build_orchestration_service(
        persistence
    )

    result = service.complete_step_and_limit_run(
        db,
        run_id='run-limit-101',
        step_index=7,
        error_code='max_steps_reached',
        error_message='Step budget exhausted.',
        state_json={'max_steps': 7},
        output_state_json={'reason': 'budget'},
        completed_at=COMPLETED_AT,
    )

    assert result == (run, step)

    persistence.complete_step_and_limit_run.assert_called_once_with(
        db,
        run_id='run-limit-101',
        step_index=7,
        error_code='max_steps_reached',
        error_message='Step budget exhausted.',
        state_json={'max_steps': 7},
        output_state_json={'reason': 'budget'},
        completed_at=COMPLETED_AT,
    )

    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()
    assert db.refresh.call_args_list == [
        call(run),
        call(step),
    ]


def test_orchestration_failure_rolls_back() -> None:
    db = Mock()
    persistence = Mock()
    persistence.complete_step_and_limit_run.side_effect = (
        ValueError('limit conflict')
    )

    service = build_orchestration_service(
        persistence
    )

    try:
        service.complete_step_and_limit_run(
            db,
            run_id='run-limit-101',
            step_index=7,
            error_code='max_steps_reached',
            error_message=None,
            state_json={},
            completed_at=COMPLETED_AT,
        )
    except ValueError as exc:
        assert str(exc) == 'limit conflict'
    else:
        raise AssertionError(
            'Orchestration failure should propagate'
        )

    db.commit.assert_not_called()
    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()


def test_source_contracts() -> None:
    persistence_source = inspect.getsource(
        AgentPersistenceService.complete_step_and_limit_run
    )
    orchestration_source = inspect.getsource(
        AgentOrchestrationService.complete_step_and_limit_run
    )

    assert 'AgentStep(' not in persistence_source
    assert 'db.add(' not in persistence_source
    assert 'db.commit(' not in persistence_source
    assert 'db.rollback(' not in persistence_source
    assert "'limit_exceeded'" in persistence_source
    assert 'active_tool_call_indices' in persistence_source

    assert 'db.commit()' in orchestration_source
    assert 'db.rollback()' in orchestration_source
    assert orchestration_source.count('db.refresh(') == 2

    ast.parse(
        Path(
            AgentPersistenceService
            .complete_step_and_limit_run
            .__code__.co_filename
        ).read_text(encoding='utf-8')
    )


def main() -> None:
    tests = (
        test_success_is_controlled_terminal,
        test_blank_error_contract_rejected_before_lock,
        test_missing_run_rejected,
        test_run_status_must_be_running,
        test_latest_step_is_required,
        test_normalized_current_node_is_required,
        test_missing_step_rejected,
        test_step_must_be_running,
        test_run_and_step_node_must_match,
        test_active_tool_calls_are_rejected,
        test_started_at_contract_is_required,
        test_completion_time_order_is_enforced,
        test_default_output_contains_terminal_snapshot,
        test_input_state_is_copied,
        test_orchestration_success_commits_and_refreshes,
        test_orchestration_failure_rolls_back,
        test_source_contracts,
    )

    for test in tests:
        test()

    print(
        'Agent limit_exceeded terminal assertions passed'
    )
    print(f'passed_count={len(tests)}')


if __name__ == '__main__':
    main()
