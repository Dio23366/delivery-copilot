from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import asdict
from importlib import util
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai.schemas import KnowledgeCitationSnapshot, RetrievalStatus
from app.database import init_db
from app.models import AIAnalysisLog, Base


def assert_schema() -> None:
    assert set(RetrievalStatus.__args__) == {'not_attempted', 'succeeded', 'no_results', 'failed'}
    snapshot = KnowledgeCitationSnapshot(
        citation_id='c1',
        rank=1,
        chunk_id=10,
        document_id=20,
        document_title='Doc',
        scope_type='project',
        doc_type='solution_note',
        source_kind='manual',
        source_name='notes.md',
        source_uri=None,
        chunk_index=0,
        chunk_text='hello',
        similarity_score=0.9,
    )
    payload = asdict(snapshot)
    assert payload['citation_id'] == 'c1'
    assert payload['rank'] == 1
    assert payload['chunk_text'] == 'hello'


def assert_model_defaults() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        analysis = AIAnalysisLog(
            issue_id=1,
            issue_summary='s',
            possible_root_cause='r',
            recommended_actions_json='[]',
            customer_update_draft='c',
            risk_level='low',
            project_impact='p',
        )
        session.add(analysis)
        session.flush()
        assert analysis.retrieval_status == 'not_attempted'
        assert analysis.retrieval_query is None
        assert analysis.knowledge_citations_json == '[]'
        assert analysis.retrieval_error_code is None
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def assert_sqlite_legacy_compatibility() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / 'legacy_ai.sqlite3'
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE ai_analysis_logs (
                    id INTEGER PRIMARY KEY,
                    issue_id INTEGER NOT NULL,
                    analysis_type VARCHAR(100) NOT NULL DEFAULT 'issue_summarizer',
                    provider VARCHAR(50) NOT NULL DEFAULT 'rule_based_fallback',
                    model_name VARCHAR(255),
                    prompt_version VARCHAR(100),
                    issue_summary TEXT NOT NULL,
                    possible_root_cause TEXT NOT NULL,
                    recommended_actions_json TEXT NOT NULL,
                    customer_update_draft TEXT NOT NULL,
                    risk_level VARCHAR(50) NOT NULL,
                    project_impact TEXT NOT NULL,
                    feedback_status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    feedback_note TEXT,
                    edited_output TEXT,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
            conn.execute(
                "INSERT INTO ai_analysis_logs (issue_id, issue_summary, possible_root_cause, recommended_actions_json, customer_update_draft, risk_level, project_impact) VALUES (1, 's', 'r', '[]', 'c', 'low', 'p')"
            )
            conn.commit()
        finally:
            conn.close()

        env = os.environ.copy()
        env['DATABASE_URL'] = f'sqlite:///{db_path}'
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get('PYTHONPATH', '')
        script = "from app.database import init_db; init_db(); init_db(); print('ok')"
        subprocess.run([sys.executable, '-c', script], check=True, env=env, cwd=str(Path(__file__).resolve().parents[1]))

        conn = sqlite3.connect(db_path)
        try:
            columns = {row[1] for row in conn.execute('PRAGMA table_info(ai_analysis_logs)').fetchall()}
            assert 'retrieval_status' in columns
            assert 'retrieval_query' in columns
            assert 'knowledge_citations_json' in columns
            assert 'retrieval_error_code' in columns
            row = conn.execute('SELECT retrieval_status, knowledge_citations_json FROM ai_analysis_logs WHERE id = 1').fetchone()
            assert row[0] == 'not_attempted'
            assert row[1] == '[]'
        finally:
            conn.close()


def assert_serializer() -> None:
    from app.api.ai import _load_knowledge_citations, _serialize_analysis

    class Log:
        pass

    def make_log() -> Log:
        log = Log()
        log.id = 1
        log.issue_id = 10
        log.analysis_type = 'issue_summarizer'
        log.provider = 'rule_based_fallback'
        log.model_name = None
        log.prompt_version = 'issue_summarizer_v3'
        log.issue_summary = 's'
        log.possible_root_cause = 'r'
        log.recommended_actions_json = '[]'
        log.customer_update_draft = 'c'
        log.risk_level = 'low'
        log.project_impact = 'p'
        log.feedback_status = 'pending'
        log.feedback_note = None
        log.edited_output = None
        log.retrieval_status = 'not_attempted'
        log.retrieval_query = None
        log.knowledge_citations_json = '[]'
        log.retrieval_error_code = None
        log.created_at = None
        log.updated_at = None
        return log

    log = make_log()
    assert _serialize_analysis(log)['knowledge_grounded'] is False

    log = make_log()
    log.provider = 'llm'
    log.retrieval_status = 'succeeded'
    log.knowledge_citations_json = json.dumps([
        {'citation_id': 'c1'},
        {'citation_id': 'c2'},
    ])
    log.prompt_version = 'issue_summarizer_v3'
    payload = _serialize_analysis(log)
    assert payload['knowledge_grounded'] is False

    log = make_log()
    log.provider = 'llm'
    log.retrieval_status = 'succeeded'
    log.knowledge_citations_json = json.dumps([
        {'citation_id': 'c1'},
        {'citation_id': 'c2'},
    ])
    log.prompt_version = 'issue_summarizer_v4_grounded'
    payload = _serialize_analysis(log)
    assert payload['knowledge_grounded'] is True

    log = make_log()
    log.provider = 'rule_based_fallback'
    log.retrieval_status = 'succeeded'
    log.knowledge_citations_json = json.dumps([
        {'citation_id': 'c1'},
    ])
    log.prompt_version = 'issue_summarizer_v4_grounded'
    assert _serialize_analysis(log)['knowledge_grounded'] is False

    log = make_log()
    log.provider = 'llm'
    log.retrieval_status = 'no_results'
    log.knowledge_citations_json = '[]'
    log.prompt_version = 'issue_summarizer_v4_grounded'
    assert _serialize_analysis(log)['knowledge_grounded'] is False

    log = make_log()
    log.knowledge_citations_json = '{bad json'
    assert _serialize_analysis(log)['knowledge_citations'] == []
    assert _serialize_analysis(log)['knowledge_grounded'] is False

    log = make_log()
    log.knowledge_citations_json = json.dumps({'not': 'list'})
    assert _serialize_analysis(log)['knowledge_citations'] == []
    assert _serialize_analysis(log)['knowledge_grounded'] is False
    assert _load_knowledge_citations(None) == []
    assert _load_knowledge_citations('   ') == []


def assert_migration_metadata() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    migration_path = (
        backend_root
        / 'alembic'
        / 'versions'
        / '0004_grounded_rag_analysis.py'
    )

    assert migration_path.is_file()

    spec = util.spec_from_file_location(
        'delivery_copilot_migration_0004_grounded_rag_analysis',
        migration_path,
    )

    assert spec is not None
    assert spec.loader is not None

    migration = util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == '0004_grounded_rag_analysis'
    assert migration.down_revision == '0003_embeddings'


def main() -> None:
    assert_schema()
    assert_model_defaults()
    assert_sqlite_legacy_compatibility()
    assert_serializer()
    assert_migration_metadata()
    print('Grounded RAG persistence foundation assertions passed')


if __name__ == '__main__':
    main()
