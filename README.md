# APS Server

APS Vault를 API로 조회하고 Idea를 접수하는 self-hosted 서버다. 기본 기능은 AI 없이 동작한다.

## 시작

Docker Engine과 Compose가 필요하다.

```bash
cp .env.example .env
```

`.env`에 서로 다른 32자 이상의 token을 입력한다.

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

기본 주소는 `http://127.0.0.1:8080`이다.

## 사용 예

Idea 원문 접수:

```bash
curl -X POST http://127.0.0.1:8080/v1/ideas/text \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-binary '새 Idea 내용'
```

Idea 조회:

```bash
curl http://127.0.0.1:8080/v1/ideas \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN"
```

Vault 문서 갱신:

```bash
curl -X POST http://127.0.0.1:8080/v1/jobs \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation":"vault.content.refresh","input":{},"context":{}}'
```

Project·Service 조회는 `vault.content.refresh`가 성공한 뒤 사용할 수 있다. HTML을 지원하는 조회 API에는 `?format=html`을 붙인다.

## 확장 설치

기본 container는 Core API만 활성화한다. 공식 확장은 이미지에 포함되지만 설치 전에는 operation, schedule과 전용 API를 사용할 수 없다.

```bash
docker compose exec aps-server aps extensions install briefing
docker compose exec aps-server aps extensions install migration
docker compose restart aps-server
```

`APS_INITIAL_EXTENSIONS=briefing,migration`을 설정하면 container 최초 시작 시 설치할 수도 있다.

## 권한

- `viewer`: 문서와 결과 조회
- `operator`: 조회, Idea 접수와 허용된 Job 실행
- `scheduler`: 등록된 schedule 실행

## 문서

- [설치와 운영](docs/CONTAINER_DEPLOYMENT.md)
- [API 사용](docs/API_REFERENCE.md)
- [Idea 문서](docs/IDEA_DOCUMENT_FORMAT.md)
- [선택형 AI](docs/AI_EXECUTION.md)
- [Migration 확장](extensions/migration/README.md)
- [보안](SECURITY.md)
- [OpenAPI](specs/aps-api.openapi.json)

[Apache License 2.0](LICENSE)
