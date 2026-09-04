"""Fixed operation allowlist and Vault-backed operation executor."""

from __future__ import annotations

from .agent import AgentExecutionContext, AgentExecutionError, AgentExecutor
from .config import Settings
from .content_models import IdeaCurationPlan, IdeasData
from .content_store import ContentStore
from .extension_host import ExtensionHost, ExtensionHostError
from .extensions import ExtensionRegistry
from .idea_catalog import IdeaCatalogError, load_idea_catalog
from .idea_search import search_ideas
from .idea_service import IdeaService, IdeaServiceError
from .models import (
    BriefingDailyJobRequest,
    BriefingProjectJobRequest,
    CreateJobRequest,
    IdeasCurateJobRequest,
    IdeasIndexRefreshJobRequest,
    OperationName,
    ServiceMaintenanceDueJobRequest,
    VaultAuditJobRequest,
)
from .runtime import OperationRegistry, OperationResult, OperationSpec
from .vault import VaultRepository
from .vault_files import read_vault_text


class OperationError(RuntimeError):
    def __init__(self, message: str, code: str = "OPERATION_FAILED") -> None:
        super().__init__(message)
        self.code = code


class OperationHandlers:
    """Domain handlers used by the immutable operation registry."""

    def __init__(
        self,
        settings: Settings,
        vault: VaultRepository,
        extensions: ExtensionRegistry,
        agent: AgentExecutor,
    ) -> None:
        self.vault = vault
        self.agent = agent
        self.extension_host = ExtensionHost(settings, extensions, vault)

    def extension_operation(self, request: CreateJobRequest) -> OperationResult:
        try:
            return OperationResult(output=self.extension_host.execute(request))
        except ExtensionHostError as error:
            raise OperationError(str(error), error.code) from error

    def vault_audit(self, _: CreateJobRequest) -> OperationResult:
        issues: list[dict[str, str]] = []
        projects = self.vault.root / "02_Projects"
        active_count = 0
        for note in sorted(projects.glob("*.md")):
            content = read_vault_text(self.vault.root, note)
            parts = content.split("---", 2)
            if not content.startswith("---") or len(parts) < 3:
                issues.append({"path": note.name, "code": "PROJECT_FRONTMATTER_INVALID"})
                continue
            metadata: dict[str, str] = {}
            frontmatter = parts[1]
            for line in frontmatter.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.split(" #", 1)[0].strip()
            if not metadata.get("status"):
                issues.append({"path": note.name, "code": "PROJECT_STATUS_MISSING"})
            elif metadata["status"] == "In_Progress":
                active_count += 1
        return OperationResult(output={"active_projects": active_count, "issues": issues, "healthy": not issues})

    def ideas_index(self, _: CreateJobRequest) -> OperationResult:
        try:
            return OperationResult(output=load_idea_catalog(self.vault.root))
        except (OSError, IdeaCatalogError) as error:
            raise OperationError(str(error), "IDEA_CATALOG_INVALID") from error

    def ideas_curate(self, _: CreateJobRequest) -> OperationResult:
        try:
            service = IdeaService(self.vault, sync_before_write=False)
            pending = service.pending()
            if pending.ideas:
                committed = IdeasData.model_validate(load_idea_catalog(self.vault.root))
                candidate_ids = {
                    result.idea_id
                    for pending_idea in pending.ideas
                    for result in search_ideas(
                        committed.ideas,
                        " ".join([pending_idea.title, *pending_idea.keywords, pending_idea.summary]),
                        5,
                    )
                }
                execution = self.agent.execute(
                    "ideas.curate-plan",
                    {
                        "pending_ideas": [item.model_dump(mode="json") for item in pending.ideas],
                        "pending_sets": [item.model_dump(mode="json") for item in pending.idea_sets],
                        "existing_candidates": [
                            item.model_dump(mode="json")
                            for item in committed.ideas
                            if item.idea_id in candidate_ids
                        ],
                    },
                    AgentExecutionContext(
                        snapshot_id=self.vault.commit(),
                        metadata={"pending_idea_count": len(pending.ideas)},
                    ),
                )
                if not isinstance(execution.output, IdeaCurationPlan):
                    raise OperationError("Idea Agent returned an unexpected result", "IDEA_CURATION_INVALID")
                output = service.curate(execution.output)
            else:
                output = service.curate()
            return OperationResult(output=output, vault_commit=self.vault.commit())
        except AgentExecutionError as error:
            raise OperationError("Idea curation Agent failed", error.code) from error
        except (OSError, IdeaCatalogError, IdeaServiceError) as error:
            code = error.code if isinstance(error, IdeaServiceError) else "IDEA_CURATION_FAILED"
            raise OperationError(str(error), code) from error


def build_operation_registry(
    settings: Settings,
    vault: VaultRepository,
    content_store: ContentStore,
    extensions: ExtensionRegistry,
    agent: AgentExecutor,
) -> OperationRegistry:
    handlers = OperationHandlers(settings, vault, extensions, agent)
    registry = OperationRegistry()
    registry.register(
        OperationSpec(
            name=OperationName.VAULT_AUDIT,
            owner="core",
            roles=frozenset({"scheduler", "operator"}),
            write_mode="none",
            request_model=VaultAuditJobRequest,
            handler=handlers.vault_audit,
        )
    )
    registry.register(
        OperationSpec(
            name=OperationName.IDEAS_INDEX_REFRESH,
            owner="core",
            roles=frozenset({"scheduler", "operator"}),
            write_mode="none",
            request_model=IdeasIndexRefreshJobRequest,
            handler=handlers.ideas_index,
            publisher=content_store.prepare_ideas,
        )
    )
    registry.register(
        OperationSpec(
            name=OperationName.IDEAS_CURATE,
            owner="core",
            roles=frozenset({"scheduler", "operator"}),
            write_mode="commit",
            request_model=IdeasCurateJobRequest,
            handler=handlers.ideas_curate,
            publisher=content_store.prepare_ideas,
        )
    )

    extension_specs = {
        OperationName.BRIEFING_DAILY: OperationSpec(
            name=OperationName.BRIEFING_DAILY,
            owner="briefing",
            roles=frozenset({"scheduler", "operator", "viewer"}),
            write_mode="none",
            request_model=BriefingDailyJobRequest,
            handler=handlers.extension_operation,
            publisher=content_store.prepare_daily,
        ),
        OperationName.BRIEFING_PROJECT: OperationSpec(
            name=OperationName.BRIEFING_PROJECT,
            owner="briefing",
            roles=frozenset({"operator", "viewer"}),
            write_mode="none",
            request_model=BriefingProjectJobRequest,
            handler=handlers.extension_operation,
            publisher=content_store.prepare_project,
        ),
        OperationName.SERVICE_MAINTENANCE_DUE: OperationSpec(
            name=OperationName.SERVICE_MAINTENANCE_DUE,
            owner="briefing",
            roles=frozenset({"scheduler", "operator", "viewer"}),
            write_mode="none",
            request_model=ServiceMaintenanceDueJobRequest,
            handler=handlers.extension_operation,
            publisher=content_store.prepare_service,
        ),
    }
    for name, owner in extensions.operation_owners.items():
        spec = extension_specs.get(name)
        if spec is None or owner != spec.owner:
            raise ValueError(f"unsupported extension operation registration: {name}")
        registry.register(spec)
    registry.freeze()
    return registry
