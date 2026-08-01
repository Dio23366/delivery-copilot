from __future__ import annotations

from dataclasses import asdict

from app.ai.context_builder import build_issue_analysis_context
from app.ai.retrieval_query_builder import build_issue_retrieval_query
from app.ai.schemas import KnowledgeEvidence, IssueAnalysisContext
from app.ai.providers.rule_based import RuleBasedIssueAnalysisProvider


class FakeIssue:
    def __init__(self):
        self.id = 101
        self.title = '  Login failure  '
        self.description = '  Token exchange fails after deployment  '
        self.issue_type = '  auth '
        self.severity = ' high '
        self.status = ' open '
        self.owner = ' alice '


class FakeProject:
    def __init__(self):
        self.id = 202
        self.name = '  Payments Platform '
        self.status = 'active'
        self.delivery_stage = ' rollout '
        self.risk_level = 'medium'
        self.health = 'green'


class FakeCustomer:
    def __init__(self):
        self.id = 303
        self.name = '  Acme Corp '
        self.industry = '  finance '


class FakeResult:
    issue_summary = 'summary'
    possible_root_cause = 'cause'
    recommended_actions = ['action1']
    customer_update_draft = 'draft'
    risk_level = 'low'
    project_impact = 'impact'


def assert_query_builder() -> None:
    issue = FakeIssue()
    project = FakeProject()
    customer = FakeCustomer()
    query = build_issue_retrieval_query(issue, project, customer)
    lines = query.split('\n')
    assert len(lines) == 8
    assert lines == [
        'Issue title: Login failure',
        'Issue description: Token exchange fails after deployment',
        'Issue type: auth',
        'Severity: high',
        'Status: open',
        'Project name: Payments Platform',
        'Delivery stage: rollout',
        'Customer industry: finance',
    ]
    assert build_issue_retrieval_query(issue, project, customer) == query
    assert 'issue_id' not in query
    assert 'owner' not in query
    assert 'customer name' not in query.lower()
    assert 'project status' not in query.lower()
    assert 'project health' not in query.lower()
    assert 'project risk level' not in query.lower()
    assert not query.endswith(' ')

    blank_issue = FakeIssue()
    blank_issue.title = '   '
    blank_issue.description = None
    blank_issue.issue_type = ''
    blank_issue.severity = '   '
    blank_issue.status = None
    blank_project = FakeProject()
    blank_project.name = None
    blank_project.delivery_stage = '   '
    blank_customer = FakeCustomer()
    blank_customer.industry = ''
    blank_query = build_issue_retrieval_query(blank_issue, blank_project, blank_customer)
    assert 'not provided' in blank_query
    assert blank_query.split('\n')[0] == 'Issue title: not provided'


def assert_evidence_schema() -> None:
    evidence = KnowledgeEvidence(
        citation_id='c1',
        rank=1,
        chunk_id=11,
        document_id=22,
        document_title='Doc',
        scope_type='project',
        doc_type='solution_note',
        source_kind='manual',
        source_name='notes.md',
        source_uri=None,
        chunk_index=0,
        chunk_text='chunk text',
        distance=0.2,
        similarity_score=0.8,
    )
    payload = asdict(evidence)
    assert payload['citation_id'] == 'c1'
    assert payload['distance'] == 0.2
    assert payload['similarity_score'] == 0.8
    try:
        evidence.rank = 2
        raise AssertionError('expected frozen dataclass')
    except Exception:
        pass


def assert_context_builder() -> None:
    issue = FakeIssue()
    project = FakeProject()
    customer = FakeCustomer()
    evidence = (
        KnowledgeEvidence(
            citation_id='c1',
            rank=1,
            chunk_id=11,
            document_id=22,
            document_title='Doc',
            scope_type='project',
            doc_type='solution_note',
            source_kind='manual',
            source_name='notes.md',
            source_uri=None,
            chunk_index=0,
            chunk_text='chunk text',
            distance=0.2,
            similarity_score=0.8,
        ),
    )
    context = build_issue_analysis_context(issue, project, customer)
    assert isinstance(context, IssueAnalysisContext)
    assert context.retrieval_query is None
    assert context.knowledge_evidence == ()

    context2 = build_issue_analysis_context(issue, project, customer, retrieval_query='  query  ', knowledge_evidence=evidence)
    assert context2.retrieval_query == 'query'
    assert context2.knowledge_evidence == evidence
    context3 = build_issue_analysis_context(issue, project, customer, retrieval_query='   ')
    assert context3.retrieval_query is None
    assert isinstance(context2.knowledge_evidence, tuple)


def assert_rule_based_regression() -> None:
    context = build_issue_analysis_context(
        FakeIssue(),
        FakeProject(),
        FakeCustomer(),
        retrieval_query='query',
        knowledge_evidence=(
            KnowledgeEvidence(
                citation_id='c1',
                rank=1,
                chunk_id=11,
                document_id=22,
                document_title='Doc',
                scope_type='project',
                doc_type='solution_note',
                source_kind='manual',
                source_name='notes.md',
                source_uri=None,
                chunk_index=0,
                chunk_text='chunk text',
                distance=0.2,
                similarity_score=0.8,
            ),
        ),
    )
    provider = RuleBasedIssueAnalysisProvider()
    result = provider.analyze_issue(context)
    assert result.issue_summary
    assert result.possible_root_cause
    assert isinstance(result.recommended_actions, list)
    assert all(
        isinstance(action, str) and action.strip()
        for action in result.recommended_actions
    )
    assert result.customer_update_draft
    assert result.risk_level
    assert result.project_impact


def main() -> None:
    assert_query_builder()
    assert_evidence_schema()
    assert_context_builder()
    assert_rule_based_regression()
    print('Grounded RAG context foundation assertions passed')


if __name__ == '__main__':
    main()
