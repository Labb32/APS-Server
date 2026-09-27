# API 사용 안내

문서 버전 `0.2.1`. 전체 request·response schema는 [OpenAPI](../specs/aps-api.openapi.json)를 기준으로 한다.

## 공통 규칙

- 기본 주소: `http://127.0.0.1:8080`
- 인증: `Authorization: Bearer <token>`
- `viewer`는 조회, `operator`는 조회·Idea 쓰기·운영 Job, `scheduler`는 일정 Job을 사용한다.
- JSON 요청은 `application/json`, 원문 Idea는 `text/plain; charset=utf-8`을 사용한다.
- HTML을 지원하는 조회 API는 `?format=html`을 받는다. 기본값은 JSON이다.
- 응답의 `X-Request-ID`를 오류 추적에 사용한다.

오류는 다음 형식이다.

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "설명",
    "request_id": "req_...",
    "details": []
  }
}
```

주요 상태 코드는 `401` 인증 실패, `403` 권한 부족, `404` 자료 없음, `409` 상태 충돌, `422` 입력 오류, `500` 저장 자료 오류, `503` 의존성 준비 실패다.

## 상태와 운영

| Method | Path | 설명 |
|---|---|---|
| GET | `/health/live` | 인증 없이 프로세스 상태 확인 |
| GET | `/health/ready` | 인증·Vault 설정 준비 확인 |
| GET | `/v1/operations` | 현재 token이 실행할 수 있는 고정 operation 조회 |
| GET | `/v1/extensions` | 설치된 공식 확장 조회 |
| GET | `/v1/scheduler` | 적용된 schedule과 활성 상태 조회 |

AI가 `none`이면 Core API는 계속 동작하고 AI가 필요한 operation은 `enabled: false`로 표시된다.

## Job

| Method | Path | 설명 |
|---|---|---|
| POST | `/v1/jobs` | Job 생성 |
| GET | `/v1/jobs/{job_id}` | 상태와 결과 조회 |
| POST | `/v1/jobs/{job_id}/cancel` | 아직 시작하지 않은 Job 취소 |
| GET | `/v1/jobs/{job_id}/artifacts/{artifact_id}` | 허용된 결과 파일 다운로드 |

Job 생성 형식:

```json
{
  "operation": "vault.content.refresh",
  "input": {},
  "context": {}
}
```

Core operation은 `vault.content.refresh`, `vault.audit`, `ideas.index.refresh`다. `ideas.curate`는 AI가 설정된 경우에만 실행된다. Job 상태는 `queued`, `syncing`, `running`, `validating`, `publishing`, `succeeded`, `failed`, `cancelled` 중 하나다.

같은 요청의 중복 생성을 막으려면 8~128자의 `Idempotency-Key`를 보낸다. 같은 키를 다른 요청에 사용하면 `409`가 반환된다.

## Vault 문서

| Method | Path | HTML | 설명 |
|---|---|:---:|---|
| GET | `/v1/content/vault` | ✓ | Project·Service 전체 문서 |
| GET | `/v1/projects` | ✓ | Project 목록 |
| GET | `/v1/projects/{project_id}` | ✓ | Project 상세 |
| GET | `/v1/services` | ✓ | Service 목록 |
| GET | `/v1/services/{service_id}` | ✓ | Service 상세 |
| GET | `/v1/content/status` |  | materialized 결과 상태 |

Project·Service는 `vault.content.refresh`가 한 번 성공한 뒤 조회할 수 있다. 조회 요청은 동기화나 Job을 자동 실행하지 않는다.

설치된 확장이 제공하는 결과는 `/v1/content/briefing/daily`, `/v1/content/projects`, `/v1/content/projects/{project_id}/briefing`, `/v1/content/services/maintenance`에서 조회한다.

## Idea 조회와 검색

| Method | Path | 설명 |
|---|---|---|
| GET | `/v1/ideas` | Idea 목록; `status`, `idea_set_id`, `format` 지원 |
| GET | `/v1/ideas/{idea_id}` | Idea 상세; `format` 지원 |
| POST | `/v1/ideas/search` | Idea lexical 검색 |
| GET | `/v1/ideas/{idea_id}/similar` | 유사 Idea 조회 |
| GET | `/v1/idea-sets` | Idea Set 목록 |
| GET | `/v1/idea-sets/recommended` | 추천 Set 하나 조회 |
| GET | `/v1/idea-sets/{idea_set_id}` | Idea Set 상세 |
| POST | `/v1/search` | Inbox·Idea·Set·Project·Service 통합 검색 |

통합 검색 예시:

```json
{
  "query": "검색어",
  "collections": ["inbox", "idea", "project"],
  "statuses": [],
  "offset": 0,
  "limit": 20
}
```

로컬 색인은 `${APS_DATA_PATH}/search/index.json`에 원자적으로 저장한다. 변경 문서만 다시 계산하며, source 오류 때 이전 정상 색인이 있으면 `stale: true`로 반환한다.

## Idea 쓰기

Idea 쓰기는 `operator`만 사용할 수 있고 경로는 항상 서버가 결정한다.

### 접수

`POST /v1/ideas`는 `content` 하나 또는 `title`과 `summary`, 선택 `keywords`를 받는다.

```json
{
  "title": "Vault 변경 알림",
  "keywords": ["vault", "notification"],
  "summary": "Vault 변경을 확인하는 Idea"
}
```

`POST /v1/ideas/text`는 UTF-8 원문을 받는다. 최대 40,000바이트이며 정규화 후 1~10,000자여야 한다. 두 API 모두 Git에서 제외된 `00_Inbox/<server-id>.md`에 frontmatter 없이 저장한다. 표시·검색·멱등 metadata는 `${APS_DATA_PATH}/ideas/intake.json`에 둔다.

선택 `Idempotency-Key`를 다시 보내면 동일 요청은 기존 Idea를 반환하고 다른 요청은 `409 IDEMPOTENCY_KEY_REUSED`로 거부한다.

### 수정과 수동 구성

| Method | Path | 설명 |
|---|---|---|
| PATCH | `/v1/ideas/{idea_id}` | pending Idea의 표시 metadata 수정; 원문은 유지 |
| POST | `/v1/ideas/merge` | 2~20개 원본을 보존한 통합 pending Idea 생성 |
| POST | `/v1/idea-sets` | 기존 Idea ID로 pending Set 생성 |

pending 상태는 `inbox`만 허용한다. 추적된 Idea의 직접 PATCH는 `409 IDEA_TRACKED_UPDATE_DISABLED`다. 추적 파일 쓰기는 검증된 Scheduler commit 흐름으로 제한한다.

## 안전 경계

- 요청자는 Vault 경로, branch, remote, executable, shell 명령, provider나 prompt를 지정할 수 없다.
- Vault sync는 clean worktree에서 fast-forward만 수행한다.
- in-process queue를 사용하는 동안 web process는 하나만 실행한다.
- token, 원문, 로컬 절대경로와 credential은 기본 로그에 남기지 않는다.
