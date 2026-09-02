# APS Server API 계약

현재 구현의 endpoint별 요청·응답, 고정 Job schema와 오류 코드는 [API_REFERENCE.md](API_REFERENCE.md)를 기준으로 한다. 이 문서는 Content 구조, 확장과 향후 계획을 함께 설명한다.

## 1. 문서 목적

APS Server는 한 사용자의 APS Vault 하나를 연결해 여러 기기와 서비스에 브리핑, Idea, Project 및 Service 정보를 제공한다.

이 문서는 현재 호출 가능한 API와 목표 API를 함께 정의한다. 구성 요소 경계는 [ARCHITECTURE.md](ARCHITECTURE.md), 개발 범위는 [PROJECT_PLAN.md](PROJECT_PLAN.md)를 따른다.

기계 판독 가능한 현재 Content 계약:

- 실행 서버 전체 계약: `/openapi.json`
- 정적 Content OpenAPI: [content-api.openapi.json](../specs/content-api.openapi.json)
- 현재 JSON 예시: [content-api.examples.json](../specs/content-api.examples.json)

| 상태 | 의미 |
|---|---|
| `active` | 현재 코드에서 호출 가능 |
| `transition` | 호출 가능하지만 최신 구조로 교체해야 함 |
| `planned` | 계약 방향만 확정하고 아직 구현하지 않음 |
| `blocked` | proposal/approval 등 선행 안전 기능 전에는 활성화 금지 |

`planned`와 `blocked` endpoint는 구현 전까지 runtime OpenAPI에 노출하지 않는다.

## 2. 서비스 단위

- 서버 인스턴스 하나는 마스터 사용자 한 명과 Vault 하나만 담당한다.
- 사용자는 여러 기기에서 요청할 수 있으며 IP나 Origin을 고정하지 않는다.
- 프록시가 있더라도 APS Server가 bearer token을 직접 검증한다.
- 요청자가 Vault 경로, remote, branch, executable, shell 명령, AI provider, 모델 또는 Codex 인자를 지정할 수 없다.
- Vault remote 동기화는 clean worktree와 fast-forward-only 조건에서만 수행한다.
- 조회 endpoint는 저장된 materialized result만 읽으며 Vault sync, AI 또는 Job을 실행하지 않는다.

## 3. 인증과 역할

```http
Authorization: Bearer <token>
```

| 역할 | 용도 | 권한 방향 |
|---|---|---|
| `operator` | 사용자의 신뢰 기기 | Content 조회, 허용 Job 생성·조회·취소, Artifact, 향후 승인 |
| `viewer` | 읽기 전용 기기 | Content 조회와 명시적으로 허용된 read-only Job |
| `scheduler` | APS 내부 cron | 등록된 정기 Job 생성과 Scheduler 상태 조회 |

현재 구현은 역할별 정적 token을 환경변수로 받는다. 목표 구조에서는 같은 사용자에게 기기별 token을 발급하고 `token_id`, 역할, 발급·만료·폐기 상태를 관리한다.

현재 Job 조회는 인증된 token이 Job ID를 알면 역할과 생성자를 구분하지 않는다. 기기 token 구현 시 operator는 전체 Job, viewer와 scheduler는 자신이 생성한 허용 Job만 조회하도록 제한한다.

## 4. JSON과 HTML 규칙

### 4.1 요청

- MVP의 구조화 요청 본문은 `application/json`을 기준으로 한다.
- operation별 Pydantic model을 사용하고 선언되지 않은 field는 거부한다.
- 자연어 내용이 필요하면 JSON의 명시된 문자열 field에만 넣는다.
- 요청 본문을 shell, prompt 또는 Codex 인자로 직접 연결하지 않는다.

`POST /v1/jobs`는 `operation` discriminator에 따라 고정된 `input/context` schema를 검증한다. 상세 variant는 [API_REFERENCE.md](API_REFERENCE.md)에 정의한다.

### 4.2 응답

Content 조회의 기본 형식은 JSON이다.

```text
format=json   # 기본값
format=html
```

| 형식 | Media type | 의미 |
|---|---|---|
| JSON | `application/json` | canonical 결과 |
| HTML | `text/html; charset=utf-8` | 같은 JSON을 고정 template에 넣은 viewer |

- AI와 공식 확장은 JSON field만 생성한다.
- AI가 HTML, CSS, JavaScript 또는 template을 생성하지 않는다.
- HTML 요청은 AI, Vault sync 또는 생성 Job을 실행하지 않는다.
- HTML renderer는 원시 문서 내용을 escape하고 외부 script와 resource를 사용하지 않는다.
- JSON 생성 실패 시 직전 정상 결과를 유지한다.

### 4.3 Content envelope

```json
{
  "schema_version": "1.0",
  "content_type": "daily_briefing",
  "generated_at": "2026-08-31T07:00:00+09:00",
  "vault_commit": "0123456789abcdef",
  "generator_version": "0.1.0",
  "stale": false,
  "partial_failure": false,
  "sha256": "...",
  "data": {}
}
```

- `vault_commit`: 결과 생성에 사용한 정확한 Vault commit
- `sha256`: canonical `data`의 checksum
- `stale`: 현재 Vault가 결과 commit보다 새롭거나 갱신 실패로 이전 결과를 반환할 때 `true`
- `partial_failure`: 일부 항목만 실패하고 나머지 결과를 제공할 때 `true`

## 5. 현재 활성 API

### 5.1 Health와 capability

| Method | Endpoint | 역할 | 상태 | 설명 |
|---|---|---|---|---|
| `GET` | `/health/live` | 공개 | `active` | web process 생존 여부 |
| `GET` | `/health/ready` | 인증 | `active` | 설정, 선택된 AI provider와 공식 briefing 확장 준비 여부 |
| `GET` | `/v1/operations` | 인증 | `active` | 현재 token이 실행할 수 있는 operation |
| `GET` | `/v1/scheduler` | operator, scheduler | `active` | Scheduler, queue와 schedule 실행 상태 |
| `GET` | `/v1/extensions` | 인증 | `active` | 현재 프로세스에 활성화된 공식 확장 |
| `GET` | `/openapi.json` | 공개 | `active` | runtime OpenAPI |
| `GET` | `/docs` | 공개 | `active` | FastAPI 문서 UI |

readiness는 Vault, 인증 설정과 명시적으로 선택한 AI provider의 준비 상태를 항상 검사한다. `briefing`이 설치된 경우에는 package 필수 파일도 추가로 검사한다. 세부 설정은 [AI_PROVIDERS.md](AI_PROVIDERS.md)를 따른다.

### 5.2 Materialized Content

| Method | Endpoint | 역할 | 상태 | 설명 |
|---|---|---|---|---|
| `GET` | `/v1/content/briefing/daily` | operator, viewer | `active` | 저장된 일일 브리핑 |
| `GET` | `/v1/content/projects` | operator, viewer | `active` | 저장된 Project catalog |
| `GET` | `/v1/content/projects/{project_id}/briefing` | operator, viewer | `active` | 저장된 Project 브리핑 |
| `GET` | `/v1/content/services/maintenance` | operator, viewer | `active` | 저장된 Service 유지보수 결과 |
| `GET` | `/v1/content/ideas` | operator, viewer | `active` | `title/keywords/summary` 기반 Idea와 Idea set 결과 |
| `GET` | `/v1/content/status` | operator, viewer | `active` | Content별 준비 상태 |

지원하는 Content endpoint는 `format=json|html`을 받는다. `/v1/content/status`는 현재 JSON만 반환한다.

생성된 결과가 없으면 다음 오류를 반환한다.

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

Content 생성 Job은 출력 `data`를 Content model로 검증하고 서버 metadata와 canonical checksum을 붙인 뒤 ContentStore에 원자적으로 게시한다. 일일 브리핑 Job은 Project catalog, 개별 Project 브리핑과 Service 유지보수 결과도 함께 게시한다.

### 5.3 Job API

| Method | Endpoint | 역할 | 상태 | 설명 |
|---|---|---|---|---|
| `POST` | `/v1/jobs` | operation 정책 | `active` | 고정 operation schema 기반 비동기 Job 생성 |
| `GET` | `/v1/jobs/{job_id}` | 인증 | `active` | Job 상태와 결과 |
| `POST` | `/v1/jobs/{job_id}/cancel` | operator | `active` | queued Job 취소 |
| `GET` | `/v1/jobs/{job_id}/artifacts/{artifact_id}` | 인증 | `active` | 검증된 경로의 Artifact 다운로드 |

현재 operation:

| Operation | 역할 | 현재 입력 | 상태 |
|---|---|---|---|
| `briefing.daily` | scheduler, operator, viewer | 빈 input/context, 생성은 항상 JSON | `briefing` 설치 시 active |
| `briefing.project` | operator, viewer | 빈 input, `project_ids` 정확히 한 개 | `briefing` 설치 시 active |
| `vault.audit` | scheduler, operator | 없음 | `active` |
| `service.maintenance_due` | scheduler, operator, viewer | 선택 기준일 | `briefing` 설치 시 active |
| `ideas.index.refresh` | scheduler, operator | 입력 없음. Vault의 고정 `01_Ideas`, `01_Idea_Sets`만 읽음 | `active` |

`briefing.daily`, `briefing.project`와 `service.maintenance_due`는 공식 `briefing` package가 설치된 경우에만 등록된다. 진입점은 연결된 Vault를 읽기 전용으로 사용하고 JSON만 출력한다. Vault에 남아 있는 기존 script는 실행하지 않는다.

`ideas.index.refresh`는 외부 AI나 실행 파일을 호출하지 않는다. Core 수집기가 Vault의 고정 디렉터리만 읽고 frontmatter를 검증한 뒤 `ideas.json`을 게시한다. 중복 ID, 잘못된 필드 또는 존재하지 않는 Idea Set 참조가 있으면 게시를 중단하고 직전 정상 결과를 보존한다.

모든 생성 operation의 목표 흐름:

```text
queued
→ syncing
→ running
→ validating JSON schema and checksum
→ publishing materialized result
→ succeeded
```

`validating` 단계에서 operation별 Content schema와 checksum을 검증하고, `publishing` 단계에서 임시 파일을 마지막 정상 결과와 원자적으로 교체한다. 검증이나 실행이 실패하면 기존 정상 결과를 보존한다.

## 6. 목표 Core Content API

### 6.1 Idea

기본 Idea 표현:

```json
{
  "idea_id": "idea_01K...",
  "title": "Vault 백업 자동화",
  "keywords": ["vault", "backup", "automation"],
  "summary": "Vault 변경 사항을 정기적으로 안전하게 보존한다.",
  "status": "organized",
  "idea_set_ids": [],
  "updated_at": "2026-08-31T09:00:00+09:00"
}
```

Idea set 표현:

```json
{
  "idea_set_id": "idea_set_01K...",
  "title": "문서 보존 자동화",
  "keywords": ["vault", "backup", "automation"],
  "summary": "문서의 안전한 보존과 복구를 함께 검토하는 Idea 묶음이다.",
  "status": "suggested",
  "member_idea_ids": ["idea_01K..."]
}
```

| Method | Endpoint | 상태 | 설명 |
|---|---|---|---|
| `GET` | `/v1/ideas` | `active` | Idea 목록과 `status`, `idea_set_id` 필터 |
| `GET` | `/v1/ideas/{idea_id}` | `active` | Idea 상세 |
| `POST` | `/v1/ideas/search` | `active` | Core lexical 검색 |
| `GET` | `/v1/ideas/{idea_id}/similar` | `active` | 특정 Idea의 lexical 유사 후보 |
| `GET` | `/v1/idea-sets/recommended` | `active` | suggested 우선, 구성원 수 기준 추천 Idea set 하나 |
| `POST` | `/v1/ideas` | `active` | 고정 `00_Inbox`에 새 pending Idea 접수 |
| `PATCH` | `/v1/ideas/{idea_id}` | `active` | pending 수정 또는 tracked Idea 즉시 commit |
| `POST` | `/v1/ideas/merge` | `active` | 원본을 보존하는 통합 Idea를 pending으로 접수 |
| `POST` | `/v1/idea-sets` | `active` | 검증할 Idea Set 후보를 pending으로 접수 |

검색 요청:

```json
{
  "query": "문서 자동 백업",
  "limit": 3
}
```

검색 응답:

```json
{
  "query": "문서 자동 백업",
  "search_mode": "lexical",
  "index_provider": "aps-server",
  "vault_commit": "0123456789abcdef",
  "results": [
    {
      "idea_id": "idea_01K...",
      "title": "Vault 백업 자동화",
      "score": 0.82,
      "matched_by": ["title", "keyword", "summary"]
    }
  ]
}
```

- `aps-index`가 없으면 `search_mode: lexical`
- `aps-index`가 준비되면 `search_mode: hybrid`
- Vector 장애 시 lexical 결과로 강등하고 상태를 표시
- 검색과 그룹화는 후보만 생성하며 자동 병합하지 않음
- 추천 가능한 Set이 없으면 `404 IDEA_SET_NOT_FOUND`

검색 결과 없음은 JSON에서 빈 `results`와 `200 OK`를 기본으로 한다. HTML은 같은 빈 결과를 empty-state로 표시한다.

### 6.2 Project

| Method | Endpoint | 상태 | 설명 |
|---|---|---|---|
| `GET` | `/v1/projects` | `planned` | Project 목록과 상태 |
| `GET` | `/v1/projects/{project_id}` | `planned` | 특정 Project 상세, Task와 일정 |
| `POST` | `/v1/project-proposals` | `blocked` | 새 Project 제안 접수 |

목록이 비어 있으면 `200 OK`와 빈 배열을 반환한다. 알 수 없는 `project_id`는 `404 PROJECT_NOT_FOUND`다. 이름은 검색 조건으로만 사용하고 리소스 identifier로 사용하지 않는다.

Project 제안은 확인 응답 후 proposal Job을 생성한다. client는 prompt, model, branch와 Vault 경로를 지정할 수 없다.

### 6.3 Service

| Method | Endpoint | 상태 | 설명 |
|---|---|---|---|
| `GET` | `/v1/services` | `planned` | Service 목록과 상태 |
| `GET` | `/v1/services/{service_id}` | `planned` | 특정 Service 상세와 점검 상태 |
| `POST` | `/v1/services/{service_id}/maintenance-requests` | `blocked` | 유지보수 요청 생성 |

목록이 비어 있으면 `200 OK`와 빈 배열을 반환한다. 알 수 없는 `service_id`는 `404 SERVICE_NOT_FOUND`다. 문서 변경이 필요한 유지보수 결과는 proposal 흐름을 사용한다.

## 7. 내부 scheduler와 큐레이션

내부 Scheduler는 공개 Job 계약과 동일한 등록 operation 및 고정 입력 model만 사용한다. 외부 queue 서비스는 현재 범위에 포함하지 않는다.

목표 operation:

| Operation | Trigger | 결과 |
|---|---|---|
| `content.refresh.daily` | 일일 schedule | 일일 브리핑 JSON 게시 |
| `content.refresh.projects` | schedule 또는 Vault 변경 | Project catalog와 브리핑 게시 |
| `content.refresh.services` | schedule 또는 요청 | Service 상태 JSON 게시 |
| `ideas.index.refresh` | Vault 변경 또는 schedule | canonical Idea JSON과 lexical 검색 원본 갱신 |
| `ideas.curate` | `15 */6 * * *` 또는 operator 요청 | pending schema 검증, Idea/Set batch commit과 canonical JSON 갱신 |

`ideas.curate`는 Core의 제한된 쓰기 operation이다. 서버가 소유한 `00_Inbox/<server-generated-id>.md`만 입력으로 읽고, schema 검증을 통과한 결과만 `01_Ideas/<idea_id>.md`와 `01_Idea_Sets/<idea_set_id>.md`에 한 번의 batch commit으로 기록한다. commit 성공 뒤에만 처리한 Inbox 원본을 제거하며 push, branch 변경, merge는 수행하지 않는다.

### Idea 쓰기 요청

모든 쓰기 endpoint는 `operator` token만 허용한다. 요청자는 Vault path, 파일명, branch, Git remote, 실행 파일 또는 AI 인자를 지정할 수 없다.

`POST /v1/ideas` 요청:

```json
{"content":"Vault 변경을 여러 기기에 알려 주는 기능을 만들고 싶다."}
```

`content` 대신 정규형 `title`, `keywords`, `summary`를 보낼 수도 있다. raw content만 받은 경우 Core는 첫 줄과 본문 일부를 임시 title/summary로 사용하고 원문 전체를 Markdown 본문에 보존한다. 성공은 `201`이며 응답의 `idea.storage`는 `inbox`, `idea.commit_status`는 `pending`, `vault_commit`은 `null`이다. 같은 pending 자료는 즉시 목록·상세·검색과 HTML viewer에 포함된다.

`PATCH /v1/ideas/{idea_id}`는 `title`, `keywords`, `summary`, `status` 중 하나 이상을 받는다. pending Idea는 Inbox만 원자적으로 갱신하고 `200`/`vault_commit: null`을 반환한다. tracked Idea는 clean worktree와 fast-forward-only sync를 확인한 뒤 해당 파일만 commit하고 새 commit ID를 반환한다. pending 상태는 `inbox` 외 값으로 바꿀 수 없다.

`POST /v1/ideas/merge`는 중복 없는 `source_idea_ids` 2~20개와 통합 결과의 `title`, `keywords`, `summary`를 받는다. 서버는 원본을 삭제·수정하지 않고 새 통합 Idea를 pending으로 저장하며 `202`를 반환한다.

`POST /v1/idea-sets`는 `title`, `keywords`, `summary`, 중복 없는 `member_idea_ids` 1~100개를 받는다. 존재하지 않는 구성원은 `404 IDEA_NOT_FOUND`, 정상 접수는 `202`다.

공통 실패는 `401 AUTHENTICATION_REQUIRED`, `403 OPERATION_FORBIDDEN`, `404 IDEA_NOT_FOUND`, `409 VAULT_DIRTY`, `409 IDEA_STATUS_INVALID`, `409 IDEA_INBOX_NOT_IGNORED`, `422 REQUEST_VALIDATION_FAILED`, `500 IDEA_INBOX_INVALID` 또는 `500 IDEA_WRITE_FAILED`다.
| `extension.refresh` | 확장 manifest schedule | 공식 확장 JSON 게시 |

- cron은 Python script나 AI provider를 직접 실행하지 않고 bounded in-process queue에 Job을 등록한다.
- schedule ID와 예정 시각으로 idempotency key를 만들어 같은 회차의 중복 생성을 피한다.
- 서버 재시작 시 `queued` Job은 다시 등록하고 실행 중이던 Job은 `JOB_INTERRUPTED` 실패 상태로 전환한다.
- 기본 누락 실행 정책은 최근 24시간 안의 마지막 해당 회차를 한 번 실행하는 것이다.
- provider 실패 시 직전 정상 Content를 유지한다.

## 8. 공식 확장 계약

초기에는 APS가 배포하고 서명한 공식 확장만 허용한다. 커뮤니티 플러그인은 범위 밖이다.

확장 manifest 예시:

```json
{
  "id": "briefing",
  "version": "1.0.0",
  "type": "content-provider",
  "aps_api": "1",
  "capabilities": ["daily_briefing", "project_briefing"],
  "operations": ["briefing.daily", "briefing.project"],
  "schedules": [
    {
      "schedule_id": "briefing.daily-refresh",
      "cron": "0 6 * * *",
      "timezone": "Asia/Seoul",
      "enabled": true,
      "request": {"operation":"briefing.daily","input":{},"context":{}}
    }
  ],
  "network": "none"
}
```

확장 규칙:

- APS Server가 정규화한 읽기 전용 데이터만 입력으로 받는다.
- Vault와 Git에 직접 접근하거나 수정하지 않는다.
- canonical JSON schema를 통과한 결과만 반환한다.
- 인증, queue, scheduler와 AI provider 연결은 Core를 통해 사용한다.
- 임의 route, shell, executable과 설치 hook을 등록하지 않는다.
- HTML template은 JSON viewer 역할만 한다.

현재 설치 명령:

```text
aps extensions list
aps extensions install <official-id>
```

- 설치 대상은 image의 `APS_OFFICIAL_EXTENSIONS_PATH`에 포함된 공식 package로 제한한다.
- 설치는 `APS_EXTENSIONS_PATH`에 원자적으로 복사하고 활성화는 서버 재시작 시 수행한다.
- 재시작 시 manifest Operation과 Schedule을 함께 등록하며 hot loading하지 않는다.
- 공식 ID, version, APS 호환성, package-local entrypoint와 고정 Job model을 검증한다.
- checksum·서명 검증과 update·disable은 후속 범위다.
- API를 통한 설치와 임의 URL 설치는 제공하지 않는다.

읽기 전용 상태 API는 후속으로 추가할 수 있다.

| Method | Endpoint | 상태 | 설명 |
|---|---|---|---|
| `GET` | `/v1/extensions` | `active` | 현재 프로세스에서 활성화된 공식 확장과 상태 |
| `GET` | `/v1/extensions/{extension_id}` | `planned` | version, capability와 오류 |

## 9. `aps-index` 내부 계약

`aps-index`는 확장 package가 아닌 선택형 GPU 보조 서비스다. 공개 client가 직접 호출하지 않는다.

APS Server가 전달하는 인덱싱 입력:

```json
{
  "idea_id": "idea_01K...",
  "title": "Vault 백업 자동화",
  "keywords": ["vault", "backup"],
  "summary": "Vault 변경 사항을 정기적으로 보존한다.",
  "content_sha256": "...",
  "vault_commit": "0123456789abcdef"
}
```

운영 규칙:

- 내부 Docker network에서만 접근
- server 설정의 고정 endpoint와 인증 사용
- 외부 API 요청으로 endpoint나 credential 변경 금지
- model ID, version, vector dimension과 normalization 기록
- model version 변경 시 전체 rebuild
- 신규 인덱스 완성 후 원자적 교체
- 장애 시 lexical 검색 유지
- Vector 데이터는 Vault 외부 전용 volume에 저장

## 10. Vault 변경과 승인

Idea 접수는 Git-ignored `00_Inbox`를 사용하며 Project·Service 변경과 분리한다.

```text
POST /v1/ideas
→ 00_Inbox/<server-generated-idea-id>.md
→ ideas.curate Scheduler Job
→ 01_Ideas / 01_Idea_Sets 검증
→ 대상 파일 batch commit
```

이미 commit된 Idea 수정은 대상 문서만 검증해 즉시 commit한다. pending Idea 수정은 Inbox 원본만 갱신한다. Project와 Service의 추적 문서 변경 endpoint는 proposal branch, diff 검증과 명시적 승인 흐름이 완성되기 전까지 `blocked`다.

목표 흐름:

```text
request accepted into staging
→ Vault clean + fast-forward-only sync
→ isolated proposal branch
→ path/schema/diff validation
→ proposal commit
→ change summary와 diff 반환
→ explicit approve 또는 reject
→ 승인된 proposal branch 게시
→ 기본 branch 병합은 사용자/외부 절차
```

목표 API:

| Method | Endpoint | 상태 | 설명 |
|---|---|---|---|
| `GET` | `/v1/change-requests/{id}` | `blocked` | 상태와 변경 요약 |
| `GET` | `/v1/change-requests/{id}/diff` | `blocked` | 검증된 Markdown diff |
| `POST` | `/v1/change-requests/{id}/approve` | `blocked` | proposal 게시 승인 |
| `POST` | `/v1/change-requests/{id}/reject` | `blocked` | proposal 폐기 |

금지 사항:

- 기본 branch 자동 commit·push·merge
- 자동 충돌 해결
- reset, 강제 checkout과 force push
- 요청자가 지정한 path, branch, remote와 Git 명령
- 승인 전 원본 이동·삭제·덮어쓰기

## 11. HTML 웹 연결

Nginx 등 reverse proxy는 client의 bearer header를 전달할 수 있다.

```nginx
location /v1/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

브라우저용 웹서비스는 Nginx, VPN 또는 인증 gateway가 사용자를 먼저 확인해야 한다. upstream read token을 자동 주입한다면 proxy 자체 인증 없이 공개하지 않는다. token을 query string이나 HTML에 넣지 않는다.

## 12. 오류 계약

현재 JSON 오류 envelope:

```json
{
  "error": {
    "code": "REQUEST_VALIDATION_FAILED",
    "message": "요청이 API 계약을 통과하지 못했습니다.",
    "request_id": "req_01K...",
    "details": []
  }
}
```

| HTTP | 대표 code | 의미 |
|---:|---|---|
| `400` | `INVALID_FORMAT` | 응답 형식 오류 |
| `401` | `AUTHENTICATION_REQUIRED` | token 없음·잘못됨 |
| `403` | `OPERATION_FORBIDDEN` | 역할 권한 부족 |
| `404` | `CONTENT_NOT_GENERATED`, `*_NOT_FOUND` | 결과 또는 리소스 없음 |
| `409` | `JOB_NOT_CANCELLABLE`, `IDEMPOTENCY_KEY_REUSED` | 상태 또는 중복 key 충돌 |
| `410` | `ARTIFACT_EXPIRED` | Artifact 만료 |
| `422` | `REQUEST_VALIDATION_FAILED` | 요청 schema 검증 실패 |
| `500` | `CONTENT_INVALID`, `INTERNAL_ERROR` | 저장 Content 또는 내부 오류 |
| `503` | `DEPENDENCY_NOT_READY`, `JOB_QUEUE_UNAVAILABLE`, `OPERATION_NOT_AVAILABLE` | 의존성·확장 미준비 또는 내장 queue 포화·중단 |

Content, Job과 FastAPI 요청 검증 오류는 모두 이 envelope를 사용한다. 비동기 실행 실패는 Job 조회 응답의 `status: failed`와 `error`에 기록한다.

## 13. 감사와 민감정보

기록 대상:

- request ID, token ID, 역할, endpoint와 operation
- Job ID, 상태, 소요 시간과 Vault commit
- generator, 공식 확장 또는 provider ID와 version
- 결과 checksum과 필터링된 입력 요약

기본 로그 제외 대상:

- bearer token과 인증 파일 원문
- 자연어 요청과 Markdown 원문
- 로컬 절대경로와 Git credential
- AI credential과 전체 prompt

## 14. 구현 우선순위

1. 공식 확장 checksum·서명 검증과 update·disable CLI
2. proposal/approval 쓰기 흐름
3. 선택형 `aps-index`와 hybrid 검색
