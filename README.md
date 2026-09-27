# APS Server

APS Server는 한 사용자와 APS Vault를 연결하는 self-hosted API다. 인증된 문서 조회, Idea 접수와 검색, 고정 Job을 제공하며 AI 없이 사용할 수 있다.

## 빠른 시작

Docker Engine과 Compose가 필요하다.

```bash
cp .env.example .env
```

`.env`에 서로 다른 32자 이상의 token을 설정한다.

```dotenv
APS_OPERATOR_TOKEN=replace-with-long-random-token
APS_VIEWER_TOKEN=replace-with-another-long-random-token
APS_SCHEDULER_TOKEN=replace-with-third-long-random-token
APS_AI_PROVIDER=none
```

```bash
docker compose build
docker compose up -d
docker compose ps
```

기본 주소는 `http://127.0.0.1:8080`이다. Compose의 `.env` 값은 shell 변수로 자동 등록되지 않으므로 curl을 사용하려면 token을 별도로 export한다.

```bash
export APS_OPERATOR_TOKEN='...'
export APS_VIEWER_TOKEN='...'

curl http://127.0.0.1:8080/health/live
curl http://127.0.0.1:8080/health/ready \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
```

## 기본 사용

Idea를 원문으로 접수한다.

```bash
curl -X POST http://127.0.0.1:8080/v1/ideas/text \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-binary '새 Idea 설명'
```

JSON 접수도 가능하다.

```bash
curl -X POST http://127.0.0.1:8080/v1/ideas \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Vault 알림","keywords":["vault"],"summary":"Vault 변경을 확인하는 Idea"}'
```

Idea를 조회하거나 전체 문서를 검색한다.

```bash
curl http://127.0.0.1:8080/v1/ideas \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN"

curl -X POST http://127.0.0.1:8080/v1/search \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"검색어","collections":["idea","project"],"limit":10}'
```

Project와 Service는 먼저 Vault 내용을 갱신한 뒤 조회한다.

```bash
curl -X POST http://127.0.0.1:8080/v1/jobs \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation":"vault.content.refresh","input":{},"context":{}}'

curl http://127.0.0.1:8080/v1/projects \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN"
```

`POST /v1/jobs`가 반환한 `job_id`는 `GET /v1/jobs/{job_id}`로 확인한다. 사용 가능한 작업은 `GET /v1/operations`에서 조회한다.

## 권한과 저장 위치

- `viewer`: 문서와 Job 결과 조회
- `operator`: 조회, Idea 접수·수정, 허용된 Job 실행
- `scheduler`: 등록된 일정 Job 실행

Idea 접수는 Git에서 제외된 고정 `00_Inbox`에만 저장한다. API 요청으로 Vault 경로, shell 명령, 실행 파일이나 AI prompt를 지정할 수 없다. Vault 동기화는 clean worktree의 fast-forward만 허용한다.

## 문서

- [API 사용](docs/API_REFERENCE.md)
- [Docker와 Vault 연결](docs/CONTAINER_DEPLOYMENT.md)
- [구조와 데이터 경계](docs/ARCHITECTURE.md)
- [Idea 문서 형식](docs/IDEA_DOCUMENT_FORMAT.md)
- [선택형 AI 설정](docs/AI_EXECUTION.md)
- [보안 정책](SECURITY.md)
- [OpenAPI](specs/aps-api.openapi.json)

코드는 [Apache License 2.0](LICENSE)으로 제공된다.
