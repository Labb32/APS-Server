from __future__ import annotations

import secrets
import threading
from pathlib import Path

from .atomic import write_text
from .models import CreateJobRequest, ErrorDetail, Job, JobStatus, StoredJob


class JobStore:
    def __init__(self, data_path: Path) -> None:
        self.jobs_path = data_path / "jobs"
        self.jobs_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _load(path: Path) -> StoredJob:
        return StoredJob.model_validate_json(path.read_text(encoding="utf-8"))

    def create(self, request: CreateJobRequest, role: str, created_at, idempotency_key: str | None = None) -> StoredJob:
        job_id = "job_" + secrets.token_hex(13).upper()
        stored = StoredJob(
            public=Job(
                job_id=job_id,
                status=JobStatus.QUEUED,
                operation=request.operation,
                created_at=created_at,
            ),
            request=request,
            role=role,
            idempotency_key=idempotency_key,
        )
        self.save(stored)
        return stored

    def find_by_idempotency(self, role: str, key: str) -> StoredJob | None:
        with self._lock:
            for path in self.jobs_path.glob("job_*.json"):
                stored = self._load(path)
                if stored.role == role and stored.idempotency_key == key:
                    return stored
        return None

    def queued_job_ids(self) -> list[str]:
        with self._lock:
            return [
                stored.public.job_id
                for path in sorted(self.jobs_path.glob("job_*.json"))
                if (stored := self._load(path)).public.status == JobStatus.QUEUED
            ]

    def recover(self, recovered_at) -> list[str]:
        """Fail interrupted work and return persisted queued Jobs for re-enqueueing."""
        queued: list[str] = []
        active = {
            JobStatus.SYNCING,
            JobStatus.RUNNING,
            JobStatus.VALIDATING,
            JobStatus.PUBLISHING,
        }
        with self._lock:
            for path in sorted(self.jobs_path.glob("job_*.json")):
                stored = self._load(path)
                if stored.public.status == JobStatus.QUEUED:
                    queued.append(stored.public.job_id)
                elif stored.public.status in active:
                    stored.public.status = JobStatus.FAILED
                    stored.public.finished_at = recovered_at
                    stored.public.error = ErrorDetail(
                        code="JOB_INTERRUPTED",
                        message="The server stopped before the Job completed.",
                        request_id="recovery",
                    )
                    self.save(stored)
        return queued

    def path_for(self, job_id: str) -> Path:
        if not job_id.startswith("job_") or len(job_id) != 30 or not job_id[4:].isalnum():
            raise KeyError(job_id)
        return self.jobs_path / f"{job_id}.json"

    def get(self, job_id: str) -> StoredJob:
        path = self.path_for(job_id)
        with self._lock:
            if not path.is_file():
                raise KeyError(job_id)
            return self._load(path)

    def save(self, stored: StoredJob) -> None:
        path = self.path_for(stored.public.job_id)
        with self._lock:
            write_text(path, stored.model_dump_json(indent=2))

    def cancel(self, job_id: str) -> StoredJob:
        with self._lock:
            stored = self.get(job_id)
            if stored.public.status != JobStatus.QUEUED:
                raise ValueError("only queued jobs can be cancelled")
            stored.public.status = JobStatus.CANCELLED
            self.save(stored)
            return stored

    def discard_queued(self, job_id: str) -> None:
        path = self.path_for(job_id)
        with self._lock:
            stored = self.get(job_id)
            if stored.public.status != JobStatus.QUEUED:
                raise ValueError("only queued jobs can be discarded")
            path.unlink()
