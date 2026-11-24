"""Document endpoints: upload (async ingestion job), list, detail, chunks, file, delete."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import jobs
from app.api.deps import RATE, db_session, limiter
from app.config import get_settings
from app.db.models import Chunk, Document, Trace
from app.ingestion.parsers import SUPPORTED_EXTENSIONS
from app.retrieval.bm25 import invalidate_bm25
from app.schemas.api import ChunkOut, DocumentOut, JobOut, StatsOut

router = APIRouter(prefix="/api", tags=["documents"])
MAX_UPLOAD_MB = 50
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def to_out(d: Document) -> DocumentOut:
    return DocumentOut(
        id=str(d.id), filename=d.filename, title=d.title, file_type=d.file_type, lang=d.lang,
        paginated=d.paginated, num_pages=d.num_pages, num_chunks=d.num_chunks,
        num_chars=d.num_chars, status=d.status, error=d.error, source_url=d.source_url,
        license=d.license, ingest_ms=d.ingest_ms, created_at=d.created_at)


def _get_doc(session: Session, doc_id: str) -> Document:
    try:
        uid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(404, "Document not found") from None
    doc = session.get(Document, uid)
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(session: Session = Depends(db_session)) -> list[DocumentOut]:
    docs = session.scalars(select(Document).order_by(Document.created_at.desc())).all()
    return [to_out(d) for d in docs]


@router.post("/documents", response_model=JobOut, status_code=202,
             summary="Upload a document; ingestion runs in the background")
@limiter.limit(RATE)
async def upload_document(request: Request, file: UploadFile = File(...)) -> JobOut:
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type {ext}. Supported: "
                                 f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    tmp_dir = get_settings().data_path / "tmp" / uuid.uuid4().hex
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"upload{ext}"
    size = 0
    with tmp_path.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                out.close()
                tmp_path.unlink(missing_ok=True)
                tmp_dir.rmdir()
                raise HTTPException(413, f"File larger than {MAX_UPLOAD_MB} MB")
            out.write(chunk)
    job = jobs.submit(tmp_path, name)
    return JobOut(**job.to_dict())


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str) -> JobOut:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobOut(**job.to_dict())


@router.get("/jobs", response_model=list[JobOut])
def list_jobs() -> list[JobOut]:
    return [JobOut(**j.to_dict()) for j in reversed(jobs.all_jobs())]


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, session: Session = Depends(db_session)) -> DocumentOut:
    return to_out(_get_doc(session, doc_id))


@router.get("/documents/{doc_id}/chunks", response_model=list[ChunkOut])
def get_chunks(doc_id: str, page: int | None = None,
               session: Session = Depends(db_session)) -> list[ChunkOut]:
    doc = _get_doc(session, doc_id)
    stmt = select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.chunk_index)
    if page is not None:
        stmt = stmt.where(Chunk.page == page)
    return [ChunkOut(id=str(c.id), chunk_index=c.chunk_index, page=c.page, section=c.section,
                     text=c.text, char_start=c.char_start, char_end=c.char_end, lang=c.lang)
            for c in session.scalars(stmt)]


@router.get("/documents/{doc_id}/file", summary="Original file (used by the PDF viewer)")
def get_file(doc_id: str, session: Session = Depends(db_session)) -> FileResponse:
    doc = _get_doc(session, doc_id)
    ext = f".{doc.file_type}" if doc.file_type != "markdown" else ".md"
    path = get_settings().uploads_dir / f"{doc.id}{ext}"
    if not path.exists():
        matches = list(get_settings().uploads_dir.glob(f"{doc.id}.*"))
        if not matches:
            raise HTTPException(404, "File not stored")
        path = matches[0]
    return FileResponse(path, media_type=MEDIA_TYPES.get(path.suffix.lower(),
                                                         "application/octet-stream"),
                        filename=doc.filename, content_disposition_type="inline")


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, session: Session = Depends(db_session)) -> None:
    doc = _get_doc(session, doc_id)
    for p in get_settings().uploads_dir.glob(f"{doc.id}.*"):
        p.unlink(missing_ok=True)
    session.delete(doc)
    session.flush()
    invalidate_bm25()


@router.get("/stats", response_model=StatsOut, tags=["system"])
def stats(session: Session = Depends(db_session)) -> StatsOut:
    ready = Document.status == "ready"
    docs, pages, chars = session.execute(
        select(func.count(Document.id), func.coalesce(func.sum(Document.num_pages), 0),
               func.coalesce(func.sum(Document.num_chars), 0)).where(ready)).one()
    chunks = session.scalar(select(func.count(Chunk.id))) or 0
    by_lang = dict(session.execute(select(Document.lang, func.count()).where(ready)
                                   .group_by(Document.lang)).all())
    by_type = dict(session.execute(select(Document.file_type, func.count()).where(ready)
                                   .group_by(Document.file_type)).all())
    q, refusals, avg = session.execute(
        select(func.count(Trace.id),
               func.count(Trace.id).filter(Trace.refused.is_(True)),
               func.avg(Trace.total_ms))).one()
    return StatsOut(documents=docs, chunks=chunks, pages=pages, chars=chars, by_lang=by_lang,
                    by_type=by_type, questions=q, refusals=refusals,
                    avg_latency_ms=round(avg, 1) if avg is not None else None)
