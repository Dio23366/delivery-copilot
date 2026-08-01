from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.api import ai as ai_api  # noqa: E402
from app.models import (  # noqa: E402
    AIAnalysisLog,
    AgentRun,
)


def build_analysis(
    *,
    feedback_status: str = 'pending',
):
    return SimpleNamespace(
        id=68,
        issue_id=20,
        feedback_status=feedback_status,
        feedback_note=None,
        edited_output=None,
    )


def build_db(
    *,
    analysis,
    linked_run,
):
    db = Mock()

    analysis_query = Mock()
    analysis_query.filter.return_value.first.\
return_value = analysis

    run_query = Mock()
    run_query.filter.return_value.first.\
return_value = linked_run

    def query_side_effect(model):
        if model is AIAnalysisLog:
            return analysis_query

        if model is AgentRun:
            return run_query

        raise AssertionError(
            f'Unexpected queried model: {model}'
        )

    db.query.side_effect = query_side_effect

    return db


def payload(
    status: str,
    *,
    note: str | None = None,
    edited_output: str | None = None,
):
    values = {
        'feedback_status': status,
    }

    if note is not None:
        values['feedback_note'] = note

    if edited_output is not None:
        values['edited_output'] = edited_output

    return ai_api.AIAnalysisFeedbackPayload(
        **values
    )


def serializer(analysis):
    return {
        'id': analysis.id,
        'feedback_status': (
            analysis.feedback_status
        ),
        'feedback_note': analysis.feedback_note,
        'edited_output': analysis.edited_output,
    }


def test_agent_linked_feedback_uses_orchestration() -> None:
    analysis = build_analysis()
    linked_run = SimpleNamespace(
        id=101,
        analysis_log_id=68,
    )
    db = build_db(
        analysis=analysis,
        linked_run=linked_run,
    )

    finalized_analysis = build_analysis(
        feedback_status='accepted'
    )
    finalized_analysis.feedback_note = 'Reviewed.'

    orchestration = Mock()
    orchestration.finalize_waiting_review_run.\
return_value = (
        linked_run,
        finalized_analysis,
        SimpleNamespace(id=505),
    )

    with (
        patch.object(
            ai_api,
            'agent_orchestration_service',
            orchestration,
        ),
        patch.object(
            ai_api,
            '_serialize_analysis',
            serializer,
        ),
    ):
        result = ai_api.update_analysis_feedback(
            analysis_id=68,
            payload=payload(
                'accepted',
                note='Reviewed.',
            ),
            db=db,
        )

    assert result['feedback_status'] == 'accepted'

    orchestration.finalize_waiting_review_run.\
assert_called_once_with(
        db,
        analysis_id=68,
        feedback_status='accepted',
        feedback_note='Reviewed.',
        edited_output=None,
    )

    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.refresh.assert_not_called()


def test_legacy_feedback_preserves_original_path() -> None:
    analysis = build_analysis()

    db = build_db(
        analysis=analysis,
        linked_run=None,
    )

    orchestration = Mock()

    with (
        patch.object(
            ai_api,
            'agent_orchestration_service',
            orchestration,
        ),
        patch.object(
            ai_api,
            '_serialize_analysis',
            serializer,
        ),
    ):
        result = ai_api.update_analysis_feedback(
            analysis_id=68,
            payload=payload(
                'edited_and_accepted',
                note='  Reviewed.  ',
                edited_output=(
                    '  Human reviewed output.  '
                ),
            ),
            db=db,
        )

    assert (
        result['feedback_status']
        == 'edited_and_accepted'
    )
    assert result['feedback_note'] == 'Reviewed.'
    assert (
        result['edited_output']
        == 'Human reviewed output.'
    )

    orchestration.finalize_waiting_review_run.\
assert_not_called()

    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()
    db.refresh.assert_called_once_with(analysis)


def test_agent_linked_pending_is_rejected() -> None:
    analysis = build_analysis()
    linked_run = SimpleNamespace(id=101)

    db = build_db(
        analysis=analysis,
        linked_run=linked_run,
    )

    orchestration = Mock()

    with patch.object(
        ai_api,
        'agent_orchestration_service',
        orchestration,
    ):
        try:
            ai_api.update_analysis_feedback(
                analysis_id=68,
                payload=payload('pending'),
                db=db,
            )
        except HTTPException as exc:
            assert exc.status_code == 422
            assert 'final feedback status' in exc.detail
        else:
            raise AssertionError(
                'Agent-linked pending should fail'
            )

    orchestration.finalize_waiting_review_run.\
assert_not_called()
    db.commit.assert_not_called()


def test_agent_state_conflict_maps_to_409() -> None:
    analysis = build_analysis()
    linked_run = SimpleNamespace(id=101)

    db = build_db(
        analysis=analysis,
        linked_run=linked_run,
    )

    orchestration = Mock()
    orchestration.finalize_waiting_review_run.\
side_effect = ValueError(
        'Agent run cannot finalize review '
        'from status: completed'
    )

    with patch.object(
        ai_api,
        'agent_orchestration_service',
        orchestration,
    ):
        try:
            ai_api.update_analysis_feedback(
                analysis_id=68,
                payload=payload('accepted'),
                db=db,
            )
        except HTTPException as exc:
            assert exc.status_code == 409
            assert 'cannot finalize review' in exc.detail
        else:
            raise AssertionError(
                'Agent state conflict should fail'
            )

    db.commit.assert_not_called()


def test_agent_database_error_maps_to_500() -> None:
    analysis = build_analysis()
    linked_run = SimpleNamespace(id=101)

    db = build_db(
        analysis=analysis,
        linked_run=linked_run,
    )

    orchestration = Mock()
    orchestration.finalize_waiting_review_run.\
side_effect = SQLAlchemyError(
        'database failure'
    )

    with patch.object(
        ai_api,
        'agent_orchestration_service',
        orchestration,
    ):
        try:
            ai_api.update_analysis_feedback(
                analysis_id=68,
                payload=payload('rejected'),
                db=db,
            )
        except HTTPException as exc:
            assert exc.status_code == 500
            assert 'Final Review' in exc.detail
        else:
            raise AssertionError(
                'Database failure should map to 500'
            )

    db.commit.assert_not_called()


def test_missing_and_duplicate_feedback_guards() -> None:
    missing_db = build_db(
        analysis=None,
        linked_run=None,
    )

    try:
        ai_api.update_analysis_feedback(
            analysis_id=999,
            payload=payload('accepted'),
            db=missing_db,
        )
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError(
            'Missing Analysis should return 404'
        )

    finalized_analysis = build_analysis(
        feedback_status='accepted'
    )

    duplicate_db = build_db(
        analysis=finalized_analysis,
        linked_run=None,
    )

    try:
        ai_api.update_analysis_feedback(
            analysis_id=68,
            payload=payload('rejected'),
            db=duplicate_db,
        )
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError(
            'Duplicate feedback should return 409'
        )


def main() -> None:
    test_agent_linked_feedback_uses_orchestration()
    test_legacy_feedback_preserves_original_path()
    test_agent_linked_pending_is_rejected()
    test_agent_state_conflict_maps_to_409()
    test_agent_database_error_maps_to_500()
    test_missing_and_duplicate_feedback_guards()

    print(
        'Agent feedback API integration '
        'assertions passed'
    )


if __name__ == '__main__':
    main()
