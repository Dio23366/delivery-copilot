import json
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.analysis_service import analysis_service
from app.ai.mock_ai import (
    mock_customer_update_draft,
    mock_issue_summary,
    mock_requirement_parse,
    mock_risk_analysis,
)
from app.database import get_db
from app.models import AIAnalysisLog, AgentRun
from app.services.agent_orchestration_service import agent_orchestration_service

router = APIRouter()

ALLOWED_FEEDBACK_STATUSES = {'pending', 'accepted', 'rejected', 'edited_and_accepted'}
FINAL_FEEDBACK_STATUSES = {'accepted', 'rejected', 'edited_and_accepted'}


class TextPayload(BaseModel):
    text: str


class IssuePayload(BaseModel):
    issue_description: str
    comments: list[str] = []


class RiskPayload(BaseModel):
    overdue_requirements: int = 0
    blocked_issues: int = 0
    critical_issues: int = 0
    delivery_completion_rate: float = 0.0
    project_stage: str = 'active'


class CustomerUpdatePayload(BaseModel):
    project_status: str = 'active'
    issue_status: str = 'open'


class AIAnalysisFeedbackPayload(BaseModel):
    feedback_status: str
    feedback_note: str | None = None
    edited_output: str | None = None

    @field_validator('feedback_status')
    @classmethod
    def validate_feedback_status(cls, value: str) -> str:
        if value not in ALLOWED_FEEDBACK_STATUSES:
            raise ValueError('feedback_status 取值无效')
        return value

    @field_validator('edited_output')
    @classmethod
    def validate_edited_output(cls, value: str | None, info):
        feedback_status = info.data.get('feedback_status')
        if feedback_status == 'edited_and_accepted':
            if value is None or not value.strip():
                raise ValueError('edited_output 在 edited_and_accepted 时不能为空')
            return value.strip()
        return value.strip() if isinstance(value, str) else value


class AIEvaluationMetricsGroup(BaseModel):
    provider: str
    model_name: str | None
    total_analyses: int
    pending_reviews: int
    reviewed_analyses: int
    accepted: int
    rejected: int
    edited_and_accepted: int
    review_completion_rate: float | None
    positive_outcome_rate: float | None
    direct_acceptance_rate: float | None
    edit_and_accept_rate: float | None
    rejection_rate: float | None


class AIEvaluationMetricsPromptVersionGroup(BaseModel):
    prompt_version: str | None
    provider: str
    model_name: str | None
    total_analyses: int
    pending_reviews: int
    reviewed_analyses: int
    accepted: int
    rejected: int
    edited_and_accepted: int
    review_completion_rate: float | None
    positive_outcome_rate: float | None
    direct_acceptance_rate: float | None
    edit_and_accept_rate: float | None
    rejection_rate: float | None


class AIEvaluationMetricsResponse(BaseModel):
    total_analyses: int
    pending_reviews: int
    reviewed_analyses: int
    accepted: int
    rejected: int
    edited_and_accepted: int
    review_completion_rate: float | None
    positive_outcome_rate: float | None
    direct_acceptance_rate: float | None
    edit_and_accept_rate: float | None
    rejection_rate: float | None
    provider_breakdown: list[AIEvaluationMetricsGroup]
    prompt_version_breakdown: list[AIEvaluationMetricsPromptVersionGroup]


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _load_knowledge_citations(raw: str | None) -> list[dict[str, object]]:
    if raw is None or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _serialize_analysis(log: AIAnalysisLog) -> dict[str, object]:
    citations = _load_knowledge_citations(log.knowledge_citations_json)
    return {
        'analysis_id': log.id,
        'issue_id': log.issue_id,
        'analysis_type': log.analysis_type,
        'provider': log.provider,
        'model_name': log.model_name,
        'prompt_version': log.prompt_version,
        'issue_summary': log.issue_summary,
        'possible_root_cause': log.possible_root_cause,
        'recommended_actions': json.loads(log.recommended_actions_json),
        'customer_update_draft': log.customer_update_draft,
        'risk_level': log.risk_level,
        'project_impact': log.project_impact,
        'feedback_status': log.feedback_status,
        'feedback_note': log.feedback_note,
        'edited_output': log.edited_output,
        'retrieval_status': log.retrieval_status,
        'retrieval_query': log.retrieval_query,
        'knowledge_citations': citations,
        'retrieval_error_code': log.retrieval_error_code,
        'knowledge_grounded': log.provider == 'llm' and log.retrieval_status == 'succeeded' and len(citations) > 0 and log.prompt_version == 'issue_summarizer_v4_grounded',
        'created_at': log.created_at.isoformat() if log.created_at else None,
        'updated_at': log.updated_at.isoformat() if log.updated_at else None,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _build_group(rows: list[AIAnalysisLog], prompt_version: str | None = None) -> dict[str, object]:
    total_analyses = len(rows)
    accepted = sum(1 for row in rows if row.feedback_status == 'accepted')
    rejected = sum(1 for row in rows if row.feedback_status == 'rejected')
    edited_and_accepted = sum(1 for row in rows if row.feedback_status == 'edited_and_accepted')
    reviewed_analyses = accepted + rejected + edited_and_accepted
    pending_reviews = total_analyses - reviewed_analyses
    provider = rows[0].provider if rows else 'unknown'
    model_name = rows[0].model_name if rows else None
    return {
        'prompt_version': prompt_version,
        'provider': provider,
        'model_name': model_name,
        'total_analyses': total_analyses,
        'pending_reviews': pending_reviews,
        'reviewed_analyses': reviewed_analyses,
        'accepted': accepted,
        'rejected': rejected,
        'edited_and_accepted': edited_and_accepted,
        'review_completion_rate': _rate(reviewed_analyses, total_analyses),
        'positive_outcome_rate': _rate(accepted + edited_and_accepted, reviewed_analyses),
        'direct_acceptance_rate': _rate(accepted, reviewed_analyses),
        'edit_and_accept_rate': _rate(edited_and_accepted, reviewed_analyses),
        'rejection_rate': _rate(rejected, reviewed_analyses),
    }


def _group_metrics(rows: list[AIAnalysisLog], by_prompt_version: bool = False) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], list[AIAnalysisLog]] = defaultdict(list)
    for row in rows:
        key = (row.provider, row.model_name, row.prompt_version) if by_prompt_version else (row.provider, row.model_name)
        groups[key].append(row)

    breakdown = []
    for key, group_rows in groups.items():
        if by_prompt_version:
            provider, model_name, prompt_version = key
            item = _build_group(group_rows, prompt_version=prompt_version)
            item['provider'] = provider
            item['model_name'] = model_name
        else:
            provider, model_name = key
            item = _build_group(group_rows)
            item['provider'] = provider
            item['model_name'] = model_name
        breakdown.append(item)
    return breakdown


def _metrics_from_rows(rows: list[AIAnalysisLog]) -> AIEvaluationMetricsResponse:
    total_analyses = len(rows)
    accepted = sum(1 for row in rows if row.feedback_status == 'accepted')
    rejected = sum(1 for row in rows if row.feedback_status == 'rejected')
    edited_and_accepted = sum(1 for row in rows if row.feedback_status == 'edited_and_accepted')
    reviewed_analyses = accepted + rejected + edited_and_accepted
    pending_reviews = total_analyses - reviewed_analyses

    return AIEvaluationMetricsResponse(
        total_analyses=total_analyses,
        pending_reviews=pending_reviews,
        reviewed_analyses=reviewed_analyses,
        accepted=accepted,
        rejected=rejected,
        edited_and_accepted=edited_and_accepted,
        review_completion_rate=_rate(reviewed_analyses, total_analyses),
        positive_outcome_rate=_rate(accepted + edited_and_accepted, reviewed_analyses),
        direct_acceptance_rate=_rate(accepted, reviewed_analyses),
        edit_and_accept_rate=_rate(edited_and_accepted, reviewed_analyses),
        rejection_rate=_rate(rejected, reviewed_analyses),
        provider_breakdown=[
            AIEvaluationMetricsGroup(**group) for group in _group_metrics(rows, by_prompt_version=False)
        ],
        prompt_version_breakdown=[
            AIEvaluationMetricsPromptVersionGroup(**group)
            for group in _group_metrics(rows, by_prompt_version=True)
        ],
    )


@router.post('/parse-requirement')
def parse_requirement(payload: TextPayload):
    return mock_requirement_parse(payload.text)


@router.post('/summarize-issue')
def summarize_issue(payload: IssuePayload):
    return mock_issue_summary(payload.issue_description, payload.comments)


@router.post('/analyze-risk')
def analyze_risk(payload: RiskPayload):
    return mock_risk_analysis(payload.model_dump())


@router.post('/customer-update-draft')
def customer_update_draft(payload: CustomerUpdatePayload):
    return mock_customer_update_draft(payload.project_status, payload.issue_status)


@router.post('/issues/{issue_id}/summarize')
def summarize_issue_by_id(issue_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        analysis_log = analysis_service.analyze_and_store(issue_id, db)
        print(f'AI issue summary provider={analysis_log.provider}, analysis_id={analysis_log.id}, issue_id={issue_id}, retrieval_status={analysis_log.retrieval_status}')
        return _serialize_analysis(analysis_log)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'保存 AI 分析失败：{exc!s}') from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'AI 分析失败：{exc!s}') from exc


@router.get('/issues/{issue_id}/analyses')
def get_issue_analyses(issue_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    try:
        histories = analysis_service.get_issue_history(issue_id, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_serialize_analysis(item) for item in histories]


@router.get('/evaluation/metrics', response_model=AIEvaluationMetricsResponse)
def get_ai_evaluation_metrics(db: Session = Depends(get_db)) -> AIEvaluationMetricsResponse:
    rows = db.query(AIAnalysisLog).all()
    return _metrics_from_rows(rows)


@router.patch('/analyses/{analysis_id}/feedback')
def update_analysis_feedback(
    analysis_id: int,
    payload: AIAnalysisFeedbackPayload,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    analysis = (
        db.query(AIAnalysisLog)
        .filter(AIAnalysisLog.id == analysis_id)
        .first()
    )
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail='AI 分析记录不存在',
        )

    if analysis.feedback_status != 'pending':
        raise HTTPException(
            status_code=409,
            detail=(
                'Feedback has already been submitted '
                'for this analysis'
            ),
        )

    payload_data = payload.model_dump(
        exclude_unset=True
    )
    feedback_status = payload_data[
        'feedback_status'
    ]

    if feedback_status == 'edited_and_accepted':
        if 'edited_output' not in payload_data:
            raise HTTPException(
                status_code=422,
                detail=(
                    'edited_output 在 '
                    'edited_and_accepted 时不能为空'
                ),
            )

        edited_output = payload_data.get(
            'edited_output'
        )

        if (
            edited_output is None
            or not edited_output.strip()
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    'edited_output 在 '
                    'edited_and_accepted 时不能为空'
                ),
            )
    else:
        edited_output = (
            payload_data.get('edited_output')
            if 'edited_output' in payload_data
            else None
        )

    linked_agent_run = (
        db.query(AgentRun)
        .filter(
            AgentRun.analysis_log_id == analysis_id
        )
        .first()
    )

    if linked_agent_run is not None:
        if (
            feedback_status
            not in FINAL_FEEDBACK_STATUSES
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    'Agent-linked feedback requires '
                    'a final feedback status'
                ),
            )

        try:
            _, finalized_analysis, _ = (
                agent_orchestration_service
                .finalize_waiting_review_run(
                    db,
                    analysis_id=analysis_id,
                    feedback_status=feedback_status,
                    feedback_note=(
                        payload_data.get(
                            'feedback_note'
                        )
                        if 'feedback_note'
                        in payload_data
                        else None
                    ),
                    edited_output=(
                        edited_output.strip()
                        if isinstance(
                            edited_output,
                            str,
                        )
                        else None
                    ),
                )
            )
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
            raise HTTPException(
                status_code=500,
                detail=(
                    '更新 Agent Final Review 失败：'
                    f'{exc!s}'
                ),
            ) from exc

        return _serialize_analysis(
            finalized_analysis
        )

    analysis.feedback_status = feedback_status

    if 'feedback_note' in payload_data:
        analysis.feedback_note = (
            _clean_optional_text(
                payload_data.get('feedback_note')
            )
        )

    if 'edited_output' in payload_data:
        analysis.edited_output = (
            edited_output.strip()
            if isinstance(edited_output, str)
            else None
        )

    try:
        db.commit()
        db.refresh(analysis)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f'更新 AI 分析反馈失败：{exc!s}',
        ) from exc

    return _serialize_analysis(analysis)
