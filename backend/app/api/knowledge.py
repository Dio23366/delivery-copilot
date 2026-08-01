from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge import (
    DocType,
    KnowledgeChunkRead,
    KnowledgeDocumentCreate,
    KnowledgeDocumentListItem,
    KnowledgeDocumentRead,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeStatus,
    ScopeType,
)
from app.services.embedding_service import embedding_service
from app.services.knowledge_search_service import knowledge_search_service
from app.services.knowledge_service import knowledge_service

router = APIRouter()


class ChunkEmbeddingResponse(BaseModel):
    chunk_id: int
    document_id: int
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    embedded_at: datetime
    status: str = 'embedded'


class BatchEmbeddingFailureResponse(BaseModel):
    chunk_id: int
    status_code: int
    detail: str


class BatchEmbeddingResponse(BaseModel):
    document_id: int
    total: int
    succeeded: int
    skipped: int
    failed: int
    status: str
    failures: list[BatchEmbeddingFailureResponse]


def _serialize_document_list_item(document: KnowledgeDocument) -> dict[str, object]:
    return {
        'id': document.id,
        'scope_type': document.scope_type,
        'customer_id': document.customer_id,
        'project_id': document.project_id,
        'title': document.title,
        'doc_type': document.doc_type,
        'source_kind': document.source_kind,
        'source_uri': document.source_uri,
        'source_name': document.source_name,
        'content_hash': document.content_hash,
        'status': document.status,
        'chunk_count': len(document.chunks),
        'created_at': document.created_at,
        'ingested_at': document.ingested_at,
        'last_indexed_at': document.last_indexed_at,
    }


def _serialize_document_detail(document: KnowledgeDocument) -> dict[str, object]:
    data = _serialize_document_list_item(document)
    data['content_text'] = document.content_text
    return data


def _serialize_chunk(chunk: KnowledgeChunk) -> dict[str, object]:
    return {
        'id': chunk.id,
        'document_id': chunk.document_id,
        'chunk_index': chunk.chunk_index,
        'chunk_text': chunk.chunk_text,
        'char_count': chunk.char_count,
        'source_span_start': chunk.source_span_start,
        'source_span_end': chunk.source_span_end,
        'created_at': chunk.created_at,
    }


@router.post('/documents', status_code=status.HTTP_201_CREATED, response_model=KnowledgeDocumentRead)
def create_knowledge_document(payload: KnowledgeDocumentCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        document = knowledge_service.create_document(payload, db)
        return _serialize_document_detail(document)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail='Failed to create knowledge document')


@router.get('/documents', response_model=list[KnowledgeDocumentListItem])
def list_knowledge_documents(
    scope_type: ScopeType | None = None,
    customer_id: int | None = None,
    project_id: int | None = None,
    status: KnowledgeStatus | None = None,
    doc_type: DocType | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    documents = knowledge_service.list_documents(
        db,
        scope_type=scope_type.value if scope_type else None,
        customer_id=customer_id,
        project_id=project_id,
        status=status.value if status else None,
        doc_type=doc_type.value if doc_type else None,
    )
    return [_serialize_document_list_item(document) for document in documents]


@router.get('/documents/{document_id}', response_model=KnowledgeDocumentRead)
def get_knowledge_document(document_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    document = knowledge_service.get_document(document_id, db)
    return _serialize_document_detail(document)


@router.get('/documents/{document_id}/chunks', response_model=list[KnowledgeChunkRead])
def get_knowledge_document_chunks(document_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    chunks = knowledge_service.get_document_chunks(document_id, db)
    return [_serialize_chunk(chunk) for chunk in chunks]


@router.post('/chunks/{chunk_id}/embedding', response_model=ChunkEmbeddingResponse)
def embed_knowledge_chunk(chunk_id: int, force: bool = False, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        chunk = embedding_service.embed_chunk(chunk_id, db, force=force)
        return {
            'chunk_id': chunk.id,
            'document_id': chunk.document_id,
            'embedding_provider': chunk.embedding_provider,
            'embedding_model': chunk.embedding_model,
            'embedding_dimension': chunk.embedding_dimension,
            'embedded_at': chunk.embedded_at,
            'status': 'embedded',
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail='Failed to embed chunk')


@router.post('/documents/{document_id}/embeddings', response_model=BatchEmbeddingResponse)
def embed_knowledge_document_chunks(
    document_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        result = embedding_service.embed_document(
            document_id,
            db,
            force=force,
        )

        return {
            'document_id': result.document_id,
            'total': result.total,
            'succeeded': result.succeeded,
            'skipped': result.skipped,
            'failed': result.failed,
            'status': result.status,
            'failures': [
                {
                    'chunk_id': failure.chunk_id,
                    'status_code': failure.status_code,
                    'detail': failure.detail,
                }
                for failure in result.failures
            ],
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail='Failed to embed knowledge document')


@router.post('/search', response_model=KnowledgeSearchResponse)
def search_knowledge(
    payload: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
) -> KnowledgeSearchResponse:
    try:
        return knowledge_search_service.search(payload, db)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail='Knowledge search failed',
        )
