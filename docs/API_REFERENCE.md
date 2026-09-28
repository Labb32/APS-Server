# API 사용

기본 주소는 `http://127.0.0.1:8080`이며 모든 보호 API는 다음 header를 사용한다.

```http
Authorization: Bearer <token>
```

JSON이 기본 응답이다. 지원되는 조회 API는 `?format=html`로 HTML을 반환한다. 전체 schema는 [OpenAPI](../specs/aps-api.openapi.json)에 있다.

## 상태

| Method | Path | 설명 |
|---|---|---|
| GET | `/health/live` | process 상태 |
| GET | `/health/ready` | 인증과 기본 설정 상태 |
| GET | `/v1/operations` | 실행 가능한 operation |
| GET | `/v1/extensions` | 설치된 공식 extension |
| GET | `/v1/scheduler` | schedule과 queue 상태 |

## Idea

| Method | Path | 설명 |
|---|---|---|
| POST | `/v1/ideas/text` | UTF-8 원문 접수 |
| POST | `/v1/ideas` | JSON Idea 접수 |
| GET | `/v1/ideas` | Idea 목록 |
| GET | `/v1/ideas/{idea_id}` | Idea 상세 |
| PATCH | `/v1/ideas/{idea_id}` | pending Idea metadata 수정 |
| POST | `/v1/ideas/search` | Idea 검색 |
| GET | `/v1/ideas/{idea_id}/similar` | 유사 Idea |
| GET | `/v1/idea-sets` | Idea Set 목록 |
| GET | `/v1/idea-sets/{idea_set_id}` | Idea Set 상세 |
| POST | `/v1/search` | 전체 문서 검색 |

JSON 접수 예:

```json
{
  "title": "Vault 변경 알림",
  "keywords": ["vault", "notification"],
  "summary": "Vault 변경을 확인하는 Idea"
}
```

접수된 원문은 서버가 만든 ID로 Git 제외 경로 `00_Inbox`에 저장된다. 요청에서 Vault 경로를 지정할 수 없다. `Idempotency-Key`를 보내면 같은 요청의 중복 생성을 막을 수 있다.

## Vault 문서

| Method | Path | 설명 |
|---|---|---|
| GET | `/v1/content/vault` | Project·Service 전체 |
| GET | `/v1/projects` | Project 목록 |
| GET | `/v1/projects/{project_id}` | Project 상세 |
| GET | `/v1/services` | Service 목록 |
| GET | `/v1/services/{service_id}` | Service 상세 |
| GET | `/v1/content/status` | 게시된 결과 상태 |

조회 API는 저장된 결과만 읽는다. 최신 Vault 내용을 반영하려면 `vault.content.refresh` Job을 실행한다.

Briefing 확장을 설치하고 AI를 활성화하면 다음 결과를 사용할 수 있다.

| Method | Path | 설명 |
|---|---|---|
| GET | `/v1/content/briefing/daily` | 일일 briefing |
| GET | `/v1/content/projects/{project_id}/briefing` | Project briefing |
| GET | `/v1/content/services/maintenance` | Service 유지보수 현황 |

기본 응답은 JSON이며 `?format=html`로 HTML을 요청할 수 있다.

## Job

| Method | Path | 설명 |
|---|---|---|
| POST | `/v1/jobs` | Job 생성 |
| GET | `/v1/jobs/{job_id}` | 상태와 결과 |
| POST | `/v1/jobs/{job_id}/cancel` | 대기 중인 Job 취소 |
| GET | `/v1/jobs/{job_id}/artifacts/{artifact_id}` | 결과 파일 다운로드 |

```json
{
  "operation": "vault.content.refresh",
  "input": {},
  "context": {}
}
```

Core operation은 `vault.content.refresh`, `vault.audit`, `ideas.index.refresh`, `ideas.curate`다. `ideas.curate`는 AI가 설정된 경우에만 활성화된다.

## 오류

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

문의할 때 응답의 `X-Request-ID` 또는 `request_id`를 사용한다.
