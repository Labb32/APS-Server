from __future__ import annotations

from html import escape
from pathlib import Path
import re
from urllib.parse import quote

from .content_models import (
    DailyBriefingResponse,
    IdeaSet,
    IdeaItem,
    IdeasResponse,
    IdeaSetsResponse,
    Issue,
    ProjectBriefing,
    ProjectBriefingResponse,
    ProjectCatalogResponse,
    ServiceMaintenanceItem,
    ServiceMaintenanceResponse,
    TaskItem,
    VaultDocumentDetailResponse,
    VaultDocumentListResponse,
    VaultDocumentsResponse,
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

    def vault_document_list(self, response: VaultDocumentListResponse, collection: str) -> str:
        title = "APS Projects" if collection == "projects" else "APS Services"
        rows = []
        for document in response.data.documents:
            url = f"/v1/{collection}/{quote(document.document_id, safe='')}?format=html"
            rows.append(
                "<tr>"
                f'<td class="mono">{self._text(document.document_id)}</td>'
                f'<td><a href="{url}">{self._text(document.name)}</a></td>'
                f'<td>{self._text(document.status or "-")}</td>'
                f'<td>{self._text(document.summary or "-")}</td></tr>'
            )
        values = self._base(response, title)
        table_rows = "".join(rows) or '<tr><td colspan="4">No documents</td></tr>'
        values["BODY_HTML"] = (
            f'<p>{len(response.data.documents)} documents</p>'
            '<div class="table-scroll"><table><thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Summary</th></tr></thead>'
            f'<tbody>{table_rows}</tbody></table></div>'
        )
        return self._render("vault_document.html", values, {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "BODY_HTML"})

    def vault_documents(self, response: VaultDocumentsResponse) -> str:
        values = self._base(response, "APS Vault Documents")
        sections = []
        for collection, documents in (("projects", response.data.projects), ("services", response.data.services)):
            rows = "".join(
                f'<li><a href="/v1/{collection}/{quote(item.document_id, safe="")}?format=html">{self._text(item.name)}</a>'
                f' · {self._text(item.status or "-")}</li>'
                for item in documents
            )
            sections.append(f'<section><h2>{collection.title()} ({len(documents)})</h2><ul>{rows}</ul></section>')
        values["BODY_HTML"] = "".join(sections)
        return self._render("vault_document.html", values, {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "BODY_HTML"})

    def vault_document_detail(self, response: VaultDocumentDetailResponse, collection: str) -> str:
        document = response.data.document
        metadata = "".join(
            f"<dt>{self._text(key)}</dt><dd>{self._text(value)}</dd>"
            for key, value in sorted(document.metadata.items())
        )
        values = self._base(response, document.name)
        values["BODY_HTML"] = (
            f'<p class="mono">{self._text(document.document_id)} · {self._text(document.status or "-")}</p>'
            f'<p>{self._text(document.summary)}</p><dl>{metadata}</dl>'
            f'<section><h2>Markdown</h2><pre class="markdown-source">{self._text(document.content)}</pre></section>'
            f'<p><a href="/v1/{collection}?format=html">Back to {self._text(collection)}</a></p>'
        )
        return self._render("vault_document.html", values, {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "BODY_HTML"})

    def _idea_page(self, response: IdeasResponse | IdeaSetsResponse, title: str, body: str) -> str:
        values = self._base(response, title)
        values["BODY_HTML"] = body
        return self._render("vault_document.html", values, {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "BODY_HTML"})

    def idea_detail(self, response: IdeasResponse, idea: IdeaItem) -> str:
        body = (
            f'<p class="mono">{self._text(idea.idea_id)} · {self._text(idea.status)}</p>'
            f'<p>{self._text(idea.summary)}</p>'
            f'<pre class="markdown-source">{self._text(idea.content)}</pre>'
        )
        return self._idea_page(response, idea.title, body)

    def idea_sets(self, response: IdeaSetsResponse) -> str:
        rows = []
        for item in response.data:
            url = "/v1/idea-sets/" + quote(item.idea_set_id, safe="") + "?format=html"
            rows.append(f'<li><a href="{url}">{self._text(item.title)}</a> · {self._text(item.status)}</li>')
        return self._idea_page(response, "APS Idea Sets", f'<p>{len(rows)} Idea Sets</p><ul>{"".join(rows)}</ul>')

    def idea_set_detail(self, response: IdeasResponse, idea_set: IdeaSet) -> str:
        members = "".join(f"<li>{self._text(item)}</li>" for item in idea_set.member_idea_ids)
        body = (
            f'<p class="mono">{self._text(idea_set.idea_set_id)} · {self._text(idea_set.status)}</p>'
            f'<p>{self._text(idea_set.summary)}</p><ul>{members}</ul>'
            f'<pre class="markdown-source">{self._text(idea_set.content)}</pre>'
        )
        return self._idea_page(response, idea_set.title, body)

    def _render(self, filename: str, values: dict[str, str], raw: set[str]) -> str:
        document = (self.templates / filename).read_text(encoding="utf-8")
        missing = set(re.findall(r"\{\{([A-Z_]+)\}\}", document)) - values.keys()
        if missing:
            raise ValueError(f"unresolved HTML template placeholder in {filename}: {', '.join(sorted(missing))}")
        for key, value in values.items():
            replacement = value if key in raw else self._text(value)
            document = document.replace("{{" + key + "}}", replacement)
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
        keywords = " ".join(f'<span class="badge">{self._text(keyword)}</span>' for keyword in idea.keywords)
        idea_sets = ", ".join(idea.idea_set_ids) or "unassigned"
        return (
            '<article class="card">'
            f'<div>{keywords} <span class="state">{self._text(idea.status)} · {self._text(idea.commit_status)}</span></div>'
            f'<h3>{self._text(idea.title)}</h3><p>{self._text(idea.summary)}</p>'
            f'<div class="card-foot"><span>{self._text(idea.idea_id)} · {self._text(idea.updated_at.isoformat())}</span><span>{self._text(idea_sets)}</span></div>'
            '</article>'
        )

    def _idea_set(self, idea_set: IdeaSet) -> str:
        members = "".join(f"<li>{self._text(item)}</li>" for item in idea_set.member_idea_ids)
        keywords = " ".join(f'<span class="badge">{self._text(item)}</span>' for item in idea_set.keywords)
        return (
            '<details class="record"><summary>'
            f'<span class="state">{self._text(idea_set.status)} · {self._text(idea_set.commit_status)}</span><span>{self._text(idea_set.title)}</span>'
            f'<span class="mono">{len(idea_set.member_idea_ids)} ideas</span></summary>'
            f'<div class="record-body"><section><h3>Summary</h3><p>{self._text(idea_set.summary)}</p><h3>Members</h3><ul>{members}</ul></section><section><h3>Keywords</h3><p>{keywords}</p></section></div></details>'
        )

    def ideas(self, response: IdeasResponse, status_filter: str) -> str:
        values = self._base(response, "APS Ideas")
        values.update(
            {
                "IDEA_COUNT": str(len(response.data.ideas)),
                "IDEA_SET_COUNT": str(len(response.data.idea_sets)),
                "STATUS_FILTER": status_filter,
                "IDEA_CARDS_HTML": "".join(self._idea_card(item) for item in response.data.ideas) or '<div class="empty">조건에 맞는 아이디어가 없습니다.</div>',
                "IDEA_SET_RECORDS_HTML": "".join(self._idea_set(item) for item in response.data.idea_sets) or '<div class="empty">생성된 유사 Idea set이 없습니다.</div>',
            }
        )
        return self._render(
            "ideas.html",
            values,
            {"APS_CONTENT_CSS", "STALE_BADGE_HTML", "IDEA_CARDS_HTML", "IDEA_SET_RECORDS_HTML"},
        )
