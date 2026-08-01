from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from app.models import Customer, KnowledgeChunk, KnowledgeDocument, Project
from app.schemas.knowledge import KnowledgeDocumentCreate
from app.services.text_chunker import TextChunker


class KnowledgeService:
    def __init__(self) -> None:
        self.chunker = TextChunker()

    def _normalize_text(self, value: str) -> str:
        return value.replace('\r\n', '\n').strip()

    def _compute_hash(self, value: str) -> str:
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    def _validate_scope(self, payload: KnowledgeDocumentCreate) -> None:
        if payload.scope_type.value == 'global':
            if payload.customer_id is not None or payload.project_id is not None:
                raise HTTPException(status_code=422, detail='Invalid scope_type')
        elif payload.scope_type.value == 'customer':
            if payload.customer_id is None or payload.project_id is not None:
                raise HTTPException(status_code=422, detail='Invalid scope_type')
        elif payload.scope_type.value == 'project':
            if payload.project_id is None or payload.customer_id is not None:
                raise HTTPException(status_code=422, detail='Invalid scope_type')
        else:
            raise HTTPException(status_code=422, detail='Invalid scope_type')

    def _ensure_related_entities(self, payload: KnowledgeDocumentCreate, db: Session) -> None:
        if payload.customer_id is not None:
            customer = db.query(Customer).filter(Customer.id == payload.customer_id).first()
            if customer is None:
                raise HTTPException(status_code=404, detail='Customer not found')
        if payload.project_id is not None:
            project = db.query(Project).filter(Project.id == payload.project_id).first()
            if project is None:
                raise HTTPException(status_code=404, detail='Project not found')

    def _check_duplicate(self, scope_type: str, customer_id: int | None, project_id: int | None, content_hash: str, db: Session) -> None:
        query = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.scope_type == scope_type,
            KnowledgeDocument.content_hash == content_hash,
            KnowledgeDocument.status != 'archived',
        )
        if scope_type == 'global':
            query = query.filter(KnowledgeDocument.customer_id.is_(None), KnowledgeDocument.project_id.is_(None))
        elif scope_type == 'customer':
            query = query.filter(KnowledgeDocument.customer_id == customer_id, KnowledgeDocument.project_id.is_(None))
        elif scope_type == 'project':
            query = query.filter(KnowledgeDocument.project_id == project_id, KnowledgeDocument.customer_id.is_(None))
        if query.first() is not None:
            raise HTTPException(status_code=409, detail='Duplicate knowledge document content within the same scope')

    def create_document(self, payload: KnowledgeDocumentCreate, db: Session) -> KnowledgeDocument:
        self._validate_scope(payload)
        self._ensure_related_entities(payload, db)

        title = payload.title.strip()
        content_text = self._normalize_text(payload.content_text)
        if not title:
            raise HTTPException(status_code=422, detail='title must not be blank')
        if not content_text:
            raise HTTPException(status_code=422, detail='content_text must not be blank')

        content_hash = self._compute_hash(content_text)
        self._check_duplicate(payload.scope_type.value, payload.customer_id, payload.project_id, content_hash, db)

        document = KnowledgeDocument(
            scope_type=payload.scope_type.value,
            customer_id=payload.customer_id,
            project_id=payload.project_id,
            title=title,
            doc_type=payload.doc_type.value,
            source_kind=payload.source_kind.value,
            source_uri=payload.source_uri.strip() if isinstance(payload.source_uri, str) and payload.source_uri.strip() else None,
            source_name=payload.source_name.strip() if isinstance(payload.source_name, str) and payload.source_name.strip() else None,
            content_text=content_text,
            content_hash=content_hash,
            version_label=payload.version_label.strip() if isinstance(payload.version_label, str) and payload.version_label.strip() else None,
            status='pending',
        )

        try:
            db.add(document)
            db.flush()

            chunks = self.chunker.chunk(content_text)
            if not chunks:
                raise HTTPException(status_code=500, detail='Text chunker produced no chunks')

            for index, chunk in enumerate(chunks):
                if not chunk.chunk_text:
                    raise HTTPException(status_code=500, detail='Text chunker produced empty chunk')
                if chunk.source_span_start < 0:
                    raise HTTPException(status_code=500, detail='Invalid chunk span')
                if chunk.source_span_end <= chunk.source_span_start:
                    raise HTTPException(status_code=500, detail='Invalid chunk span')
                if chunk.source_span_end > len(content_text):
                    raise HTTPException(status_code=500, detail='Invalid chunk span')
                if content_text[chunk.source_span_start:chunk.source_span_end] != chunk.chunk_text:
                    raise HTTPException(status_code=500, detail='Chunk text does not match normalized content span')

                db.add(
                    KnowledgeChunk(
                        document_id=document.id,
                        chunk_index=index,
                        chunk_text=chunk.chunk_text,
                        chunk_title=None,
                        section_path=None,
                        page_number=None,
                        token_count=None,
                        char_count=len(chunk.chunk_text),
                        source_span_start=chunk.source_span_start,
                        source_span_end=chunk.source_span_end,
                        metadata_json=None,
                    )
                )

            now = datetime.utcnow()
            document.status = 'ready'
            document.ingested_at = now
            document.last_indexed_at = now
            db.commit()
            db.refresh(document)
            return document
        except Exception:
            db.rollback()
            raise

    def list_documents(self, db: Session, **filters) -> list[KnowledgeDocument]:
        query = db.query(KnowledgeDocument).options(selectinload(KnowledgeDocument.chunks))
        if filters.get('scope_type') is not None:
            query = query.filter(KnowledgeDocument.scope_type == filters['scope_type'])
        if filters.get('customer_id') is not None:
            query = query.filter(KnowledgeDocument.customer_id == filters['customer_id'])
        if filters.get('project_id') is not None:
            query = query.filter(KnowledgeDocument.project_id == filters['project_id'])
        if filters.get('status') is not None:
            query = query.filter(KnowledgeDocument.status == filters['status'])
        if filters.get('doc_type') is not None:
            query = query.filter(KnowledgeDocument.doc_type == filters['doc_type'])
        return query.order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc()).all()

    def get_document(self, document_id: int, db: Session) -> KnowledgeDocument:
        document = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
        if document is None:
            raise HTTPException(status_code=404, detail='Knowledge document not found')
        return document

    def get_document_chunks(self, document_id: int, db: Session) -> list[KnowledgeChunk]:
        self.get_document(document_id, db)
        return (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index.asc(), KnowledgeChunk.id.asc())
            .all()
        )


knowledge_service = KnowledgeService()
