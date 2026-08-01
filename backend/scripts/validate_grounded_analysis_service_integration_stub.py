from __future__ import annotations

import json
import sqlite3
import tempfile
from dataclasses import asdict

from app.ai.analysis_service import IssueAnalysisService
from app.ai.grounded_retrieval_service import GroundedRetrievalOutcome
from app.ai.schemas import KnowledgeCitationSnapshot, KnowledgeEvidence
from app.api.ai import _serialize_analysis
from app.database import init_db
from app.models import AIAnalysisLog
from app.schemas.knowledge import KnowledgeSearchContext


class FakeIssue:
    def __init__(self):
        self.id = 101
        self.project_id = 202
        self.title = 'issue'
        self.description = 'desc'
        self.issue_type = 'incident'
        self.severity = 'high'
        self.status = 'open'
        self.owner = 'ops'


class FakeProject:
    def __init__(self):
        self.id = 202
        self.customer_id = 303
        self.name = 'project'
        self.status = 'active'
        self.delivery_stage = 'rollout'
        self.risk_level = 'medium'
        self.health = 'green'


class FakeCustomer:
    def __init__(self):
        self.id = 303
        self.name = 'customer'
        self.industry = 'finance'


class StubRetrievalService:
    def __init__(self, outcome: GroundedRetrievalOutcome):
        self.outcome = outcome
        self.calls = []

    def retrieve(self, issue, project, customer, db):
        self.calls.append((issue, project, customer, db))
        return self.outcome


class StubLLMProvider:
    def __init__(self, provider='llm', model_name='gpt-4.1-mini', result=None):
        self.last_provider_name = provider
        self.last_model_name = model_name if provider == 'llm' else None
        self.result = result or type('Result', (), {
            'issue_summary': 'summary',
            'possible_root_cause': 'cause',
            'recommended_actions': ['action1'],
            'customer_update_draft': 'draft',
            'risk_level': 'low',
            'project_impact': 'impact',
        })()
        self.calls = []

    def analyze_issue(self, context):
        self.calls.append(context)
        return self.result


class FakeSession:
    def __init__(self, issue=None, project=None, customer=None):
        self.issue = issue or FakeIssue()
        self.project = project or FakeProject()
        self.customer = customer or FakeCustomer()
        self.commit_calls = 0
        self.rollback_calls = 0
        self.add_calls = 0
        self.refresh_calls = 0
        self.saved = None

    def query(self, model):
        if model.__name__ == 'Issue':
            return FakeQuery([self.issue])
        if model.__name__ == 'Project':
            return FakeQuery([self.project]) if self.issue.project_id else FakeQuery([None])
        if model.__name__ == 'Customer':
            return FakeQuery([self.customer]) if self.project.customer_id else FakeQuery([None])
        if model.__name__ == 'AIAnalysisLog':
            return FakeQuery([self.saved] if self.saved else [])
        return FakeQuery([])

    def add(self, obj):
        self.add_calls += 1
        self.saved = obj

    def commit(self):
        self.commit_calls += 1
        if self.saved is not None and getattr(self.saved, 'id', None) is None:
            self.saved.id = 500

    def refresh(self, obj):
        self.refresh_calls += 1
        if getattr(obj, 'id', None) is None:
            obj.id = 500

    def rollback(self):
        self.rollback_calls += 1


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class QueryResult:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class CursorlessLog:
    pass


def make_outcome(status='succeeded', citations=None, error_code=None):
    citations = citations or ()
    evidence = tuple(
        KnowledgeEvidence(
            citation_id=f'K{i+1}',
            rank=i + 1,
            chunk_id=10 + i,
            document_id=20 + i,
            document_title=f'Doc {i+1}',
            scope_type='global',
            doc_type='solution_note',
            source_kind='manual',
            source_name='notes.md',
            source_uri=None,
            chunk_index=i,
            chunk_text=f'chunk {i+1}',
            distance=0.1 * (i + 1),
            similarity_score=1 - 0.1 * (i + 1),
        )
        for i, _ in enumerate(citations)
    )
    citation_snapshots = tuple(
        KnowledgeCitationSnapshot(
            citation_id=item.citation_id,
            rank=item.rank,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            document_title=item.document_title,
            scope_type=item.scope_type,
            doc_type=item.doc_type,
            source_kind=item.source_kind,
            source_name=item.source_name,
            source_uri=item.source_uri,
            chunk_index=item.chunk_index,
            chunk_text=item.chunk_text,
            similarity_score=item.similarity_score,
        )
        for item in evidence
    )
    return GroundedRetrievalOutcome(
        retrieval_status=status,
        retrieval_query='retrieval query',
        knowledge_evidence=evidence,
        knowledge_citations=citation_snapshots,
        retrieval_error_code=error_code,
    )


def assert_success_case() -> None:
    retrieval = StubRetrievalService(make_outcome(citations=(1, 2, 3)))
    llm = StubLLMProvider(provider='llm', model_name='gpt-4.1-mini')
    service = IssueAnalysisService(llm_provider=llm, grounded_retrieval_service=retrieval)
    db = FakeSession()
    log = service.analyze_and_store(101, db)
    assert retrieval.calls[0][0].id == 101
    assert retrieval.calls[0][1].id == 202
    assert retrieval.calls[0][2].id == 303
    assert retrieval.calls[0][3] is db
    assert llm.calls[0].retrieval_query == 'retrieval query'
    assert llm.calls[0].knowledge_evidence == retrieval.outcome.knowledge_evidence
    assert log.retrieval_status == 'succeeded'
    assert log.retrieval_query == 'retrieval query'
    assert json.loads(log.knowledge_citations_json)[0]['citation_id'] == 'K1'
    assert log.retrieval_error_code is None
    assert log.provider == 'llm'
    assert log.model_name == 'gpt-4.1-mini'
    assert log.prompt_version == 'issue_summarizer_v4_grounded'
    assert _serialize_analysis(log)['knowledge_grounded'] is True
    assert db.commit_calls == 1
    assert log.id == 500


def assert_no_results_case() -> None:
    retrieval = StubRetrievalService(make_outcome(status='no_results'))
    llm = StubLLMProvider()
    service = IssueAnalysisService(llm_provider=llm, grounded_retrieval_service=retrieval)
    db = FakeSession()
    log = service.analyze_and_store(101, db)
    assert log.retrieval_status == 'no_results'
    assert json.loads(log.knowledge_citations_json) == []
    assert log.retrieval_error_code is None
    assert log.prompt_version == 'issue_summarizer_v4_grounded'
    assert _serialize_analysis(log)['knowledge_grounded'] is False
    assert llm.calls[0].knowledge_evidence == ()


def assert_failed_case() -> None:
    retrieval = StubRetrievalService(make_outcome(status='failed', error_code='retrieval_internal_error'))
    llm = StubLLMProvider()
    service = IssueAnalysisService(llm_provider=llm, grounded_retrieval_service=retrieval)
    db = FakeSession()
    log = service.analyze_and_store(101, db)
    assert log.retrieval_status == 'failed'
    assert json.loads(log.knowledge_citations_json) == []
    assert log.retrieval_error_code == 'retrieval_internal_error'
    assert log.prompt_version == 'issue_summarizer_v4_grounded'
    assert _serialize_analysis(log)['knowledge_grounded'] is False
    assert len(llm.calls) == 1


def assert_rule_based_fallback_case() -> None:
    retrieval = StubRetrievalService(make_outcome(citations=(1,)))
    llm = StubLLMProvider(provider='rule_based_fallback', model_name=None)
    service = IssueAnalysisService(llm_provider=llm, grounded_retrieval_service=retrieval)
    db = FakeSession()
    log = service.analyze_and_store(101, db)
    assert log.provider == 'rule_based_fallback'
    assert log.prompt_version == 'issue_summarizer_v4_grounded'
    assert _serialize_analysis(log)['knowledge_grounded'] is False


def assert_route_shape() -> None:
    retrieval = StubRetrievalService(make_outcome(citations=(1,)))
    llm = StubLLMProvider()
    service = IssueAnalysisService(llm_provider=llm, grounded_retrieval_service=retrieval)
    db = FakeSession()
    log = service.analyze_and_store(101, db)
    serialized = _serialize_analysis(log)
    assert serialized['analysis_id'] == log.id
    assert serialized['retrieval_status'] == 'succeeded'


def assert_history_compatibility() -> None:
    old_log = CursorlessLog()
    old_log.id = 1
    old_log.issue_id = 101
    old_log.analysis_type = 'issue_summarizer'
    old_log.provider = 'llm'
    old_log.model_name = 'gpt-4.1-mini'
    old_log.prompt_version = 'issue_summarizer_v3'
    old_log.issue_summary = 'summary'
    old_log.possible_root_cause = 'cause'
    old_log.recommended_actions_json = '[]'
    old_log.customer_update_draft = 'draft'
    old_log.risk_level = 'low'
    old_log.project_impact = 'impact'
    old_log.feedback_status = 'pending'
    old_log.feedback_note = None
    old_log.edited_output = None
    old_log.retrieval_status = 'not_attempted'
    old_log.retrieval_query = None
    old_log.knowledge_citations_json = '[]'
    old_log.retrieval_error_code = None
    old_log.created_at = None
    old_log.updated_at = None
    assert _serialize_analysis(old_log)['knowledge_grounded'] is False

    v4_log = CursorlessLog()
    v4_log.__dict__.update(old_log.__dict__)
    v4_log.retrieval_status = 'succeeded'
    v4_log.prompt_version = 'issue_summarizer_v4_grounded'
    v4_log.knowledge_citations_json = json.dumps([asdict(make_outcome(citations=(1,)).knowledge_citations[0])])
    assert _serialize_analysis(v4_log)['knowledge_grounded'] is True


def main() -> None:
    assert_success_case()
    assert_no_results_case()
    assert_failed_case()
    assert_rule_based_fallback_case()
    assert_route_shape()
    assert_history_compatibility()
    print('Grounded analysis service integration stub assertions passed')


if __name__ == '__main__':
    main()
