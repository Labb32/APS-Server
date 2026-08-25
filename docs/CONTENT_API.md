# APS Server M1 Content API

## 1. 문서 상태

- 상태: M1 목표 계약 초안
- 대상 버전: `v1`
- 작성일: 2026-08-25
- 구현 상태: JSON·고정 template HTML 조회 기반 구현 중

이 문서는 APS Server가 외부 클라이언트에 제공할 콘텐츠 조회·입력 API와 내부 갱신 Job의 M1 범위를 정의한다. 현재 소스 코드의 API를 그대로 설명하는 문서가 아니며, M1 구현은 이 계약에 맞춰 변경한다.

기계 판독 가능한 요청·응답 schema 원본은 [`specs/content-api.openapi.json`](../specs/content-api.openapi.json)이며 전체 JSON 예시는 [`specs/content-api.examples.json`](../specs/content-api.examples.json)에 있다. JSON·HTML 콘텐츠 필드가 변경되면 이 문서, OpenAPI 계약, 고정 HTML template과 검증 테스트를 함께 변경한다.

M1에서는 자유 질문형 `agent.query`를 제공하지 않는다. Codex는 API 조회 시마다 실행하지 않고, 정기 갱신 Job 또는 사용자가 명시적으로 확인한 프로젝트 제안 작업에서만 실행한다.

현재 구현된 범위는 사전 생성 JSON 콘텐츠의 JSON·HTML 조회, 콘텐츠 상태 조회, 아이디어 staging 접수와 프로젝트 요청 확인 화면 생성 전 단계까지다. HTML은 canonical JSON을 고정 template에 안전하게 삽입해 요청 시 렌더링한다. 주기적 콘텐츠 생성기와 확인 후 `project.propose` 실행은 후속 작업이다.

## 2. 인스턴스와 사용자 모델

- APS Server 컨테이너 하나는 사용자 한 명을 담당한다.
- 여러 사용자를 지원할 때는 사용자별 컨테이너와 저장소를 분리한다.
- 사용자는 데스크탑, 노트북, 모바일, 외부 에이전트 등 여러 기기에서 요청할 수 있다.
- 요청 IP, Origin 또는 네트워크 위치는 사용자 신원의 근거로 사용하지 않는다.
- 프록시는 선택 사항이며, APS Server 자체 인증은 항상 수행한다.
- 공동 작업은 다중 사용자 tenant 기능이 아니라 공유된 `ProjectContext`의 Git 운영 정책으로 처리한다.

## 3. 인증과 권한

모든 API 요청은 bearer token 인증을 사용한다. 기기마다 서로 다른 token을 발급하고, 각 token은 현재 APS Server 인스턴스에 대한 권한을 나타낸다.

| 역할 | 사용처 | 권한 |
|---|---|---|
| `owner` | 사용자의 데스크탑·노트북 | 모든 콘텐츠 조회, 입력, 수동 갱신, Job 조회·취소, 프로젝트 제안 확인 |
| `reader` | 모바일·외부 에이전트 | 미리 생성된 콘텐츠 조회만 |
| `scheduler` | cron·systemd timer | 사전에 허용된 갱신 Job 생성과 해당 Job 조회 |

인증 정책은 다음과 같다.

- 인증되지 않은 요청은 `401 Unauthorized`로 거부한다.
- 역할에 허용되지 않은 요청은 `403 Forbidden`으로 거부한다.
- rate limit은 요청 IP가 아니라 token을 기준으로 적용한다.
- 로그에는 token 원문을 남기지 않고 `token_id`와 역할만 기록한다.
- token 원문과 token 저장 파일은 Git, Docker image, Job 결과와 Artifact에 포함하지 않는다.
- 프록시가 인증했더라도 APS Server가 token을 다시 검증한다.
- 인터넷을 통해 직접 접근할 때는 TLS 또는 신뢰할 수 있는 VPN을 사용한다.

M1 token은 API로 발급하지 않는다. 서버 외부에서 생성한 token의 식별자, 역할과 hash를 read-only secret으로 주입한다. token 변경은 설정 reload 또는 컨테이너 재시작으로 적용한다.

## 4. 콘텐츠 생성 원칙

콘텐츠 조회 API는 Codex를 즉시 실행하지 않는다. 검증을 통과해 저장된 최신 결과만 반환한다.

```text
cron / owner refresh request
  -> 공통 Job API
  -> Vault clean 검사
  -> fetch + fast-forward-only 동기화
  -> Vault commit 변경 여부 확인
  -> Codex 구조화 응답 생성
  -> canonical JSON schema 검증
  -> HTML 렌더링
  -> 전체 결과 검증
  -> 최신 정상 결과 원자적 교체

content GET request
  -> 인증과 권한 확인
  -> 저장된 최신 결과 조회
  -> JSON 또는 HTML 반환
```

Codex는 콘텐츠 단위로 canonical JSON을 한 번 생성한다. HTML을 별도로 생성하도록 Codex를 다시 호출하지 않는다.

```text
Codex -> canonical JSON -> JSON 응답
                       -> 서버 HTML renderer -> HTML 응답
```

동일한 `content_type`, 대상 ID, Vault commit과 generator version에 정상 결과가 존재하면 기본적으로 재생성을 생략한다. `owner`의 명시적인 강제 갱신만 이를 무시할 수 있다.

## 5. 공통 콘텐츠 메타데이터

JSON 콘텐츠는 다음 메타데이터를 포함한다.

```json
{
  "schema_version": "1.0",
  "content_type": "daily_briefing",
  "generated_at": "2026-08-25T07:00:00+09:00",
  "vault_commit": "0123456789abcdef",
  "generator_version": "0.1.0",
  "stale": false,
  "partial_failure": false,
  "sha256": "...",
  "data": {}
}
```

- `schema_version`: 콘텐츠 JSON schema 버전
- `content_type`: 생성된 콘텐츠 종류
- `generated_at`: 결과 생성 시각
- `vault_commit`: 생성에 사용한 APS Vault commit
- `generator_version`: 생성기와 template 버전
- `stale`: 현재 Vault 기준으로 결과가 오래되었는지 여부
- `partial_failure`: 일부 프로젝트 또는 서비스 생성 실패 여부
- `sha256`: 반환 콘텐츠의 checksum
- `data`: 콘텐츠별 본문

HTML 응답에도 같은 메타데이터를 `<meta>` 또는 안전한 JSON metadata block으로 포함한다. AI가 생성한 HTML이나 JavaScript를 그대로 실행하지 않는다.

## 6. 응답 형식

콘텐츠 조회 endpoint는 `format` query parameter를 지원한다.

| 값 | 응답 media type | 설명 |
|---|---|---|
| `json` | `application/json` | canonical 구조화 결과 |
| `html` | `text/html; charset=utf-8` | 서버 template으로 렌더링한 결과 |

기본 형식은 `json`이다. 지원하지 않는 형식은 `400 INVALID_FORMAT`으로 거부한다.

입력·확인 endpoint는 JSON 요청만 받는다. 비동기 작업의 최종 결과가 콘텐츠라면 완료 후 JSON과 HTML 형식으로 조회할 수 있다.

## 7. M1 API 목록

### 7.1 매일 브리핑 조회

```http
GET /v1/content/briefing/daily?format=json
GET /v1/content/briefing/daily?format=html
```

진행 중 프로젝트의 오늘 할 작업, 프로젝트 Task, 확인할 결정과 활성 서비스 점검 요약을 반환한다.

허용 역할: `owner`, `reader`

API 조회는 Codex를 실행하지 않는다. 결과가 아직 없으면 `404 CONTENT_NOT_GENERATED`, 마지막 정상 결과가 있지만 현재 Vault보다 오래되었으면 해당 결과와 `stale: true`를 반환한다.

### 7.2 프로젝트 목록 조회

```http
GET /v1/content/projects?format=json
GET /v1/content/projects?format=html
```

외부 클라이언트가 사용할 수 있는 논리적 `project_id`, 프로젝트명, 상태, tier와 브리핑 제공 여부를 반환한다. Vault 내부 경로와 파일명은 공개 계약에 포함하지 않는다.

허용 역할: `owner`, `reader`

예시:

```json
{
  "schema_version": "1.0",
  "content_type": "project_catalog",
  "generated_at": "2026-08-25T07:00:00+09:00",
  "vault_commit": "0123456789abcdef",
  "generator_version": "0.1.0",
  "stale": false,
  "partial_failure": false,
  "sha256": "...",
  "data": {
    "projects": [
      {
        "project_id": "aps-server-briefing",
        "name": "APS 서버 단위 브리핑 운영",
        "status": "In_Progress",
        "tier": "T4",
        "briefing_available": true
      }
    ]
  }
}
```

### 7.3 프로젝트별 브리핑 조회

```http
GET /v1/content/projects/{project_id}/briefing?format=json
GET /v1/content/projects/{project_id}/briefing?format=html
```

지정한 프로젝트의 현재 목표, 오늘 할 작업, 관련 Task, 완료 조건과 사용자 결정 항목을 반환한다.

허용 역할: `owner`, `reader`

요청자는 Vault 경로나 파일명을 전달하지 않는다. 서버가 `project_id`를 내부 프로젝트 문서와 `ProjectContext`에 매핑한다. 알 수 없는 ID는 `404 PROJECT_NOT_FOUND`로 응답한다.

### 7.4 서비스 유지보수 조회

```http
GET /v1/content/services/maintenance?format=json
GET /v1/content/services/maintenance?format=html
```

활성 서비스의 최근 점검일, 다음 점검 예정일, 점검 지연 여부와 유지보수 요약을 반환한다.

허용 역할: `owner`, `reader`

선택 query parameter:

- `scope=due`: 오늘 점검 기한이 도래했거나 지난 서비스만 반환한다. 기본값이다.
- `scope=overdue`: 점검 기한이 지난 서비스만 반환한다.
- `scope=upcoming`: 아직 기한이 도래하지 않은 활성 서비스를 반환한다.
- `scope=all`: 모든 활성 서비스의 유지보수 상태를 반환한다.

JSON 응답 예시:

```json
{
  "schema_version": "1.0",
  "content_type": "service_maintenance",
  "generated_at": "2026-08-25T07:00:00+09:00",
  "vault_commit": "0123456789abcdef",
  "generator_version": "0.1.0",
  "stale": false,
  "partial_failure": false,
  "sha256": "...",
  "data": {
    "as_of_date": "2026-08-25",
    "scope": "due",
    "summary": {
      "active_services": 3,
      "due": 1,
      "overdue": 0,
      "upcoming": 2
    },
    "services": [
      {
        "service_id": "aps-daily-briefing",
        "name": "APS 일일 브리핑 및 대시보드",
        "service_status": "Active",
        "maintenance_cycle": "매주",
        "maintenance_interval_days": 7,
        "last_maintenance": "2026-08-22",
        "next_maintenance_due": "2026-08-29",
        "due_status": "upcoming",
        "days_overdue": 0,
        "maintenance_summary": "브리핑 실행과 프로젝트 연결 상태를 확인한다."
      }
    ]
  }
}
```

`due_status`는 `due`, `overdue`, `upcoming`, `unknown` 중 하나다. 날짜와 지연 일수는 service frontmatter를 기준으로 서버가 결정적으로 계산하며 Codex 판단에 맡기지 않는다.

HTML 응답은 고정된 서비스 유지보수 template에 같은 JSON 데이터를 삽입한다. 카드 디자인, 상태 색상, 정렬과 필터 동작은 template 버전으로 고정하며 Codex가 HTML을 생성하지 않는다.

필수 metadata가 없거나 날짜가 잘못된 서비스는 전체 생성을 실패시키지 않고 `due_status: "unknown"`과 구조화된 issue를 포함한다.

### 7.5 아이디어 목록 조회

```http
GET /v1/content/ideas?format=json
GET /v1/content/ideas?format=html
```

접수된 아이디어, 정리된 아이디어, 유사 아이디어 묶음, 중복 가능성과 프로젝트 전환 후보를 반환한다.

허용 역할: `owner`, `reader`

선택 query parameter:

- `status=received|organized|proposed|published|all`
- `cluster_id=<logical-id>`

원본 아이디어와 Codex가 생성한 정리 결과의 연결 관계를 유지한다.

### 7.6 아이디어 추가

```http
POST /v1/ideas
Authorization: Bearer <owner-device-token>
Content-Type: application/json
```

허용 역할: `owner`

요청 예시:

```json
{
  "content": "프로젝트 문서를 음성으로 브리핑하는 기능",
  "tags": ["briefing", "voice"]
}
```

아이디어 추가 요청에서는 Codex를 실행하지 않는다. 입력을 검증하고 수정하지 않은 원문, 접수 시각과 요청 token 식별자를 staging 저장소에 보존한다.

응답 예시:

```json
{
  "idea_id": "idea_01K...",
  "status": "received",
  "received_at": "2026-08-25T14:00:00+09:00"
}
```

Vault proposal 및 승인 흐름이 구현되기 전까지 `received`는 Vault에 게시되었다는 의미가 아니다.

### 7.7 프로젝트 게시 요청

```http
POST /v1/project-requests
Authorization: Bearer <owner-device-token>
Content-Type: application/json
```

허용 역할: `owner`

요청 예시:

```json
{
  "title": "음성 프로젝트 브리핑",
  "objective": "APS 프로젝트 브리핑을 음성으로 제공한다.",
  "source_idea_ids": ["idea_01K..."],
  "constraints": [
    "기존 일일 브리핑 결과를 재사용한다"
  ]
}
```

첫 요청에서는 Codex를 실행하거나 Vault를 변경하지 않는다. 서버가 입력을 정규화하고 예상 작업을 확인 응답으로 반환한다.

```json
{
  "request_id": "project_request_01K...",
  "status": "confirmation_required",
  "confirmation": {
    "summary": "새 프로젝트 문서와 ProjectContext 초안을 생성합니다.",
    "planned_changes": [
      "프로젝트 문서 초안 생성",
      "ProjectContext brief와 초기 Task 생성",
      "간단한 마일스톤과 일정 제안"
    ],
    "expires_at": "2026-08-25T14:30:00+09:00"
  }
}
```

### 7.8 프로젝트 게시 요청 확인

```http
POST /v1/project-requests/{request_id}/confirm
Authorization: Bearer <owner-device-token>
```

허용 역할: `owner`

확인 요청은 해당 프로젝트 제안의 Codex 생성 작업을 승인한다. 확인한 token은 원 요청 token과 같은 소유자 인스턴스에 속해야 한다. 만료되었거나 이미 처리된 확인은 `409`로 거부한다.

성공 시 비동기 `project.propose` Job을 생성하고 `202 Accepted`를 반환한다.

```json
{
  "job_id": "job_01K...",
  "status": "queued",
  "operation": "project.propose",
  "status_url": "/v1/jobs/job_01K..."
}
```

Job은 격리된 작업 디렉터리에서 Codex를 실행하고 프로젝트 문서, brief, 초기 Task와 일정 초안을 생성한다. 생성 결과는 schema와 파일 정책을 검증한 후 proposal branch에만 commit한다.

한 번의 사전 확인만 사용하는 M1에서는 기본 브랜치에 자동 병합하거나 push하지 않는다. 기본 브랜치 반영은 사용자가 Git에서 수행한다. 향후 서버가 병합까지 수행하려면 생성된 diff를 보여주고 별도의 명시적 최종 승인을 받는 계약을 먼저 추가한다.

### 7.9 콘텐츠 생성 상태

```http
GET /v1/content/status
```

허용 역할: `owner`, `reader`

최신 생성 commit, 생성 시각, 오래됨 여부, 콘텐츠별 준비 상태와 부분 실패를 반환한다.

```json
{
  "vault_commit": "0123456789abcdef",
  "generated_at": "2026-08-25T07:00:42+09:00",
  "generator_version": "0.1.0",
  "stale": false,
  "content": {
    "daily_briefing": {
      "status": "ready",
      "formats": ["json", "html"]
    },
    "projects": {
      "status": "ready",
      "succeeded": 4,
      "failed": 1
    },
    "ideas": {
      "status": "ready"
    },
    "service_maintenance": {
      "status": "ready",
      "due": 1,
      "overdue": 0,
      "formats": ["json", "html"]
    }
  }
}
```

## 8. 내부 Job operation

cron, systemd timer와 owner의 수동 갱신은 직접 Codex나 Vault script를 실행하지 않고 공통 Job API를 사용한다.

| Operation | 실행 주체 | 목적 | Vault 쓰기 |
|---|---|---|---|
| `briefing.refresh` | `scheduler`, `owner` | 일일·프로젝트별 브리핑과 프로젝트 목록 갱신 | 없음 |
| `services.refresh` | `scheduler`, `owner` | 활성 서비스 유지보수 상태와 조회 콘텐츠 갱신 | 없음 |
| `ideas.organize` | `scheduler`, `owner` | 새 아이디어 분류, 유사 항목 묶음과 병합 제안 생성 | staging 결과만 |
| `projects.refresh` | `scheduler`, `owner` | 게시된 프로젝트의 캐시와 목록 갱신 | 없음 |
| `project.propose` | 확인한 `owner` 요청 | 격리된 프로젝트 문서 초안과 proposal branch 생성 | proposal branch만 |
| `vault.audit` | `scheduler`, `owner` | Vault metadata와 ProjectContext 연결 점검 | 없음 |

`scheduler`는 `project.propose`를 생성할 수 없다. `reader`는 어떤 Job도 생성하거나 취소할 수 없다.

Job 생성 endpoint는 기존 비동기 계약을 사용한다.

```http
POST /v1/jobs
Authorization: Bearer <token>
Idempotency-Key: <8-128 characters>
Content-Type: application/json
```

모든 operation은 operation별 고정 schema로 입력을 검증한다. shell 명령, 실행 파일 경로, Codex CLI 인자와 Vault 내부 경로는 API 입력으로 받지 않는다.

## 9. 아이디어 정리와 중복 처리

`ideas.organize`는 원본 아이디어를 삭제하거나 직접 덮어쓰지 않는다. Codex는 다음과 같은 구조화 결과만 제안한다.

```json
{
  "cluster_id": "cluster_01K...",
  "canonical_idea": "음성 기반 프로젝트 브리핑",
  "member_idea_ids": ["idea_A", "idea_B", "idea_C"],
  "categories": ["briefing", "accessibility"],
  "merge_status": "suggested"
}
```

- 원본 아이디어 ID와 원문은 보존한다.
- 동일 아이디어 여부는 Codex 결과만으로 확정하지 않는다.
- 주기적 정리는 staging의 논리적 묶음과 병합 제안까지만 수행한다.
- Vault 반영이 필요하면 proposal branch와 명시적 승인 흐름을 사용한다.

## 10. 갱신과 결과 보존

- 서버 pipeline이 Vault 동기화를 소유한다.
- Vault 동기화는 clean worktree에서 fast-forward 가능한 경우에만 수행한다.
- Job은 실행에 사용한 Vault commit을 고정해 기록한다.
- 한 Job이 콘텐츠를 읽는 동안 다른 동기화가 입력을 변경하지 않도록 전체 실행 잠금 또는 commit별 snapshot을 사용한다.
- 프로젝트별 생성 실패는 다른 프로젝트와 서비스 결과 생성을 막지 않는다.
- JSON schema, 날짜, 필수 필드, HTML marker와 파일 크기를 검증한다.
- 모든 검증을 통과한 결과만 최신 결과로 원자적으로 교체한다.
- 실패하면 직전 정상 결과를 유지하고 `stale: true`와 실패 원인을 기록한다.
- Job, staging 입력, Artifact와 결과의 보존 기간 및 정리 정책을 설정으로 관리한다.

## 11. 오류 형식

모든 JSON 오류는 동일한 envelope를 사용한다.

```json
{
  "error": {
    "code": "CONTENT_NOT_GENERATED",
    "message": "아직 생성된 콘텐츠가 없습니다.",
    "request_id": "req_01K...",
    "details": []
  }
}
```

주요 오류 code:

| HTTP | Code | 의미 |
|---:|---|---|
| `400` | `INVALID_INPUT` | 요청 schema 또는 값이 잘못됨 |
| `400` | `INVALID_FORMAT` | 지원하지 않는 응답 형식 |
| `401` | `AUTHENTICATION_REQUIRED` | 인증정보 없음 또는 잘못된 token |
| `403` | `OPERATION_FORBIDDEN` | token 역할에 허용되지 않은 요청 |
| `404` | `CONTENT_NOT_GENERATED` | 생성된 정상 콘텐츠 없음 |
| `404` | `PROJECT_NOT_FOUND` | 알 수 없는 논리적 프로젝트 ID |
| `404` | `REQUEST_NOT_FOUND` | 알 수 없는 아이디어·프로젝트 요청 ID |
| `409` | `CONFIRMATION_EXPIRED` | 확인 요청 만료 |
| `409` | `INVALID_STATE` | 현재 상태에서 수행할 수 없는 요청 |
| `429` | `RATE_LIMITED` | token별 호출 한도 초과 |
| `503` | `CONTENT_REFRESHING` | 첫 정상 결과를 생성 중임 |

## 12. M1 제외 범위

- 자유 질문형 `agent.query`
- 요청자가 지정하는 Vault 경로
- 임의 Codex prompt, 모델, CLI 인자와 shell 명령
- API 요청마다 실행되는 Codex
- 다중 사용자 tenant와 사용자별 데이터 ACL
- 요청 IP 또는 Origin 기반 사용자 인증
- Vault 기본 브랜치 자동 commit·push·merge
- Git 충돌 자동 병합, reset과 강제 checkout
- 확인되지 않은 프로젝트 문서 게시
- AI가 생성한 HTML 또는 JavaScript의 직접 실행
- 외부 queue와 다중 웹 프로세스

## 13. M1 완료 기준

- 단일 사용자 인스턴스에 여러 기기 token을 등록하고 개별 폐기할 수 있다.
- 프록시 없이도 APS Server가 모든 요청을 직접 인증한다.
- `reader`, `owner`, `scheduler` 권한 테스트가 통과한다.
- 콘텐츠 GET 요청에서 Codex가 실행되지 않는다.
- 일일 브리핑, 프로젝트 목록·브리핑, 서비스 유지보수와 아이디어 목록을 JSON·HTML로 조회한다.
- 아이디어 추가가 원문을 보존하고 Codex 없이 staging에 접수된다.
- cron Job이 새 아이디어를 구조화하고 원본을 삭제하지 않은 채 유사 항목을 묶는다.
- 프로젝트 게시 요청은 확인 전 Codex나 Vault 변경을 수행하지 않는다.
- 확인된 요청만 `project.propose` Job을 생성하고 proposal branch 밖에 쓰지 않는다.
- Vault commit이 같고 generator version이 같으면 불필요한 Codex 재실행을 생략한다.
- 일부 프로젝트 실패 시 나머지 결과와 직전 정상 결과를 유지한다.
- token, 질문 원문, Vault 절대경로와 문서 원문이 일반 로그에 기록되지 않는다.

## 14. Nginx 웹 연결

HTML endpoint는 완전한 HTML 문서를 반환하므로 Nginx가 그대로 reverse proxy할 수 있다. APS Server 자체 bearer 인증은 프록시 사용 여부와 관계없이 항상 유지한다.

일반 API client가 bearer token을 직접 보내는 경우 Nginx는 인증 header를 그대로 전달한다.

```nginx
location /v1/content/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

일반 브라우저에서 직접 웹페이지처럼 사용할 경우 브라우저는 bearer token을 자동으로 넣지 않는다. 이 경우 Nginx가 Basic Auth, VPN 인증 또는 별도 인증 gateway로 사용자를 먼저 확인한 뒤 해당 인스턴스의 `reader` token을 upstream 요청에 넣는다.

```nginx
location = / {
    return 302 /v1/content/briefing/daily?format=html;
}

location /v1/content/ {
    auth_basic "APS";
    auth_basic_user_file /etc/nginx/secrets/aps.htpasswd;

    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Authorization "Bearer REPLACE_WITH_INSTANCE_READER_TOKEN";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

두 번째 형태에서 Nginx 설정의 reader token은 배포 시 실제 secret으로 치환하고 설정 파일 권한을 제한한다. Nginx 인증 없이 reader token만 자동 주입하면 해당 웹 주소를 아는 모든 요청자가 인증된 것으로 처리되므로 허용하지 않는다.

인터넷에 공개할 때는 TLS를 필수로 사용한다. 개인 VPN 내부라면 Nginx 없이 bearer token을 직접 전달할 수 있지만, 일반 브라우저 탐색을 위해 query parameter나 URL에 token을 넣지는 않는다.
