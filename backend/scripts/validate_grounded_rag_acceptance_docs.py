from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = ROOT / 'docs' / 'grounded-rag-acceptance.md'
JSON_PATH = ROOT / 'docs' / 'evidence' / 'grounded-rag-analysis-67.json'


def assert_files_exist() -> None:
    assert DOC_PATH.is_file()
    assert JSON_PATH.is_file()


def assert_json() -> dict[str, object]:
    raw = JSON_PATH.read_text(encoding='utf-8')
    assert raw.endswith('\n')
    data = json.loads(raw)
    required = {
        'acceptance_status',
        'analysis_id',
        'issue_id',
        'provider',
        'model_name',
        'prompt_version',
        'retrieval_status',
        'retrieval_query_present',
        'citation_count',
        'top_document_id',
        'top_document_title',
        'retrieval_error_code',
        'knowledge_grounded',
        'risk_level',
        'feedback_status',
        'analysis_total_before',
        'analysis_total_after',
        'latest_analysis_id_after',
        'postgresql_record_verified',
        'analysis_history_verified',
        'git_commit',
        'git_tag',
        'runtime_alembic_revision',
    }
    assert required.issubset(data)
    assert data['acceptance_status'] == 'passed'
    assert data['analysis_id'] == 67
    assert data['issue_id'] == 17
    assert data['provider'] == 'llm'
    assert data['model_name'] == 'gpt-5.5'
    assert data['prompt_version'] == 'issue_summarizer_v4_grounded'
    assert data['retrieval_status'] == 'succeeded'
    assert data['citation_count'] == 4
    assert data['top_document_id'] == 3
    assert data['knowledge_grounded'] is True
    assert data['analysis_total_before'] == 66
    assert data['analysis_total_after'] == 67
    assert data['latest_analysis_id_after'] == 67
    assert data['git_commit'] == '1ef73af'
    assert data['git_tag'] == 'sprint-2c1b-3a-grounded-prompt'
    assert 'retrieval_query' not in data
    assert 'chunk_text' not in data
    assert 'api_key' not in data
    assert 'authorization' not in data
    assert 'prompt' not in data
    return data


def assert_markdown() -> None:
    text = DOC_PATH.read_text(encoding='utf-8')
    assert text.endswith('\n')
    sections = [
        '# Grounded RAG End-to-End Acceptance',
        '## 1. Acceptance Status',
        '## 2. Runtime and Git Baseline',
        '## 3. Acceptance Scenario',
        '## 4. Verified End-to-End Chain',
        '## 5. Acceptance Evidence',
        '## 6. Structured Output Contract',
        '## 7. Grounding and Safety Semantics',
        '## 8. Persistence and Audit Evidence',
        '## 9. Known Limitations',
        '## 10. Post-Acceptance Knowledge Cleanup',
        '## 11. Reproduction Notes',
        '## 12. Conclusion',
    ]
    for section in sections:
        assert section in text
    required_strings = [
        'Analysis #67',
        'Document #3',
        'knowledge_grounded=true',
        'issue_summarizer_v4_grounded',
        '0004_grounded_rag_analysis',
        '[evidence snapshot](./evidence/grounded-rag-analysis-67.json)',
        'Known Limitations',
        'Document #4',
        'archived',
        '3 chunks',
        '1536',
        'citation snapshot',
        'result_count=1',
        'No LLM request',
        'No Analysis record',
    ]
    for value in required_strings:
        assert value in text
    forbidden = [
        'sk-',
        'Bearer ',
        'API_LLM_API_KEY',
        'EMBEDDING_API_KEY',
        'ap-southeast-1.maas',
        'Smoke Test 文档仍存在，可能进入低排名 Citations',
        'may enter low-ranked citations',
    ]
    for value in forbidden:
        assert value not in text


def main() -> None:
    assert_files_exist()
    assert_json()
    assert_markdown()
    print('Grounded RAG acceptance documentation assertions passed')


if __name__ == '__main__':
    main()
