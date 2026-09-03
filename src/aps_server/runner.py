"""Bounded in-process queue and serialized APS job execution."""

from __future__ import annotations

import secrets
import queue
import threading
from datetime import UTC, datetime

from .config import Settings
from .content_store import ContentStore, ContentValidationError
from .models import ErrorDetail, JobStatus
from .operations import OperationError
from .runtime import OperationRegistry, OperationRegistryError
from .store import JobStore
from .vault import VaultError, VaultRepository


class JobRunner:
    def __init__(
        self,
        settings: Settings,
        store: JobStore,
        content_store: ContentStore,
        vault: VaultRepository,
        operations: OperationRegistry,
    ) -> None:
        self.settings = settings
        self.store = store
        self.content_store = content_store
        self.vault = vault
        self.operations = operations
        self.queue: queue.Queue[str] = queue.Queue(maxsize=settings.job_queue_size)
        self._workers: list[threading.Thread] = []
        self._known: set[str] = set()
        self._known_lock = threading.Lock()
        self._execution_lock = threading.Lock()
        self._stopping = threading.Event()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for number in range(self.settings.job_workers):
            worker = threading.Thread(
                target=self._worker,
                name=f"aps-job-{number + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)
        for job_id in self.store.recover(datetime.now(UTC)):
            self.submit(job_id)

    def submit(self, job_id: str) -> None:
        if not self._started or self._stopping.is_set():
            raise RuntimeError("Job queue is not running")
        with self._known_lock:
            if job_id in self._known:
                return
            self._known.add(job_id)
        try:
            self.queue.put_nowait(job_id)
        except queue.Full:
            with self._known_lock:
                self._known.discard(job_id)
            raise RuntimeError("Job queue is full") from None

    def shutdown(self) -> None:
        if not self._started:
            return
        self._stopping.set()
        for worker in self._workers:
            worker.join(timeout=1)

    def status(self) -> dict[str, int]:
        with self._known_lock:
            enqueued = len(self._known)
        return {
            "queued_and_running": enqueued,
            "capacity": self.settings.job_queue_size,
            "workers": self.settings.job_workers,
        }

    def _worker(self) -> None:
        while not self._stopping.is_set():
            try:
                job_id = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                # One Vault is shared by all operations. Serialize sync, generation,
                # validation and publication even when multiple queue workers exist.
                with self._execution_lock:
                    self._run(job_id)
            finally:
                with self._known_lock:
                    self._known.discard(job_id)
                self.queue.task_done()

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
            spec = self.operations.get(stored.request.operation)
            operation_result = self.operations.execute(stored.request)
            if operation_result.vault_commit is not None:
                stored.public.vault_commit = operation_result.vault_commit
            stored.public.status = JobStatus.VALIDATING
            self.store.save(stored)
            if stored.public.vault_commit is None:
                raise OperationError("operation has no Vault snapshot", "VAULT_COMMIT_MISSING")
            publications = (
                spec.publisher(operation_result.output, stored.public.vault_commit)
                if spec.publisher is not None
                else []
            )
            if publications:
                stored.public.status = JobStatus.PUBLISHING
                self.store.save(stored)
                self.content_store.publish(publications)
                primary = publications[0]
                stored.public.result = {
                    "content_type": primary.content_type,
                    "published": True,
                    "generated_at": primary.generated_at.isoformat(),
                    "sha256": primary.sha256,
                    "content_url": primary.content_url,
                    "published_content": [
                        {
                            "content_type": publication.content_type,
                            "sha256": publication.sha256,
                            "content_url": publication.content_url,
                        }
                        for publication in publications
                    ],
                }
            else:
                stored.public.result = operation_result.output
            stored.public.status = JobStatus.SUCCEEDED
        except Exception as error:  # Worker boundary: isolate one failed Job from the process.
            stored.public.status = JobStatus.FAILED
            if isinstance(error, ContentValidationError):
                error_code = "OUTPUT_SCHEMA_INVALID"
            elif isinstance(error, (OperationError, OperationRegistryError, VaultError)):
                error_code = error.code
            else:
                error_code = "INTERNAL_JOB_ERROR"
            stored.public.error = ErrorDetail(
                code=error_code,
                message=str(error),
                request_id="req_" + secrets.token_hex(13).upper(),
            )
        finally:
            stored.public.finished_at = datetime.now(UTC)
            self.store.save(stored)
