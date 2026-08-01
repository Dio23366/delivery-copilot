from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIAnalysisLog, Issue
from app.schemas.agent_tools import (
    AGENT_ANALYSIS_HISTORY_LIMIT,
    AgentAnalysisHistoryInput,
    AgentAnalysisHistoryItem,
    AgentAnalysisHistoryOutput,
    AgentKnowledgeCitation,
)


class AgentAnalysisHistoryToolAdapter:
    def execute(
        self,
        issue_id: int,
        db: Session,
    ) -> AgentAnalysisHistoryOutput:
        validated_input = AgentAnalysisHistoryInput(
            issue_id=issue_id
        )
        issue = db.get(Issue, validated_input.issue_id)
        if issue is None:
            raise LookupError(
                f"Issue not found: {validated_input.issue_id}"
            )

        statement = (
            select(AIAnalysisLog)
            .where(
                AIAnalysisLog.issue_id
                == validated_input.issue_id
            )
            .order_by(
                AIAnalysisLog.created_at.desc(),
                AIAnalysisLog.id.desc(),
            )
            .limit(AGENT_ANALYSIS_HISTORY_LIMIT)
        )
        rows = tuple(db.scalars(statement).all())
        analyses = tuple(
            self._to_history_item(row)
            for row in rows
        )

        return AgentAnalysisHistoryOutput(
            issue_id=validated_input.issue_id,
            analysis_count=len(analyses),
            analyses=analyses,
        )

    def _to_history_item(
        self,
        row: AIAnalysisLog,
    ) -> AgentAnalysisHistoryItem:
        recommended_actions = tuple(
            self._load_json_list(
                row.recommended_actions_json,
                field_name="recommended_actions_json",
            )
        )
        citation_payloads = self._load_json_list(
            row.knowledge_citations_json,
            field_name="knowledge_citations_json",
        )
        knowledge_citations = tuple(
            AgentKnowledgeCitation.model_validate(payload)
            for payload in citation_payloads
        )
        knowledge_grounded = (
            row.provider == "llm"
            and row.retrieval_status == "succeeded"
            and bool(knowledge_citations)
            and row.prompt_version
            == "issue_summarizer_v4_grounded"
        )

        return AgentAnalysisHistoryItem(
            analysis_id=row.id,
            issue_id=row.issue_id,
            analysis_type=row.analysis_type,
            provider=row.provider,
            model_name=row.model_name,
            prompt_version=row.prompt_version,
            issue_summary=row.issue_summary,
            possible_root_cause=row.possible_root_cause,
            recommended_actions=recommended_actions,
            customer_update_draft=(
                row.customer_update_draft
            ),
            risk_level=row.risk_level,
            project_impact=row.project_impact,
            feedback_status=row.feedback_status,
            feedback_note=row.feedback_note,
            edited_output=row.edited_output,
            retrieval_status=row.retrieval_status,
            retrieval_query=row.retrieval_query,
            knowledge_citations=knowledge_citations,
            retrieval_error_code=(
                row.retrieval_error_code
            ),
            knowledge_grounded=knowledge_grounded,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _load_json_list(
        raw_value: str,
        *,
        field_name: str,
    ) -> list[Any]:
        if not isinstance(raw_value, str):
            raise ValueError(
                f"{field_name} must be stored as JSON text"
            )

        try:
            parsed = json.loads(raw_value)
        except JSONDecodeError as exc:
            raise ValueError(
                f"{field_name} contains invalid JSON"
            ) from exc

        if not isinstance(parsed, list):
            raise ValueError(
                f"{field_name} must contain a JSON array"
            )

        return parsed


agent_analysis_history_tool_adapter = (
    AgentAnalysisHistoryToolAdapter()
)
