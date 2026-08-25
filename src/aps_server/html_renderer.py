from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import quote

from .content_models import (
    DailyBriefingResponse,
    IdeaCluster,
    IdeaItem,
    IdeasResponse,
    Issue,
    ProjectBriefing,
    ProjectBriefingResponse,
    ProjectCatalogResponse,
    ServiceMaintenanceItem,
    ServiceMaintenanceResponse,
    TaskItem,
)


class HTMLRenderer:
    def __init__(self) -> None:
        self.templates = Path(__file__).parent / "templates"
        self.css = (self.templates / "content.css").read_text(encoding="utf-8")

    @staticmethod
    def _text(value: object | None) -> str:
        return escape("" if value is None else str(value), quote=True)

    @staticmethod
    def _date(value: object | None) -> str:
        return "-" if value is None else escape(str(value), quote=True)

    def _base(self, response, title: str) -> dict[str, str]:
        return {
            "SCHEMA_VERSION": response.schema_version,
            "VAULT_COMMIT": response.vault_commit,
            "VAULT_COMMIT_SHORT": response.vault_commit[:12],
            "GENERATED_AT": response.generated_at.isoformat(),
            "PAGE_TITLE": title,
            "SHA256": response.sha256,
            "STALE_BADGE_HTML": '<span class="stale">STALE</span>' if response.stale else "",
            "APS_CONTENT_CSS": self.css,
        }

    def _render(self, filename: str, values: dict[str, str], raw: set[str]) -> str:
        document = (self.templates / filename).read_text(encoding="utf-8")
        for key, value in values.items():
            replacement = value if key in raw else self._text(value)
            document = document.replace("{{" + key + "}}", replacement)
        if "{{" in document or "}}" in document:
            raise ValueError(f"unresolved HTML template placeholder in {filename}")
        return document

    def _task(self, task: TaskItem) -> str:
        task_id = f'<span class="mono">{self._text(task.task_id)}</span> ' if task.task_id else ""
        return (
            f'<li><span class="task-title">{task_id}{self._text(task.title)}</span>'
            f'<span class="completion">{self._text(task.completion)} · {self._text(task.status)}</span></li>'
        )

    def _issue(self, issue: Issue) -> str:
        subject = f" · {self._text(issue.subject_id)}" if issue.subject_id else ""
        return (
            f'<div class="card"><span class="badge alert">{self._text(issue.code)}</span>'
            f'<p>{self._text(issue.message)}{subject}</p></div>'
        )

    def _service_row(self, service: ServiceMaintenanceItem) -> str:
        return (
            "<tr>"
            f"<td><strong>{self._text(service.name)}</strong><br><span class=\"mono muted\">{self._text(service.service_id)}</span></td>"
            f'<td><span class="state {self._text(service.due_status)}">{self._text(service.due_status)}</span></td>'
            f"<td>{self._text(service.maintenance_cycle or '-')}</td>"
            f"<td>{self._date(service.last_maintenance)}</td>"
            f"<td>{self._date(service.next_maintenance_due)}</td>"
            f"<td>{service.days_overdue}</td>"
            f"<td>{self._text(service.maintenance_summary or '-')}</td>"
            "</tr>"
        )

    def _daily_service_row(self, service: ServiceMaintenanceItem) -> str:
        return (
            "<tr>"
            f"<td><strong>{self._text(service.name)}</strong><br><span class=\"mono muted\">{self._text(service.service_id)}</span></td>"
            f'<td><span class="state {self._text(service.due_status)}">{self._text(service.due_status)}</span></td>'
            f"<td>{self._date(service.last_maintenance)}</td>"
            f"<td>{self._date(service.next_maintenance_due)}</td>"
            f"<td>{self._text(service.maintenance_summary or '-')}</td>"
            "</tr>"
        )

    def _project_record(self, project: ProjectBriefing) -> str:
        tasks = "".join(self._task(task) for task in project.tasks) or '<li class="muted">등록된 작업 없음</li>'
        decisions = "".join(f"<li>{self._text(item)}</li>" for item in project.decisions) or '<li class="muted">확인할 결정 없음</li>'
        issues = "".join(self._issue(issue) for issue in project.issues)
        project_url = "/v1/content/projects/" + quote(project.project_id, safe="") + "/briefing?format=html"
        return (
            '<details class="record">'
            f'<summary><span class="badge">{self._text(project.tier or "-")}</span>'
            f'<a href="{project_url}">{self._text(project.name)}</a><span class="state">{self._text(project.status)}</span></summary>'
            '<div class="record-body">'
            f'<section><h3>Today tasks</h3><ol>{tasks}</ol></section>'
            f'<section><h3>Decisions</h3><ul>{decisions}</ul></section>'
            '</div>'
            f'<div class="card-foot"><span>{self._text(project.summary)}</span><span>{len(project.issues)} issues</span></div>'
            f"{issues}</details>"
        )

    def daily_briefing(self, response: DailyBriefingResponse) -> str:
        values = self._base(response, "APS Daily Briefing")
        projects = "".join(self._project_record(item) for item in response.data.projects)
        services = "".join(self._daily_service_row(item) for item in response.data.service_maintenance)
        if not projects:
            projects = '<div class="empty">표시할 프로젝트가 없습니다.</div>'
        if not services:
            services = '<tr><td colspan="5" class="muted">점검 대상 서비스가 없습니다.</td></tr>'
        values.update(
            {
                "AS_OF_DATE": str(response.data.as_of_date),
                "ACTIVE_PROJECT_COUNT": str(response.data.summary.active_projects),
                "TASK_COUNT": str(response.data.summary.tasks),
                "DECISION_COUNT": str(response.data.summary.decisions),
                "SERVICE_DUE_COUNT": str(response.data.summary.services_due),
                "PROJECT_RESULT_SUMMARY": f"{len(response.data.projects)} project records",
                "SERVICE_RESULT_SUMMARY": f"{len(response.data.service_maintenance)} service records",
                "PROJECT_RECORDS_HTML": projects,
                "SERVICE_ROWS_HTML": services,
            }
        )
        return self._render(
            "daily_briefing.html",
            values,
            {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "PROJECT_RECORDS_HTML", "SERVICE_ROWS_HTML"},
        )

    def project_catalog(self, response: ProjectCatalogResponse) -> str:
        values = self._base(response, "APS Project Catalog")
        rows = []
        for project in response.data.projects:
            project_url = "/v1/content/projects/" + quote(project.project_id, safe="") + "/briefing?format=html"
            available = "READY" if project.briefing_available else "MISSING"
            rows.append(
                "<tr>"
                f'<td class="mono">{self._text(project.project_id)}</td>'
                f'<td><a href="{project_url}"><strong>{self._text(project.name)}</strong></a></td>'
                f"<td>{self._text(project.status)}</td><td>{self._text(project.tier or '-')}</td>"
                f'<td><span class="state">{available}</span></td></tr>'
            )
        values.update(
            {
                "PROJECT_COUNT": str(len(response.data.projects)),
                "BRIEFING_COUNT": str(sum(item.briefing_available for item in response.data.projects)),
                "PROJECT_ROWS_HTML": "".join(rows) or '<tr><td colspan="5" class="muted">등록된 프로젝트가 없습니다.</td></tr>',
            }
        )
        return self._render(
            "project_catalog.html",
            values,
            {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "PROJECT_ROWS_HTML"},
        )

    def project_briefing(self, response: ProjectBriefingResponse) -> str:
        project = response.data.project
        values = self._base(response, project.name)
        values.update(
            {
                "PROJECT_NAME": project.name,
                "PROJECT_ID": project.project_id,
                "PROJECT_STATUS": project.status,
                "PROJECT_TIER": project.tier or "-",
                "PROJECT_SUMMARY": project.summary,
                "TASK_ITEMS_HTML": "".join(self._task(item) for item in project.tasks) or '<li class="muted">등록된 작업 없음</li>',
                "DECISION_ITEMS_HTML": "".join(f"<li>{self._text(item)}</li>" for item in project.decisions) or '<li class="muted">확인할 결정 없음</li>',
                "ISSUE_COUNT": str(len(project.issues)),
                "ISSUE_ITEMS_HTML": "".join(self._issue(item) for item in project.issues) or '<div class="empty">확인할 문제가 없습니다.</div>',
            }
        )
        return self._render(
            "project_briefing.html",
            values,
            {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "TASK_ITEMS_HTML", "DECISION_ITEMS_HTML", "ISSUE_ITEMS_HTML"},
        )

    def service_maintenance(self, response: ServiceMaintenanceResponse) -> str:
        values = self._base(response, "APS Service Maintenance")
        services = "".join(self._service_row(item) for item in response.data.services)
        issues = [issue for service in response.data.services for issue in service.issues]
        summary = response.data.summary
        values.update(
            {
                "AS_OF_DATE": str(response.data.as_of_date),
                "SCOPE": response.data.scope,
                "ACTIVE_SERVICE_COUNT": str(summary.active_services),
                "DUE_COUNT": str(summary.due),
                "OVERDUE_COUNT": str(summary.overdue),
                "UPCOMING_COUNT": str(summary.upcoming),
                "UNKNOWN_COUNT": str(summary.unknown),
                "SERVICE_ROWS_HTML": services or '<tr><td colspan="7" class="muted">조건에 맞는 서비스가 없습니다.</td></tr>',
                "ISSUE_COUNT": str(len(issues)),
                "ISSUE_ITEMS_HTML": "".join(self._issue(item) for item in issues) or '<div class="empty">metadata 문제가 없습니다.</div>',
            }
        )
        return self._render(
            "service_maintenance.html",
            values,
            {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "SERVICE_ROWS_HTML", "ISSUE_ITEMS_HTML"},
        )

    def _idea_card(self, idea: IdeaItem) -> str:
        tags = " ".join(f'<span class="badge">{self._text(tag)}</span>' for tag in idea.tags)
        return (
            '<article class="card">'
            f'<div>{tags} <span class="state">{self._text(idea.status)}</span></div>'
            f'<h3>{self._text(idea.idea_id)}</h3><p>{self._text(idea.content)}</p>'
            f'<div class="card-foot"><span>{self._text(idea.received_at.isoformat())}</span><span>{self._text(idea.cluster_id or "unclustered")}</span></div>'
            '</article>'
        )

    def _idea_cluster(self, cluster: IdeaCluster) -> str:
        members = "".join(f"<li>{self._text(item)}</li>" for item in cluster.member_idea_ids)
        categories = " ".join(f'<span class="badge">{self._text(item)}</span>' for item in cluster.categories)
        return (
            '<details class="record"><summary>'
            f'<span class="state">{self._text(cluster.merge_status)}</span><span>{self._text(cluster.canonical_idea)}</span>'
            f'<span class="mono">{len(cluster.member_idea_ids)} ideas</span></summary>'
            f'<div class="record-body"><section><h3>Members</h3><ul>{members}</ul></section><section><h3>Categories</h3><p>{categories}</p></section></div></details>'
        )

    def ideas(self, response: IdeasResponse, status_filter: str) -> str:
        values = self._base(response, "APS Ideas")
        values.update(
            {
                "IDEA_COUNT": str(len(response.data.ideas)),
                "CLUSTER_COUNT": str(len(response.data.clusters)),
                "STATUS_FILTER": status_filter,
                "IDEA_CARDS_HTML": "".join(self._idea_card(item) for item in response.data.ideas) or '<div class="empty">조건에 맞는 아이디어가 없습니다.</div>',
                "CLUSTER_RECORDS_HTML": "".join(self._idea_cluster(item) for item in response.data.clusters) or '<div class="empty">생성된 유사 아이디어 묶음이 없습니다.</div>',
            }
        )
        return self._render(
            "ideas.html",
            values,
            {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "IDEA_CARDS_HTML", "CLUSTER_RECORDS_HTML"},
        )
