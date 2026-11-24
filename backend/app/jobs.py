"""Background ingestion jobs with progress, run one at a time.

One worker on purpose: embedding is CPU and RAM heavy, and on an 8 GB laptop two parallel
ingestions would just thrash. Job state is in memory (fine for a single-process server);
the documents table is the durable record.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.ingestion.pipeline import ingest_file

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    filename: str
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0.0
    document_id: str | None = None
    error: str | None = None
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")


def submit(path: Path, filename: str) -> Job:
    job = Job(id=uuid.uuid4().hex, filename=filename)
    with _lock:
        _jobs[job.id] = job
        # keep memory bounded
        if len(_jobs) > 200:
            for old in list(_jobs)[:50]:
                _jobs.pop(old, None)
    _executor.submit(_run, job, path)
    return job


def _run(job: Job, path: Path) -> None:
    def progress(stage: str, frac: float) -> None:
        job.stage, job.progress = stage, round(min(max(frac, 0.0), 1.0), 3)

    job.status = "running"
    try:
        named = path.with_name(job.filename)
        path.rename(named)
        result = ingest_file(named, progress=progress)
        job.document_id, job.skipped = result.document_id, result.skipped
        job.status, job.stage, job.progress = "done", "done", 1.0
    except Exception as e:  # noqa: BLE001
        log.exception("Job %s failed", job.id)
        job.status, job.error = "failed", str(e)[:500]
    finally:
        # The upload lives alone in its own temp folder; remove the folder.
        try:
            for p in path.parent.iterdir():
                p.unlink(missing_ok=True)
            path.parent.rmdir()
        except OSError:
            log.warning("Could not clean temp folder %s", path.parent)


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def all_jobs() -> list[Job]:
    return list(_jobs.values())
