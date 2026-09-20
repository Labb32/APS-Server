"""Read-only briefing inputs and the fixed APS Agent bridge."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


ACTIVE_PROJECT_STATES = {"In_Progress", "개발중"}
ACTIVE_SERVICE_STATES = {"Active", "서비스중"}
BRIEF_PROMPT_PATH = Path(".brief") / "brief.md"
PROJECT_CONTEXTS_PATH = Path("05_ProjectContexts")
AGENT_COMMAND = (sys.executable, "-m", "aps_server.ai_bridge", "--task", "briefing.project-analyze")


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


def abnormal(note: Note, message: str) -> ProjectResult:
    return ProjectResult(note.metadata.get("briefing_id", ""), note.title, "abnormal", [], [message])


def parse_agent_response(note: Note, response: str) -> ProjectResult:
    if not response.strip():
        return abnormal(note, "AI provider 브리핑 응답이 비어 있습니다.")
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return abnormal(note, "AI provider 응답을 구조화된 결과로 해석할 수 없습니다.")
    tasks = payload.get("today_tasks", [])
    notes = payload.get("notes", [])
    if not isinstance(tasks, list) or not all(isinstance(item, str) for item in tasks):
        return abnormal(note, "오늘 할 일 형식이 올바르지 않습니다.")
    if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
        return abnormal(note, "기타 특이사항 형식이 올바르지 않습니다.")
    tasks = [item.strip() for item in tasks if item.strip()][:3]
    notes = [item.strip() for item in notes if item.strip()][:2]
    if not tasks:
        return abnormal(note, "당일 작업 내용이 없습니다." + (f" {' '.join(notes)}" if notes else ""))
    return ProjectResult(note.metadata.get("briefing_id", ""), note.title, "success", tasks, notes)


def run_project_briefings(
    notes: list[Note], vault: Path, today: date, dry_run: bool, only_project: str | None,
    timeout_seconds: int, parallel_projects: int,
) -> list[ProjectResult]:
    active = [note for note in notes if note.metadata.get("status") in ACTIVE_PROJECT_STATES]
    if only_project:
        active = [note for note in active if note.metadata.get("briefing_id") == only_project]

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
                AGENT_COMMAND,
                cwd=context_root,
                input=request.encode("utf-8"),
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return abnormal(note, f"AI provider 실행 시간이 {timeout_seconds}초를 초과했습니다.")
        except OSError as error:
            return abnormal(note, f"AI gateway bridge를 시작할 수 없습니다: {type(error).__name__}")
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            stdout = completed.stdout.decode("utf-8", errors="replace").strip()
            detail = stderr or stdout or "출력 없음"
            return abnormal(note, f"AI provider 실행 실패(exit {completed.returncode}): {detail}")
        return parse_agent_response(note, completed.stdout.decode("utf-8", errors="replace").strip())

    with ThreadPoolExecutor(max_workers=max(1, min(parallel_projects, 8))) as executor:
        return [result for result in executor.map(run_one, active) if result is not None]
