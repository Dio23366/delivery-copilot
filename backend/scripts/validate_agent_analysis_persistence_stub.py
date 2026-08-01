from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.services.agent_orchestration_service import (  # noqa: E402
    AgentOrchestrationService,
)
from app.services.agent_persistence_service import (  # noqa: E402
    AGENT_ANALYSIS_PERSISTENCE_VERSION,
    AgentPersistenceService,
)


COMPLETED_AT = datetime(2026, 7, 28, 12, 0, 0)
FINAL_REVIEW_STARTED_AT = datetime(
    2026,
    7,
    28,
    12,
    0,
    1,
)


def citation() -> dict[str, object]:
    return {
        'citation_id': 'K1',
        'rank': 1,
        'chunk_id': 11,
        'document_id': 3,
        'document_title': 'API Authentication Guide',
        'scope_type': 'global',
        'doc_type': 'troubleshooting_guide',
        'source_kind': 'knowledge_base',
        'source_name': 'Delivery Knowledge',
        'source_uri': None,
        'chunk_index': 0,
        'chunk_text': 'Refresh the service token.',
        'similarity_score': 0.93,
    }


def generated_analysis() -> dict[str, object]:
    return {
        'generation_version': (
            'agent_analysis_generation_v0.1'
        ),
        'analysis_type': 'issue_summarizer',
        'provider': 'llm',
        'model_name': 'gpt-test',
        'prompt_version': (
            'issue_summarizer_v4_grounded'
        ),
        'provider_fallback_reason': None,
        'issue_summary': 'Authentication requests fail.',
        'possible_root_cause': 'The token expired.',
        'recommended_actions': [
            'Refresh the service token.',
            'Confirm authentication recovery.',
        ],
        'customer_update_draft': (
            'We identified an expired token.'
        ),
        'risk_level': 'high',
        'project_impact': 'Deployment is blocked.',
        'retrieval_status': 'succeeded',
        'retrieval_query': (
            'authentication token expired'
        ),
        'knowledge_citations': [citation()],
        'retrieval_error_code': None,
        'supplemental_evidence_count': 2,
    }


class FakeSession:
    def __init__(
        self,
        *,
        assign_analysis_id: bool = True,
    ) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.refreshed: list[object] = []
        self.assign_analysis_id = assign_analysis_id
        self.events: list[str] = []

    def add(self, value: object) -> None:
        self.added.append(value)
        self.events.append(
            f'add:{type(value).__name__}'
        )

    def flush(self) -> None:
        self.flush_count += 1
        self.events.append('flush')

        if not self.assign_analysis_id:
            return

        for value in self.added:
            if (
                type(value).__name__ == 'AIAnalysisLog'
                and getattr(value, 'id', None) is None
            ):
                value.id = 68

    def commit(self) -> None:
        self.commit_count += 1
        self.events.append('commit')

    def rollback(self) -> None:
        self.rollback_count += 1
        self.events.append('rollback')

    def refresh(self, value: object) -> None:
        self.refreshed.append(value)
        self.events.append(
            f'refresh:{type(value).__name__}'
        )


def fixture(
    *,
    assign_analysis_id: bool = True,
):
    state = {
        'issue_id': 17,
        'generated_analysis': generated_analysis(),
        'evidence_sufficient': True,
    }
    run = SimpleNamespace(
        id=101,
        run_id='run-persist-101',
        issue_id=17,
        analysis_log_id=None,
        run_status='running',
        current_node='persist_analysis',
        state_json=deepcopy(state),
        step_count=6,
        waiting_since=None,
        resume_node=None,
        error_code='STALE_ERROR',
        error_message='Stale error',
        completed_at=None,
    )
    step = SimpleNamespace(
        id=606,
        agent_run_id=101,
        step_index=6,
        node_name='persist_analysis',
        step_status='running',
        input_state_json=deepcopy(state),
        output_state_json=None,
        error_code='STALE_STEP',
        error_message='Stale step error',
        started_at=COMPLETED_AT,
        completed_at=None,
    )
    db = FakeSession(
        assign_analysis_id=assign_analysis_id,
    )
    service = AgentPersistenceService.__new__(
        AgentPersistenceService
    )
    service.lock_run_by_run_id = Mock(
        return_value=run
    )
    service.lock_step_by_run_and_index = Mock(
        return_value=step
    )
    return service, db, run, step, state


def call_persistence(
    service: AgentPersistenceService,
    db: FakeSession,
):
    return (
        service
        .persist_generated_analysis_and_advance_to_final_review(
            db,
            run_id='run-persist-101',
            step_index=6,
            completed_at=COMPLETED_AT,
            final_review_started_at=(
                FINAL_REVIEW_STARTED_AT
            ),
        )
    )


def assert_raises(
    expected_type: type[BaseException],
    expected_text: str,
    callback,
) -> None:
    try:
        callback()
    except expected_type as exc:
        assert expected_text in str(exc)
        return

    raise AssertionError(
        f'Expected {expected_type.__name__}: '
        f'{expected_text}'
    )


def test_successful_atomic_transition() -> None:
    service, db, run, step, _ = fixture()

    (
        result_run,
        completed_step,
        analysis,
        final_review_step,
    ) = call_persistence(service, db)

    assert result_run is run
    assert completed_step is step
    assert analysis.id == 68
    assert analysis.issue_id == 17
    assert analysis.feedback_status == 'pending'

    assert step.step_status == 'completed'
    assert step.completed_at == COMPLETED_AT
    assert step.error_code is None
    assert step.error_message is None
    assert step.output_state_json == {
        'persistence_version': (
            AGENT_ANALYSIS_PERSISTENCE_VERSION
        ),
        'analysis_log_id': 68,
        'feedback_status': 'pending',
        'next_node': 'final_review',
    }

    assert run.analysis_log_id == 68
    assert run.run_status == 'generating_analysis'
    assert run.current_node == 'final_review'
    assert run.step_count == 7
    assert run.waiting_since is None
    assert run.resume_node is None
    assert run.error_code is None
    assert run.error_message is None
    assert run.completed_at is None
    assert run.state_json['analysis_log_id'] == 68
    assert run.state_json['pending_approval'] is True
    assert (
        run.state_json['generated_analysis']
        == generated_analysis()
    )

    assert final_review_step.step_index == 7
    assert final_review_step.node_name == 'final_review'
    assert final_review_step.step_status == 'running'
    assert (
        final_review_step.input_state_json
        == run.state_json
    )
    assert (
        final_review_step.started_at
        == FINAL_REVIEW_STARTED_AT
    )


def test_analysis_field_mapping_and_json() -> None:
    service, db, _, _, _ = fixture()

    _, _, analysis, _ = call_persistence(
        service,
        db,
    )

    payload = generated_analysis()
    assert analysis.analysis_type == (
        payload['analysis_type']
    )
    assert analysis.provider == payload['provider']
    assert analysis.model_name == payload['model_name']
    assert (
        analysis.prompt_version
        == payload['prompt_version']
    )
    assert (
        json.loads(
            analysis.recommended_actions_json
        )
        == payload['recommended_actions']
    )
    assert (
        json.loads(
            analysis.knowledge_citations_json
        )
        == payload['knowledge_citations']
    )


def test_input_state_is_not_mutated() -> None:
    service, db, run, step, original = fixture()
    original_run_state = run.state_json
    original_step_input = step.input_state_json
    frozen_original = deepcopy(original)

    call_persistence(service, db)

    assert original == frozen_original
    assert original_run_state == frozen_original
    assert original_step_input == frozen_original
    assert run.state_json is not original_run_state


def test_persistence_is_transaction_neutral() -> None:
    service, db, _, _, _ = fixture()
    call_persistence(service, db)

    assert db.flush_count == 2
    assert db.commit_count == 0
    assert db.rollback_count == 0
    assert db.refreshed == []
    assert db.events == [
        'add:AIAnalysisLog',
        'flush',
        'add:AgentStep',
        'flush',
    ]


def test_lock_order_run_then_step() -> None:
    service, db, _, _, _ = fixture()
    order: list[str] = []

    run_lock = service.lock_run_by_run_id
    step_lock = service.lock_step_by_run_and_index

    service.lock_run_by_run_id = Mock(
        side_effect=lambda *args, **kwargs: (
            order.append('run'),
            run_lock(*args, **kwargs),
        )[1]
    )
    service.lock_step_by_run_and_index = Mock(
        side_effect=lambda *args, **kwargs: (
            order.append('step'),
            step_lock(*args, **kwargs),
        )[1]
    )

    call_persistence(service, db)
    assert order == ['run', 'step']


def test_missing_run_rejected() -> None:
    service, db, _, _, _ = fixture()
    service.lock_run_by_run_id.return_value = None

    assert_raises(
        LookupError,
        'Agent run not found',
        lambda: call_persistence(service, db),
    )


def test_wrong_run_status_rejected() -> None:
    service, db, run, _, _ = fixture()
    run.run_status = 'generating_analysis'

    assert_raises(
        ValueError,
        'cannot persist analysis from status',
        lambda: call_persistence(service, db),
    )


def test_wrong_run_node_rejected() -> None:
    service, db, run, _, _ = fixture()
    run.current_node = 'generate_analysis'

    assert_raises(
        ValueError,
        'unexpected persistence node',
        lambda: call_persistence(service, db),
    )


def test_stale_step_index_rejected() -> None:
    service, db, run, _, _ = fixture()
    run.step_count = 7

    assert_raises(
        ValueError,
        'Only the latest Agent step',
        lambda: call_persistence(service, db),
    )


def test_existing_analysis_link_rejected_before_add() -> None:
    service, db, run, _, _ = fixture()
    run.analysis_log_id = 67

    assert_raises(
        ValueError,
        'already has an analysis_log_id',
        lambda: call_persistence(service, db),
    )
    assert db.added == []


def test_missing_step_rejected() -> None:
    service, db, _, _, _ = fixture()
    service.lock_step_by_run_and_index.return_value = None

    assert_raises(
        LookupError,
        'Agent step not found',
        lambda: call_persistence(service, db),
    )


def test_wrong_step_status_rejected() -> None:
    service, db, _, step, _ = fixture()
    step.step_status = 'completed'

    assert_raises(
        ValueError,
        'Step must be running',
        lambda: call_persistence(service, db),
    )


def test_wrong_step_node_rejected() -> None:
    service, db, _, step, _ = fixture()
    step.node_name = 'generate_analysis'

    assert_raises(
        ValueError,
        'unexpected persistence node',
        lambda: call_persistence(service, db),
    )


def test_state_snapshot_mismatch_rejected() -> None:
    service, db, _, step, _ = fixture()
    step.input_state_json = {
        'different': True,
    }

    assert_raises(
        ValueError,
        'state snapshot does not match',
        lambda: call_persistence(service, db),
    )


def test_missing_generated_analysis_rejected() -> None:
    service, db, run, step, _ = fixture()
    run.state_json.pop('generated_analysis')
    step.input_state_json = deepcopy(
        run.state_json
    )

    assert_raises(
        ValueError,
        'must contain generated_analysis',
        lambda: call_persistence(service, db),
    )


def test_generated_field_drift_rejected() -> None:
    service, db, run, step, _ = fixture()
    run.state_json[
        'generated_analysis'
    ]['unexpected'] = True
    step.input_state_json = deepcopy(
        run.state_json
    )

    assert_raises(
        ValueError,
        'fields do not match',
        lambda: call_persistence(service, db),
    )


def test_controlled_values_rejected() -> None:
    cases = (
        ('provider', 'unknown', 'provider'),
        ('risk_level', 'urgent', 'risk_level'),
        (
            'retrieval_status',
            'partial',
            'retrieval_status',
        ),
    )

    for field_name, value, expected in cases:
        service, db, run, step, _ = fixture()
        run.state_json[
            'generated_analysis'
        ][field_name] = value
        step.input_state_json = deepcopy(
            run.state_json
        )

        assert_raises(
            ValueError,
            expected,
            lambda: call_persistence(
                service,
                db,
            ),
        )


def test_action_and_citation_contracts() -> None:
    service, db, run, step, _ = fixture()
    run.state_json[
        'generated_analysis'
    ]['recommended_actions'] = []
    step.input_state_json = deepcopy(
        run.state_json
    )

    assert_raises(
        ValueError,
        'must not be empty',
        lambda: call_persistence(service, db),
    )

    service, db, run, step, _ = fixture()
    run.state_json[
        'generated_analysis'
    ]['knowledge_citations'][0].pop(
        'chunk_id'
    )
    step.input_state_json = deepcopy(
        run.state_json
    )

    assert_raises(
        ValueError,
        'citation fields',
        lambda: call_persistence(service, db),
    )


def test_nonfinite_json_rejected() -> None:
    service, db, run, step, _ = fixture()
    run.state_json[
        'generated_analysis'
    ]['knowledge_citations'][0][
        'similarity_score'
    ] = math.nan
    step.input_state_json = deepcopy(
        run.state_json
    )

    assert_raises(
        ValueError,
        'must be JSON serializable',
        lambda: call_persistence(service, db),
    )


def test_final_review_time_order_rejected() -> None:
    service, db, _, _, _ = fixture()

    assert_raises(
        ValueError,
        'cannot start before',
        lambda: (
            service
            .persist_generated_analysis_and_advance_to_final_review(
                db,
                run_id='run-persist-101',
                step_index=6,
                completed_at=FINAL_REVIEW_STARTED_AT,
                final_review_started_at=COMPLETED_AT,
            )
        ),
    )


def test_missing_database_id_rejected() -> None:
    service, db, _, _, _ = fixture(
        assign_analysis_id=False
    )

    assert_raises(
        RuntimeError,
        'positive integer id',
        lambda: call_persistence(service, db),
    )
    assert len(db.added) == 1


def test_orchestration_commit_and_refresh() -> None:
    persistence = Mock()
    run = SimpleNamespace()
    completed_step = SimpleNamespace()
    analysis = SimpleNamespace()
    final_review_step = SimpleNamespace()

    persistence.persist_generated_analysis_and_advance_to_final_review.return_value = (
        run,
        completed_step,
        analysis,
        final_review_step,
    )
    service = AgentOrchestrationService(
        persistence_service=persistence
    )
    db = FakeSession()

    result = (
        service
        .persist_generated_analysis_and_advance_to_final_review(
            db,
            run_id='run-persist-101',
            step_index=6,
            completed_at=COMPLETED_AT,
            final_review_started_at=(
                FINAL_REVIEW_STARTED_AT
            ),
        )
    )

    assert result == (
        run,
        completed_step,
        analysis,
        final_review_step,
    )
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert db.refreshed == [
        run,
        completed_step,
        analysis,
        final_review_step,
    ]


def test_orchestration_rolls_back() -> None:
    persistence = Mock()
    persistence.persist_generated_analysis_and_advance_to_final_review.side_effect = RuntimeError(
        'boom'
    )
    service = AgentOrchestrationService(
        persistence_service=persistence
    )
    db = FakeSession()

    assert_raises(
        RuntimeError,
        'boom',
        lambda: (
            service
            .persist_generated_analysis_and_advance_to_final_review(
                db,
                run_id='run-persist-101',
                step_index=6,
            )
        ),
    )

    assert db.commit_count == 0
    assert db.rollback_count == 1
    assert db.refreshed == []


TESTS = (
    test_successful_atomic_transition,
    test_analysis_field_mapping_and_json,
    test_input_state_is_not_mutated,
    test_persistence_is_transaction_neutral,
    test_lock_order_run_then_step,
    test_missing_run_rejected,
    test_wrong_run_status_rejected,
    test_wrong_run_node_rejected,
    test_stale_step_index_rejected,
    test_existing_analysis_link_rejected_before_add,
    test_missing_step_rejected,
    test_wrong_step_status_rejected,
    test_wrong_step_node_rejected,
    test_state_snapshot_mismatch_rejected,
    test_missing_generated_analysis_rejected,
    test_generated_field_drift_rejected,
    test_controlled_values_rejected,
    test_action_and_citation_contracts,
    test_nonfinite_json_rejected,
    test_final_review_time_order_rejected,
    test_missing_database_id_rejected,
    test_orchestration_commit_and_refresh,
    test_orchestration_rolls_back,
)


def main() -> None:
    for test in TESTS:
        test()

    print(
        'Agent analysis persistence assertions passed '
        f'{len(TESTS)}/{len(TESTS)}'
    )


if __name__ == '__main__':
    main()
