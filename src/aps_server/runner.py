from __future__ import annotations

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from .config import Settings
from .models import ErrorDetail, JobStatus
from .operations import OperationExecutor
from .store import JobStore
from .vault import VaultRepository


class JobRunner:
    def __init__(self, settings: Settings, store: JobStore, vault: VaultRepository) -> None:
        self.settings = settings
        self.store = store
        self.vault = vault
        self.operations = OperationExecutor(settings, vault)
        self.pool = ThreadPoolExecutor(max_workers=settings.job_workers, thread_name_prefix="aps-job")

    def submit(self, job_id: str) -> None:
        self.pool.submit(self._run, job_id)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _run(self, job_id: str) -> None:
        stored = self.store.get(job_id)
        if stored.public.status == JobStatus.CANCELLED:
            return
        try:
            if self.settings.sync_before_job:
                stored.public.status = JobStatus.SYNCING
                stored.public.started_at = datetime.now(UTC)
                self.store.save(stored)
                stored.public.vault_commit = self.vault.sync()
            else:
                stored.public.started_at = datetime.now(UTC)
                stored.public.vault_commit = self.vault.commit() if (self.vault.root / ".git").exists() else "unversioned-test-vault"

            stored.public.status = JobStatus.RUNNING
            self.store.save(stored)
            result, artifacts, artifact_paths = self.operations.execute(job_id, stored.request)
            stored.public.status = JobStatus.VALIDATING
            self.store.save(stored)
            stored.public.result = result
            stored.public.artifacts = artifacts
            stored.artifact_paths = artifact_paths
            stored.public.status = JobStatus.SUCCEEDED
        except Exception as error:  # Worker boundary: isolate one failed Job from the process.
            stored.public.status = JobStatus.FAILED
            stored.public.error = ErrorDetail(
                code=type(error).__name__.upper(),
                message=str(error),
                request_id="req_" + secrets.token_hex(13).upper(),
            )
        finally:
            stored.public.finished_at = datetime.now(UTC)
            self.store.save(stored)
