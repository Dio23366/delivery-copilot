from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.services.agent_persistence_service import (  # noqa: E402
    AgentPersistenceService,
)
from app.services.agent_orchestration_service import (  # noqa: E402
    AgentOrchestrationService,
)


STARTED_AT = datetime(2026, 7, 25, 10, 0, 0)
WAITING_AT = datetime(2026, 7, 25, 10, 5, 0)
COMPLETED_AT = datetime(2026, 7, 25, 10, 10, 0)


def build_fixture():
    db = Mock()

    agent_run = SimpleNamespace(
        id=101,
        run_id='run-final-review-101',
        issue_id=20,
        analysis_log_id=68,
        run_status='waiting_for_final_review',
        current_node='await_final_review',
        state_json={
            'analysis_log_id': 68,
            'pending_approval': True,
            'draft_analysis': {
                'summary': 'Original AI output',
            },
        },
        waiting_since=WAITING_AT,
        resume_node='finalize_run',
        started_at=STARTED_AT,
        completed_at=None,
        step_count=4,
        error_code='STALE_RUN_ERROR',
        error_message='Stale Run error',
    )

    analysis = SimpleNamespace(
        id=68,
        issue_id=20,
        feedback_status='pending',
        feedback_note=None,
        edited_output=None,
    )

    interrupted_step = SimpleNamespace(
        id=404,
        agent_run_id=101,
        step_index=4,
        node_name='await_final_review',
        step_status='interrupted',
    )

    service = AgentPersistenceService()

    run_lock = Mock(return_value=agent_run)
    analysis_lock = Mock(return_value=analysis)
    step_lock = Mock(return_value=interrupted_step)

    service.lock_run_by_analysis_id = run_lock
    service.lock_analysis_by_id = analysis_lock
    service.lock_step_by_run_and_index = step_lock

    order = Mock()
    order.attach_mock(run_lock, 'run_lock')
    order.attach_mock(analysis_lock, 'analysis_lock')
    order.attach_mock(step_lock, 'step_lock')
    order.attach_mock(db.add, 'add')
    order.attach_mock(db.flush, 'flush')

    return (
        service,
        db,
        agent_run,
        analysis,
        interrupted_step,
        order,
    )


def assert_transaction_neutral(db: Mock) -> None:
    assert db.flush.call_count == 1
    assert db.commit.call_count == 0
    assert db.rollback.call_count == 0
    assert db.refresh.call_count == 0


def test_accepted_finalizes_run() -> None:
    (
        service,
        db,
        agent_run,
        analysis,
        interrupted_step,
        order,
    ) = build_fixture()

    original_state = agent_run.state_json

    result_run, result_analysis, final_step = (
        service.finalize_waiting_review_run_and_append_step(
            db,
            analysis_id=68,
            feedback_status='accepted',
            feedback_note='  Reviewed and accepted.  ',
            completed_at=COMPLETED_AT,
        )
    )

    assert result_run is agent_run
    assert result_analysis is analysis

    assert analysis.feedback_status == 'accepted'
    assert analysis.feedback_note == 'Reviewed and accepted.'
    assert analysis.edited_output is None

    assert agent_run.run_status == 'completed'
    assert agent_run.current_node == 'finalize_run'
    assert agent_run.waiting_since is None
    assert agent_run.resume_node is None
    assert agent_run.error_code is None
    assert agent_run.error_message is None
    assert agent_run.completed_at == COMPLETED_AT
    assert agent_run.step_count == 5

    assert agent_run.state_json is not original_state
    assert agent_run.state_json['pending_approval'] is False
    assert agent_run.state_json['final_status'] == 'accepted'
    assert agent_run.state_json['analysis_log_id'] == 68

    assert interrupted_step.step_status == 'interrupted'

    assert final_step.agent_run_id == 101
    assert final_step.step_index == 5
    assert final_step.node_name == 'finalize_run'
    assert final_step.step_status == 'completed'
    assert final_step.started_at == COMPLETED_AT
    assert final_step.completed_at == COMPLETED_AT
    assert final_step.input_state_json['pending_approval'] is True
    assert final_step.output_state_json['pending_approval'] is False
    assert final_step.output_state_json['final_status'] == 'accepted'

    call_order = [
        call[0]
        for call in order.mock_calls
    ]
    assert call_order == [
        'run_lock',
        'analysis_lock',
        'step_lock',
        'add',
        'flush',
    ]

    db.add.assert_called_once_with(final_step)
    assert_transaction_neutral(db)


def test_rejected_is_completed_business_outcome() -> None:
    service, db, run, analysis, _, _ = build_fixture()

    result_run, result_analysis, result_step = (
        service.finalize_waiting_review_run_and_append_step(
            db,
            analysis_id=68,
            feedback_status='rejected',
            feedback_note='  Not suitable for customer use. ',
            completed_at=COMPLETED_AT,
        )
    )

    assert result_run is run
    assert result_analysis is analysis
    assert analysis.feedback_status == 'rejected'
    assert run.run_status == 'completed'
    assert run.state_json['final_status'] == 'rejected'
    assert result_step.step_status == 'completed'
    assert_transaction_neutral(db)


def test_edited_and_accepted_trims_output() -> None:
    service, db, run, analysis, _, _ = build_fixture()

    _, _, final_step = (
        service.finalize_waiting_review_run_and_append_step(
            db,
            analysis_id=68,
            feedback_status='edited_and_accepted',
            feedback_note='   ',
            edited_output='  Human reviewed customer update.  ',
            completed_at=COMPLETED_AT,
        )
    )

    assert analysis.feedback_status == 'edited_and_accepted'
    assert analysis.feedback_note is None
    assert (
        analysis.edited_output
        == 'Human reviewed customer update.'
    )
    assert run.state_json['final_status'] == (
        'edited_and_accepted'
    )
    assert final_step.output_state_json['final_status'] == (
        'edited_and_accepted'
    )
    assert_transaction_neutral(db)


def test_invalid_feedback_rejected_before_locking() -> None:
    service, db, _, _, _, _ = build_fixture()

    try:
        service.finalize_waiting_review_run_and_append_step(
            db,
            analysis_id=68,
            feedback_status='pending',
            completed_at=COMPLETED_AT,
        )
    except ValueError as exc:
        assert 'Unsupported final feedback status' in str(exc)
    else:
        raise AssertionError('pending should be rejected')

    service.lock_run_by_analysis_id.assert_not_called()
    db.flush.assert_not_called()


def test_edited_output_is_required() -> None:
    service, db, _, _, _, _ = build_fixture()

    for value in (None, '', '   '):
        try:
            service.finalize_waiting_review_run_and_append_step(
                db,
                analysis_id=68,
                feedback_status='edited_and_accepted',
                edited_output=value,
                completed_at=COMPLETED_AT,
            )
        except ValueError as exc:
            assert 'edited_output is required' in str(exc)
        else:
            raise AssertionError(
                'Blank edited_output should be rejected'
            )

    service.lock_run_by_analysis_id.assert_not_called()
    db.flush.assert_not_called()


def test_missing_run_is_rejected() -> None:
    service, db, _, _, _, _ = build_fixture()
    service.lock_run_by_analysis_id.return_value = None

    try:
        service.finalize_waiting_review_run_and_append_step(
            db,
            analysis_id=68,
            feedback_status='accepted',
            completed_at=COMPLETED_AT,
        )
    except LookupError as exc:
        assert 'Agent run not found for analysis' in str(exc)
    else:
        raise AssertionError('Missing Run should be rejected')

    service.lock_analysis_by_id.assert_not_called()
    db.flush.assert_not_called()


def test_invalid_run_contract_is_rejected() -> None:
    cases = [
        ('run_status', 'running', 'cannot finalize review'),
        ('current_node', 'other_node', 'unexpected final review node'),
        ('waiting_since', None, 'must have waiting_since'),
        ('resume_node', 'route_investigation', 'unexpected final review resume_node'),
        ('step_count', 0, 'must have an interrupted step'),
    ]

    for field, value, expected_message in cases:
        service, db, run, _, _, _ = build_fixture()
        setattr(run, field, value)

        try:
            service.finalize_waiting_review_run_and_append_step(
                db,
                analysis_id=68,
                feedback_status='accepted',
                completed_at=COMPLETED_AT,
            )
        except ValueError as exc:
            assert expected_message in str(exc)
        else:
            raise AssertionError(
                f'Invalid Run field should fail: {field}'
            )

        db.flush.assert_not_called()


def test_missing_analysis_is_rejected() -> None:
    service, db, _, _, _, _ = build_fixture()
    service.lock_analysis_by_id.return_value = None

    try:
        service.finalize_waiting_review_run_and_append_step(
            db,
            analysis_id=68,
            feedback_status='accepted',
            completed_at=COMPLETED_AT,
        )
    except LookupError as exc:
        assert 'AI analysis log not found' in str(exc)
    else:
        raise AssertionError('Missing Analysis should fail')

    service.lock_step_by_run_and_index.assert_not_called()
    db.flush.assert_not_called()


def test_analysis_contract_is_rejected() -> None:
    cases = [
        ('id', 69, 'analysis link changed'),
        ('issue_id', 999, 'issue mismatch'),
        ('feedback_status', 'accepted', 'already been finalized'),
    ]

    for field, value, expected_message in cases:
        service, db, _, analysis, _, _ = build_fixture()
        setattr(analysis, field, value)

        try:
            service.finalize_waiting_review_run_and_append_step(
                db,
                analysis_id=68,
                feedback_status='accepted',
                completed_at=COMPLETED_AT,
            )
        except ValueError as exc:
            assert expected_message in str(exc)
        else:
            raise AssertionError(
                f'Invalid Analysis field should fail: {field}'
            )

        service.lock_step_by_run_and_index.assert_not_called()
        db.flush.assert_not_called()


def test_final_review_step_contract_is_rejected() -> None:
    cases = [
        ('node_name', 'generate_analysis', 'not await_final_review'),
        ('step_status', 'completed', 'must be interrupted'),
    ]

    for field, value, expected_message in cases:
        service, db, _, _, step, _ = build_fixture()
        setattr(step, field, value)

        try:
            service.finalize_waiting_review_run_and_append_step(
                db,
                analysis_id=68,
                feedback_status='accepted',
                completed_at=COMPLETED_AT,
            )
        except ValueError as exc:
            assert expected_message in str(exc)
        else:
            raise AssertionError(
                f'Invalid Step field should fail: {field}'
            )

        db.flush.assert_not_called()


def test_missing_final_review_step_is_rejected() -> None:
    service, db, _, _, _, _ = build_fixture()
    service.lock_step_by_run_and_index.return_value = None

    try:
        service.finalize_waiting_review_run_and_append_step(
            db,
            analysis_id=68,
            feedback_status='accepted',
            completed_at=COMPLETED_AT,
        )
    except LookupError as exc:
        assert 'Final review Agent step not found' in str(exc)
    else:
        raise AssertionError('Missing Step should fail')

    db.flush.assert_not_called()


def test_completion_time_order_is_enforced() -> None:
    for invalid_time in (
        datetime(2026, 7, 25, 9, 59, 59),
        datetime(2026, 7, 25, 10, 4, 59),
    ):
        service, db, _, _, _, _ = build_fixture()

        try:
            service.finalize_waiting_review_run_and_append_step(
                db,
                analysis_id=68,
                feedback_status='accepted',
                completed_at=invalid_time,
            )
        except ValueError as exc:
            assert 'cannot precede' in str(exc)
        else:
            raise AssertionError(
                'Invalid completion time should fail'
            )

        db.flush.assert_not_called()


def test_duplicate_finalization_is_rejected() -> None:
    service, db, run, _, _, _ = build_fixture()
    run.run_status = 'completed'
    run.waiting_since = None
    run.resume_node = None

    try:
        service.finalize_waiting_review_run_and_append_step(
            db,
            analysis_id=68,
            feedback_status='accepted',
            completed_at=COMPLETED_AT,
        )
    except ValueError as exc:
        assert 'cannot finalize review from status' in str(exc)
    else:
        raise AssertionError(
            'Duplicate finalization should be rejected'
        )

    db.flush.assert_not_called()


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

    agent_run = SimpleNamespace(
        id=101,
        run_status='completed',
    )
    analysis = SimpleNamespace(
        id=68,
        feedback_status='accepted',
    )
    finalized_step = SimpleNamespace(
        id=505,
        step_status='completed',
    )

    persistence_method = (
        persistence
        .finalize_waiting_review_run_and_append_step
    )
    persistence_method.return_value = (
        agent_run,
        analysis,
        finalized_step,
    )

    service = build_orchestration_service(
        persistence
    )

    result = service.finalize_waiting_review_run(
        db,
        analysis_id=68,
        feedback_status='accepted',
        feedback_note='Reviewed.',
        completed_at=COMPLETED_AT,
    )

    assert result == (
        agent_run,
        analysis,
        finalized_step,
    )

    persistence_method.assert_called_once_with(
        db,
        analysis_id=68,
        feedback_status='accepted',
        feedback_note='Reviewed.',
        edited_output=None,
        completed_at=COMPLETED_AT,
    )

    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()

    assert db.refresh.call_args_list == [
        call(agent_run),
        call(analysis),
        call(finalized_step),
    ]


def test_orchestration_failure_rolls_back() -> None:
    db = Mock()
    persistence = Mock()

    persistence_method = (
        persistence
        .finalize_waiting_review_run_and_append_step
    )
    persistence_method.side_effect = ValueError(
        'Final Review conflict'
    )

    service = build_orchestration_service(
        persistence
    )

    try:
        service.finalize_waiting_review_run(
            db,
            analysis_id=68,
            feedback_status='accepted',
            completed_at=COMPLETED_AT,
        )
    except ValueError as exc:
        assert str(exc) == 'Final Review conflict'
    else:
        raise AssertionError(
            'Orchestration failure should propagate'
        )

    db.commit.assert_not_called()
    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()


def main() -> None:
    test_accepted_finalizes_run()
    test_rejected_is_completed_business_outcome()
    test_edited_and_accepted_trims_output()
    test_invalid_feedback_rejected_before_locking()
    test_edited_output_is_required()
    test_missing_run_is_rejected()
    test_invalid_run_contract_is_rejected()
    test_missing_analysis_is_rejected()
    test_analysis_contract_is_rejected()
    test_final_review_step_contract_is_rejected()
    test_missing_final_review_step_is_rejected()
    test_completion_time_order_is_enforced()
    test_duplicate_finalization_is_rejected()
    test_orchestration_success_commits_and_refreshes()
    test_orchestration_failure_rolls_back()

    print(
        'Agent final review persistence assertions passed'
    )


if __name__ == '__main__':
    main()
