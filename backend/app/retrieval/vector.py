"""Dense vector search over chunks with pgvector (cosine distance, HNSW index)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.retrieval.embedder import get_embedder
from app.retrieval.types import RetrievedChunk


def vector_search(session: Session, query: str, k: int,
                  document_ids: list[str] | None = None) -> list[RetrievedChunk]:
    qvec = get_embedder().embed_query(query)
    distance = Chunk.embedding.cosine_distance(qvec)
    stmt = (
        select(Chunk, Document, distance.label("distance"))
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "ready")
        .order_by(distance)
        .limit(k)
    )
    if document_ids:
        stmt = stmt.where(Chunk.document_id.in_(document_ids))

    results: list[RetrievedChunk] = []
    for rank, (chunk, doc, dist) in enumerate(session.execute(stmt).all(), start=1):
        score = 1.0 - float(dist)  # cosine similarity
        results.append(RetrievedChunk(
            chunk_id=str(chunk.id), document_id=str(doc.id), doc_title=doc.title,
            filename=doc.filename, page=chunk.page, section=chunk.section, text=chunk.text,
            char_start=chunk.char_start, char_end=chunk.char_end, lang=chunk.lang,
            paginated=doc.paginated, score=score, rank=rank, scores={"vector": score},
        ))
    return results
