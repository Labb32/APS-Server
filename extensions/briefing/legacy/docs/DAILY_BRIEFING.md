# APS 아침 브리핑 사용법

브리핑의 목적은 현재 기기의 코드 상태를 진단하는 것이 아니라, APS Vault에 기록된 계획·Task·인계 문서에서 오늘 할 일을 짧게 전달하는 것이다.

## 실행 흐름

```text
APS Vault git pull --ff-only
  → 02_Projects에서 In_Progress 프로젝트 선택
  → 05_ProjectContexts/<briefing_id>만 읽기
  → 프로젝트별 Codex를 병렬 실행
  → 03_Services 유지보수 일정 결합
  → Markdown / JSON / HTML 출력
```

브리핑은 개발 프로젝트 저장소, Git 브랜치·커밋·dirty worktree와 구현 코드를 읽지 않는다. 따라서 해당 프로젝트가 이 기기에 없어도 결과가 같고, 다른 기기에서 진행한 코드 변경을 재분석하지 않는다.

## 대상과 필수 파일

- 프로젝트 문서: `02_Projects/*.md`
- 대상 조건: `status: In_Progress`와 고유 `briefing_id`
- 컨텍스트: `05_ProjectContexts/<briefing_id>`
- 필수 지침: `05_ProjectContexts/<briefing_id>/.brief/brief.md`
- 서비스 일정: `03_Services/*.md`

`.aps.local.json`의 프로젝트 경로는 개발 폴더 링크용이며 브리핑 대상 판정과 입력에는 사용하지 않는다.

## 실행

```powershell
# Windows
py scripts/daily_briefing.py
py scripts/daily_briefing.py --html
py scripts/daily_briefing.py --html --no-open
py scripts/daily_briefing.py --json
py scripts/daily_briefing.py --dry-run
py scripts/daily_briefing.py --project project-bnh
```

```bash
# macOS/Linux
python3 scripts/daily_briefing.py --html
```

모든 실행은 기본적으로 먼저 APS Vault에 `git pull --ff-only`를 수행한다. 충돌, 로컬 변경 충돌 또는 인증 실패로 fast-forward할 수 없으면 오래된 문서로 계속하지 않고 종료한다.

오프라인 실행이나 테스트에서 현재 로컬 스냅샷을 의도적으로 사용할 때만 `--no-pull`을 붙인다.

```powershell
py scripts/daily_briefing.py --dry-run --no-pull
```

pull로 실행기 자체가 갱신되면 새 실행기로 한 번 다시 시작한다. 동기화 메시지는 표준 오류에 출력되어 `--json` 결과를 훼손하지 않는다.

## 로컬 설정

`.aps.local.json`은 프로젝트별 legacy runner 설정에만 선택 사항이다. APS Server에서는 AI provider를 `.env` 또는 `APS_CONFIG_FILE`로 명시적으로 선택해야 하며, 이 문서의 runner 예시는 provider 기본값을 의미하지 않는다.

```json
{
  "projects": {
    "project-bnh": {
      "path": "~/Projects/project-BnH",
      "mounts": [".brief", "personal"]
    }
  },
  "runner": {
    "command": [],
    "timeout_seconds": 600,
    "parallel_projects": 3
  }
}
```

- `projects`: 이 기기에서 개발할 폴더의 링크 구성 정보
- `runner.command`: 비어 있으면 Windows의 `codex.cmd`, 그 외 환경의 `codex`
- `timeout_seconds`: 프로젝트 하나의 실행 제한
- `parallel_projects`: 동시에 생성할 프로젝트 수, 1~8
- `{schema}`: 사용자 지정 명령에서 응답 스키마 절대경로로 치환

Codex는 각 Vault 컨텍스트를 작업 디렉터리로 삼아 `--ephemeral --sandbox read-only`로 실행된다.

## 프로젝트별 문서 규칙

`.brief/brief.md`에는 다음만 적는다.

- 우선 읽을 계획·Task·인계 문서
- 오늘 작업을 고르는 순서
- 프로젝트 고유 완료 기준
- 문서에 명시된 막힘을 전달하는 규칙

Git/코드 조사, 현재 브랜치 판단, 현재 기기에서 개발을 이어서 하라는 권장은 넣지 않는다. 새 템플릿은 `scripts/project_briefing_kit`에 있다.

프로젝트 링크와 새 기기 설정은 현재 Vault 템플릿의 [`05_ProjectContexts/README.md`](../../../../vault-template/05_ProjectContexts/README.md)를 따른다.

## HTML과 종료 코드

기본 HTML은 `scripts/web/briefing.html`에 생성되며 Git에서 제외된다. 검색, 필터, 정렬, 로컬 완료 체크와 후속 질문 맥락 복사를 제공한다. 체크 상태는 브라우저 `localStorage`에만 저장된다.

- `0`: 모든 브리핑과 서비스 판정 성공
- `1`: 일부 프로젝트 또는 서비스가 비정상
- `2`: Vault 동기화, 설정 또는 실행 준비 실패

## 장애 대응

| 증상 | 확인 |
|---|---|
| 프로젝트가 표시되지 않음 | `02_Projects`의 `In_Progress`, `briefing_id` 확인 |
| `brief.md` 누락 | `05_ProjectContexts/<briefing_id>/.brief/brief.md` 확인 |
| pull 실패 | Vault의 로컬 변경·충돌, remote와 Git 인증 확인 |
| Codex 실행 실패 | CLI 설치·인증, `runner.command`, timeout 확인 |
| 브리핑이 과도하게 김 | 해당 `.brief/brief.md`가 코드/Git 조사를 요구하는지 확인 |
| HTML이 오래됨 | `--html`로 다시 생성하고 날짜 확인 |

## 일일 동기화

브리핑 시작 시 pull은 자동이다. 작업 종료 후 push는 변경의 종류에 따라 수행한다.

- 프로젝트 코드: 프로젝트 저장소
- 브리핑·계획·Task·인계 문서: APS Vault

서로 다른 저장소이므로 두 종류를 모두 수정했다면 둘 다 커밋·push해야 한다. junction/symlink는 로컬 파일 복사를 없애지만 원격 Git 이력을 합치지는 않는다.

## 서비스 유지보수

활성 서비스는 `last_maintenance + maintenance_interval_days`로 기한을 계산한다. 실제 점검을 완료한 뒤에만 서비스 문서의 `last_maintenance`를 완료일로 갱신한다. `maintenance_interval_days: 0`은 정기 점검 없음이다.
