from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import json
from types import MappingProxyType
from typing import Any, Protocol

from pydantic import ValidationError

from app.ai.prompt_builder import (
    ISSUE_SUMMARIZER_PROMPT_VERSION,
)
from app.ai.providers.llm import LLMIssueAnalysisProvider
from app.ai.schemas import (
    IssueAnalysisContext,
    KnowledgeCitationSnapshot,
    KnowledgeEvidence,
    ProviderAnalysisResult,
    SupplementalEvidence,
)
from app.schemas.agent_tools import (
    AgentAnalysisHistoryItem,
    AgentDeliveryRiskOutput,
    AgentSearchKnowledgeOutput,
)
from app.services.agent_tool_registry import (
    CALCULATE_DELIVERY_RISK_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    SEARCH_KNOWLEDGE_TOOL,
)


AGENT_ANALYSIS_GENERATION_VERSION = (
    "agent_analysis_generation_v0.1"
)
GENERATED_ANALYSIS_STATE_KEY = "generated_analysis"
ANALYSIS_TYPE = "issue_summarizer"

ISSUE_CONTEXT_FIELDS = frozenset(
    {
        "issue_id",
        "issue_title",
        "issue_description",
        "issue_type",
        "severity",
        "status",
        "owner",
        "project_name",
        "project_status",
        "delivery_stage",
        "risk_level",
        "health",
        "customer_name",
        "customer_industry",
        "customer_contact",
    }
)
CONTROLLED_PROVIDER_NAMES = frozenset(
    {"llm", "rule_based_fallback"}
)


class AgentAnalysisProviderPort(Protocol):
    name: str

    def analyze_issue(
        self,
        context: IssueAnalysisContext,
    ) -> object:
        ...


class AgentAnalysisGenerationError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        normalized_code = error_code.strip()
        normalized_message = message.strip()
        if not normalized_code:
            raise ValueError(
                "Generation error_code must be nonblank"
            )
        if not normalized_message:
            raise ValueError(
                "Generation message must be nonblank"
            )
        super().__init__(normalized_message)
        self.error_code = normalized_code


@dataclass(frozen=True, slots=True)
class AgentAnalysisGenerationOutcome:
    analysis_result: ProviderAnalysisResult
    analysis_context: IssueAnalysisContext
    knowledge_citations: tuple[
        KnowledgeCitationSnapshot,
        ...,
    ]
    supplemental_evidence: tuple[
        SupplementalEvidence,
        ...,
    ]
    provider_fallback_reason: str | None
    state_update: Mapping[str, object]
    generation_version: str = (
        AGENT_ANALYSIS_GENERATION_VERSION
    )

    def as_dict(self) -> dict[str, object]:
        return {
            "generation_version": self.generation_version,
            "analysis_result": asdict(
                self.analysis_result
            ),
            "knowledge_citations": [
                asdict(item)
                for item in self.knowledge_citations
            ],
            "supplemental_evidence": [
                asdict(item)
                for item in self.supplemental_evidence
            ],
            "provider_fallback_reason": (
                self.provider_fallback_reason
            ),
            "state_update": dict(self.state_update),
        }

    def to_state_update(self) -> dict[str, object]:
        return dict(self.state_update)


class AgentAnalysisGenerationService:
    def __init__(
        self,
        *,
        analysis_provider: (
            AgentAnalysisProviderPort | None
        ) = None,
    ) -> None:
        self._analysis_provider = (
            analysis_provider
            if analysis_provider is not None
            else LLMIssueAnalysisProvider()
        )

    def generate(
        self,
        state: Mapping[str, Any],
    ) -> AgentAnalysisGenerationOutcome:
        if not isinstance(state, Mapping):
            self._fail(
                "invalid_agent_state",
                "Agent state must be a mapping.",
            )
        if state.get("evidence_sufficient") is not True:
            self._fail(
                "evidence_not_sufficient",
                (
                    "Analysis generation requires a "
                    "sufficient evidence decision."
                ),
            )
        self._required_text(
            state.get("evidence_reason"),
            "invalid_evidence_reason",
            "evidence_reason",
        )
        if state.get("selected_tool") is not None:
            self._fail(
                "tool_execution_incomplete",
                (
                    "Analysis generation requires "
                    "selected_tool to be cleared."
                ),
            )

        issue_context = self._issue_context(
            state.get("issue_context")
        )
        tool_results = self._mapping_items(
            state.get("tool_results"),
            "invalid_tool_results",
            "tool_results",
        )
        retrieved_evidence = self._mapping_items(
            state.get("retrieved_evidence"),
            "invalid_retrieved_evidence",
            "retrieved_evidence",
        )
        self._validate_evidence_links(
            tool_results,
            retrieved_evidence,
        )

        (
            retrieval_status,
            retrieval_query,
            knowledge_evidence,
            knowledge_citations,
            retrieval_error_code,
        ) = self._knowledge_context(
            tool_results,
            retrieved_evidence,
        )
        supplemental_evidence = (
            self._supplemental_evidence(
                state,
                tool_results,
                retrieved_evidence,
            )
        )
        has_primary_supplemental = any(
            item.evidence_type in {
                "analysis_history",
                "human_clarification",
            }
            for item in supplemental_evidence
        )
        if not knowledge_evidence and not has_primary_supplemental:
            self._fail(
                "missing_generation_evidence",
                (
                    "Analysis generation requires usable "
                    "knowledge, accepted history, or human "
                    "clarification evidence."
                ),
            )
        analysis_context = self._analysis_context(
            issue_context,
            retrieval_query,
            knowledge_evidence,
            supplemental_evidence,
        )

        raw_result = (
            self._analysis_provider.analyze_issue(
                analysis_context
            )
        )
        analysis_result = self._provider_result(
            raw_result
        )
        fallback_reason = self._optional_text(
            getattr(
                self._analysis_provider,
                "last_fallback_reason",
                None,
            ),
            "invalid_provider_fallback_reason",
            "provider.last_fallback_reason",
        )

        generated_analysis = {
            "generation_version": (
                AGENT_ANALYSIS_GENERATION_VERSION
            ),
            "analysis_type": ANALYSIS_TYPE,
            "provider": analysis_result.provider,
            "model_name": analysis_result.model_name,
            "prompt_version": (
                analysis_result.prompt_version
            ),
            "provider_fallback_reason": (
                fallback_reason
            ),
            "issue_summary": (
                analysis_result.issue_summary
            ),
            "possible_root_cause": (
                analysis_result.possible_root_cause
            ),
            "recommended_actions": list(
                analysis_result.recommended_actions
            ),
            "customer_update_draft": (
                analysis_result.customer_update_draft
            ),
            "risk_level": analysis_result.risk_level,
            "project_impact": (
                analysis_result.project_impact
            ),
            "retrieval_status": retrieval_status,
            "retrieval_query": retrieval_query,
            "knowledge_citations": [
                asdict(item)
                for item in knowledge_citations
            ],
            "retrieval_error_code": (
                retrieval_error_code
            ),
            "supplemental_evidence_count": len(
                supplemental_evidence
            ),
        }
        state_update = MappingProxyType(
            {
                GENERATED_ANALYSIS_STATE_KEY: (
                    generated_analysis
                )
            }
        )

        return AgentAnalysisGenerationOutcome(
            analysis_result=analysis_result,
            analysis_context=analysis_context,
            knowledge_citations=(
                knowledge_citations
            ),
            supplemental_evidence=(
                supplemental_evidence
            ),
            provider_fallback_reason=fallback_reason,
            state_update=state_update,
        )

    def _knowledge_context(
        self,
        tool_results: tuple[
            Mapping[str, object],
            ...,
        ],
        retrieved_evidence: tuple[
            Mapping[str, object],
            ...,
        ],
    ) -> tuple[
        str,
        str | None,
        tuple[KnowledgeEvidence, ...],
        tuple[KnowledgeCitationSnapshot, ...],
        str | None,
    ]:
        search_results = self._tool_results_for(
            tool_results,
            SEARCH_KNOWLEDGE_TOOL,
        )
        knowledge_envelopes = tuple(
            item
            for item in retrieved_evidence
            if item.get("evidence_type")
            == "knowledge_chunk"
        )
        for item in knowledge_envelopes:
            if item.get("source_tool") != SEARCH_KNOWLEDGE_TOOL:
                self._fail(
                    "invalid_retrieved_evidence",
                    (
                        "Knowledge evidence must originate "
                        "from search_knowledge."
                    ),
                )

        if not search_results:
            if knowledge_envelopes:
                self._fail(
                    "orphan_knowledge_evidence",
                    (
                        "Knowledge evidence requires a "
                        "search_knowledge Tool result."
                    ),
                )
            return (
                "not_attempted",
                None,
                (),
                (),
                None,
            )

        try:
            output = AgentSearchKnowledgeOutput.model_validate(
                self._result_json(search_results[0])
            )
        except ValidationError as exc:
            raise AgentAnalysisGenerationError(
                error_code="invalid_search_result",
                message=(
                    "search_knowledge result violates "
                    "the frozen Tool schema."
                ),
            ) from exc
        evidence = tuple(
            KnowledgeEvidence(
                **item.model_dump(mode="python")
            )
            for item in output.knowledge_evidence
        )
        citations = tuple(
            KnowledgeCitationSnapshot(
                **item.model_dump(mode="python")
            )
            for item in output.knowledge_citations
        )
        actual_payloads = tuple(
            dict(self._mapping(
                item.get("payload"),
                "invalid_retrieved_evidence",
                "retrieved_evidence.payload",
            ))
            for item in knowledge_envelopes
        )
        expected_payloads = tuple(
            item.model_dump(mode="json")
            for item in output.knowledge_evidence
        )
        if actual_payloads != expected_payloads:
            self._fail(
                "knowledge_evidence_mismatch",
                (
                    "retrieved_evidence does not match "
                    "the search_knowledge result."
                ),
            )

        return (
            output.retrieval_status,
            output.retrieval_query,
            evidence,
            citations,
            output.retrieval_error_code,
        )

    def _supplemental_evidence(
        self,
        state: Mapping[str, Any],
        tool_results: tuple[
            Mapping[str, object],
            ...,
        ],
        retrieved_evidence: tuple[
            Mapping[str, object],
            ...,
        ],
    ) -> tuple[SupplementalEvidence, ...]:
        items: list[SupplementalEvidence] = []

        for envelope in retrieved_evidence:
            if envelope.get("evidence_type") != (
                "analysis_history"
            ):
                continue
            if envelope.get("source_tool") != (
                GET_ANALYSIS_HISTORY_TOOL
            ):
                self._fail(
                    "invalid_retrieved_evidence",
                    (
                        "Analysis history evidence must "
                        "originate from get_analysis_history."
                    ),
                )
            try:
                history = AgentAnalysisHistoryItem.model_validate(
                    self._mapping(
                        envelope.get("payload"),
                        "invalid_retrieved_evidence",
                        "retrieved_evidence.payload",
                    )
                )
            except ValidationError as exc:
                raise AgentAnalysisGenerationError(
                    error_code="invalid_history_evidence",
                    message=(
                        "Analysis history evidence violates "
                        "the frozen Tool schema."
                    ),
                ) from exc
            if history.feedback_status not in {
                "accepted",
                "edited_and_accepted",
            }:
                continue
            items.append(
                SupplementalEvidence(
                    evidence_id=(
                        f"H{history.analysis_id}"
                    ),
                    evidence_type=(
                        "analysis_history"
                    ),
                    source_name=(
                        GET_ANALYSIS_HISTORY_TOOL
                    ),
                    content=self._history_content(
                        history
                    ),
                )
            )

        clarification = self._optional_text(
            state.get("clarification_response"),
            "invalid_clarification_response",
            "clarification_response",
        )
        if clarification is not None:
            items.append(
                SupplementalEvidence(
                    evidence_id="C1",
                    evidence_type=(
                        "human_clarification"
                    ),
                    source_name="human_review",
                    content=clarification,
                )
            )

        risk_results = self._tool_results_for(
            tool_results,
            CALCULATE_DELIVERY_RISK_TOOL,
        )
        if risk_results:
            try:
                risk = AgentDeliveryRiskOutput.model_validate(
                    self._result_json(risk_results[0])
                )
            except ValidationError as exc:
                raise AgentAnalysisGenerationError(
                    error_code="invalid_delivery_risk_result",
                    message=(
                        "Delivery risk result violates the "
                        "frozen Tool schema."
                    ),
                ) from exc
            items.append(
                SupplementalEvidence(
                    evidence_id="R1",
                    evidence_type="delivery_risk",
                    source_name=(
                        CALCULATE_DELIVERY_RISK_TOOL
                    ),
                    content=json.dumps(
                        risk.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )

        return tuple(items)

    def _analysis_context(
        self,
        context: Mapping[str, object],
        retrieval_query: str | None,
        knowledge_evidence: tuple[
            KnowledgeEvidence,
            ...,
        ],
        supplemental_evidence: tuple[
            SupplementalEvidence,
            ...,
        ],
    ) -> IssueAnalysisContext:
        project = self._optional_group(
            {
                "id": None,
                "name": context["project_name"],
                "status": context["project_status"],
                "delivery_stage": context[
                    "delivery_stage"
                ],
                "risk_level": context["risk_level"],
                "health": context["health"],
            }
        )
        customer = self._optional_group(
            {
                "id": None,
                "name": context["customer_name"],
                "industry": context[
                    "customer_industry"
                ],
            }
        )
        return IssueAnalysisContext(
            issue={
                "id": context["issue_id"],
                "title": context["issue_title"],
                "description": context[
                    "issue_description"
                ],
                "issue_type": context["issue_type"],
                "severity": context["severity"],
                "status": context["status"],
                "owner": context["owner"],
            },
            project=project,
            customer=customer,
            retrieval_query=retrieval_query,
            knowledge_evidence=knowledge_evidence,
            supplemental_evidence=(
                supplemental_evidence
            ),
        )

    def _provider_result(
        self,
        raw_result: object,
    ) -> ProviderAnalysisResult:
        provider = self._required_text(
            getattr(
                self._analysis_provider,
                "last_provider_name",
                getattr(
                    self._analysis_provider,
                    "name",
                    None,
                ),
            ),
            "invalid_provider_name",
            "provider.last_provider_name",
        )
        if provider not in CONTROLLED_PROVIDER_NAMES:
            self._fail(
                "invalid_provider_name",
                "Provider name is not controlled.",
            )
        model_name = self._optional_text(
            getattr(
                self._analysis_provider,
                "last_model_name",
                None,
            ),
            "invalid_model_name",
            "provider.last_model_name",
        )
        if provider != "llm":
            model_name = None

        try:
            actions = self._text_items(
                getattr(
                    raw_result,
                    "recommended_actions",
                ),
                "recommended_actions",
            )
            risk_level = self._required_text(
                getattr(raw_result, "risk_level"),
                "invalid_analysis_result",
                "risk_level",
            )
            if risk_level not in {
                "low",
                "medium",
                "high",
                "critical",
            }:
                self._fail(
                    "invalid_analysis_result",
                    "risk_level is not controlled.",
                )
            return ProviderAnalysisResult(
                issue_summary=self._required_text(
                    getattr(
                        raw_result,
                        "issue_summary",
                    ),
                    "invalid_analysis_result",
                    "issue_summary",
                ),
                possible_root_cause=(
                    self._required_text(
                        getattr(
                            raw_result,
                            "possible_root_cause",
                        ),
                        "invalid_analysis_result",
                        "possible_root_cause",
                    )
                ),
                recommended_actions=list(actions),
                customer_update_draft=(
                    self._required_text(
                        getattr(
                            raw_result,
                            "customer_update_draft",
                        ),
                        "invalid_analysis_result",
                        "customer_update_draft",
                    )
                ),
                risk_level=risk_level,
                project_impact=self._required_text(
                    getattr(
                        raw_result,
                        "project_impact",
                    ),
                    "invalid_analysis_result",
                    "project_impact",
                ),
                provider=provider,
                model_name=model_name,
                prompt_version=(
                    ISSUE_SUMMARIZER_PROMPT_VERSION
                ),
            )
        except AttributeError as exc:
            raise AgentAnalysisGenerationError(
                error_code="invalid_analysis_result",
                message=(
                    "Provider result is missing required "
                    "analysis fields."
                ),
            ) from exc

    def _issue_context(
        self,
        value: object,
    ) -> Mapping[str, object]:
        context = dict(self._mapping(
            value,
            "invalid_issue_context",
            "issue_context",
        ))
        if frozenset(context) != ISSUE_CONTEXT_FIELDS:
            self._fail(
                "invalid_issue_context",
                (
                    "issue_context fields do not match "
                    "the frozen Agent contract."
                ),
            )
        issue_id = context["issue_id"]
        if type(issue_id) is not int or issue_id < 1:
            self._fail(
                "invalid_issue_context",
                (
                    "issue_context.issue_id must be a "
                    "positive integer."
                ),
            )
        for name in (
            "issue_title",
            "severity",
            "status",
        ):
            context[name] = self._required_text(
                context[name],
                "invalid_issue_context",
                f"issue_context.{name}",
            )
        for name in (
            ISSUE_CONTEXT_FIELDS
            - {
                "issue_id",
                "issue_title",
                "severity",
                "status",
            }
        ):
            context[name] = self._optional_text(
                context[name],
                "invalid_issue_context",
                f"issue_context.{name}",
            )
        return MappingProxyType(context)

    def _validate_evidence_links(
        self,
        tool_results: tuple[
            Mapping[str, object],
            ...,
        ],
        retrieved_evidence: tuple[
            Mapping[str, object],
            ...,
        ],
    ) -> None:
        calls: dict[str, str] = {}

        for item in tool_results:
            tool_name = self._required_text(
                item.get("tool_name"),
                "invalid_tool_results",
                "tool_results.tool_name",
            )
            call_identity = self._required_text(
                item.get("call_identity"),
                "invalid_tool_results",
                "tool_results.call_identity",
            )
            if item.get("execution_status") != "completed":
                self._fail(
                    "invalid_tool_results",
                    (
                        "Analysis generation accepts only "
                        "completed Tool results."
                    ),
                )
            self._mapping(
                item.get("result_json"),
                "invalid_tool_results",
                "tool_results.result_json",
            )
            if call_identity in calls:
                self._fail(
                    "duplicate_tool_results",
                    (
                        "tool_results contains a duplicate "
                        "call_identity."
                    ),
                )
            calls[call_identity] = tool_name

        for item in retrieved_evidence:
            source_tool = self._required_text(
                item.get("source_tool"),
                "invalid_retrieved_evidence",
                "retrieved_evidence.source_tool",
            )
            call_identity = self._required_text(
                item.get("source_call_identity"),
                "invalid_retrieved_evidence",
                (
                    "retrieved_evidence."
                    "source_call_identity"
                ),
            )
            if calls.get(call_identity) != source_tool:
                self._fail(
                    "orphan_retrieved_evidence",
                    (
                        "retrieved_evidence must link to "
                        "the matching completed Tool call."
                    ),
                )

    def _tool_results_for(
        self,
        tool_results: tuple[
            Mapping[str, object],
            ...,
        ],
        tool_name: str,
    ) -> tuple[Mapping[str, object], ...]:
        matches = tuple(
            item
            for item in tool_results
            if item.get("tool_name") == tool_name
        )
        if len(matches) > 1:
            self._fail(
                "duplicate_tool_results",
                f"Duplicate {tool_name} Tool results.",
            )
        return matches

    def _result_json(
        self,
        tool_result: Mapping[str, object],
    ) -> Mapping[str, object]:
        if tool_result.get("execution_status") != (
            "completed"
        ):
            self._fail(
                "invalid_tool_results",
                (
                    "Analysis generation accepts only "
                    "completed Tool results."
                ),
            )
        return self._mapping(
            tool_result.get("result_json"),
            "invalid_tool_results",
            "tool_results.result_json",
        )

    @staticmethod
    def _history_content(
        history: AgentAnalysisHistoryItem,
    ) -> str:
        payload = {
            "analysis_id": history.analysis_id,
            "feedback_status": (
                history.feedback_status
            ),
            "issue_summary": history.issue_summary,
            "possible_root_cause": (
                history.possible_root_cause
            ),
            "recommended_actions": list(
                history.recommended_actions
            ),
            "customer_update_draft": (
                history.customer_update_draft
            ),
            "risk_level": history.risk_level,
            "project_impact": history.project_impact,
            "edited_output": history.edited_output,
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _optional_group(
        values: dict[str, object],
    ) -> dict[str, object] | None:
        meaningful = tuple(
            value
            for key, value in values.items()
            if key != "id"
        )
        return values if any(
            value is not None
            for value in meaningful
        ) else None

    def _mapping_items(
        self,
        value: object,
        error_code: str,
        field_name: str,
    ) -> tuple[Mapping[str, object], ...]:
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes))
        ):
            self._fail(
                error_code,
                (
                    f"{field_name} must be a sequence "
                    "of mappings."
                ),
            )
        return tuple(
            self._mapping(
                item,
                error_code,
                field_name,
            )
            for item in value
        )

    @staticmethod
    def _mapping(
        value: object,
        error_code: str,
        field_name: str,
    ) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise AgentAnalysisGenerationError(
                error_code=error_code,
                message=f"{field_name} must be a mapping.",
            )
        return value

    def _text_items(
        self,
        value: object,
        field_name: str,
    ) -> tuple[str, ...]:
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes))
        ):
            self._fail(
                "invalid_analysis_result",
                f"{field_name} must be a text sequence.",
            )
        return tuple(
            self._required_text(
                item,
                "invalid_analysis_result",
                field_name,
            )
            for item in value
        )

    @staticmethod
    def _required_text(
        value: object,
        error_code: str,
        field_name: str,
    ) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
        ):
            raise AgentAnalysisGenerationError(
                error_code=error_code,
                message=(
                    f"{field_name} must be a normalized "
                    "nonblank string."
                ),
            )
        return value

    @staticmethod
    def _optional_text(
        value: object,
        error_code: str,
        field_name: str,
    ) -> str | None:
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
        ):
            raise AgentAnalysisGenerationError(
                error_code=error_code,
                message=(
                    f"{field_name} must be None or a "
                    "normalized nonblank string."
                ),
            )
        return value

    @staticmethod
    def _fail(
        error_code: str,
        message: str,
    ) -> None:
        raise AgentAnalysisGenerationError(
            error_code=error_code,
            message=message,
        )


agent_analysis_generation_service = (
    AgentAnalysisGenerationService()
)
