# APS Server

APS Server는 한 사용자와 한 APS Vault를 연결하는 self-hosted API다. Vault 문서를 원본으로 사용하고, 인증된 조회·Inbox 접수·고정 Job을 제공한다. AI는 선택 사항이다. 현재 버전은 `0.2.1` Core beta이며 AI 사서와 공식 확장은 후속 범위다.

## 빠른 시작

Docker Engine과 Compose를 준비하고 설정 파일을 만든다.

```bash
cp .env.example .env
```

`.env`에 서로 다른 긴 `APS_OPERATOR_TOKEN`, `APS_VIEWER_TOKEN`, `APS_SCHEDULER_TOKEN`을 넣는다. 기본 `APS_VAULT_MODE=local`, `APS_AI_PROVIDER=none`으로 Core를 시작할 수 있다. AI 생성 작업을 사용하려면 [AI 실행·provider 설정](docs/AI_EXECUTION.md)을 참고한다.

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

기본 주소는 `127.0.0.1:8080`이다.

아래 curl 예시는 token을 현재 shell의 `APS_OPERATOR_TOKEN`, `APS_VIEWER_TOKEN` 변수에도 넣은 상태를 가정한다. Compose가 읽는 `.env` 값은 host shell 변수로 자동 export되지 않는다.

```bash
curl http://127.0.0.1:8080/health/live
curl http://127.0.0.1:8080/health/ready \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"
```

`live`는 프로세스 생존, `ready`는 인증된 준비 상태를 확인한다. 원격 Git Vault와 기존 Vault mount, volume·reverse proxy 설정은 [배포 안내](docs/CONTAINER_DEPLOYMENT.md)를 따른다. 실사용 Vault 연결 전에는 별도 임시 Vault에서 권한과 동기화 경계를 확인한다.

## 기본 API

보호된 요청은 `Authorization: Bearer <token>`을 사용한다. `viewer`는 조회와 허용된 읽기 작업, `operator`는 운영·Idea 접수·허용 Job, `scheduler`는 등록된 일정 작업을 담당한다.

```bash
curl http://127.0.0.1:8080/v1/ideas \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN"

curl -X POST http://127.0.0.1:8080/v1/ideas \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Vault 알림","keywords":["vault"],"summary":"Vault 변경을 확인하는 Idea"}'

curl -X POST http://127.0.0.1:8080/v1/ideas/text \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: text/plain; charset=utf-8" \
  --data-binary '새 Idea 설명'

curl -X POST http://127.0.0.1:8080/v1/jobs \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation":"vault.content.refresh","input":{},"context":{}}'

# 위 Job이 succeeded가 된 뒤 조회
curl http://127.0.0.1:8080/v1/projects \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN"

curl http://127.0.0.1:8080/v1/operations \
  -H "Authorization: Bearer $APS_OPERATOR_TOKEN"

curl -X POST http://127.0.0.1:8080/v1/search \
  -H "Authorization: Bearer $APS_VIEWER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"검색 색인","collections":["idea","project"],"limit":10}'
```

Idea 접수는 서버가 관리하는 Git-ignored `00_Inbox`에만 기록한다. 요청자가 Vault 경로·shell·AI prompt를 지정할 수 없다. Project·Service 조회는 첫 `vault.content.refresh` 완료 전 `CONTENT_NOT_GENERATED`를 반환한다. Idea 조회는 첫 게시 전에도 빈 catalog와 Inbox pending 항목을 제공한다. Content GET은 AI나 동기화 Job을 시작하지 않는다. 현재의 endpoint·schema·오류는 [API Reference](docs/API_REFERENCE.md)와 [OpenAPI](specs/aps-api.openapi.json)에 있다.

## Job과 확장

Job은 `/v1/operations`에 보이는 고정 operation과 입력 schema만 받는다. `POST /v1/jobs`가 반환한 `job_id`로 `/v1/jobs/{job_id}`를 조회한다. 내장 queue를 사용하는 동안 web process는 하나만 운영한다.

공식 `briefing` package는 선택 설치한다. 설치 후 재시작해야 operation과 schedule이 활성화된다.

```bash
docker compose exec aps-server aps extensions list
docker compose exec aps-server aps extensions install briefing
docker compose restart aps-server
```

계획 중인 `migration`, `service-security` 및 별도 `aps-index` 서비스는 현재 설치 가능한 기능으로 간주하지 않는다. [공식 확장 계획](docs/EXTENSION_PLAN.md)과 [플러그인 상세](plugins/README.md)에 목표와 선행 조건이 있다.

## 문서

- [베타 목표](docs/PROJECT_PLAN.md) · [구현 현황과 다음 작업](docs/TASKS.md) · [개발 노트](docs/DEVELOPMENT_NOTES.md)
- [현재 API](docs/API_REFERENCE.md) · [아키텍처](docs/ARCHITECTURE.md) · [AI 실행·provider 설정](docs/AI_EXECUTION.md)
- [Core 검색](docs/SEARCH.md)
- [배포](docs/CONTAINER_DEPLOYMENT.md) · [공개 전 확인](docs/PRE_RELEASE_QA.md) · [보안 정책](SECURITY.md)

Vault sync는 clean worktree의 fast-forward만 허용한다. 자동 merge·reset·강제 checkout·force push는 하지 않는다. Project·Service 원본 변경은 proposal branch와 명시적 승인 기능 전까지 허용하지 않는다.

코드는 [Apache License 2.0](LICENSE)으로 제공된다. 변경·배포 시 [NOTICE](NOTICE)의 출처 고지를 보존한다.
