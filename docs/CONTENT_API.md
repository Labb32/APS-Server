# API 목표 계약

이 문서는 **앞으로 구현할 API 방향**을 설명한다. 현재 호출 가능한 경로·요청·응답·오류는 [API Reference](API_REFERENCE.md)와 런타임 `/openapi.json`을 기준으로 한다. 목표 기능을 현재 활성 기능으로 해석하지 않는다.

## 기본 규칙

- 서버 하나는 사용자 한 명과 Vault 하나를 담당한다. `operator`, `viewer`, `scheduler`의 기존 Bearer token 권한을 유지한다.
- 요청자는 Vault 경로·remote·branch, shell·실행 파일, AI provider·model·prompt를 지정하지 못한다. 고정 operation과 검증된 ID·schema만 받는다.
- Content GET은 저장된 결과만 읽으며 Vault 동기화, AI 호출 또는 생성 Job을 시작하지 않는다.
- JSON은 정규화 metadata, 논리 ID, 기준 Vault revision, 필요한 경우 검증된 Markdown 본문을 포함한다. HTML은 **같은 JSON**을 서버의 고정 template으로 표시하며 원시 HTML·스크립트를 안전하게 처리한다.
- 생성 실패 시 이전 정상 결과를 보존하고 `stale`·생성 시각·기준 revision을 표시한다. 결과 checksum과 부분 실패 여부는 응답 계약에 포함한다.

## 목표 기능과 상태

| 기능 | 상태 | 계약 방향 |
|---|---|---|
| 기존 Idea 목록·상세·검색·Inbox JSON 접수 | active | 현재 계약은 [API Reference](API_REFERENCE.md)의 6·8절 |
| Project 목록·상세 | active | `/v1/projects`, `/v1/projects/{project_id}`. 전체 상태를 기본 조회하고 허용된 Markdown 본문 포함 |
| Service 목록·상세 | active | `/v1/services`, `/v1/services/{service_id}`. 전체 상태를 기본 조회하고 허용된 Markdown 본문 포함 |
| Idea Set 전체 목록·상세 | active | 기존 추천 endpoint의 의미를 유지하면서 별도 계약 정의 |
| `text/plain` Inbox POST | active | `POST /v1/ideas/text`. 기존 JSON 접수 유지, UTF-8·길이·정규화·Idempotency-Key 검증 |
| 공통 문서 검색 | planned | 고정 collection과 논리 ID를 사용. 기존 Idea 검색 API는 유지 |
| archive 다운로드 | planned | `migration` 확장의 operator 전용 만료 Artifact. 일반 Content와 분리 |
| archive 업로드로 새 Vault 시작 | blocked | staging 검증, 사전 등록 대상 ID, 실패 복구가 준비된 뒤 활성화 |
| Project·Service 원본 변경 | blocked | proposal branch·diff·명시적 승인 흐름이 선행돼야 함 |

`planned`는 설계 목표, `blocked`는 선행 안전 기능 전까지 비활성인 기능이다. 새 경로·media type·필드는 구현 전에 기존 클라이언트 호환 계약을 확정한다. text POST는 자유 형식 agent 요청이나 경로 선택으로 해석하지 않는다.

## Job과 AI

API 요청과 내부 cron은 같은 고정 operation·Job 경로를 사용한다. AI가 없는 정상 상태와 AI 설정 오류·외부 장애를 구분한다. AI 의존 operation은 미연결 시 비활성 이유를 표시하되 Core readiness와 기본 조회를 막지 않는다. 외부 AI 큐·스케줄러를 연결해도 APS Server가 결과 schema, 기준 Vault revision과 쓰기 권한을 최종 검증한다. 외부 worker에는 Vault/Git 직접 쓰기 권한을 주지 않는다. 상세는 [Agent 실행 설계](AGENT_EXECUTOR_DESIGN.md)와 [작업 목록](TASKS.md)을 따른다.

## 확장과 별도 서비스

`briefing`, `migration`, `service-security`의 개발 순서와 제한 capability는 [공식 확장 계획](EXTENSION_PLAN.md)에 있다. 미설치·AI 장애는 각 확장의 생성 기능에만 영향을 준다. `aps-index`는 독립 서비스이며 [Vault 원본 검색 모드와 선택적 DB 원본 모드](../plugins/aps-index/README.md)를 구분한다. DB 원본 모드의 장애를 존재하지 않는 Vault 데이터로 정상 대체하지 않는다.

## 쓰기 경계

Inbox 접수·pending 수정은 서버 소유 Git-ignored `00_Inbox`에만 기록한다. 자동 tracked Idea/Set 쓰기는 검증된 `01_Ideas`·`01_Idea_Sets` 대상 Scheduler commit 흐름으로 제한한다. tracked Idea 직접 `PATCH`는 `409 IDEA_TRACKED_UPDATE_DISABLED`로 거부한다. Project/Service 제안은 원본 반영 전까지 파생 artifact만 만든다. Vault sync는 clean worktree의 fast-forward만 허용하며 자동 merge·reset·강제 checkout·force push를 하지 않는다.
