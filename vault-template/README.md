# APS Vault

APS Vault는 개발 Idea를 Project로 구체화하고, 배포 후 Service와 ProjectContext까지 연결하는 로컬 우선 Markdown 워크스페이스다. 특정 편집기나 AI에 종속되지 않으며 Git으로 변경 이력을 관리한다.

사람은 이 README와 [운영 가이드](98_Documents/APS/OPERATIONS_GUIDE.md)를 기준으로 사용한다. AI 도구에는 루트 [AGENTS.md](AGENTS.md)가 기본 권한과 안전 규칙을 전달한다.

## 시작하기

```bash
git init -b main
git add .
git commit -m "Initialize APS Vault"
```

새 문서는 `99_Templates`에서 해당 유형의 템플릿을 복사해 작성한다. 기기별 개발 프로젝트 경로는 `.aps.local.example.json`을 복사한 `.aps.local.json`에만 기록하며 이 파일은 Git에 포함하지 않는다.

## 기본 구조

| 경로 | 역할 | Git 정책 |
|---|---|---|
| `00_Inbox` | 미정리 Idea와 APS Server staging | 내용 제외 |
| `01_Ideas` | 정리·검증된 Idea | 추적 |
| `01_Idea_Sets` | 관련 Idea 그룹과 병합 후보 | 추적 |
| `02_Projects` | 목표와 완료 조건이 있는 Project | 추적 |
| `03_Services` | 운영 Service와 유지보수 기준 | 추적 |
| `04_Archives` | 비활성 기록 | 추적 |
| `05_ProjectContexts` | 브리핑, Task, 계획과 인계 원본 | 추적 |
| `98_Documents/APS` | Vault 운영 정책과 가이드 | 추적 |
| `99_Templates` | 표준 frontmatter와 문서 템플릿 | 추적 |

## Idea 흐름

```text
00_Inbox에 원문 접수
→ title·keywords·summary 정리
→ ID와 참조 검증
→ 01_Ideas / 01_Idea_Sets에 게시
→ commit 성공 후 Inbox 원본 제거
```

`00_Inbox`는 clone-local 경로이므로 별도 백업이 필요하다. 기존 Idea의 ID는 제목이나 파일명이 바뀌어도 유지한다.

## Project와 Service

Idea가 명확한 결과물과 완료 조건을 가지면 Project로 전환한다. `In_Progress` Project는 `briefing_id`와 동일한 `05_ProjectContexts/<briefing_id>`를 사용한다. 배포 후 지속적인 점검이 필요한 결과물은 Service로 기록하고 유지보수 주기와 마지막 완료일을 관리한다.

## AI 도구와 함께 사용하기

AI에게 Vault 루트를 제공한 뒤 `AGENTS.md`, 관련 템플릿과 요청 대상 문서만 읽도록 한다. AI 연결 자체는 전체 Vault 쓰기, Git commit, 외부 전송 또는 Project·Service 변경 권한을 의미하지 않는다. 중요한 변경은 diff를 확인하고 사람이 승인한다.

## APS Server 연결

APS Server 한 개에는 한 사용자의 Vault clone 하나를 연결한다. Server는 조회 결과와 브리핑을 파생 데이터로 만들며 Vault Markdown이 항상 원본이다. Idea 접수는 Git에서 제외된 `00_Inbox`, 검증된 Idea 게시만 `01_Ideas`와 `01_Idea_Sets`를 사용한다.

공개 저장소에는 실제 개인 Idea, ProjectContext, credential, token 또는 로컬 절대경로를 포함하지 않는다.
