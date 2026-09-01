#!/usr/bin/env python3
"""APS Vault의 개발 프로젝트와 서비스 유지보수 일일 브리핑 실행기."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import html
import json
import locale
import os
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ACTIVE_PROJECT_STATES = {"In_Progress", "개발중"}
ACTIVE_SERVICE_STATES = {"Active", "서비스중"}
BRIEF_PROMPT_PATH = Path(".brief") / "brief.md"
PROJECT_CONTEXTS_PATH = Path("05_ProjectContexts")
RESPONSE_SCHEMA_PATH = Path(__file__).with_name("briefing_response.schema.json")
SYNC_MARKER = "APS_DAILY_BRIEFING_SYNCED"


@dataclass
class Note:
    path: Path
    metadata: dict[str, str]
    content: str

    @property
    def title(self) -> str:
        for line in self.content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return self.path.stem


@dataclass
class ProjectResult:
    briefing_id: str
    name: str
    status: str
    today_tasks: list[str]
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "briefing_id": self.briefing_id,
            "name": self.name,
            "status": self.status,
            "notes": self.notes,
        }
        if self.status == "success":
            result["today_tasks"] = self.today_tasks
        return result


def parse_frontmatter(path: Path) -> Note:
    content = path.read_text(encoding="utf-8-sig")
    lines = content.splitlines()
    metadata: dict[str, str] = {}
    if not lines or lines[0].strip() != "---":
        return Note(path, metadata, content)

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        metadata[key.strip()] = value.strip('"\'')
    return Note(path, metadata, content)


def load_notes(directory: Path) -> list[Note]:
    if not directory.exists():
        return []
    return [parse_frontmatter(path) for path in sorted(directory.glob("*.md"))]


def parse_iso_date(value: str, field: str, path: Path) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path}: {field}는 YYYY-MM-DD 형식이어야 합니다: {value}") from error


def make_project_request(note: Note, context_root: Path, prompt_path: Path, today: date) -> str:
    local_prompt = prompt_path.read_text(encoding="utf-8-sig")
    return f"""# APS 일일 개발 브리핑 요청

- 브리핑 날짜: {today.isoformat()}
- APS 프로젝트 컨텍스트: {context_root}
- APS 프로젝트 문서: {note.path}

아래 프로젝트별 지침과 현재 작업 디렉터리의 계획·Task·인계 문서만 읽고 오늘 할 일을 선정하세요.
외부 개발 저장소, Git 브랜치·커밋·dirty worktree와 실제 구현 코드는 조사하거나 추측하지 마세요.
이전 작업의 구현 차이를 분석하거나 현재 기기에서 개발을 이어서 하라고 권장하지 마세요.
브리핑만 반환하고 파일은 변경하지 마세요.
반드시 지정된 JSON 스키마에 맞춰 응답하세요.
- today_tasks: 오늘 실제로 수행할 작업. 당일 작업이 없으면 빈 배열
- today_tasks의 각 항목은 행동과 완료 기준을 담은 한 문장. 목표·현재 상태·첫 행동·종료 기록을 별도 항목으로 만들지 말 것
- notes: 문서에 명시된 막힘 또는 사용자 결정만 최대 2개. 일반 주의, 현황 요약과 종료 기록은 제외. 없으면 빈 배열

## 프로젝트별 브리핑 지침

{local_prompt}

## APS 프로젝트 문서

{note.content}
"""


def decode_process_output(value: bytes) -> str:
    """UTF-8을 우선하되 Windows 로컬 코드페이지를 쓰는 CLI 출력도 수용한다."""
    encodings = ["utf-8", locale.getpreferredencoding(False)]
    for encoding in dict.fromkeys(encodings):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            pass
    return value.decode("utf-8", errors="replace")


def sync_vault(vault: Path, timeout: int = 120) -> bool:
    """브리핑 입력을 읽기 전에 Vault를 fast-forward로 갱신한다."""
    if not (vault / ".git").exists():
        raise RuntimeError(f"APS Vault가 Git 저장소가 아닙니다: {vault}")

    def git(*args: str) -> subprocess.CompletedProcess[bytes]:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        return subprocess.run(
            ["git", "-C", str(vault), *args],
            capture_output=True,
            timeout=timeout,
            check=False,
            env=environment,
        )

    before = git("rev-parse", "HEAD")
    if before.returncode != 0:
        raise RuntimeError(decode_process_output(before.stderr).strip() or "현재 Vault 커밋을 확인할 수 없습니다.")
    pulled = git("pull", "--ff-only")
    if pulled.returncode != 0:
        detail = decode_process_output(pulled.stderr).strip() or decode_process_output(pulled.stdout).strip()
        raise RuntimeError(f"APS Vault를 fast-forward로 갱신할 수 없습니다: {detail or '출력 없음'}")
    after = git("rev-parse", "HEAD")
    if after.returncode != 0:
        raise RuntimeError(decode_process_output(after.stderr).strip() or "갱신된 Vault 커밋을 확인할 수 없습니다.")
    return before.stdout.strip() != after.stdout.strip()


def runner_command(config: dict[str, Any], os_name: str | None = None) -> list[str]:
    """설정 명령을 우선하고, 비어 있으면 운영체제에 맞는 Codex CLI를 사용한다."""
    configured = config.get("runner", {}).get("command", [])
    if isinstance(configured, list) and configured:
        return [str(part).replace("{schema}", str(RESPONSE_SCHEMA_PATH)) for part in configured]
    codex_executable = "codex.cmd" if (os.name if os_name is None else os_name) == "nt" else "codex"
    return [
        codex_executable, "exec", "--ephemeral", "--sandbox", "read-only",
        "--output-schema", str(RESPONSE_SCHEMA_PATH), "-",
    ]


def abnormal(note: Note, message: str) -> ProjectResult:
    return ProjectResult(
        briefing_id=note.metadata.get("briefing_id", ""),
        name=note.title,
        status="abnormal",
        today_tasks=[],
        notes=[message],
    )


def parse_agent_response(note: Note, response: str) -> ProjectResult:
    if not response.strip():
        return abnormal(note, "Codex 브리핑 응답이 비어 있습니다.")
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return abnormal(note, "Codex 응답을 구조화된 결과로 해석할 수 없습니다.")
    tasks = payload.get("today_tasks", [])
    notes = payload.get("notes", [])
    if not isinstance(tasks, list) or not all(isinstance(item, str) for item in tasks):
        return abnormal(note, "오늘 할 일 형식이 올바르지 않습니다.")
    if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
        return abnormal(note, "기타 특이사항 형식이 올바르지 않습니다.")
    tasks = [item.strip() for item in tasks if item.strip()]
    notes = [item.strip() for item in notes if item.strip()]
    tasks = tasks[:3]
    notes = notes[:2]
    if not tasks:
        return abnormal(note, "당일 작업 내용이 없습니다." + (f" {' '.join(notes)}" if notes else ""))
    return ProjectResult(
        briefing_id=note.metadata.get("briefing_id", ""),
        name=note.title,
        status="success",
        today_tasks=tasks,
        notes=notes,
    )


def run_project_briefings(
    notes: list[Note],
    config: dict[str, Any],
    vault: Path,
    today: date,
    dry_run: bool,
    only_project: str | None,
) -> list[ProjectResult]:
    command = runner_command(config)
    timeout = int(config.get("runner", {}).get("timeout_seconds", 600))
    parallel_projects = int(config.get("runner", {}).get("parallel_projects", 3))
    parallel_projects = max(1, min(parallel_projects, 8))

    active = [n for n in notes if n.metadata.get("status") in ACTIVE_PROJECT_STATES]
    if only_project:
        active = [n for n in active if n.metadata.get("briefing_id") == only_project]

    def run_one(note: Note) -> ProjectResult | None:
        briefing_id = note.metadata.get("briefing_id", "")
        if not briefing_id:
            return None

        context_root = vault / PROJECT_CONTEXTS_PATH / briefing_id
        prompt_path = context_root / BRIEF_PROMPT_PATH
        if not context_root.is_dir():
            return abnormal(note, f"APS 프로젝트 컨텍스트가 없습니다: {context_root}")
        if not prompt_path.is_file():
            return abnormal(note, "APS 프로젝트 컨텍스트에 `.brief/brief.md`가 누락되었습니다.")

        request = make_project_request(note, context_root, prompt_path, today)
        if dry_run:
            return ProjectResult(briefing_id, note.title, "ready", [], [f"컨텍스트 준비 완료: {context_root}"])

        try:
            completed = subprocess.run(
                [str(part) for part in command],
                cwd=context_root,
                input=request.encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return abnormal(note, f"Codex 실행 시간이 {timeout}초를 초과했습니다.")
        except OSError as error:
            return abnormal(note, f"Codex 실행기를 시작할 수 없습니다: {error}")

        if completed.returncode != 0:
            stderr = decode_process_output(completed.stderr).strip()
            stdout = decode_process_output(completed.stdout).strip()
            detail = stderr or stdout or "출력 없음"
            return abnormal(note, f"Codex 실행 실패(exit {completed.returncode}): {detail}")
        response = decode_process_output(completed.stdout).strip()
        return parse_agent_response(note, response)

    with ThreadPoolExecutor(max_workers=parallel_projects) as executor:
        return [result for result in executor.map(run_one, active) if result is not None]


def render_project_markdown(results: list[ProjectResult]) -> list[str]:
    sections = ["## 개발 프로젝트"]
    if not results:
        return [*sections, "- 오늘 브리핑 대상인 개발중 프로젝트가 없습니다."]
    for result in results:
        sections.append(f"\n### {result.name}")
        if result.status == "success":
            sections.append("- 오늘 할 일:")
            sections.extend(f"  - {task}" for task in result.today_tasks)
            sections.append("- 기타 특이사항:")
            sections.extend(f"  - {note}" for note in result.notes)
            if not result.notes:
                sections.append("  - 없음")
        else:
            sections.append("- 기타:")
            sections.extend(f"  - {note}" for note in result.notes)
    return sections


def service_maintenance(notes: list[Note], today: date) -> tuple[list[str], bool]:
    sections: list[str] = ["## 서비스 유지보수"]
    failed = False
    due_items = 0

    for note in notes:
        if note.metadata.get("service_status") not in ACTIVE_SERVICE_STATES:
            continue
        raw_interval = note.metadata.get("maintenance_interval_days", "")
        if raw_interval in {"", "0"}:
            if raw_interval == "":
                sections.append(f"- 설정 필요: `{note.path.name}`의 `maintenance_interval_days`")
                failed = True
            continue
        try:
            interval = int(raw_interval)
            last = parse_iso_date(note.metadata.get("last_maintenance", ""), "last_maintenance", note.path)
        except (ValueError, TypeError) as error:
            sections.append(f"- 설정 오류: {error}")
            failed = True
            continue
        if interval < 1:
            sections.append(f"- 설정 오류: `{note.path.name}`의 유지보수 일수는 1 이상 또는 0(없음)이어야 합니다.")
            failed = True
            continue

        due = last + timedelta(days=interval)
        if today < due:
            continue
        due_items += 1
        overdue = (today - due).days
        overdue_text = "오늘 기한" if overdue == 0 else f"{overdue}일 경과"
        summary = note.metadata.get("maintenance_summary", "서비스 문서의 유지보수 매뉴얼을 확인한다.")
        relative = f"03_Services/{note.path.name}"
        sections.extend(
            [
                f"\n### {note.title}",
                f"- 기한: {due.isoformat()} ({overdue_text}, {note.metadata.get('maintenance_cycle', interval)})",
                f"- 권장 작업: {summary}",
                f"- 완료 후: `{relative}`의 `last_maintenance`를 `{today.isoformat()}`로 갱신",
            ]
        )

    if due_items == 0:
        sections.append("- 기한이 지난 활성 서비스가 없습니다.")
    return sections, failed


def render_briefing_html(
    results: list[ProjectResult],
    project_notes: list[Note],
    service_notes: list[Note],
    today: date,
    output_path: Path,
    vault: Path,
) -> str:
    """브리핑 결과를 외부 자원 없는 읽기 전용 HTML로 렌더링한다."""
    note_by_id = {note.metadata.get("briefing_id", ""): note for note in project_notes}

    def text(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def link_to(path: Path) -> str:
        return Path(os.path.relpath(path, output_path.parent)).as_posix()

    project_rows: list[str] = []
    for result in results:
        note = note_by_id.get(result.briefing_id)
        metadata = note.metadata if note else {}
        doc_path = note.path if note else vault / "02_Projects"
        tier = metadata.get("tier", "—")
        deadline = metadata.get("deadline", "") or "기한 미정"
        form = metadata.get("final_form", "—")
        tasks = "".join(
            f'<li><label class="task"><input type="checkbox" data-task-key="{text(today.isoformat())}:{text(result.briefing_id)}:{index}"><span>{text(task)}</span></label></li>'
            for index, task in enumerate(result.today_tasks)
        )
        notes = "".join(f"<li>{text(item)}</li>" for item in result.notes)
        if not tasks:
            tasks = "<li class=\"muted\">당일 작업 없음</li>"
        if not notes:
            notes = "<li class=\"muted\">특이사항 없음</li>"
        state_label = "정상" if result.status == "success" else ("준비" if result.status == "ready" else "확인 필요")
        search = text(f"{result.name} {tier} {form} {' '.join(result.today_tasks)} {' '.join(result.notes)}".lower())
        project_rows.append(f"""
        <details class="record" data-kind="project" data-state="{text(result.status)}" data-tier="{text(tier)}" data-deadline="{text(metadata.get('deadline', ''))}" data-project="{text(result.name)}" data-briefing-id="{text(result.briefing_id)}" data-search="{search}" open>
          <summary><span class="tier">{text(tier)}</span><span class="record-name">{text(result.name)}</span><span class="state {'alert' if result.status == 'abnormal' else ''}">{state_label}</span><span class="deadline">{text(deadline)}</span></summary>
          <div class="record-body"><div><h3>오늘 할 일</h3><ol class="task-list">{tasks}</ol></div><div><h3>기타 특이사항</h3><ul class="note-list">{notes}</ul></div></div>
          <div class="handoff"><input class="question" placeholder="이 브리핑에 이어서 물어볼 내용"><button class="copy-context">질문 맥락 복사</button>{'<button class="copy-retry">재실행 명령 복사</button>' if result.status == 'abnormal' else ''}</div>
          <div class="record-foot"><span>{text(form)} · {text(result.briefing_id)}</span><a href="{text(link_to(doc_path))}">PROJECT DOC ↗</a></div>
        </details>""")

    service_rows: list[str] = []
    for note in service_notes:
        if note.metadata.get("service_status") not in ACTIVE_SERVICE_STATES:
            continue
        try:
            interval = int(note.metadata.get("maintenance_interval_days", "0"))
            last = parse_iso_date(note.metadata.get("last_maintenance", ""), "last_maintenance", note.path)
            due = last + timedelta(days=interval) if interval else None
            overdue = max(0, (today - due).days) if due else 0
            due_text = f"{overdue}일 지연" if overdue else ("오늘 점검" if due == today else "정상")
        except (ValueError, TypeError):
            due_text, overdue = "설정 확인", 1
        summary = note.metadata.get("maintenance_summary", "서비스 문서에서 점검 내용을 확인한다.")
        search = text(f"{note.title} {summary}".lower())
        service_rows.append(f"""
        <details class="record" data-kind="service" data-state="{'abnormal' if overdue else 'success'}" data-project="{text(note.title)}" data-search="{search}">
          <summary><span class="tier">SVC</span><span class="record-name">{text(note.title)}</span><span class="state {'alert' if overdue else ''}">{text(due_text)}</span><span class="deadline">최근 {text(note.metadata.get('last_maintenance', '—'))}</span></summary>
          <div class="record-body single"><div><h3>점검 내용</h3><p>{text(summary)}</p></div></div>
          <div class="record-foot"><span>{text(note.metadata.get('maintenance_cycle', '주기 미정'))}</span><a href="{text(link_to(note.path))}">SERVICE DOC ↗</a></div>
        </details>""")

    records = "".join(project_rows + service_rows) or '<div class="empty">오늘 표시할 브리핑 대상이 없습니다.</div>'
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{today.isoformat()} APS Briefing</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#c9c9c5;color:#111;font-family:"Arial Narrow",Arial,"Noto Sans KR",sans-serif;background-image:linear-gradient(#00000009 1px,transparent 1px),linear-gradient(90deg,#00000009 1px,transparent 1px);background-size:24px 24px}}a{{color:inherit}}.wrap{{width:min(1180px,calc(100% - 28px));margin:auto}}header{{padding:22px 0 14px;border-bottom:3px solid #111;display:flex;justify-content:space-between;align-items:end}}h1{{margin:0;font-size:clamp(1.4rem,4vw,2.5rem);line-height:1;text-transform:uppercase}}header p{{margin:6px 0 0;color:#444}}.date{{font:700 .75rem monospace;text-align:right}}.controls{{display:grid;grid-template-columns:minmax(220px,1fr) auto auto auto auto;gap:8px;margin:16px 0}}input,button,select{{height:42px;border:2px solid #111;border-radius:0;background:#deded9;color:#111;padding:0 13px;font:700 .78rem monospace}}button{{cursor:pointer}}button.active{{background:#111;color:#eee}}.filters{{display:flex}}.filters button{{border-right:0}}.filters button:last-child{{border-right:2px solid #111}}.count{{border-top:1px solid #777;border-bottom:1px solid #777;padding:8px 2px;margin-bottom:16px;font:700 .72rem monospace}}.record{{border:2px solid #111;border-bottom:0;background:#d7d7d2}}.record:last-child{{border-bottom:2px solid #111}}.record[open]{{background:#e1e1dc}}summary{{display:grid;grid-template-columns:62px minmax(220px,1fr) 100px 130px;align-items:center;gap:10px;padding:12px;cursor:pointer;border-bottom:0}}details[open] summary{{border-bottom:1px solid #777}}.tier{{font:900 .9rem monospace}}.record-name{{font-weight:900}}.state{{justify-self:start;border:1px solid #111;padding:3px 7px;font:800 .67rem monospace;background:#eee}}.state.alert{{background:#111;color:#fff}}.deadline{{text-align:right;font:.72rem monospace}}.record-body{{display:grid;grid-template-columns:1.2fr 1fr;gap:30px;padding:16px 74px}}.record-body.single{{grid-template-columns:1fr}}h3{{font:800 .68rem monospace;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px}}ol,ul{{margin:0;padding-left:20px;font-size:.86rem}}li+li{{margin-top:6px}}.muted{{color:#666}}.task{{display:grid;grid-template-columns:22px 1fr;align-items:start;cursor:pointer}}.task input{{width:16px;height:16px;margin:2px 0 0;padding:0;accent-color:#111}}.task input:checked+span{{text-decoration:line-through;color:#666}}.handoff{{display:grid;grid-template-columns:1fr auto auto;gap:8px;padding:0 74px 16px}}.handoff button{{height:36px}}.question{{height:36px}}.record-foot{{display:flex;justify-content:space-between;border-top:1px solid #999;padding:8px 12px;font:.68rem monospace}}.record-foot a{{font-weight:900}}.empty{{border:2px solid #111;padding:50px;text-align:center;font:700 .8rem monospace}}.hidden{{display:none}}.toast{{position:fixed;right:16px;bottom:16px;background:#111;color:#eee;padding:11px 14px;font:700 .72rem monospace;z-index:10}}footer{{padding:24px 0;font:.68rem monospace;color:#444}}
@media(max-width:700px){{header{{align-items:start}}.date{{display:none}}.controls{{grid-template-columns:1fr}}.filters{{display:grid;grid-template-columns:repeat(3,1fr)}}summary{{grid-template-columns:48px 1fr auto}}.deadline{{display:none}}.record-body{{grid-template-columns:1fr;padding:15px;gap:18px}}.handoff{{grid-template-columns:1fr;padding:0 15px 15px}}}}
</style></head><body><header class="wrap"><div><h1>APS / Daily Briefing</h1><p>프로젝트 실행 결과와 서비스 점검 현황</p></div><div class="date">{today.isoformat()}<br>STATIC REPORT</div></header>
<main class="wrap"><div class="controls"><input id="search" type="search" placeholder="SEARCH / 프로젝트, 작업, 특이사항"><div class="filters"><button class="active" data-filter="all">전체</button><button data-filter="project">프로젝트</button><button data-filter="service">서비스</button></div><select id="sort"><option value="tier-desc">TIER ↓</option><option value="tier-asc">TIER ↑</option><option value="deadline">기한순</option><option value="name">이름순</option></select><select id="deadline-filter"><option value="all">기한 전체</option><option value="dated">기한 있음</option><option value="week">7일 이내</option><option value="none">기한 미정</option></select><button id="attention">확인 필요</button></div><div class="count">VISIBLE RECORDS / <b id="count">0</b> · CHECKED TASKS / <b id="checked">0</b></div><section id="records">{records}</section></main>
<footer class="wrap"><a href="{text(link_to(vault / 'scripts' / 'web' / 'dashboard.html'))}">← APS DASHBOARD</a> // READ-ONLY STATIC BRIEFING</footer>
<script>const records=[...document.querySelectorAll('.record')],search=document.querySelector('#search'),sort=document.querySelector('#sort'),deadlineFilter=document.querySelector('#deadline-filter'),recordsRoot=document.querySelector('#records'),reportDate=new Date('{today.isoformat()}T00:00:00');let filter='all',attention=false;const saved=JSON.parse(localStorage.getItem('aps-briefing-tasks')||'{{}}');function checkedCount(){{document.querySelector('#checked').textContent=document.querySelectorAll('[data-task-key]:checked').length}}document.querySelectorAll('[data-task-key]').forEach(box=>{{box.checked=!!saved[box.dataset.taskKey];box.onchange=()=>{{saved[box.dataset.taskKey]=box.checked;localStorage.setItem('aps-briefing-tasks',JSON.stringify(saved));checkedCount()}}}});function deadlineMatch(r){{if(r.dataset.kind!=='project'||deadlineFilter.value==='all')return true;const d=r.dataset.deadline;if(deadlineFilter.value==='none')return !d;if(!d)return false;if(deadlineFilter.value==='dated')return true;const days=(new Date(d+'T00:00:00')-reportDate)/86400000;return days>=0&&days<=7}}function compare(a,b){{if(a.dataset.kind!==b.dataset.kind)return a.dataset.kind==='project'?-1:1;if(a.dataset.kind==='service')return a.dataset.project.localeCompare(b.dataset.project,'ko');if(sort.value==='name')return a.dataset.project.localeCompare(b.dataset.project,'ko');if(sort.value==='deadline')return (a.dataset.deadline||'9999').localeCompare(b.dataset.deadline||'9999');return sort.value==='tier-asc'?a.dataset.tier.localeCompare(b.dataset.tier):b.dataset.tier.localeCompare(a.dataset.tier)}}function apply(){{const q=search.value.trim().toLowerCase();let count=0;records.sort(compare).forEach(r=>{{recordsRoot.appendChild(r);const show=(filter==='all'||r.dataset.kind===filter)&&(!attention||r.dataset.state==='abnormal')&&deadlineMatch(r)&&r.dataset.search.includes(q);r.classList.toggle('hidden',!show);if(show)count++}});document.querySelector('#count').textContent=count;checkedCount()}}function toast(message){{const old=document.querySelector('.toast');if(old)old.remove();const el=document.createElement('div');el.className='toast';el.textContent=message;document.body.appendChild(el);setTimeout(()=>el.remove(),1800)}}async function copy(value){{try{{await navigator.clipboard.writeText(value);toast('클립보드에 복사했습니다.')}}catch{{prompt('아래 내용을 복사하세요.',value)}}}}document.querySelectorAll('.copy-context').forEach(button=>button.onclick=()=>{{const r=button.closest('.record'),tasks=[...r.querySelectorAll('.task span')].map(x=>'- '+x.textContent).join('\\n'),notes=[...r.querySelectorAll('.note-list li')].map(x=>'- '+x.textContent).join('\\n'),question=r.querySelector('.question').value.trim()||'이 브리핑을 기준으로 다음 행동을 구체화해줘.';copy(`[APS 브리핑 후속 질문]\n프로젝트: ${{r.dataset.project}}\n오늘 할 일:\n${{tasks||'- 없음'}}\n특이사항:\n${{notes||'- 없음'}}\n질문: ${{question}}`)}});document.querySelectorAll('.copy-retry').forEach(button=>button.onclick=()=>{{const r=button.closest('.record');copy(`python3 scripts/daily_briefing.py --project ${{r.dataset.briefingId}} --html`)}});document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));apply()}});document.querySelector('#attention').onclick=e=>{{attention=!attention;e.currentTarget.classList.toggle('active',attention);apply()}};search.oninput=apply;sort.onchange=apply;deadlineFilter.onchange=apply;apply();</script></body></html>"""


def open_html_viewer(path: Path) -> bool:
    """생성한 HTML을 운영체제의 기본 브라우저에서 연다."""
    try:
        return webbrowser.open(path.as_uri(), new=2, autoraise=True)
    except (OSError, webbrowser.Error):
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APS 일일 개발 및 서비스 유지보수 브리핑")
    parser.add_argument("--vault", type=Path, help="APS Vault 루트(기본: 스크립트의 상위 폴더)")
    parser.add_argument("--config", type=Path, help="로컬 설정 파일(기본: <vault>/.aps.local.json)")
    parser.add_argument("--today", help="판정 기준일 YYYY-MM-DD(테스트/과거 재현용)")
    parser.add_argument("--project", help="특정 briefing_id만 실행")
    parser.add_argument("--dry-run", action="store_true", help="경로와 프롬프트만 검증하고 AI 실행은 생략")
    parser.add_argument("--no-pull", action="store_true", help="실행 전 APS Vault fast-forward pull을 생략")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="브리핑 결과를 구조화 JSON으로 출력")
    output.add_argument(
        "--html", nargs="?", const="scripts/web/briefing.html", metavar="PATH",
        help="인터랙티브 HTML로 저장하고 기본 브라우저에서 열기(기본 경로: <vault>/scripts/web/briefing.html)",
    )
    parser.add_argument("--no-open", action="store_true", help="--html 파일을 생성하되 브라우저는 열지 않음")
    args = parser.parse_args()
    if args.no_open and not args.html:
        parser.error("--no-open은 --html과 함께 사용해야 합니다.")
    return args


def main() -> int:
    # Windows PowerShell의 레거시 cp949 출력에서도 문서 제목의 이모지를 안전하게 표시한다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    vault = (args.vault or Path(__file__).resolve().parent.parent).resolve()
    config_path = (args.config or vault / ".aps.local.json").resolve()
    today = parse_iso_date(args.today, "today", config_path) if args.today else date.today()

    if not args.no_pull and not os.environ.get(SYNC_MARKER):
        try:
            changed = sync_vault(vault)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            print(f"브리핑 전 Vault 동기화 실패: {error}", file=sys.stderr)
            return 2
        print("APS Vault 동기화 완료" + (" (새 커밋 적용)" if changed else " (이미 최신)"), file=sys.stderr)
        if changed:
            environment = os.environ.copy()
            environment[SYNC_MARKER] = "1"
            try:
                completed = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
                    env=environment,
                    check=False,
                )
            except OSError as error:
                print(f"갱신된 브리핑 실행기를 다시 시작할 수 없습니다: {error}", file=sys.stderr)
                return 2
            return completed.returncode

    config: dict[str, Any] = {}
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as error:
            print(f"설정 파일을 읽을 수 없습니다: {error}", file=sys.stderr)
            return 2
    projects = load_notes(vault / "02_Projects")
    services = load_notes(vault / "03_Services")
    project_results = run_project_briefings(
        projects, config, vault, today, args.dry_run, args.project
    )
    service_sections, service_failed = service_maintenance(services, today)
    project_failed = any(result.status == "abnormal" for result in project_results)

    if args.html:
        html_path = Path(args.html)
        if not html_path.is_absolute():
            html_path = vault / html_path
        html_path = html_path.resolve()
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            render_briefing_html(project_results, projects, services, today, html_path, vault),
            encoding="utf-8",
        )
        print(f"브리핑 HTML 생성: {html_path}")
        viewer_failed = False
        if not args.no_open:
            if open_html_viewer(html_path):
                print(f"브리핑 뷰어 열기: {html_path.as_uri()}")
            else:
                print("기본 브라우저를 열 수 없습니다. 생성된 HTML 파일을 직접 여세요.", file=sys.stderr)
                viewer_failed = True
        return 1 if project_failed or service_failed or viewer_failed else 0

    if args.json:
        payload = {
            "date": today.isoformat(),
            "status": "partial_failure" if project_failed or service_failed else "success",
            "projects": [result.as_dict() for result in project_results],
            "service_maintenance_markdown": service_sections[1:],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if project_failed or service_failed else 0

    output = [f"# {today.isoformat()} APS 아침 브리핑"]
    output.extend(["", *render_project_markdown(project_results), "", *service_sections])
    print("\n".join(output).rstrip())
    return 1 if project_failed or service_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

