# APS Server API Reference

문서 버전 `0.2.1` · 기준일 `2026-09-27`

이 문서는 현재 FastAPI 애플리케이션이 제공하는 실제 client 계약이다. 전체 machine-readable schema는 [aps-api.openapi.json](../specs/aps-api.openapi.json), 제품의 목표 범위는 [PROJECT_PLAN](PROJECT_PLAN.md), 구성 요소 경계는 [ARCHITECTURE](ARCHITECTURE.md)를 참고한다.

## 1. 공통 규칙

### Base URL과 media type

```text
http://<aps-server-host>:8080
```

- 업무 API prefix: `/v1`
- JSON 요청과 응답: `application/json; charset=utf-8`
- HTML viewer: `text/html; charset=utf-8`
- 날짜: ISO 8601 `YYYY-MM-DD`
- 일시: timezone이 포함된 ISO 8601 문자열
- 알 수 없는 JSON 필드: 허용하지 않음

### 인증과 역할

`/health/live`를 제외한 업무 API는 다음 헤더가 필요하다.

```http
Authorization: Bearer <device-token>
```

| Role | 권한 |
|---|---|
| `operator` | Content 조회, 허용된 모든 Job 생성, queued Job 취소 |
| `viewer` | Content 조회, briefing·service Job 생성 |
| `scheduler` | 예약 실행용 Job 생성. 일반 Content 조회 불가 |

APS Server는 IP, Origin 또는 proxy header를 사용자 인증 근거로 사용하지 않는다.

### 공통 헤더

| Header | 방향 | 필수 | 설명 |
|---|---|---:|---|
| `Authorization` | 요청 | 대부분 필수 | Bearer token |
| `Content-Type` | 요청 | body 사용 시 | JSON은 `application/json`, text Inbox는 `text/plain` |
| `Idempotency-Key` | Job·Idea 접수 요청 | 선택 | Job은 8~128자, Idea는 영숫자·`._~-` 8~128자 |
| `X-Request-ID` | 응답 | 항상 | 서버가 생성한 요청 추적 ID |
| `ETag` | HTML Content 응답 | HTML만 | canonical data checksum |

## 2. 공통 오류 형식

동기 HTTP 오류는 모두 다음 envelope를 사용한다.

```json
{
  "error": {
    "code": "REQUEST_VALIDATION_FAILED",
    "message": "요청이 API 계약을 통과하지 못했습니다.",
    "request_id": "req_0123456789ABCDEF0123456789",
    "details": [
      {
        "location": "body.briefing.project.context.project_ids",
        "message": "List should have at least 1 item after validation, not 0",
        "type": "too_short"
      }
    ]
  }
}
```

설정된 역할별 Bearer token은 각각 32자 이상이고 서로 달라야 한다. 본문의 `request_id`는 `X-Request-ID` 헤더와 같다. 검증 오류는 위치, 설명과 유형만 반환하며 요청 원문이나 token은 포함하지 않는다.

### HTTP 오류 코드

| HTTP | Code | 의미 |
|---:|---|---|
| `400` | `INVALID_FORMAT` | `format`이 `json`, `html`이 아님 |
| `401` | `AUTHENTICATION_REQUIRED` | Bearer token 없음 또는 불일치 |
| `403` | `OPERATION_FORBIDDEN` | role 권한 부족 |
| `403` | `ARTIFACT_PATH_INVALID` | Artifact 격리 경로 위반 |
| `404` | `ROUTE_NOT_FOUND` | 등록되지 않은 API 경로 |
| `404` | `CONTENT_NOT_GENERATED` | 정상 materialized 결과가 아직 없음 |
| `404` | `IDEA_NOT_FOUND` | Idea ID가 최신 결과에 없음 |
| `404` | `IDEA_SET_NOT_FOUND` | Idea Set ID 또는 추천 결과 없음 |
| `404` | `PROJECT_NOT_FOUND`, `SERVICE_NOT_FOUND` | 조회 ID가 게시된 catalog에 없음 |
| `404` | `JOB_NOT_FOUND` | Job ID 없음 |
| `404` | `ARTIFACT_NOT_FOUND` | Artifact ID 없음 |
| `409` | `JOB_NOT_CANCELLABLE` | queued가 아닌 Job 취소 요청 |
| `409` | `IDEMPOTENCY_KEY_REUSED` | 같은 key를 다른 payload에 재사용 |
| `409` | `IDEA_TRACKED_UPDATE_DISABLED` | tracked Idea 직접 수정 금지 |
| `410` | `ARTIFACT_EXPIRED` | Artifact가 만료 또는 제거됨 |
| `413` | `IDEA_CONTENT_TOO_LARGE` | text Inbox 요청이 40,000바이트 초과 |
| `415` | `UNSUPPORTED_MEDIA_TYPE` | text Inbox 요청의 media type 오류 |
| `422` | `REQUEST_VALIDATION_FAILED` | body, path 또는 query schema 오류 |
| `422` | `IDEA_TEXT_INVALID` | text Inbox 본문 인코딩·길이·문자 오류 |
| `500` | `CONTENT_INVALID` | 저장 JSON의 schema/checksum 오류 |
| `500` | `SEARCH_INDEX_INVALID` | 최초 검색 색인을 source에서 만들 수 없음 |
| `500` | `INTERNAL_ERROR` | 분류되지 않은 서버 오류 |
| `503` | `DEPENDENCY_NOT_READY` | Core Vault 또는 인증 설정 미준비 |
| `503` | `AI_DISABLED` | AI provider가 `none`인 작업 요청 |
| `503` | `PROVIDER_NOT_CONFIGURED` | 선택한 AI provider 설정이 부족한 작업 요청 |
| `503` | `JOB_QUEUE_UNAVAILABLE` | 내장 queue가 가득 찼거나 종료 중 |
| `503` | `OPERATION_NOT_AVAILABLE` | 필요한 공식 확장이 설치되지 않음 |

## 3. Health와 operation

### `GET /health/live`

인증 없이 process 생존 여부만 확인한다.

성공 `200`:

```json
{"status":"live"}
```

### `GET /health/ready`

Core의 token과 Vault 준비 상태를 확인한다. AI provider나 선택 확장의 부재·장애는 Core readiness를 실패로 바꾸지 않는다. 설치된 확장 manifest 자체가 잘못되면 보안상 서버 기동이 실패할 수 있다.

성공 `200`: `{"status":"ready"}`

실패: `401 AUTHENTICATION_REQUIRED`, `503 DEPENDENCY_NOT_READY`. `503`의 `details[0].configured`는 `false`다.

### `GET /v1/operations`

호출 role에 허용된 operation만 반환한다. AI 작업은 provider가 없거나 설정이 부족할 때도 목록에 남고 `enabled:false`, `disabled_reason:AI_DISABLED` 또는 `PROVIDER_NOT_CONFIGURED`를 표시한다.

성공 `200`:

```json
{
  "operations": [
    {"name":"vault.content.refresh","write_mode":"none","enabled":true}
  ]
}
```

비활성 AI 작업의 예: `{"name":"ideas.curate","write_mode":"commit","enabled":false,"disabled_reason":"AI_DISABLED"}`.

실패: `401 AUTHENTICATION_REQUIRED`.

### `GET /v1/extensions`

현재 서버 프로세스에서 활성화된 공식 확장을 반환한다. 기본 Core-only 상태에서는 빈 배열이다.

```json
{"extensions":[]}
```

`briefing` 설치 후 서버를 재시작한 경우:

```json
{
  "extensions":[
    {
      "extension_id":"briefing",
      "version":"0.1.0",
      "installed":true,
      "active":true,
      "operations":["briefing.daily","briefing.project","service.maintenance_due"],
      "schedules":["briefing.daily-refresh","briefing.service-maintenance"],
      "restart_required":false
    }
  ]
}
```

### `GET /v1/scheduler`

내장 Scheduler와 Job queue 상태, 등록 schedule 및 마지막 실행 정보를 반환한다. `operator`와 `scheduler`만 호출할 수 있다.

성공 `200`:

```json
{
  "enabled": true,
  "running": true,
  "last_tick_at": "2026-09-01T00:00:00Z",
  "queue": {"queued_and_running": 1, "capacity": 100, "workers": 2},
  "schedules": [
    {
      "schedule_id": "vault-content",
      "source": "core",
      "cron": "0 */6 * * *",
      "timezone": "Asia/Seoul",
      "enabled": true,
      "disabled_reason": null,
      "request": {"operation":"vault.content.refresh","input":{},"context":{}},
      "runtime": {
        "last_checked_at": "2026-09-01T00:00:00Z",
        "last_scheduled_for": "2026-08-31T21:00:00Z",
        "last_job_id": "job_0123456789ABCDEF0123456789",
        "last_error": null
      }
    }
  ]
}
```

Core Schedule은 `APS_SCHEDULES_PATH`(Compose 기본 `/config/schedules.json`, 독립 실행 기본 `${APS_DATA_PATH}/schedules.json`)에서, 확장 Schedule은 설치된 manifest에서 읽는다. `APS_SCHEDULE_OVERRIDES_PATH`는 같은 ID의 `cron`, `timezone`, `enabled`만 재정의한다. 새 기본 일정은 `vault-content`·`idea-curate`·`vault-audit`다. 이전 설정의 `idea-index`는 유지된다. AI 의존 작업이 비활성이면 override가 켜져 있어도 해당 schedule의 `enabled`는 `false`, `disabled_reason`은 `AI_DISABLED` 또는 `PROVIDER_NOT_CONFIGURED`다. 가용한 작업은 `disabled_reason:null`이다. 설정 변경은 재시작 후 적용된다.

실패: `401 AUTHENTICATION_REQUIRED`, `403 OPERATION_FORBIDDEN`.

## 4. Job API

### 상태 전이

```text
queued → syncing → running → validating → publishing → succeeded
```

실패 시 어느 단계에서든 `failed`가 된다. `queued`만 `cancelled`로 변경할 수 있다. 요청이 `202`로 접수된 뒤의 실행 실패는 HTTP 오류가 아니라 Job의 `status/error`로 조회한다.

### 고정 요청 envelope

```json
{
  "operation": "<registered-operation>",
  "input": {},
  "context": {}
}
```

`operation`이 discriminator다. 선택된 operation의 schema에 없는 `input/context` 필드는 `422 REQUEST_VALIDATION_FAILED`다.

#### `briefing.daily`

```json
{"operation":"briefing.daily","input":{},"context":{}}
```

- Role: `scheduler`, `operator`, `viewer`
- 게시: daily briefing, Project catalog, Service maintenance, Project별 briefing
- HTML 생성 옵션은 없다. HTML은 저장 JSON 조회 시 렌더링한다.
- 공식 `briefing` 확장이 활성화되지 않았으면 `503 OPERATION_NOT_AVAILABLE`이다.

#### `briefing.project`

```json
{
  "operation":"briefing.project",
  "input":{},
  "context":{"project_ids":["aps-server"]}
}
```

- Role: `operator`, `viewer`
- `project_ids`: 정확히 1개
- Project ID pattern: `^[a-z0-9][a-z0-9-]{0,63}$`
- Vault 경로나 문서 이름은 받을 수 없다.

#### `vault.audit`

```json
{"operation":"vault.audit","input":{},"context":{}}
```

- Role: `scheduler`, `operator`
- 활성 Project와 briefing 연결 상태를 반환하는 비게시 진단 Job

#### `service.maintenance_due`

```json
{
  "operation":"service.maintenance_due",
  "input":{"date":"2026-09-01"},
  "context":{}
}
```

- Role: `scheduler`, `operator`, `viewer`
- `input.date`: 선택, ISO date. 생략하면 서버 실행일 기준

#### `ideas.index.refresh`

```json
{"operation":"ideas.index.refresh","input":{},"context":{}}
```

- Role: `scheduler`, `operator`
- 고정 `01_Ideas`, `01_Idea_Sets`를 검증해 canonical `ideas.json` 게시
- path, model, executable, keyword와 임의 옵션은 허용하지 않음

#### `vault.content.refresh`

```json
{"operation":"vault.content.refresh","input":{},"context":{}}
```

- Role: `scheduler`, `operator`; AI·공식 확장 없이 실행 가능
- Project·Service 원문 catalog와 Idea·Idea Set catalog를 같은 Vault revision으로 검증·게시
- 결과의 `content_url`은 `/v1/content/vault`, `published_content`에는 `/v1/content/ideas`도 포함
- 잘못된 문서가 있으면 Job은 `VAULT_DOCUMENT_INVALID`로 실패하고 이전 정상 게시 결과를 보존

### `POST /v1/jobs`

선택 헤더:

```http
Idempotency-Key: device-01-20260901-ideas-refresh
```

성공 `202`:

```json
{
  "job_id":"job_0123456789ABCDEF0123456789",
  "status":"queued",
  "operation":"ideas.index.refresh",
  "created_at":"2026-09-01T09:00:00+09:00",
  "status_url":"/v1/jobs/job_0123456789ABCDEF0123456789"
}
```

동일 role, key, payload이면 기존 Job 정보를 다시 `202`로 반환한다. 동일 key와 다른 payload는 `409 IDEMPOTENCY_KEY_REUSED`다.

| 실패 HTTP | Code |
|---:|---|
| `401` | `AUTHENTICATION_REQUIRED` |
| `403` | `OPERATION_FORBIDDEN` |
| `409` | `IDEMPOTENCY_KEY_REUSED` |
| `422` | `REQUEST_VALIDATION_FAILED` |
| `503` | `AI_DISABLED`, `PROVIDER_NOT_CONFIGURED`, `OPERATION_NOT_AVAILABLE` |

### `GET /v1/jobs/{job_id}`

모든 인증 role이 최신 Job을 조회할 수 있다.

성공 `200`:

```json
{
  "job_id":"job_0123456789ABCDEF0123456789",
  "status":"succeeded",
  "operation":"ideas.index.refresh",
  "created_at":"2026-09-01T09:00:00+09:00",
  "started_at":"2026-09-01T09:00:01+09:00",
  "finished_at":"2026-09-01T09:00:03+09:00",
  "vault_commit":"0123456789abcdef0123456789abcdef01234567",
  "result":{
    "content_type":"ideas",
    "published":true,
    "generated_at":"2026-09-01T00:00:03+00:00",
    "sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "content_url":"/v1/content/ideas",
    "published_content":[
      {"content_type":"ideas","sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","content_url":"/v1/content/ideas"}
    ]
  },
  "artifacts":[],
  "error":null
}
```

실행 실패도 조회 자체는 `200`이다.

```json
{
  "status":"failed",
  "error":{
    "code":"IDEA_CATALOG_INVALID",
    "message":"Example.md: title is required",
    "request_id":"req_0123456789ABCDEF0123456789",
    "details":[]
  }
}
```

#### 비동기 Job failure code

| Code | 의미 |
|---|---|
| `VAULT_DIRTY` | commit되지 않은 Vault 변경으로 sync 거부 |
| `VAULT_NOT_FAST_FORWARD` | upstream으로 fast-forward 불가 |
| `VAULT_NOT_REPOSITORY` | Vault가 Git 저장소가 아님 |
| `VAULT_PUSH_FAILED` | local commit은 생성됐지만 tracking upstream fast-forward push 실패 |
| `VAULT_SYNC_FAILED` | 기타 Git 처리 실패 |
| `EXTENSION_NOT_READY` | 공식 확장 필수 파일 누락 |
| `PROVIDER_EXECUTION_FAILED` | provider 실행 실패 또는 timeout |
| `PROVIDER_OUTPUT_INVALID` | provider 출력 JSON 오류 |
| `IDEA_CATALOG_INVALID` | Idea frontmatter, ID 또는 Set 참조 오류 |
| `VAULT_DOCUMENT_INVALID` | Project·Service·Idea·Set 문서 검증 오류 |
| `OUTPUT_SCHEMA_INVALID` | 생성 결과가 canonical schema를 통과하지 못함 |
| `OPERATION_FAILED` | 등록 operation 처리 실패 |
| `INTERNAL_JOB_ERROR` | 분류되지 않은 worker 오류 |
| `JOB_INTERRUPTED` | 서버 종료로 진행 중 Job을 완료하지 못함 |

HTTP 실패: `401 AUTHENTICATION_REQUIRED`, `404 JOB_NOT_FOUND`.

### `POST /v1/jobs/{job_id}/cancel`

`operator`만 queued Job을 취소한다. 성공은 변경된 Job과 `202`다.

실패: `401 AUTHENTICATION_REQUIRED`, `403 OPERATION_FORBIDDEN`, `404 JOB_NOT_FOUND`, `409 JOB_NOT_CANCELLABLE`.

### `GET /v1/jobs/{job_id}/artifacts/{artifact_id}`

Job에 등록되고 `/data/artifacts/{job_id}` 아래로 검증된 파일만 반환한다.
현재 일반 Job Artifact 조회 경로만 활성이다. Vault archive 생성·다운로드는 `migration` 확장 계획에 속하며 아직 제공하지 않는다.

실패: `401 AUTHENTICATION_REQUIRED`, `404 JOB_NOT_FOUND`, `404 ARTIFACT_NOT_FOUND`, `403 ARTIFACT_PATH_INVALID`, `410 ARTIFACT_EXPIRED`.

## 5. Materialized Content API

Content GET은 Codex나 provider를 실행하지 않는다. Idea 조회는 마지막 정상 JSON에 Git-ignored Inbox의 pending 항목을 겹쳐 표시한다.

### 공통 envelope

```json
{
  "schema_version":"1.0",
  "content_type":"ideas",
  "generated_at":"2026-09-01T00:00:03+00:00",
  "vault_commit":"0123456789abcdef0123456789abcdef01234567",
  "generator_version":"0.2.1",
  "stale":false,
  "partial_failure":false,
  "sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "data":{}
}
```

`sha256`는 `data`를 key 정렬·공백 제거 canonical JSON으로 직렬화해 계산한다. 필터가 적용되면 필터 결과 기준으로 다시 계산한다.

| Method | Path | Query |
|---|---|---|
| `GET` | `/v1/content/briefing/daily` | `format` |
| `GET` | `/v1/content/projects` | `format` |
| `GET` | `/v1/content/projects/{project_id}/briefing` | `format` |
| `GET` | `/v1/content/services/maintenance` | `format`, `scope` |
| `GET` | `/v1/content/vault` | `format`; Project·Service materialized 원문 catalog |
| `GET` | `/v1/content/ideas` | `format`, `status`, `idea_set_id` |
| `GET` | `/v1/content/status` | 없음, JSON 전용 |

- `format`: `json` 또는 `html`, 기본 `json`
- `scope`: `due`, `overdue`, `upcoming`, `all`, 기본 `due`
- HTML은 JSON viewer이며 별도 원본으로 저장하지 않음
- HTML 보안 헤더: private cache, CSP, ETag, `Vary: Authorization`, `nosniff`

공통 실패: `400 INVALID_FORMAT`, `401 AUTHENTICATION_REQUIRED`, `403 OPERATION_FORBIDDEN`, `404 CONTENT_NOT_GENERATED`, `422 REQUEST_VALIDATION_FAILED`, `500 CONTENT_INVALID`.

### Core 문서 조회

| 종류 | 목록 | 상세 | JSON data |
|---|---|---|---|
| Project | `GET /v1/projects` | `GET /v1/projects/{project_id}` | 목록 `documents[]` 요약, 상세 `document`와 Markdown `content` |
| Service | `GET /v1/services` | `GET /v1/services/{service_id}` | 같은 구조 |
| Idea | `GET /v1/ideas` | `GET /v1/ideas/{idea_id}` | 기존 Idea envelope와 Markdown `content` |
| Idea Set | `GET /v1/idea-sets` | `GET /v1/idea-sets/{idea_set_id}` | 전체 목록과 상세 `idea_set` |

목록의 `status`는 선택적 정확 일치 필터이며 기본은 전체 상태다. `format=html`은 같은 결과를 고정 template으로 표시하고 Markdown/HTML을 escape한다. Project·Service는 첫 `vault.content.refresh` 전 `404 CONTENT_NOT_GENERATED`, Idea·Set은 빈 catalog와 Inbox pending 항목을 `200`으로 제공한다. Project는 안정된 `project_id`(기존 `briefing_id`도 허용), Service는 `service_id`가 필요하다. 중복·잘못된 ID와 frontmatter는 refresh Job을 실패시킨다. 기존 `/v1/content/projects`와 `/v1/content/services/maintenance`는 briefing·유지보수 결과이므로 일반 원문 조회로 대체하지 않는다.

## 6. Idea Resource API

Idea API는 게시된 `ideas.json`에 Git-ignored `00_Inbox`의 pending 항목을 겹쳐 표시한다. 첫 index 게시 전에는 빈 catalog를 사용하므로 Inbox 접수와 조회가 가능하다. 이때 `vault_commit: "0000000"`은 실제 Git revision이 아닌 미게시 표시다. tracked Idea·Set은 `ideas.index.refresh` 또는 `vault.content.refresh`가 게시된 뒤 나타난다. 검색 응답은 `search_mode: lexical`, `index_provider: aps-server`다.

### `GET /v1/ideas`

`IdeasResponse` envelope를 JSON으로 반환한다.

| Query | 값 | 기본값 |
|---|---|---|
| `status` | `inbox`, `incubator`, `organized`, `proposed`, `published`, `archived`, `all` | `all` |
| `idea_set_id` | `^idea_set_[A-Z0-9]+$` | 없음 |

결과가 없으면 빈 배열과 `200`. 실패는 공통 Content 오류와 같다.

### `GET /v1/ideas/{idea_id}`

성공 `200`:

```json
{
  "vault_commit":"0123456789abcdef0123456789abcdef01234567",
  "generated_at":"2026-09-01T00:00:03+00:00",
  "idea":{
    "idea_id":"idea_3EED9B9A451E",
    "title":"Example",
    "keywords":["example"],
    "summary":"Example Idea",
    "status":"incubator",
    "idea_set_ids":[],
    "updated_at":"2026-08-31T00:00:00+00:00"
  }
}
```

실패: `404 IDEA_NOT_FOUND`, 공통 인증·검증·Content 오류.

### `POST /v1/ideas/search`

요청:

```json
{"query":"markdown agent rules","limit":5}
```

| Field | 제약 |
|---|---|
| `query` | trim 후 1~200자 |
| `limit` | 1~50, 기본 10 |

성공 `200`:

```json
{
  "query":"markdown agent rules",
  "search_mode":"lexical",
  "index_provider":"aps-server",
  "vault_commit":"0123456789abcdef0123456789abcdef01234567",
  "results":[
    {
      "idea_id":"idea_3EED9B9A451E",
      "title":"AI 에이전트 규칙을 관리하는 로컬 퍼스트 마크다운 워크스페이스",
      "score":0.83,
      "matched_by":["title","keyword","summary"]
    }
  ]
}
```

일치 항목이 없으면 `results: []`와 `200`이다. 점수는 title 55%, keyword 30%, summary 15%를 기본 가중치로 사용하고 제목 substring을 가산한다.

실패: 공통 Content 오류, `422 REQUEST_VALIDATION_FAILED`.

### `GET /v1/ideas/{idea_id}/similar`

`limit`은 1~50, 기본 5다. 자기 자신을 제외하고 제목 문자열 유사도, keyword Jaccard와 summary token Jaccard를 결합한다.

실패: `404 IDEA_NOT_FOUND`와 공통 Idea 오류.

### `POST /v1/search`

Inbox·Idea·Idea Set·Project·Service의 제목·키워드·요약을 검색한다. `operator`와 `viewer`가 호출할 수 있고 AI provider나 `aps-index`를 사용하지 않는다.

```json
{
  "query":"검색 색인",
  "collections":["idea","project"],
  "statuses":["organized","In_Progress"],
  "offset":0,
  "limit":20
}
```

`query`는 trim 후 1~200자다. 빈 collection·status 배열은 전체를 뜻하며 collection은 `inbox`, `idea`, `idea_set`, `project`, `service`만 허용한다. status는 정확 일치, `offset`은 0~10,000, `limit`은 1~100이다.

성공 `200`은 `search_mode`, `embedding_model`, `index_revision`, `indexed_at`, `stale`, `total`, `next_offset`과 결과를 반환한다. 결과는 collection·논리 ID·제목·상태·요약·0~1 점수 및 `title`, `keyword`, `summary`, `embedding` 일치 근거를 포함한다. 정상 모드는 `hybrid`와 `aps-hash-subword-v1-256`이며 임베딩 실패 시 `lexical_fallback`과 `embedding_model:null`이다. source 오류 중에는 이전 정상 색인을 `stale:true`로 제공하고, 최초 구축 실패는 `500 SEARCH_INDEX_INVALID`다. 상세 수명주기와 품질 범위는 [Core 검색](SEARCH.md)을 따른다.

### `GET /v1/idea-sets/recommended`

`suggested`를 `approved`보다 먼저 선택하고 같은 상태에서는 구성원 수가 많은 Set, ID 순으로 결정한다.

성공 `200`은 `vault_commit`, `generated_at`, `idea_set`을 반환한다. 추천 Set이 없으면 `404 IDEA_SET_NOT_FOUND`다.

## 7. 운영 및 호환성

- API 요청자는 Vault path, branch, remote, executable 또는 Codex argument를 지정할 수 없다.
- Content 조회와 lexical 검색은 AI를 호출하지 않는다.
- 기본 `sync_before_job=true`에서 Vault가 dirty하면 Job은 `VAULT_DIRTY`다.
- Vault sync는 fetch와 fast-forward-only merge만 사용한다.
- in-process queue를 사용하는 동안 web process는 하나만 실행한다.
- Scheduler는 외부 queue를 사용하지 않으며 schedule 회차별 idempotency key를 내부 생성한다.
- 시작 시 queued Job은 다시 queue에 넣고 진행 중이던 Job은 `JOB_INTERRUPTED`로 종료한다.
- 필드 제거, 의미 변경 또는 enum 축소 시 API/schema version을 올린다.
- 업그레이드 전 저장된 Job의 알려진 `input.format`, `include_services`, 빈 `project_ids`는 조회 시 내부 정규화하지만 새 API 요청에서는 허용하지 않는다.
- Token, Markdown 원문, 로컬 절대경로, Git/AI credential은 기본 로그에서 제외한다.

## 8. Idea Write API

Idea 쓰기는 `operator`만 허용한다. 모든 파일명과 Vault 경로는 서버가 결정하며 client request에는 path, branch, remote, executable, prompt, model 또는 Codex argument가 없다.

### `POST /v1/ideas`

고정 `00_Inbox`에 새 Idea를 원자적으로 저장한다. JSON 요청은 기존 `/v1/ideas`를 사용한다.

```json
{
  "title": "Vault 변경 알림",
  "keywords": ["vault", "notification"],
  "summary": "Vault 변경을 여러 기기에 알려 주는 Idea"
}
```

정규형 입력은 `title` 1~200자와 `summary` 1~2000자를 함께 보내고 `keywords`를 최대 20개/각 1~80자로 보낸다. 또는 이 필드들 대신 `content` 1~10000자만 보낼 수 있다. `content`는 frontmatter나 자동 제목 없이 Inbox 파일에 저장한다. 구조화 입력은 제목·요약·키워드를 frontmatter 없는 읽기 쉬운 Markdown 본문으로 기록한다. 표시용 metadata와 멱등 정보는 `${APS_DATA_PATH}/ideas/intake.json`에 분리한다. raw content만 받은 경우 첫 번째 non-blank 줄을 임시 title로, 앞 2000자를 임시 summary로 사용한다. 알 수 없는 field와 requester ID는 거부한다.

성공 `201 Created`:

```json
{
  "idea": {
    "idea_id": "idea_0123456789ABCDEF0123",
    "title": "Vault 변경 알림",
    "keywords": ["vault", "notification"],
    "summary": "Vault 변경을 여러 기기에 알려 주는 Idea",
    "status": "inbox",
    "idea_set_ids": [],
    "updated_at": "2026-09-01T03:00:00Z",
    "storage": "inbox",
    "commit_status": "pending"
  },
  "source_idea_ids": [],
  "vault_commit": null
}
```

### `POST /v1/ideas/text`

`Content-Type: text/plain` 또는 `text/plain; charset=utf-8`로 UTF-8 본문을 보낸다. 최대 40,000바이트, NFC·LF 정규화와 trim 후 1~10,000자이며 제어 문자는 tab과 줄바꿈만 허용한다. 본문은 자유 형식 agent 지시나 Vault 경로로 해석하지 않고 `POST /v1/ideas`의 `content`와 동일한 고정 Inbox 접수로 처리한다. 성공 응답은 같은 `IdeaMutationResponse`, 상태는 `201`이다. 다른 media type은 `415 UNSUPPORTED_MEDIA_TYPE`, 잘못된 UTF-8·빈 내용·초과 길이는 `422 IDEA_TEXT_INVALID` 또는 `413 IDEA_CONTENT_TOO_LARGE`다.

두 POST 모두 선택적 `Idempotency-Key`(8~128자, 영숫자와 `._~-`)를 받는다. 같은 키와 동일한 정규화 요청을 다시 보내면 기존 Idea ID와 현재 상태를 반환한다. 같은 키에 다른 요청을 보내면 `409 IDEMPOTENCY_KEY_REUSED`다. 키와 요청의 hash는 서버 metadata에 저장하고 정리 commit 시 tracked Idea에 보존한다. 키가 없으면 각 요청을 새 접수로 처리한다.

### `PATCH /v1/ideas/{idea_id}`

`title`, `keywords`, `summary`, `status` 중 하나 이상만 전송한다. pending Idea 수정은 표시·검색 metadata에 반영하고 Inbox 원문은 변경하지 않는다. `status`는 `inbox`로 유지해야 한다. tracked Idea에 대한 기존 즉시 commit 동작은 중단했다. 같은 경로의 tracked 수정 요청은 `409 IDEA_TRACKED_UPDATE_DISABLED`를 반환하며 원본을 변경하지 않는다. 추후 proposal·승인 흐름이 마련되면 별도 계약으로 제공한다.

성공은 `200 OK`이고 pending 수정의 `vault_commit`은 `null`이다.

### `POST /v1/ideas/merge`

원본 2~20개를 보존하면서 통합 결과를 새 pending Idea로 접수한다. 현재 Core는 client가 제공한 정규형 title/keywords/summary를 저장하며 자동 AI 재작성은 수행하지 않는다.
AI `none` 모드에서도 접수할 수 있지만 자동 병합·tracked commit은 하지 않는다. `commit_status: pending`이 실제 상태다.

```json
{
  "source_idea_ids": ["idea_A", "idea_B"],
  "title": "통합 Idea",
  "keywords": ["merge"],
  "summary": "두 Idea를 보존하면서 만든 통합 후보"
}
```

성공은 `202 Accepted`이고 응답 `source_idea_ids`에 검증된 원본 ID가 포함된다. 원본 ID 중 하나라도 없으면 `404 IDEA_NOT_FOUND`다.

### `POST /v1/idea-sets`

```json
{
  "title": "Vault 자동화",
  "keywords": ["vault", "automation"],
  "summary": "Vault 자동화와 관련된 Idea 후보 묶음",
  "member_idea_ids": ["idea_A", "idea_B"]
}
```

구성원은 1~100개의 중복 없는 기존 또는 pending Idea ID여야 한다. 성공 `202 Accepted` 응답은 `idea_set.storage: inbox`, `commit_status: pending`, `status: suggested`를 반환한다.
AI `none` 모드에서도 후보를 Inbox에 접수할 수 있다. 추천 조회는 저장된 후보를 읽을 뿐 AI 생성 Job을 시작하지 않는다.

### `ideas.curate` Job

```json
{"operation":"ideas.curate","input":{},"context":{}}
```

`operator`와 내부 `scheduler`만 생성할 수 있다. Job은 서버 소유 Inbox 문서와 Core가 선택한 lexical 유사 후보를 고정 `ideas.curate-plan` workflow로 분석한다. AI 결과의 source ID, schema, 중복 후보와 대상 경로를 검증한 뒤 `01_Ideas`, `01_Idea_Sets`에 한 batch commit으로 게시한다. commit 성공 뒤에만 해당 Inbox 파일을 제거한다. `APS_VAULT_PUSH_AFTER_COMMIT=true`이면 현재 tracking upstream으로 fast-forward push하며 branch 전환, merge, reset과 force push는 하지 않는다. 처리할 문서가 없으면 현재 catalog를 다시 게시하고 새 commit은 만들지 않는다.

AI provider 또는 구조화 출력 검증이 실패하면 Job은 `PROVIDER_*`, `AGENT_OUTPUT_INVALID` 또는 `IDEA_CURATION_INVALID` 오류로 종료되고 Inbox와 직전 정상 Content를 유지한다.

기본 schedule은 `15 */6 * * *`이며 timezone은 서버 Scheduler 설정을 따른다.

### 쓰기 오류

| HTTP | Code | 조건 |
|---:|---|---|
| `401` | `AUTHENTICATION_REQUIRED` | token 누락 또는 불일치 |
| `403` | `OPERATION_FORBIDDEN` | viewer가 쓰기 요청 |
| `404` | `IDEA_NOT_FOUND` | 대상, 병합 원본 또는 Set 구성원 없음 |
| `409` | `IDEA_STATUS_INVALID` | pending Idea를 inbox 이외 상태로 수정 |
| `409` | `IDEA_INBOX_NOT_IGNORED` | Vault의 고정 `00_Inbox` ignore 정책 누락 |
| `409` | `VAULT_DIRTY` | tracked 수정 또는 curate 전에 추적 worktree 변경 존재 |
| `422` | `REQUEST_VALIDATION_FAILED` | field 누락, 범위·형식 위반 또는 알 수 없는 field |
| `500` | `IDEA_INBOX_INVALID` | 서버 소유 Inbox 문서가 schema 위반 |
| `500` | `IDEA_WRITE_FAILED` | 원자 저장 또는 제한된 Git commit 실패 |
